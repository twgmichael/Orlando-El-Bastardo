#!/usr/bin/env python3
"""
register_studio_chat_asset.py — promote a Studio Chat–built asset into the
main production pipeline's asset registry (oeb.config.json).

Section 14 of docs/planning/REVIEW-AUDIT.md ("Realignment — closing the
canonical-ID/registry dependency now"), plan item 1: given a Studio Chat
Canonical Asset, write/update its entry in oeb.config.json's `assets` map
so export_blender.py/export_usd.py/export_godot.py can place it in a
production SceneSpec by canonical_id, exactly like an artist-made asset.

Studio Chat's canonical_id slugs (e.g. prop_round_dining_table_rounded_A)
are already the same shape as the registry's existing keys -- this is a
registration step, not a naming-scheme translation. Kind mapping (finalized,
confirmed no exporter reads `kind` for anything except the now-removed
audio validator check):

    location_/set_        -> set
    character_/char_      -> character
    everything else       -> prop   (vehicle_, ship_, asset_, prop_, ...)

Why this doesn't read StudioChatAsset.glb_path directly: that column (and
StudioChatAssetRevision.glb_path) is populated at job-*creation* time from
a payload built by app.routers.conversations._build_job_payload, which
uses a literal "{job_id}" path template -- it is never substituted back
into the DB after the job completes. It is not a usable filesystem path
today. The real, resolved artifact location lives in the Job's Artifact
records instead, so this script always ends up walking: job_id -> job
trace -> the .glb artifact's download URL.

Two independent, first-class, mutually exclusive resolvers produce that
job_id (plus a canonical_id and kind hint) before the shared pipeline
(find artifact, download, register) runs -- see
docs/planning/REVIEW-AUDIT.md section 16, "Resolver design correction:
symmetric inputs, not a bypass". Neither is a fallback for the other:

  --asset-id  resolves via a Studio Chat asset's current revision
              (StudioChatAssetRevision.job_id).
  --job-id    resolves via a directly-submitted job's own payload
              (payload.blueprint.canonical_id), e.g. a job submitted by
              tools/submit_blueprint_job.py that has no Studio Chat
              asset/revision row at all.

Usage:
    python3 tools/register_studio_chat_asset.py --asset-id prop_round_dining_table_rounded_A \\
        --harness-url http://localhost:8088 --admin-token local-admin-token

    python3 tools/register_studio_chat_asset.py --job-id 2a0f3cb1-... \\
        --harness-url http://localhost:8088 --admin-token local-admin-token

    # Preview without writing anything:
    python3 tools/register_studio_chat_asset.py --asset-id <id> --admin-token ... --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import NamedTuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent

KIND_FOLDERS = {
    "prop": "props",
    "set": "sets",
    "character": "characters",
}


def _get_json(url: str, admin_token: str) -> dict:
    request = urllib.request.Request(
        url, headers={"Authorization": f"Bearer {admin_token}"}
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read())


def kind_for_canonical_id(asset_id: str, override: str | None) -> str:
    if override:
        if override not in KIND_FOLDERS:
            raise SystemExit(f"--kind must be one of {sorted(KIND_FOLDERS)}, got {override!r}")
        return override
    if asset_id.startswith(("location_", "set_")):
        return "set"
    if asset_id.startswith(("character_", "char_")):
        return "character"
    # vehicle_, ship_, asset_, prop_, and any other prefix all register as
    # prop -- confirmed safe in REVIEW-AUDIT.md section 14: no exporter
    # branches on kind for placement/animation, only the now-removed audio
    # validator check ever consumed it.
    return "prop"


class BuildResolution(NamedTuple):
    """What either resolver must produce before the shared pipeline runs."""
    job_id: str
    canonical_id: str
    source_revision: int | None  # informational only; None when resolved via --job-id


def resolve_via_asset_id(harness_url: str, admin_token: str, asset_id: str) -> BuildResolution:
    try:
        asset_state = _get_json(
            f"{harness_url}/api/v1/studio-chat/assets/{asset_id}/state", admin_token
        )
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"Could not fetch asset {asset_id!r}: HTTP {exc.code}") from exc

    current_revision = asset_state["current_revision"]
    revisions = _get_json(
        f"{harness_url}/api/v1/studio-chat/assets/{asset_id}/revisions", admin_token
    )
    revision = next(
        (r for r in revisions.get("revisions", []) if r.get("revision") == current_revision),
        None,
    )
    if revision is None or not revision.get("job_id"):
        raise SystemExit(
            f"Asset {asset_id!r} revision {current_revision} has no linked job_id "
            "-- cannot locate its built .glb"
        )
    return BuildResolution(job_id=revision["job_id"], canonical_id=asset_id, source_revision=current_revision)


def resolve_via_job_id(harness_url: str, admin_token: str, job_id: str) -> BuildResolution:
    try:
        job = _get_json(f"{harness_url}/api/v1/jobs/{job_id}", admin_token)
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"Could not fetch job {job_id!r}: HTTP {exc.code}") from exc

    blueprint = (job.get("payload") or {}).get("blueprint") or {}
    canonical_id = blueprint.get("canonical_id")
    if not canonical_id:
        raise SystemExit(
            f"Job {job_id!r} has no payload.blueprint.canonical_id -- cannot register "
            "(not a job submitted by tools/submit_blueprint_job.py?)"
        )
    return BuildResolution(job_id=job_id, canonical_id=canonical_id, source_revision=None)


def find_glb_artifact(harness_url: str, admin_token: str, job_id: str) -> dict:
    trace = _get_json(f"{harness_url}/api/v1/debug/jobs/{job_id}/trace", admin_token)
    for artifact in trace.get("artifacts", []):
        filename = str(artifact.get("filename", ""))
        if filename.lower().endswith(".glb"):
            return artifact
    raise SystemExit(f"No .glb artifact found on job {job_id} (checked {len(trace.get('artifacts', []))} artifacts)")


def download_artifact(harness_url: str, admin_token: str, artifact: dict, dest: Path) -> int:
    review_url = artifact["review_url"]
    request = urllib.request.Request(
        f"{harness_url}{review_url}", headers={"Authorization": f"Bearer {admin_token}"}
    )
    dest.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(request, timeout=60) as response:
        data = response.read()
    dest.write_bytes(data)
    return len(data)


def register_in_config(config_path: Path, asset_id: str, rel_file: str, kind: str) -> None:
    config = json.loads(config_path.read_text())
    config.setdefault("assets", {})[asset_id] = {
        "file": rel_file,
        "node": asset_id,
        "kind": kind,
    }
    config_path.write_text(json.dumps(config, indent=2) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    resolver_group = parser.add_mutually_exclusive_group(required=True)
    resolver_group.add_argument("--asset-id", help="Resolve via a Studio Chat asset's current revision")
    resolver_group.add_argument("--job-id", help="Resolve via a directly-submitted job's own payload")
    parser.add_argument("--harness-url", default=os.environ.get("OEB_HARNESS_URL", "http://localhost:8088"))
    parser.add_argument("--admin-token", default=os.environ.get("API_ADMIN_TOKEN", ""), required=False)
    parser.add_argument("--config", default=str(PROJECT_ROOT / "oeb.config.json"))
    parser.add_argument("--asset-root", default=None, help="Defaults to asset_root in the config file")
    parser.add_argument("--kind", default=None, choices=sorted(KIND_FOLDERS), help="Override the derived kind")
    parser.add_argument("--dry-run", action="store_true", help="Print what would happen; write nothing")
    args = parser.parse_args()

    if not args.admin_token:
        raise SystemExit("--admin-token required (or set API_ADMIN_TOKEN)")

    config_path = Path(args.config)
    config = json.loads(config_path.read_text())
    asset_root = Path(args.asset_root or config.get("asset_root", "assets"))
    if not asset_root.is_absolute():
        asset_root = PROJECT_ROOT / asset_root

    if args.asset_id:
        resolution = resolve_via_asset_id(args.harness_url, args.admin_token, args.asset_id)
    else:
        resolution = resolve_via_job_id(args.harness_url, args.admin_token, args.job_id)

    artifact = find_glb_artifact(args.harness_url, args.admin_token, resolution.job_id)
    kind = kind_for_canonical_id(resolution.canonical_id, args.kind)
    rel_file = f"{KIND_FOLDERS[kind]}/{resolution.canonical_id}.glb"
    dest = asset_root / rel_file

    print(f"canonical_id: {resolution.canonical_id}")
    revision_note = f"revision {resolution.source_revision}" if resolution.source_revision is not None else "direct job"
    print(f"resolved via: {'--asset-id' if args.asset_id else '--job-id'}  ({revision_note}, job {resolution.job_id})")
    print(f"kind:         {kind}")
    print(f"artifact:     {artifact['filename']} ({artifact.get('size_bytes', '?')} bytes)")
    print(f"dest:         {dest}")
    print(f"registry:     {config_path} -> assets.{resolution.canonical_id} = "
          f"{{file: {rel_file!r}, node: {resolution.canonical_id!r}, kind: {kind!r}}}")

    if args.dry_run:
        print("(dry run -- nothing written)")
        return 0

    size = download_artifact(args.harness_url, args.admin_token, artifact, dest)
    print(f"Wrote {size} bytes to {dest}")
    register_in_config(config_path, resolution.canonical_id, rel_file, kind)
    print(f"Updated {config_path}. Review and commit it yourself -- this script does not touch git.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
