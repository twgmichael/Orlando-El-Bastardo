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
FIGHTER_COMPONENTS = [
    "wedge nose",
    "compact dark cockpit",
    "low main hull",
    "two swept wings",
    "two large rear engines",
    "crooked tail fin",
    "asymmetric greebles",
]
OFFICE_COMPONENTS = [
    "office floor",
    "back wall",
    "desk",
    "large window",
    "lamp",
    "two chairs",
]
PARK_COMPONENTS = [
    "grass ground",
    "walking path",
    "four trees",
    "park bench",
]
STATION_COMPONENTS = [
    "central habitat hub",
    "large observation window",
    "outer ring modules",
    "four docking arms",
    "antenna mast",
    "solar panel arrays",
]


def request_text(request: str, spec: dict | None = None) -> str:
    parts = [request]
    if spec:
        parts.extend([
            str(spec.get("canonical_id", "")),
            str(spec.get("name", "")),
            str(spec.get("style", "")),
            " ".join(str(c) for c in spec.get("components", [])),
        ])
    return " ".join(parts).lower()


def text_has_any(text: str, words: tuple[str, ...]) -> bool:
    tokens = set(re.findall(r"[a-z0-9]+", text.lower()))
    return any(word in tokens for word in words)


def infer_kind(request: str, spec: dict | None = None) -> str:
    text = request_text(request, spec)
    if text_has_any(text, ("office", "park", "room", "street", "alley", "forest", "set", "location", "bay", "clinic", "medical", "lab")):
        return "location"
    if text_has_any(text, ("chair", "desk", "lamp", "table", "prop")) and not text_has_any(text, ("room", "office")):
        return "prop"
    if text_has_any(text, ("ship", "spaceship", "fighter", "vehicle", "craft", "car", "truck")):
        return "vehicle"
    return "asset"


def request_wants_station(request: str, spec: dict | None = None) -> bool:
    return text_has_any(request_text(request, spec), ("station", "orbital", "habitat", "ring", "dock", "solar"))


def request_wants_office(request: str, spec: dict | None = None) -> bool:
    return text_has_any(request_text(request, spec), ("office", "desk", "chair", "lamp", "workspace"))


def request_wants_park(request: str, spec: dict | None = None) -> bool:
    return text_has_any(request_text(request, spec), ("park", "tree", "path", "trail", "bench", "grass", "garden"))


def default_components_for(request: str, spec: dict | None = None) -> list[str]:
    if request_wants_office(request, spec):
        return OFFICE_COMPONENTS
    if request_wants_park(request, spec):
        return PARK_COMPONENTS
    if request_wants_station(request, spec):
        return STATION_COMPONENTS
    if infer_kind(request, spec) == "vehicle":
        return FIGHTER_COMPONENTS
    return ["primary structure", "secondary feature", "detail element"]


def parse_args():
    parser = argparse.ArgumentParser(prog="studio_chat")
    parser.add_argument("request", help="Creative build request")
    parser.add_argument("--harness-url", default=os.environ.get("OEB_HARNESS_URL", ""))
    parser.add_argument("--admin-token", default=os.environ.get("API_ADMIN_TOKEN", ""))
    parser.add_argument("--ollama-url", default=os.environ.get("OLLAMA_BASE_URL", DEFAULT_OLLAMA_URL))
    parser.add_argument("--model", default=os.environ.get("OEB_STUDIO_CHAT_MODEL", DEFAULT_MODEL))
    parser.add_argument("--dry-run", action="store_true", help="Print the spec without submitting a job")
    parser.add_argument(
        "--legacy-local-intake",
        action="store_true",
        help="Run the old CLI-owned LLM intake flow instead of calling /api/v1/studio-chat",
    )
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
    stem = "_".join(useful[:4]) or "primitive_asset"
    return f"asset_{stem}_A"


def normalize_id(text: str, fallback: str = "object") -> str:
    words = re.findall(r"[a-z0-9]+", str(text).lower())
    return "_".join(words) or fallback


def named_object_candidates(request: str) -> list[str]:
    text = request.lower()
    text = re.sub(r"\b(build|make|create|with|and|a|an|the|in|on|at|to|from|of|for)\b", " ", text)
    text = re.sub(r"\b(left|right|center|middle|rear|back|front|large|small|tall|wide|facing|mounted)\b", " ", text)
    parts = [p.strip() for p in re.split(r"[,.;]|\s+and\s+|\s+with\s+", text) if p.strip()]
    candidates = []
    for part in parts:
        words = [w for w in re.findall(r"[a-z0-9]+", part) if w not in {"room", "scene", "set", "location"}]
        if words:
            candidates.append("_".join(words[-3:]))
    return candidates[:12]


def scene_object_component(obj: dict) -> str:
    parts = []
    count = obj.get("count")
    size = obj.get("size")
    label = obj.get("label") or obj.get("id") or "object"
    placement = obj.get("placement")
    mounting = obj.get("mounting")
    orientation = obj.get("orientation") or {}

    if isinstance(count, int) and count > 1:
        number_words = {2: "two", 3: "three", 4: "four", 5: "five", 6: "six"}
        parts.append(number_words.get(count, str(count)))
    if size:
        parts.append(str(size))
    parts.append(str(label))
    if placement:
        parts.append(str(placement))
    if mounting:
        parts.append(str(mounting))
    if isinstance(orientation, dict):
        faces = orientation.get("faces")
        if faces:
            parts.append(f"facing_{faces}")
    return normalize_id("_".join(parts), "component")


def derive_spec_from_scene_plan(request: str, scene_plan: dict) -> dict:
    objects = scene_plan.get("objects") if isinstance(scene_plan, dict) else []
    components = []
    if isinstance(objects, list):
        for obj in objects:
            if isinstance(obj, dict):
                components.append(scene_object_component(obj))

    style = scene_plan.get("style") if isinstance(scene_plan, dict) else None
    scene_type = scene_plan.get("scene_type") if isinstance(scene_plan, dict) else None
    return normalize_spec(request, {
        "canonical_id": slugify_asset_id(request),
        "name": str(scene_type or "Primitive Asset Concept").replace("_", " ").title(),
        "kind": infer_kind(request),
        "style": style or request,
        "creative_request": request,
        "build_method": "blender_primitives",
        "components": components,
        "scene_plan": scene_plan,
        "repaired_scene_plan": scene_plan,
        "deliverables": ["glb", "preview_render", "review_page"],
    })


def normalize_spec(request: str, spec: dict) -> dict:
    canonical_id = str(spec.get("canonical_id", "")).strip()
    inferred_kind = infer_kind(request, spec)
    if (
        not re.fullmatch(r"[a-z]+_[a-z0-9_]+_A", canonical_id)
        or "snake_case" in canonical_id
        or canonical_id in {"ship_A", "asset_A"}
        or (canonical_id.startswith("ship_") and inferred_kind != "vehicle")
    ):
        spec["canonical_id"] = slugify_asset_id(request)

    spec.setdefault("name", "Primitive Asset Concept")
    spec["kind"] = inferred_kind
    spec["creative_request"] = request
    spec["build_method"] = "blender_primitives"
    spec["deliverables"] = ["glb", "preview_render", "review_page"]

    components = spec.get("components")
    if not isinstance(components, list) or not components:
        spec["components"] = default_components_for(request, spec)
    else:
        generic = {"cube", "sphere", "cylinder", "cone", "primitive"}
        component_words = {str(c).lower().strip() for c in components}
        if component_words <= generic:
            spec["components"] = default_components_for(request, spec)
    return spec


def ollama_generate(args, prompt: str) -> dict:
    payload = {
        "model": args.model,
        "prompt": prompt,
        "stream": False,
        "format": "json",
    }
    result = post_json(f"{args.ollama_url.rstrip('/')}/api/generate", payload, timeout=180)
    raw_response = result["response"]
    return {
        "prompt": prompt,
        "raw_response": raw_response,
        "parsed_response": extract_json(raw_response),
    }


def scene_plan_prompt(request: str) -> str:
    return f"""
You are the production-designer intake assistant for a deterministic Blender studio harness.
Turn the user's creative request into one strict JSON scene plan. Do not include markdown.

Schema:
{{
  "scene_type": "short_snake_case_scene_type",
  "style": "short visual style summary",
  "objects": [
    {{
      "id": "stable_snake_case_object_id",
      "label": "human readable object name",
      "category": "seating|surface|storage|screen|lighting|bed|medical|plant|path|wall_item|machine|structure|unknown",
      "count": 1,
      "size": "small|medium|large|wide|tall",
      "placement": "center|left|right|front|rear_wall|back|corner|on_surface",
      "mounting": "floor|wall|ceiling|surface",
      "orientation": {{"faces": "target_object_id"}}
    }}
  ],
  "relationships": [
    {{"subject": "object_id", "relation": "faces|left_of|right_of|behind|in_front_of|near|on_top_of|mounted_on|inside|around|aligned_with", "target": "object_id_or_scene_feature"}}
  ]
}}

Rules:
- Every named object in the user request must appear as its own object.
- Preserve quantities, sizes, mounting, placement, and orientation.
- Relationship records may reference objects, but cannot replace object records.
- Use primitive-friendly categories. Do not request external assets.
- Use stable snake_case ids.
- Output only valid JSON.

User request: {request}
""".strip()


def repair_scene_plan_prompt(request: str, scene_plan: dict, named_objects: list[str]) -> str:
    return f"""
You are repairing a scene plan for a deterministic Blender studio harness.
Compare the original creative request to the parsed scene plan and return one corrected JSON scene plan. Do not include markdown.

Repair rules:
- Every named object from the request must be represented in objects.
- Preserve quantities such as two chairs or 3 trees.
- Preserve size hints like large, small, wide, tall.
- Preserve mounting and placement hints like rear wall, corner, on desk, background.
- Preserve relationships like facing, next to, left of, right of, mounted on.
- Keep object ids stable when they are already good.
- Output only valid JSON in the same schema.

Original creative request: {request}

Possible named object hints from request: {json.dumps(named_objects)}

Current scene plan:
{json.dumps(scene_plan, indent=2)}
""".strip()


def legacy_spec_prompt(request: str) -> str:
    prompt = f"""
You are the production-designer intake assistant for a deterministic Blender studio harness.
Turn the user's request into one strict JSON object. Do not include markdown.

Schema:
{{
  "canonical_id": "asset_snake_case_A",
  "name": "Display Name",
  "kind": "asset",
  "style": "short visual style summary",
  "build_method": "blender_primitives",
  "components": ["component phrase", "..."],
  "deliverables": ["glb", "preview_render", "review_page"]
}}

Rules:
- Use kind "location" for places or scenes, "vehicle" for ships/craft, "prop" for single objects, or "asset" when unsure.
- Use build_method "blender_primitives".
- Keep components buildable from cubes, cylinders, cones, spheres, and simple materials.
- Components should be actual requested objects or scene features, not only primitive names.
- Use short snake_case phrases with semantic nouns and optional hints, like examination_table_center, monitor_on_wall, chair_left, lamp_on_desk, window_back_wall.
- Every named object in the user request must appear as its own component. Relationship hints may reference other components, but cannot replace them.
- Do not pad the component list with generic primitives; two specific components are better than five vague ones.
- Do not request external assets.
- canonical_id must be lowercase snake case, start with asset_, and end with _A.

User request: {request}
""".strip()
    return prompt


def ollama_spec(args) -> dict:
    scene_trace = ollama_generate(args, scene_plan_prompt(args.request))
    scene_plan = scene_trace["parsed_response"]
    named_objects = named_object_candidates(args.request)

    repair_trace = None
    repaired_scene_plan = scene_plan
    try:
        repair_trace = ollama_generate(args, repair_scene_plan_prompt(args.request, scene_plan, named_objects))
        repaired_scene_plan = repair_trace["parsed_response"]
    except (urllib.error.URLError, TimeoutError, KeyError, json.JSONDecodeError):
        repair_trace = {
            "prompt": repair_scene_plan_prompt(args.request, scene_plan, named_objects),
            "raw_response": "",
            "parsed_response": scene_plan,
            "repair_failed": True,
        }

    spec = derive_spec_from_scene_plan(args.request, repaired_scene_plan)
    return {
        "scene_plan_prompt": scene_trace["prompt"],
        "scene_plan_response": scene_trace["raw_response"],
        "parsed_scene_plan": scene_plan,
        "repair_prompt": repair_trace["prompt"],
        "repair_response": repair_trace["raw_response"],
        "repaired_scene_plan": repaired_scene_plan,
        "llm_prompt": legacy_spec_prompt(args.request),
        "raw_response": scene_trace["raw_response"],
        "parsed_response": scene_plan,
        "spec": spec,
    }


def main() -> int:
    args = parse_args()
    if not args.dry_run and not args.legacy_local_intake:
        if not args.harness_url:
            print("[studio_chat] ERROR: set OEB_HARNESS_URL or pass --harness-url", file=sys.stderr)
            return 2
        if not args.admin_token:
            print("[studio_chat] ERROR: set API_ADMIN_TOKEN or pass --admin-token", file=sys.stderr)
            return 2

        try:
            result = post_json(
                f"{args.harness_url.rstrip('/')}/api/v1/studio-chat",
                {"prompt": args.request},
                token=args.admin_token,
                timeout=240,
            )
        except urllib.error.HTTPError as exc:
            print(f"[studio_chat] ERROR: harness rejected studio chat ({exc.code}): {exc.read().decode()}", file=sys.stderr)
            return 3
        except urllib.error.URLError as exc:
            print(f"[studio_chat] ERROR: could not reach studio chat at {args.harness_url}: {exc}", file=sys.stderr)
            return 3

        print(json.dumps({
            "job_id": result["job_id"],
            "status": result["status"],
            "review_url": result["review_url"],
            "trace_url": result["trace_url"],
            "canonical_id": result["canonical_id"],
            "saved_llm_response": result["saved_llm_response"],
        }, indent=2))
        return 0

    if not args.dry_run:
        if not args.harness_url:
            print("[studio_chat] ERROR: set OEB_HARNESS_URL or pass --harness-url", file=sys.stderr)
            return 2
        if not args.admin_token:
            print("[studio_chat] ERROR: set API_ADMIN_TOKEN or pass --admin-token", file=sys.stderr)
            return 2

        try:
            accepted = post_json(
                f"{args.harness_url.rstrip('/')}/api/v1/conversations/accept",
                {"creative_request": args.request},
                token=args.admin_token,
                timeout=10,
            )
            print(
                f"[studio_chat] 200 OK harness accepted prompt at {accepted['accepted_at']}",
                file=sys.stderr,
                flush=True,
            )
        except urllib.error.HTTPError as exc:
            print(f"[studio_chat] ERROR: harness rejected prompt ({exc.code}): {exc.read().decode()}", file=sys.stderr)
            return 3
        except urllib.error.URLError as exc:
            print(f"[studio_chat] ERROR: could not reach harness at {args.harness_url}: {exc}", file=sys.stderr)
            return 3

    try:
        llm_trace = ollama_spec(args)
    except (urllib.error.URLError, TimeoutError) as exc:
        print(f"[studio_chat] ERROR: could not reach Ollama at {args.ollama_url}: {exc}", file=sys.stderr)
        return 2
    except (KeyError, json.JSONDecodeError) as exc:
        print(f"[studio_chat] ERROR: Ollama did not return valid build JSON: {exc}", file=sys.stderr)
        return 2

    if args.dry_run:
        print(json.dumps({
            "creative_request": args.request,
            "scene_plan_prompt": llm_trace["scene_plan_prompt"],
            "scene_plan_response": llm_trace["scene_plan_response"],
            "parsed_scene_plan": llm_trace["parsed_scene_plan"],
            "repair_prompt": llm_trace["repair_prompt"],
            "repair_response": llm_trace["repair_response"],
            "repaired_scene_plan": llm_trace["repaired_scene_plan"],
            "llm_prompt": llm_trace["llm_prompt"],
            "llm_response": llm_trace["raw_response"],
            "parsed_llm_response": llm_trace["parsed_response"],
            "spec": llm_trace["spec"],
        }, indent=2))
        return 0

    try:
        result = post_json(
            f"{args.harness_url.rstrip('/')}/api/v1/conversations/jobs",
            {
                "creative_request": args.request,
                "llm_response": llm_trace["raw_response"],
                "llm_prompt": llm_trace["llm_prompt"],
                "scene_plan_prompt": llm_trace["scene_plan_prompt"],
                "scene_plan_response": llm_trace["scene_plan_response"],
                "repair_prompt": llm_trace["repair_prompt"],
                "repair_response": llm_trace["repair_response"],
                "scene_plan": llm_trace["parsed_scene_plan"],
                "repaired_scene_plan": llm_trace["repaired_scene_plan"],
                "spec": llm_trace["spec"],
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
        "saved_llm_response": result["job"].get("llm_response") is not None,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
