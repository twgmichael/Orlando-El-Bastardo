#!/usr/bin/env python3
"""set_designer.py -- the production-designer role's rough tier
(docs/planning/PRODUCTION-DESIGNER-PLAN.md, "Assignment interface":
automatic loop, no human dispatch), relocated out of
tools/producer.py's --primitive-fallback per the 2026-08-10 discovery
there: Producer had accreted this role's job (resolve a location
against approved stand-ins first, fall back to a primitive placeholder
otherwise) directly into its own per-scene loop, contradicting
PRODUCER-PLAN.md's own "never to improvise, substitute, or build"
charter. Producer now only ever writes a `kind: "location"` NEEDED
ticket for an unmapped location -- this script is what resolves it.

Runs as a job on the existing worker-agent job queue
(docs/planning/WORKER-AGENT-PLAN.md), via the *existing*
BlenderCLIAdapter's `script_file` payload mode -- no new adapter code.
Deliberately stdlib-only (no jsonschema, no third-party deps), matching
tools/placeholder_blueprint.py's own convention, so it runs identically
under Blender's bundled Python (as the worker invokes it) or the
project's own .venv (for direct CLI use/testing).

CLI:
  .venv/bin/python tools/set_designer.py \\
      --location-name red_dragon_inn_engine_room \\
      --script scripts/pilot/pilot.md --episode pilot --scene-number 3

Resolves the location (tier-1 stand-in match, else tier-2 primitive
build), then re-invokes producer.py for just that scene
(`--scenes N`) so the production process continues automatically --
no human step for this tier. Never fatal: an unresolvable location
exits non-zero with a clear message; the scene simply stays
NEEDS_ASSETS, same as before this script existed.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import placeholder_blueprint  # noqa: E402
import llm_asset_match  # noqa: E402

CONFIG_PATH = "oeb.config.json"
RESOLVER_MAP_PATH = "data/resolver_map.json"
STANDINS_PATH = "data/standins.json"
PLACEHOLDER_ASSETS_ROOT = "assets/placeholders"
VENV_PY = ".venv/bin/python"


def _load_json(path: str) -> dict:
    return json.loads(Path(path).read_text())


def _write_json(path: str, data: dict) -> None:
    Path(path).write_text(json.dumps(data, indent=2) + "\n")


def _real_location_candidates(rmap: dict) -> list[dict]:
    """Non-placeholder resolver_map.json locations -- the real,
    already-built library tier-1.5 checks against. No authored
    free-text description field exists on a location entry today, so
    the candidate description is synthesized from its actual marks/
    default_props ids -- honest signal (real names in the real asset),
    just thinner than hand-written prose would be.
    """
    out = []
    for tag, entry in rmap.get("locations", {}).items():
        if entry.get("placeholder"):
            continue
        marks = ", ".join(entry.get("marks", [])[:6])
        props = ", ".join(p.get("asset_id", "") for p in entry.get("default_props", [])[:6])
        desc_parts = []
        if marks:
            desc_parts.append(f"marks: {marks}")
        if props:
            desc_parts.append(f"props: {props}")
        out.append({"id": tag, "display_name": tag, "description": "; ".join(desc_parts)})
    return out


def resolve_location(
    location_name: str,
    *,
    int_ext: str | None = None,
    scene_evidence: str | None = None,
    config_path: str = CONFIG_PATH,
    resolver_map_path: str = RESOLVER_MAP_PATH,
    standins_path: str = STANDINS_PATH,
    placeholder_assets_root: str = PLACEHOLDER_ASSETS_ROOT,
) -> dict:
    """Resolve *location_name* -- a raw screenplay location_tag Producer
    could not match directly against `data/resolver_map.json`'s
    `locations` map. Tier-1 stand-in match first (approved sets/
    locations, per the "Set Designer" feedback: read the deliberate
    author direction first); tier-1.5 LLM match against the real
    library (docs/planning/LLM-ASSET-MATCHING-PLAN.md) when *scene_evidence*
    is given and tier-1 misses; tier-2 primitive placeholder build only
    when nothing else resolves it. Mutates the real registries on disk,
    same ones Producer/export_blender.py already read -- no separate
    store.

    *int_ext* ("INT"/"EXT"/"INT/EXT", from tools/screenplay.py's own
    scene parse) drives docs/planning/CAMERA-SHOT-SCALE-PLAN.md's
    shot_scale classification for a tier-2 build -- see
    placeholder_blueprint.classify_shot_scale(). None (e.g. a direct
    CLI call with no scene context) degrades to "intimate", the same
    default every location had before this field existed.

    *scene_evidence* is the scripted slugline/action text tier-1.5
    grounds a match against -- optional so every existing caller
    (direct CLI testing, anything not yet passing it) degrades to the
    original tier-1 -> tier-2 behavior unchanged.

    Returns {"tier": "stand_in"|"llm_stand_in"|"primitive"|None,
    "resolved_tag": str|None, "error": str|None}.
    """
    rmap = _load_json(resolver_map_path)
    standins = _load_json(standins_path)

    # Tier 1: has a human/prior run already mapped this exact tag to a
    # real or previously-built location? (Producer's own direct-match
    # check already ruled out location_name itself being a resolver_map
    # key -- that's why this script was invoked at all.)
    standin = standins.get("location_standins", {}).get(location_name)
    if standin and standin in rmap.get("locations", {}):
        return {"tier": "stand_in", "resolved_tag": location_name, "error": None}

    # Tier 1.5 (docs/planning/LLM-ASSET-MATCHING-PLAN.md): does this
    # scripted tag actually refer to a real, already-built location the
    # exact-match stand-in table just doesn't know about yet? Only
    # tried when scene_evidence is available and there's at least one
    # real candidate to check against; any failure (no match, no
    # evidence, model unavailable) falls straight through to tier-2
    # unchanged -- never blocks resolution.
    if scene_evidence:
        candidates = _real_location_candidates(rmap)
        if candidates:
            result = llm_asset_match.match_existing_asset(
                location_name, scene_evidence, candidates, "location")
            if result["matched_id"] and llm_asset_match.grounded(
                    result["evidence"], scene_evidence):
                standins.setdefault("location_standins", {})[location_name] = result["matched_id"]
                _write_json(standins_path, standins)
                return {"tier": "llm_stand_in", "resolved_tag": location_name, "error": None}

    # Tier 2: no approved match -- build a crude primitive placeholder,
    # registered under location_name itself (so tier-1's direct-match
    # check resolves it instantly on any future occurrence).
    try:
        shot_scale = placeholder_blueprint.classify_shot_scale(int_ext, location_name)
        canonical_id = placeholder_blueprint.slugify_placeholder_id(location_name, "location")
        bp = placeholder_blueprint.default_placeholder_blueprint(
            canonical_id, "location", location_name, with_location_marks=True,
            shot_scale=shot_scale)
        placeholder_blueprint.build_placeholder_glb(
            bp, f"{placeholder_assets_root}/{canonical_id}.glb",
            f"out/blueprint_builds/{canonical_id}.blend",
            f"out/blueprint_builds/{canonical_id}.manifest.json")
        placeholder_blueprint.register_placeholder_asset(
            config_path, canonical_id, "location", f"placeholders/{canonical_id}.glb",
            source="set_designer")
        placeholder_blueprint.register_placeholder_location(
            resolver_map_path, location_name, canonical_id, source="set_designer",
            shot_scale=shot_scale)
    except Exception as exc:  # noqa: BLE001 -- must not crash the job
        return {"tier": None, "resolved_tag": None, "error": str(exc)}

    return {"tier": "primitive", "resolved_tag": location_name, "error": None}


def trigger_continuation(script: str, episode: str, scene_number: int, *, extra_args: list[str] | None = None) -> int:
    """Re-invoke producer.py for just the now-unblocked scene -- the
    "continues the production process" half of this role, per the
    PRODUCTION-DESIGNER-PLAN.md automatic-loop design. Does not re-run
    anything already delivered.

    Always passes --no-render (fixed 2026-08-13, found via
    tools/casting_director.py's own trigger_continuation() sharing
    this exact bug): without it, producer.py's default is to actually
    render (real headless-Blender video) as a side effect of a worker
    job whose only purpose is to unblock a location. Rendering stays
    an explicit, separate pass.
    """
    cmd = [VENV_PY, "tools/producer.py", "--script", script,
           "--primitive-fallback", "--scenes", str(scene_number), "--no-render"]
    if extra_args:
        cmd.extend(extra_args)
    result = subprocess.run(cmd)
    return result.returncode


def main() -> int:
    # Invoked either as `.venv/bin/python tools/set_designer.py <args>`
    # (direct CLI use) or `blender --background --python
    # tools/set_designer.py -- <args>` (the worker job queue's
    # BlenderCLIAdapter script_file mode) -- in the latter case
    # sys.argv also carries Blender's own arguments, so only what's
    # after `--` belongs to this script. Same convention as
    # assets/effects/hyperspace_effect_v1.1.0/attach_ship.py.
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]

    p = argparse.ArgumentParser(prog="set_designer")
    p.add_argument("--location-name", required=True)
    p.add_argument("--script", required=True, help="Episode script path, for continuation")
    p.add_argument("--episode", required=True)
    p.add_argument("--scene-number", type=int, required=True)
    p.add_argument("--int-ext", default=None,
                   help="INT/EXT/INT-EXT from the scene's own slugline, "
                        "for shot_scale classification (default: intimate)")
    p.add_argument("--location-context", default=None,
                   help="Scripted slugline/action text for this scene "
                        "(docs/planning/LLM-ASSET-MATCHING-PLAN.md tier-1.5 "
                        "grounding); omitted means tier-1.5 is skipped, "
                        "same tier-1 -> tier-2 behavior as before it existed")
    p.add_argument("--config", default=CONFIG_PATH)
    p.add_argument("--resolver-map", default=RESOLVER_MAP_PATH)
    p.add_argument("--standins", default=STANDINS_PATH)
    p.add_argument("--placeholder-assets-root", default=PLACEHOLDER_ASSETS_ROOT)
    p.add_argument("--no-continue", action="store_true",
                   help="Resolve only; skip re-invoking producer.py (testing aid)")
    args = p.parse_args(argv)

    result = resolve_location(
        args.location_name,
        int_ext=args.int_ext,
        scene_evidence=args.location_context,
        config_path=args.config,
        resolver_map_path=args.resolver_map,
        standins_path=args.standins,
        placeholder_assets_root=args.placeholder_assets_root,
    )
    print(json.dumps({"location_name": args.location_name, **result}, indent=2))

    if result["error"] or not result["resolved_tag"]:
        print(f"[set_designer] FAILED to resolve '{args.location_name}'; scene stays NEEDS_ASSETS")
        return 1

    print(f"[set_designer] resolved '{args.location_name}' via {result['tier']} tier")

    if args.no_continue:
        return 0

    return trigger_continuation(args.script, args.episode, args.scene_number)


if __name__ == "__main__":
    sys.exit(main())
