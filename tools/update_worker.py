#!/usr/bin/env python3
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request


def request_json(method: str, url: str, token: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=20) as response:
        return json.loads(response.read().decode())


def worker_state(base_url: str, token: str, worker_id: str) -> dict:
    return request_json("GET", f"{base_url}/api/v1/workers/{worker_id}", token)


def main() -> int:
    parser = argparse.ArgumentParser(description="Request a harness-managed worker self-update.")
    parser.add_argument("--harness-url", default=os.environ.get("OEB_HARNESS_URL", ""))
    parser.add_argument("--admin-token", default=os.environ.get("API_ADMIN_TOKEN", ""))
    parser.add_argument("--worker", required=True)
    parser.add_argument("--target-git-sha", default="")
    parser.add_argument(
        "--mode",
        default="drain_then_update",
        choices=["drain_then_update", "update_if_idle", "force_update"],
    )
    parser.add_argument("--wait", action="store_true")
    parser.add_argument("--timeout-seconds", type=int, default=600)
    args = parser.parse_args()

    if not args.harness_url:
        raise SystemExit("Set OEB_HARNESS_URL or pass --harness-url")
    if not args.admin_token:
        raise SystemExit("Set API_ADMIN_TOKEN or pass --admin-token")

    base_url = args.harness_url.rstrip("/")
    body = {
        "mode": args.mode,
        "target_git_sha": args.target_git_sha or None,
    }
    try:
        response = request_json(
            "POST",
            f"{base_url}/api/v1/workers/{args.worker}/update",
            args.admin_token,
            body,
        )
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode()
        print(f"update request failed ({exc.code}): {detail}", file=sys.stderr)
        return 1

    print(json.dumps(response, indent=2))
    if not args.wait:
        return 0

    deadline = time.monotonic() + args.timeout_seconds
    last_state = None
    while time.monotonic() < deadline:
        state = worker_state(base_url, args.admin_token, args.worker)
        update_state = state.get("update_state")
        if update_state != last_state:
            print(
                f"{args.worker} update_state={update_state} "
                f"git_sha={state.get('git_sha') or 'unknown'} "
                f"current_job={state.get('current_job_id') or '-'}",
                file=sys.stderr,
            )
            last_state = update_state
        if update_state in {"complete", "failed", "idle"}:
            print(json.dumps(state, indent=2))
            return 0 if update_state == "complete" else 1
        time.sleep(5)

    print(f"timed out waiting for {args.worker} update", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
