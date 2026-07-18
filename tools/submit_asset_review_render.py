#!/usr/bin/env python3
"""Submit an existing asset for studio harness review renders."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DEFAULT_VIEWS = "top,bottom,left,right,front,back,action"
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
    parser.add_argument("--asset", required=True, help="Repo-relative or worker-visible asset path")
    parser.add_argument("--asset-id", required=True)
    parser.add_argument("--views", default=DEFAULT_VIEWS)
    parser.add_argument("--quality", choices=("preview", "final"), default="preview")
    parser.add_argument("--output-namespace")
    parser.add_argument("--artifact-prefix")
    parser.add_argument("--priority", type=int, default=10)
    parser.add_argument("--preferred-worker-id")
    parser.add_argument("--width", type=int)
    parser.add_argument("--height", type=int)
    parser.add_argument("--samples", type=int)
    parser.add_argument("--output-path")
    parser.add_argument("--harness-url", default=os.environ.get("OEB_HARNESS_URL", ""))
    parser.add_argument(
        "--staging",
        action="store_true",
        help=f"Submit to the docker-pi staging harness ({DEFAULT_STAGING_HARNESS_URL})",
    )
    parser.add_argument("--admin-token", default=os.environ.get("API_ADMIN_TOKEN", ""))
    parser.add_argument("--public-base-url", default=os.environ.get("OEB_HARNESS_PUBLIC_BASE_URL", ""))
    parser.add_argument("--wait", action="store_true", help="Poll until the job leaves pending/running")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    harness_url = DEFAULT_STAGING_HARNESS_URL if args.staging and not args.harness_url else args.harness_url
    if not harness_url:
        raise SystemExit(
            "Set OEB_HARNESS_URL, pass --harness-url, or pass --staging for docker-pi"
        )

    token = args.admin_token
    if not token:
        raise SystemExit("Set API_ADMIN_TOKEN or pass --admin-token")

    base_url = normalize_base_url(harness_url)
    public_base_url = normalize_base_url(args.public_base_url) if args.public_base_url else base_url
    views = [view.strip() for view in args.views.split(",") if view.strip()]
    body = {
        "asset_path": args.asset,
        "asset_id": args.asset_id,
        "views": views,
        "quality": args.quality,
        "output_namespace": args.output_namespace,
        "artifact_prefix": args.artifact_prefix,
        "priority": args.priority,
        "preferred_worker_id": args.preferred_worker_id,
        "width": args.width,
        "height": args.height,
        "samples": args.samples,
        "output_path": args.output_path,
    }
    body = {key: value for key, value in body.items() if value is not None}

    job = request_json("POST", f"{base_url}/api/v1/jobs/asset-review-renders", token, body)
    job_id = job["id"]
    gallery_url = f"{public_base_url}/review/assets/{args.asset_id}"
    job_url = f"{public_base_url}/review/jobs/{job_id}"
    print(json.dumps({
        "job_id": job_id,
        "status": job["status"],
        "gallery_url": gallery_url,
        "job_url": job_url,
    }, indent=2))

    if args.wait:
        while True:
            time.sleep(5)
            job = request_json("GET", f"{base_url}/api/v1/jobs/{job_id}", token)
            print(f"{job_id} {job['status']}", file=sys.stderr)
            if job["status"] not in {"pending", "running"}:
                break
        print(json.dumps({
            "job_id": job_id,
            "status": job["status"],
            "gallery_url": gallery_url,
            "job_url": job_url,
        }, indent=2))


if __name__ == "__main__":
    main()
