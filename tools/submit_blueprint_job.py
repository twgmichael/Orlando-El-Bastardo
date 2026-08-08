#!/usr/bin/env python3
"""Submit a Blueprint to the studio harness as a real job.

Wires tools/blueprint_interpreter.py into the harness job system: no
server-side changes needed, since the generic POST /api/v1/jobs endpoint
already accepts an arbitrary payload dict, and the worker's
BlenderCLIAdapter already runs any script_file/script_args generically
(the same mechanism Studio Chat's own build jobs run through -- see
app.routers.conversations._build_job_payload, which now targets this
same script). This is what makes the interpreter's output show up as
real Artifact rows -- required for
tools/register_studio_chat_asset.py-style registration to find it. See
docs/planning/REVIEW-AUDIT.md section 13.

Usage:
    python3 tools/submit_blueprint_job.py --blueprint-file blueprint.json \\
        --harness-url http://localhost:8088 --admin-token local-admin-token --wait
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


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


def build_job_payload(blueprint: dict) -> dict:
    canonical_id = blueprint["canonical_id"]
    blueprint_json = json.dumps(blueprint)

    job_root = f"jobs/{{job_id}}"
    glb_path = f"{job_root}/assets/{canonical_id}.glb"
    blend_path = f"{job_root}/assets/{canonical_id}.blend"
    manifest_path = f"{job_root}/out/blueprint_builds/{canonical_id}.json"

    return {
        "title": f"Build {canonical_id} from Blueprint",
        "description": f"Blueprint build: {canonical_id}",
        "required_capabilities": ["blender.command_line"],
        "policy": "run_anywhere",
        "payload": {
            "tool": "blueprint_interpreter",
            "script_file": "tools/blueprint_interpreter.py",
            "cwd": "{workspace_root}",
            "artifact_paths": [
                f"{{output_root}}/{glb_path}",
                f"{{output_root}}/{blend_path}",
                f"{{output_root}}/{manifest_path}",
            ],
            "artifact_type": "asset_build",
            "script_args": [
                "--blueprint-json",
                blueprint_json,
                "--glb-output",
                f"{{output_root}}/{glb_path}",
                "--blend-output",
                f"{{output_root}}/{blend_path}",
                "--manifest-output",
                f"{{output_root}}/{manifest_path}",
            ],
            "blueprint": blueprint,
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--blueprint-file", help="Path to a Blueprint JSON file")
    group.add_argument("--blueprint-json", help="Blueprint JSON as a literal string")
    parser.add_argument("--harness-url", default=os.environ.get("OEB_HARNESS_URL", "http://localhost:8088"))
    parser.add_argument("--admin-token", default=os.environ.get("API_ADMIN_TOKEN", ""))
    parser.add_argument("--priority", type=int, default=0)
    parser.add_argument("--preferred-worker-id")
    parser.add_argument("--wait", action="store_true", help="Poll until the job leaves pending/running")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    token = args.admin_token
    if not token:
        raise SystemExit("Set API_ADMIN_TOKEN or pass --admin-token")

    if args.blueprint_file:
        blueprint = json.loads(open(args.blueprint_file, encoding="utf-8").read())
    else:
        blueprint = json.loads(args.blueprint_json)

    if "canonical_id" not in blueprint:
        raise SystemExit("Blueprint JSON must include canonical_id")

    base_url = normalize_base_url(args.harness_url)
    job_request = build_job_payload(blueprint)
    job_request["priority"] = args.priority
    if args.preferred_worker_id:
        job_request["preferred_worker_id"] = args.preferred_worker_id

    job = request_json("POST", f"{base_url}/api/v1/jobs", token, job_request)
    job_id = job["id"]
    print(json.dumps({"job_id": job_id, "status": job["status"]}, indent=2))

    if args.wait:
        while True:
            time.sleep(2)
            job = request_json("GET", f"{base_url}/api/v1/jobs/{job_id}", token)
            print(f"{job_id} {job['status']}", file=sys.stderr)
            if job["status"] not in {"pending", "running"}:
                break
        print(json.dumps({"job_id": job_id, "status": job["status"]}, indent=2))


if __name__ == "__main__":
    main()
