#!/usr/bin/env python3
"""
Studio Chat visual-variety benchmark.

Phase 4 of docs/planning/REVIEW-AUDIT.md section 9: replace "how many
milestones shipped" with a real signal for whether Studio Chat is
producing more varied, detailed output over time.

Submits a fixed set of creative prompts to a running Studio Chat harness
(the same /api/v1/studio-chat endpoint the CLI and browser UI use), waits
for each build job to complete, and records what actually got built --
primitive count and the mix of primitive types used per job, pulled from
the real worker's build log. Re-run this after any change to the resolver,
compiler, or tools/blueprint_interpreter.py / tools/oeb_blender/recipes.py
and diff the results against a prior run to see whether output variety
actually moved.

This intentionally does not judge visual quality (no human/vision-model
review here) -- it judges structural variety: object count and primitive
mix are a cheap, objective proxy for "still just boxy primitives" vs.
"using the recipe library". Pair with human/gallery review for the
subjective call.

Usage:
    python3 tools/studio_chat_benchmark.py \\
        --harness-url http://localhost:8088 \\
        --admin-token local-admin-token \\
        --output docs/planning/benchmarks/results.jsonl
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

# Fixed benchmark set. Keep stable across runs -- editing a prompt here
# breaks comparability with prior results.jsonl entries for that prompt.
# Deliberately spans: single-category furniture (exercises the Phase 2
# category-routing fix), a multi-part vehicle, an aircraft, a lit prop,
# and a location -- not just one easy case.
BENCHMARK_PROMPTS = [
    "Build an office chair with a rounded seat.",
    "Build a wooden storage cabinet with two drawers.",
    "Build a small bed with a soft mattress and a pillow.",
    "Build a round dining table with rounded corners and thin legs.",
    "Build a two-wheeled motorcycle with a low frame and handlebars.",
    "Build a small fighter spaceship with swept wings and a cockpit.",
    "Build a floor lamp with a warm glow.",
    "Build a park bench next to a tree.",
]


def submit_job(harness_url: str, admin_token: str, prompt: str) -> dict:
    request = urllib.request.Request(
        f"{harness_url}/api/v1/studio-chat",
        data=json.dumps({"prompt": prompt}).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {admin_token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read())


def fetch_trace(harness_url: str, admin_token: str, job_id: str) -> dict:
    request = urllib.request.Request(
        f"{harness_url}/api/v1/debug/jobs/{job_id}/trace",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read())


def wait_for_completion(harness_url: str, admin_token: str, job_id: str, timeout_s: int = 60) -> dict:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        trace = fetch_trace(harness_url, admin_token, job_id)
        job = trace.get("job", {})
        status = job.get("status")
        if status in {"completed", "failed", "error"}:
            return trace
        time.sleep(1.5)
    raise TimeoutError(f"Job {job_id} did not finish within {timeout_s}s")


def primitive_mix_from_log(log_output: str) -> dict[str, int]:
    """Count primitive types created, parsed from the glTF export log lines
    Blender prints (e.g. 'Extracting primitive: Cube.004'). Object names
    map to primitive kind by stripping the numeric/dedup suffix.
    """
    mix: dict[str, int] = {}
    for match in re.finditer(r"Extracting primitive: (\w+)", log_output):
        raw_name = match.group(1)
        kind = re.sub(r"\.\d+$", "", raw_name)
        mix[kind] = mix.get(kind, 0) + 1
    return mix


def run_benchmark(harness_url: str, admin_token: str, prompts: list[str]) -> list[dict]:
    results = []
    for prompt in prompts:
        print(f"-> {prompt}", file=sys.stderr)
        started = time.time()
        try:
            submission = submit_job(harness_url, admin_token, prompt)
            job_id = submission["job_id"]
            trace = wait_for_completion(harness_url, admin_token, job_id)
            job = trace.get("job", {})
            attempts = trace.get("attempts", [])
            log_output = attempts[-1]["log_output"] if attempts else ""
            primitive_mix = primitive_mix_from_log(log_output)
            result = {
                "prompt": prompt,
                "job_id": job_id,
                "canonical_id": submission.get("canonical_id"),
                "status": job.get("status"),
                "primitive_count": sum(primitive_mix.values()),
                "primitive_mix": primitive_mix,
                "distinct_primitive_kinds": len(primitive_mix),
                "duration_s": round(time.time() - started, 2),
            }
        except (urllib.error.URLError, TimeoutError, KeyError) as exc:
            result = {
                "prompt": prompt,
                "status": "harness_error",
                "error": str(exc),
                "duration_s": round(time.time() - started, 2),
            }
        print(f"   {result.get('status')}: {result.get('primitive_mix', result.get('error'))}", file=sys.stderr)
        results.append(result)
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--harness-url", default="http://localhost:8088")
    parser.add_argument("--admin-token", required=True)
    parser.add_argument("--output", default=None, help="Append JSONL results here")
    args = parser.parse_args()

    run_started_at = datetime.now(timezone.utc).isoformat()
    results = run_benchmark(args.harness_url, args.admin_token, BENCHMARK_PROMPTS)

    summary = {
        "run_started_at": run_started_at,
        "prompt_count": len(BENCHMARK_PROMPTS),
        "completed": sum(1 for r in results if r.get("status") == "completed"),
        "total_primitive_count": sum(r.get("primitive_count", 0) for r in results),
        "results": results,
    }

    if args.output:
        with open(args.output, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(summary) + "\n")
        print(f"Appended run to {args.output}", file=sys.stderr)

    print(json.dumps(summary, indent=2))
    return 0 if summary["completed"] == summary["prompt_count"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
