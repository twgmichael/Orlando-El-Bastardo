#!/usr/bin/env python3
"""Upload a local file over an existing studio harness artifact row."""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen


DEFAULT_HARNESS_URL = "http://oeb-studio.docker-pi"


def normalize_base_url(url: str) -> str:
    url = url.strip().rstrip("/")
    if url and "://" not in url:
        url = f"http://{url}"
    if not url:
        raise SystemExit("Set OEB_HARNESS_URL or pass --harness-url")
    return url


def artifact_id_from(value: str) -> str:
    parsed = urlparse(value)
    path = parsed.path if parsed.scheme else value
    artifact_id = path.rstrip("/").rsplit("/", 1)[-1]
    if not artifact_id:
        raise SystemExit("Could not determine artifact id")
    return artifact_id


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
        raise SystemExit(f"HTTP {exc.code} from harness: {detail}") from exc
    except URLError as exc:
        raise SystemExit(f"Could not reach harness: {exc.reason}") from exc


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact", required=True, help="Artifact id or /review/artifacts/{id} URL")
    parser.add_argument("--file", required=True, type=Path, help="Local artifact file to upload")
    parser.add_argument("--harness-url", default=os.environ.get("OEB_HARNESS_URL", DEFAULT_HARNESS_URL))
    parser.add_argument("--admin-token", default=os.environ.get("API_ADMIN_TOKEN", ""))
    parser.add_argument("--mime-type")
    parser.add_argument("--provenance", default="backfilled")
    parser.add_argument("--metadata-json", default="")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.admin_token:
        raise SystemExit("Set API_ADMIN_TOKEN or pass --admin-token")
    if not args.file.is_file():
        raise SystemExit(f"File not found: {args.file}")

    artifact_id = artifact_id_from(args.artifact)
    content = args.file.read_bytes()
    checksum = hashlib.sha256(content).hexdigest()
    mime_type = args.mime_type or mimetypes.guess_type(args.file.name)[0] or "application/octet-stream"
    base_url = normalize_base_url(args.harness_url)
    url = f"{base_url}/api/v1/jobs/artifacts/{artifact_id}/file"
    artifact = post_file(
        url,
        args.admin_token,
        args.file,
        {
            "mime_type": mime_type,
            "checksum_sha256": checksum,
            "provenance": args.provenance,
            "review_metadata_json": args.metadata_json,
        },
    )
    print(json.dumps({
        "artifact_id": artifact["id"],
        "job_id": artifact["job_id"],
        "filename": artifact["filename"],
        "size_bytes": artifact["size_bytes"],
        "public_url": artifact["public_url"] or f"{base_url}/review/artifacts/{artifact['id']}",
        "storage_path": artifact["storage_path"],
    }, indent=2))


if __name__ == "__main__":
    main()
