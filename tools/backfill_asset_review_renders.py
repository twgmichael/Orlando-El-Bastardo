#!/usr/bin/env python3
"""Copy locally rendered asset review PNGs into a harness job's artifact store."""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


DEFAULT_HARNESS_URL = "http://oeb-studio.docker-pi"
REVIEW_VIEWS = ("front", "back", "left", "right", "top", "bottom", "action")


def normalize_base_url(url: str) -> str:
    url = url.strip().rstrip("/")
    if url and "://" not in url:
        url = f"http://{url}"
    if not url:
        raise SystemExit("Set OEB_HARNESS_URL or pass --harness-url")
    return url


def detect_view(asset_id: str, path: Path) -> str | None:
    stem = path.stem
    prefix = f"{asset_id}_"
    view = stem[len(prefix):] if stem.startswith(prefix) else stem.rsplit("_", 1)[-1]
    return view if view in REVIEW_VIEWS else None


def post_file(url: str, token: str, file_path: Path, params: dict[str, str]) -> dict:
    query = urlencode({key: value for key, value in params.items() if value})
    req = Request(
        f"{url}?{query}",
        data=file_path.read_bytes(),
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": params.get("mime_type") or "application/octet-stream",
        },
    )
    try:
        with urlopen(req, timeout=120) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"HTTP {exc.code} from harness while uploading {file_path.name}: {detail}") from exc
    except URLError as exc:
        raise SystemExit(f"Could not reach harness while uploading {file_path.name}: {exc.reason}") from exc


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--asset-id", required=True)
    parser.add_argument("--asset-path", default="")
    parser.add_argument("--quality", default="preview")
    parser.add_argument("--renders-dir", required=True, type=Path)
    parser.add_argument("--pattern", default="*.png")
    parser.add_argument("--harness-url", default=os.environ.get("OEB_HARNESS_URL", DEFAULT_HARNESS_URL))
    parser.add_argument("--admin-token", default=os.environ.get("API_ADMIN_TOKEN", ""))
    parser.add_argument("--worker-token", default=os.environ.get("OEB_WORKER_TOKEN", ""))
    parser.add_argument("--worker-token-file", default="~/.oeb-harness-worker-token")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.renders_dir.is_dir():
        raise SystemExit(f"Render directory not found: {args.renders_dir}")

    base_url = normalize_base_url(args.harness_url)
    token = args.admin_token
    upload_url = f"{base_url}/api/v1/jobs/{args.job_id}/artifact-files/admin"
    if not token:
        worker_token_file = Path(args.worker_token_file).expanduser()
        token = args.worker_token or (worker_token_file.read_text().strip() if worker_token_file.is_file() else "")
        upload_url = f"{base_url}/api/v1/jobs/{args.job_id}/artifact-files"
    if not token:
        raise SystemExit("Set API_ADMIN_TOKEN, pass --admin-token, or provide a worker token")

    uploaded = []
    for path in sorted(args.renders_dir.glob(args.pattern)):
        if not path.is_file():
            continue
        view = detect_view(args.asset_id, path)
        if not view:
            continue
        content = path.read_bytes()
        checksum = hashlib.sha256(content).hexdigest()
        mime_type = mimetypes.guess_type(path.name)[0] or "image/png"
        metadata = {
            "job_type": "asset.review_render",
            "asset_id": args.asset_id,
            "asset_path": args.asset_path,
            "quality": args.quality,
            "view": view,
        }
        artifact = post_file(
            upload_url,
            token,
            path,
            {
                "artifact_type": "preview_render",
                "filename": path.name,
                "mime_type": mime_type,
                "checksum_sha256": checksum,
                "provenance": "backfilled",
                "review_metadata_json": json.dumps(metadata, separators=(",", ":")),
            },
        )
        uploaded.append({
            "view": view,
            "filename": artifact["filename"],
            "artifact_id": artifact["id"],
            "public_url": artifact["public_url"] or f"{base_url}/review/artifacts/{artifact['id']}",
        })

    if not uploaded:
        raise SystemExit(f"No review PNGs matched {args.pattern} in {args.renders_dir}")

    print(json.dumps({
        "job_id": args.job_id,
        "asset_id": args.asset_id,
        "gallery_url": f"{base_url}/review/assets/{args.asset_id}",
        "uploaded": uploaded,
    }, indent=2))


if __name__ == "__main__":
    main()
