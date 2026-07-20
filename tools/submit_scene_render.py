#!/usr/bin/env python3
"""Submit a scene script to the studio harness for a Blender render."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DEFAULT_STAGING_HARNESS_URL = "http://oeb-studio.docker-pi"


def normalize_base_url(url: str) -> str:
    url = url.strip().rstrip("/")
    if url and "://" not in url:
        url = f"http://{url}"
    return url


def request_json(method: str, url: str, token: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urlopen(req, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"HTTP {exc.code} from harness: {detail}") from exc
    except URLError as exc:
        raise SystemExit(f"Could not reach harness: {exc.reason}") from exc


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scene-name", required=True)
    parser.add_argument("--script", "--script-path", dest="script_path", required=True)
    parser.add_argument("--quality", choices=("draft", "preview", "final"), default="preview")
    parser.add_argument("--mode", choices=("preview", "blocking"))
    parser.add_argument("--width", type=int)
    parser.add_argument("--height", type=int)
    parser.add_argument("--worker", "--preferred-worker-id", dest="preferred_worker_id")
    parser.add_argument("--priority", type=int, default=10)
    parser.add_argument("--require-gpu-cycles", action="store_true")
    parser.add_argument("--expected-frames", type=int)
    parser.add_argument("--blender-timeout-seconds", type=int)
    parser.add_argument("--harness-url", default=os.environ.get("OEB_HARNESS_URL", DEFAULT_STAGING_HARNESS_URL))
    parser.add_argument("--admin-token", default=os.environ.get("API_ADMIN_TOKEN", ""))
    parser.add_argument("--public-base-url", default=os.environ.get("OEB_HARNESS_PUBLIC_BASE_URL", ""))
    parser.add_argument("--wait", action="store_true", help="Poll until the job leaves pending/running")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.admin_token:
        raise SystemExit("Set API_ADMIN_TOKEN or pass --admin-token")

    base_url = normalize_base_url(args.harness_url)
    public_base_url = normalize_base_url(args.public_base_url) if args.public_base_url else base_url
    body = {
        "scene_name": args.scene_name,
        "script_path": args.script_path,
        "quality": args.quality,
        "mode": args.mode,
        "width": args.width,
        "height": args.height,
        "preferred_worker_id": args.preferred_worker_id,
        "priority": args.priority,
        "require_gpu_cycles": args.require_gpu_cycles,
        "expected_frames": args.expected_frames,
        "blender_timeout_seconds": args.blender_timeout_seconds,
    }
    body = {key: value for key, value in body.items() if value is not None}

    job = request_json("POST", f"{base_url}/api/v1/scene-renders", args.admin_token, body)
    review_url = job["review_url"]
    if review_url.startswith("/"):
        review_url = f"{public_base_url}{review_url}"
    trace_url = job["trace_url"]
    if trace_url.startswith("/"):
        trace_url = f"{public_base_url}{trace_url}"
    print(json.dumps({
        "job_id": job["job_id"],
        "status": job["status"],
        "review_url": review_url,
        "trace_url": trace_url,
    }, indent=2))

    if args.wait:
        while True:
            time.sleep(5)
            status_job = request_json("GET", f"{base_url}/api/v1/jobs/{job['job_id']}", args.admin_token)
            print(f"{job['job_id']} {status_job['status']}", file=sys.stderr)
            if status_job["status"] not in {"pending", "running"}:
                break


if __name__ == "__main__":
    main()
