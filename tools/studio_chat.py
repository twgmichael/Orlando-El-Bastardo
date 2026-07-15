#!/usr/bin/env python3
"""
Proving client for the conversation-to-build loop.

The durable interface is the harness API. This CLI is the first thin client:
creative sentence -> local Ollama JSON spec -> /api/v1/conversations/jobs.
"""

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request

DEFAULT_MODEL = "oeb-qwen2.5-3b"
DEFAULT_OLLAMA_URL = "http://localhost:11434"
DEFAULT_COMPONENTS = [
    "wedge nose",
    "compact dark cockpit",
    "low main hull",
    "two swept wings",
    "two large rear engines",
    "crooked tail fin",
    "asymmetric greebles",
]


def parse_args():
    parser = argparse.ArgumentParser(prog="studio_chat")
    parser.add_argument("request", help="Creative build request")
    parser.add_argument("--harness-url", default=os.environ.get("OEB_HARNESS_URL", ""))
    parser.add_argument("--admin-token", default=os.environ.get("API_ADMIN_TOKEN", ""))
    parser.add_argument("--ollama-url", default=os.environ.get("OLLAMA_BASE_URL", DEFAULT_OLLAMA_URL))
    parser.add_argument("--model", default=os.environ.get("OEB_STUDIO_CHAT_MODEL", DEFAULT_MODEL))
    parser.add_argument("--dry-run", action="store_true", help="Print the spec without submitting a job")
    return parser.parse_args()


def post_json(url: str, payload: dict, token: str | None = None, timeout: int = 60) -> dict:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def extract_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text.strip())


def slugify_asset_id(text: str) -> str:
    words = re.findall(r"[a-z0-9]+", text.lower())
    skip = {"a", "an", "the", "me", "make", "build", "from", "with", "of", "and"}
    useful = [w for w in words if w not in skip]
    stem = "_".join(useful[:4]) or "primitive_ship"
    return f"ship_{stem}_A"


def normalize_spec(request: str, spec: dict) -> dict:
    canonical_id = str(spec.get("canonical_id", "")).strip()
    if (
        not re.fullmatch(r"ship_[a-z0-9_]+_A", canonical_id)
        or "snake_case" in canonical_id
        or canonical_id == "ship_A"
    ):
        spec["canonical_id"] = slugify_asset_id(request)

    spec.setdefault("name", "Primitive Ship Concept")
    spec["kind"] = "ship"
    spec["build_method"] = "blender_primitives"
    spec["deliverables"] = ["glb", "preview_render", "review_page"]

    components = spec.get("components")
    if not isinstance(components, list) or len(components) < 5:
        spec["components"] = DEFAULT_COMPONENTS
    else:
        generic = {"cube", "sphere", "cylinder", "cone", "primitive"}
        component_words = {str(c).lower().strip() for c in components}
        if component_words <= generic:
            spec["components"] = DEFAULT_COMPONENTS
    return spec


def ollama_spec(args) -> dict:
    prompt = f"""
You are the production-designer intake assistant for a deterministic Blender studio harness.
Turn the user's request into one strict JSON object. Do not include markdown.

Schema:
{{
  "canonical_id": "ship_snake_case_A",
  "name": "Display Name",
  "kind": "ship",
  "style": "short visual style summary",
  "build_method": "blender_primitives",
  "components": ["component phrase", "..."],
  "deliverables": ["glb", "preview_render", "review_page"]
}}

Rules:
- Use kind "ship" for the first slice.
- Use build_method "blender_primitives".
- Keep components buildable from cubes, cylinders, cones, spheres, and simple materials.
- Do not request external assets.
- canonical_id must be lowercase snake case and end with _A.

User request: {args.request}
""".strip()
    payload = {
        "model": args.model,
        "prompt": prompt,
        "stream": False,
        "format": "json",
    }
    result = post_json(f"{args.ollama_url.rstrip('/')}/api/generate", payload, timeout=180)
    return normalize_spec(args.request, extract_json(result["response"]))


def main() -> int:
    args = parse_args()
    try:
        spec = ollama_spec(args)
    except (urllib.error.URLError, TimeoutError) as exc:
        print(f"[studio_chat] ERROR: could not reach Ollama at {args.ollama_url}: {exc}", file=sys.stderr)
        return 2
    except (KeyError, json.JSONDecodeError) as exc:
        print(f"[studio_chat] ERROR: Ollama did not return valid build JSON: {exc}", file=sys.stderr)
        return 2

    if args.dry_run:
        print(json.dumps({
            "creative_request": args.request,
            "spec": spec,
        }, indent=2))
        return 0

    if not args.harness_url:
        print("[studio_chat] ERROR: set OEB_HARNESS_URL or pass --harness-url", file=sys.stderr)
        return 2
    if not args.admin_token:
        print("[studio_chat] ERROR: set API_ADMIN_TOKEN or pass --admin-token", file=sys.stderr)
        return 2

    try:
        result = post_json(
            f"{args.harness_url.rstrip('/')}/api/v1/conversations/jobs",
            {
                "creative_request": args.request,
                "spec": spec,
            },
            token=args.admin_token,
        )
    except urllib.error.HTTPError as exc:
        print(f"[studio_chat] ERROR: harness rejected request ({exc.code}): {exc.read().decode()}", file=sys.stderr)
        return 3
    except urllib.error.URLError as exc:
        print(f"[studio_chat] ERROR: could not reach harness at {args.harness_url}: {exc}", file=sys.stderr)
        return 3

    review_url = result["review_url"]
    if review_url.startswith("/"):
        review_url = f"{args.harness_url.rstrip('/')}{review_url}"
    print(json.dumps({
        "job_id": result["job"]["id"],
        "status": result["job"]["status"],
        "review_url": review_url,
        "canonical_id": result["spec"]["canonical_id"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
