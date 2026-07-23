import json
import re
from typing import Any
import urllib.request

from app.schemas.conversation import PrimitiveBuildSpec, ScenePlan
from app.schemas.studio_chat import (
    StudioChatMessage,
    StudioChatOllamaRequest,
    StudioChatOllamaResponse,
    StudioChatPreset,
)


GENERAL_LOCAL_CHAT_PROMPT = """You are the local OEB studio chat assistant.
Answer directly and plainly. Do not claim to have submitted jobs, edited files,
created assets, or run tools. When production work is requested, explain the
smallest next buildable step or ask one concise clarifying question."""

ASSET_BUILDER_TRANSLATOR_PROMPT = """You are the OEB local asset-builder translator.
Translate approved creative asset requests into strict JSON specs for later
deterministic workers. The local coordinate frame is +X front, -X rear/back,
-Y left, +Y right, +Z up, -Z down. Emit small buildable primitive jobs. Ask a
clarifying question when the request is vague. Escalate ambiguous art direction,
reference interpretation, or visual judgment. Do not write Blender code, submit
jobs, invent unavailable assets, or add scene shells for standalone assets.
When review renders are requested and no custom view list is supplied, use
review_views: ["top", "bottom", "left", "right", "front", "rear", "action"].
Use all seven views exactly, including "action". Missing "action" is invalid.
Use semantic view names only; do not invent axis/side pairs.
Return only JSON with: action, confidence, clarification_question,
escalation_reason, build_job."""

ASSET_EDIT_TRANSLATOR_PROMPT = """You are the OEB local asset-edit translator.
Translate conversational edits into strict JSON deltas against named assets and
parts. Use +X front, -X rear/back, -Y left, +Y right, +Z up, -Z down. Prefer
target_part, operation, semantic_direction, axis, amount, units, material_delta,
requested_review_views, and escalation_reason. Ask one clarifying question if
the target part, direction, or amount is unclear. Do not mutate files or submit
worker jobs. For standard review renders, use requested_review_views:
["top", "bottom", "left", "right", "front", "rear", "action"]. Use all seven
views exactly, including "action". Return only JSON."""

SCENE_PLAN_EXTRACTOR_PROMPT = """You are the OEB local scene-plan extractor.
Convert creative scene or location requests into strict JSON scene plans with
objects, structured shape/material/style details, source phrases, and spatial
relationships. Preserve every meaningful modifier. Use OEB directions:
+X front, -X rear/back, -Y left, +Y right, +Z up, -Z down. Prefer small
buildable primitive scenes and ask for clarification when relationships or
required objects are unclear. For asset review renders, use review_views:
["top", "bottom", "left", "right", "front", "rear", "action"]. Use all seven
views exactly, including "action". Return only JSON."""

HARNESS_DEBUG_HELPER_PROMPT = """You are the OEB harness-debug helper.
Help inspect local harness, Ollama, worker, artifact, and review-page behavior.
Be precise about likely failure boundaries. Do not imply that you can run shell
commands or mutate the harness from this chat. When more evidence is needed,
name the exact endpoint, log, setting, or job identifier to check next."""


STUDIO_CHAT_PRESETS = [
    StudioChatPreset(
        id="general_local_chat",
        label="General Local Chat",
        description="Direct local-model chat with no production side effects.",
        system_prompt=GENERAL_LOCAL_CHAT_PROMPT,
        temperature=0.4,
        max_tokens=2048,
    ),
    StudioChatPreset(
        id="asset_builder_translator",
        label="Asset Builder",
        description="Translate creative asset requests into constrained primitive-builder specs.",
        system_prompt=ASSET_BUILDER_TRANSLATOR_PROMPT,
        temperature=0.2,
        max_tokens=2048,
    ),
    StudioChatPreset(
        id="asset_edit_translator",
        label="Asset Edit",
        description="Translate follow-up asset edits into constrained deltas.",
        system_prompt=ASSET_EDIT_TRANSLATOR_PROMPT,
        temperature=0.2,
        max_tokens=2048,
    ),
    StudioChatPreset(
        id="scene_plan_extractor",
        label="Scene Plan",
        description="Extract structured primitive scene plans from creative requests.",
        system_prompt=SCENE_PLAN_EXTRACTOR_PROMPT,
        temperature=0.2,
        max_tokens=3072,
    ),
    StudioChatPreset(
        id="harness_debug_helper",
        label="Harness Debug",
        description="Reason about local harness and worker issues without side effects.",
        system_prompt=HARNESS_DEBUG_HELPER_PROMPT,
        temperature=0.1,
        max_tokens=2048,
    ),
]

FIGHTER_COMPONENTS = [
    "wedge nose",
    "compact dark cockpit",
    "low main hull",
    "two swept wings",
    "two large rear engines",
    "crooked tail fin",
    "asymmetric greebles",
]
AIRCRAFT_COMPONENTS = [
    "long aircraft fuselage",
    "front nose cone",
    "left wing",
    "right wing",
    "tail fin",
    "rear engine",
]
TWO_WHEELED_VEHICLE_COMPONENTS = [
    "front wheel",
    "rear wheel",
    "low vehicle frame",
    "engine block",
    "single saddle seat",
    "handlebars",
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


class StudioChatLLMConfig:
    def __init__(self, ollama_url: str, model: str):
        self.ollama_url = ollama_url
        self.model = model


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


def get_json(url: str, timeout: int = 10) -> dict:
    req = urllib.request.Request(url, headers={"Accept": "application/json"}, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def studio_chat_presets() -> list[StudioChatPreset]:
    return STUDIO_CHAT_PRESETS


def list_ollama_models(ollama_url: str, timeout: int = 10) -> list[str]:
    payload = get_json(f"{ollama_url.rstrip('/')}/api/tags", timeout=timeout)
    return sorted(
        model["name"]
        for model in payload.get("models", [])
        if isinstance(model, dict) and isinstance(model.get("name"), str)
    )


def ollama_chat_payload(body: StudioChatOllamaRequest) -> dict[str, Any]:
    messages: list[StudioChatMessage] = []
    system_prompt = body.system_prompt.strip()
    if body.review_views:
        review_views_json = json.dumps(body.review_views)
        system_prompt = "\n\n".join([
            system_prompt,
            (
                "OEB review-view shortcut is active. When the user asks for review "
                f"renders, standard review renders, or the preferred view set, emit "
                f'exactly "review_views": {review_views_json}. Use semantic view '
                "names only. Include every listed view; omitting any listed view, "
                'especially "action", is invalid. Do not emit axis/side pairs; '
                "deterministic harness renderers own camera math."
            ),
        ]).strip()
    if system_prompt:
        messages.append(StudioChatMessage(role="system", content=system_prompt))
    messages.extend(body.messages)
    return {
        "model": body.model,
        "messages": [message.model_dump() for message in messages],
        "stream": False,
        "options": {
            "temperature": body.temperature,
            "num_predict": body.max_tokens,
        },
    }


def chat_with_ollama(
    ollama_url: str,
    body: StudioChatOllamaRequest,
    timeout: int = 120,
) -> StudioChatOllamaResponse:
    payload = ollama_chat_payload(body)
    raw_response = post_json(f"{ollama_url.rstrip('/')}/api/chat", payload, timeout=timeout)
    message = raw_response.get("message")
    if not isinstance(message, dict) or not isinstance(message.get("content"), str):
        raise ValueError("Ollama response did not include message.content")
    return StudioChatOllamaResponse(
        model=str(raw_response.get("model") or body.model),
        message={"role": "assistant", "content": message["content"]},
        done=bool(raw_response.get("done")),
        raw={
            "request": payload,
            "response": raw_response,
        },
    )


def extract_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text.strip())


def text_has_any(text: str, words: tuple[str, ...]) -> bool:
    tokens = set(re.findall(r"[a-z0-9]+", text.lower()))
    return any(word in tokens for word in words)


def is_aircraft_request(text: str) -> bool:
    tokens = set(re.findall(r"[a-z0-9]+", text.lower()))
    if tokens & {"aircraft", "airplane", "aeroplane", "jet", "biplane"}:
        return True
    surface_qualifiers = {"floor", "ground", "geometric", "geometry", "flat", "math", "mathematical"}
    return "plane" in tokens and not (tokens & surface_qualifiers)


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


def infer_kind(request: str, spec: dict | None = None) -> str:
    text = request_text(request, spec)
    if (
        text_has_any(text, ("chair", "desk", "lamp", "table", "prop", "rack", "shelf", "stool", "bed"))
        and not text_has_any(text, ("office", "location", "scene", "set"))
    ):
        return "prop"
    if text_has_any(text, ("office", "park", "room", "street", "alley", "forest", "set", "location", "bay", "clinic", "medical", "lab", "garage", "hangar")):
        return "location"
    if text_has_any(text, ("chair", "desk", "lamp", "table", "prop", "rack", "shelf", "stool", "bed")):
        return "prop"
    if is_aircraft_request(request) or text_has_any(text, ("ship", "spaceship", "fighter", "vehicle", "craft", "car", "truck", "rover", "motorcycle", "motorbike", "bike")):
        return "vehicle"
    return "asset"


def default_components_for(request: str, spec: dict | None = None) -> list[str]:
    text = request_text(request, spec)
    if text_has_any(text, ("office", "desk", "chair", "lamp", "workspace")):
        return OFFICE_COMPONENTS
    if text_has_any(text, ("park", "tree", "path", "trail", "bench", "grass", "garden")):
        return PARK_COMPONENTS
    if text_has_any(text, ("station", "orbital", "habitat", "ring", "dock", "solar")):
        return STATION_COMPONENTS
    if is_aircraft_request(request):
        return AIRCRAFT_COMPONENTS
    if text_has_any(text, ("motorcycle", "motorbike", "bike")) and not text_has_any(text, ("rack", "stand")):
        return TWO_WHEELED_VEHICLE_COMPONENTS
    if infer_kind(request, spec) == "vehicle":
        return FIGHTER_COMPONENTS
    return ["primary structure", "secondary feature", "detail element"]


SLUG_SKIP_WORDS = {
    "a", "an", "the", "me", "make", "build", "create", "from", "with", "of",
    "and", "that", "looks", "look", "like", "as", "one",
}


def slug_kind_prefix(text: str, spec: dict | None = None) -> str:
    request = request_text(text, spec)
    if text_has_any(request, ("ship", "spaceship", "fighter", "craft")):
        return "ship"
    kind = infer_kind(text, spec)
    return {
        "vehicle": "vehicle",
        "location": "location",
        "prop": "prop",
        "character": "character",
        "set": "location",
    }.get(kind, "asset")


def preserved_shape_phrase(text: str) -> str:
    lowered = text.lower()
    if match := re.search(r"\bcapital\s+letter\s+([a-z0-9])\b", lowered):
        return f"capital_letter_{match.group(1)}"
    if match := re.search(r"\bletter\s+([a-z0-9])\b", lowered):
        return f"letter_{match.group(1)}"
    if match := re.search(r"\bshaped\s+like\s+(?:a|an|the)?\s*([a-z0-9]+)\b", lowered):
        shape = match.group(1)
        return f"{shape}_shaped"
    if match := re.search(r"\blooks?\s+like\s+(?:a|an|the)?\s*([a-z0-9]+)\b", lowered):
        shape = match.group(1)
        if shape not in SLUG_SKIP_WORDS:
            return f"{shape}_shaped" if len(shape) == 1 else shape
    return ""


def slugify_asset_id(text: str) -> str:
    prefix = slug_kind_prefix(text)
    shape = preserved_shape_phrase(text)
    if shape:
        return f"{prefix}_{shape}_A"

    words = re.findall(r"[a-z0-9]+", text.lower())
    prefix_object_words = {
        "ship": {"ship", "spaceship", "fighter", "craft"},
        "vehicle": {"vehicle"},
        "location": {"location", "scene", "set"},
        "prop": {"prop"},
        "character": {"character", "char"},
        "asset": {"asset"},
    }.get(prefix, set())
    useful = [
        w for w in words
        if w not in SLUG_SKIP_WORDS and w not in prefix_object_words
    ]
    stem = "_".join(useful[:4]) or "primitive_asset"
    return f"{prefix}_{stem}_A"


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


def normalize_feature(text: str) -> str:
    return normalize_id(text, "feature")


def detail_hints_for_request(request: str) -> list[dict]:
    lowered = request.lower()
    hints = []
    if re.search(r"\brounded\s+corners?\b", lowered):
        hints.append({
            "feature": "rounded_corners",
            "source_phrase": "rounded corners",
            "shape": {"corner_style": "rounded"},
        })
    if re.search(r"\bbevel(?:ed|led)?\s+edges?\b|\bsoft\s+bevel", lowered):
        hints.append({
            "feature": "beveled_edges",
            "source_phrase": "beveled edges",
            "shape": {"edge_profile": "beveled"},
        })
    if re.search(r"\bthin\s+legs?\b", lowered):
        hints.append({
            "feature": "thin_legs",
            "source_phrase": "thin legs",
            "style_detail": "thin legs",
        })
    if re.search(r"\b(tapered|curved|soft|wide|narrow|low|tall)\b", lowered):
        for word in re.findall(r"\b(tapered|curved|soft|wide|narrow|low|tall)\b", lowered):
            hints.append({
                "feature": normalize_feature(word),
                "source_phrase": word,
                "style_detail": word,
            })
    for material_word in ("wood", "wooden", "metal", "steel", "glass", "stone", "plastic"):
        if re.search(rf"\b{material_word}\b", lowered):
            hints.append({
                "feature": normalize_feature(material_word),
                "source_phrase": material_word,
                "materials": {"primary": material_word},
            })
    return hints


def object_matches_detail_target(obj: dict, request: str) -> bool:
    tokens = set(re.findall(r"[a-z0-9]+", " ".join([
        str(obj.get("id") or ""),
        str(obj.get("label") or ""),
        str(obj.get("category") or ""),
    ]).lower()))
    request_tokens = set(re.findall(r"[a-z0-9]+", request.lower()))
    if "table" in request_tokens:
        return bool(tokens & {"table", "surface", "desk", "counter", "workbench"})
    if "chair" in request_tokens or "stool" in request_tokens:
        return bool(tokens & {"chair", "stool", "seating", "seat"})
    if "ship" in request_tokens or "vehicle" in request_tokens:
        return bool(tokens & {"ship", "vehicle", "hull", "body", "fuselage"})
    return True


def list_append_unique(values: list, value: str) -> None:
    if value and value not in values:
        values.append(value)


def enrich_scene_plan_details(request: str, scene_plan: dict) -> tuple[dict, list[str]]:
    if not isinstance(scene_plan, dict):
        return scene_plan, ["scene plan is not a JSON object"]
    objects = scene_plan.get("objects")
    if not isinstance(objects, list):
        return scene_plan, ["scene plan has no objects list"]

    hints = detail_hints_for_request(request)
    warnings = []
    if not hints:
        return scene_plan, warnings

    target = None
    for obj in objects:
        if isinstance(obj, dict) and object_matches_detail_target(obj, request):
            target = obj
            break
    if target is None:
        warnings.append("detail hints found but no target object matched")
        return scene_plan, warnings

    shape = target.setdefault("shape", {})
    if not isinstance(shape, dict):
        shape = {}
        target["shape"] = shape
    required_features = target.setdefault("required_features", [])
    if not isinstance(required_features, list):
        required_features = []
        target["required_features"] = required_features
    source_phrases = target.setdefault("source_phrases", [])
    if not isinstance(source_phrases, list):
        source_phrases = []
        target["source_phrases"] = source_phrases
    style_details = target.setdefault("style_details", [])
    if not isinstance(style_details, list):
        style_details = []
        target["style_details"] = style_details
    materials = target.setdefault("materials", {})
    if not isinstance(materials, dict):
        materials = {}
        target["materials"] = materials

    for hint in hints:
        feature = hint.get("feature")
        if feature:
            list_append_unique(required_features, feature)
        source_phrase = hint.get("source_phrase")
        if source_phrase:
            list_append_unique(source_phrases, source_phrase)
        for key, value in (hint.get("shape") or {}).items():
            shape.setdefault(key, value)
        for key, value in (hint.get("materials") or {}).items():
            materials.setdefault(key, value)
        style_detail = hint.get("style_detail")
        if style_detail:
            list_append_unique(style_details, style_detail)

    return scene_plan, warnings


def scene_object_component(obj: dict) -> str:
    parts = []
    count = obj.get("count")
    size = obj.get("size")
    label = obj.get("label") or obj.get("id") or "object"
    placement = obj.get("placement")
    mounting = obj.get("mounting")
    orientation = obj.get("orientation") or {}
    shape = obj.get("shape") or {}
    materials = obj.get("materials") or {}
    required_features = obj.get("required_features") or []
    style_details = obj.get("style_details") or []
    source_phrases = obj.get("source_phrases") or []

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
    if isinstance(shape, dict):
        for key in ("primary_form", "corner_style", "edge_profile", "profile", "silhouette"):
            if shape.get(key):
                parts.append(str(shape[key]))
    if isinstance(required_features, list):
        parts.extend(str(feature) for feature in required_features)
    if isinstance(materials, dict):
        parts.extend(str(value) for value in materials.values() if value)
    if isinstance(style_details, list):
        parts.extend(str(detail) for detail in style_details)
    if isinstance(source_phrases, list):
        parts.extend(str(phrase) for phrase in source_phrases)
    if isinstance(orientation, dict):
        faces = orientation.get("faces")
        if faces:
            parts.append(f"facing_{faces}")
    return normalize_id("_".join(parts), "component")


def normalize_spec(request: str, spec: dict) -> dict:
    canonical_id = str(spec.get("canonical_id", "")).strip()
    inferred_kind = infer_kind(request, spec)
    shape = preserved_shape_phrase(request)
    if (
        not re.fullmatch(r"[a-z]+_[a-z0-9_]+_A", canonical_id)
        or "snake_case" in canonical_id
        or canonical_id in {"ship_A", "asset_A"}
        or (canonical_id.startswith("ship_") and inferred_kind != "vehicle")
        or (canonical_id.startswith("asset_") and inferred_kind != "asset")
        or (shape and shape not in canonical_id)
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
        component_text = " ".join(component_words)
        aircraft_part_words = ("wing", "fuselage", "nose", "tail", "engine", "cockpit")
        if component_words <= generic or (
            is_aircraft_request(request) and not any(word in component_text for word in aircraft_part_words)
        ):
            spec["components"] = default_components_for(request, spec)
    return spec


def derive_spec_from_scene_plan(request: str, scene_plan: dict) -> PrimitiveBuildSpec:
    objects = scene_plan.get("objects") if isinstance(scene_plan, dict) else []
    components = []
    if isinstance(objects, list):
        for obj in objects:
            if isinstance(obj, dict):
                components.append(scene_object_component(obj))

    style = scene_plan.get("style") if isinstance(scene_plan, dict) else None
    scene_type = scene_plan.get("scene_type") if isinstance(scene_plan, dict) else None
    spec = normalize_spec(request, {
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
    return PrimitiveBuildSpec.model_validate(spec)


def scene_plan_prompt(request: str) -> str:
    return f"""
You are the production-designer intake assistant for a deterministic Blender studio harness.
Turn the user's creative request into one strict JSON asset/location graph. Do not include markdown.

Schema:
{{
  "scene_type": "short_snake_case_asset_or_location_type",
  "style": "short visual style summary",
  "objects": [
    {{
      "id": "stable_snake_case_object_id",
      "label": "human readable object name",
      "category": "seating|surface|storage|screen|lighting|bed|medical|plant|path|wall_item|machine|structure|vehicle|vehicle_part|support|opening|roof|unknown",
      "count": 1,
      "size": "small|medium|large|wide|tall",
      "placement": "center|left|right|front|back|rear|side|around|top|bottom|on_surface|rear_wall|corner",
      "mounting": "self|attached|surface|support|floor|wall|ceiling",
      "shape": {{"primary_form": "short_snake_case_form", "corner_style": "sharp|rounded|beveled", "edge_profile": "sharp|soft_beveled|thin|thick"}},
      "required_features": ["snake_case_feature"],
      "source_phrases": ["exact prompt phrase"],
      "materials": {{"primary": "wood|metal|glass|stone|fabric|unknown", "finish": "short finish phrase"}},
      "style_details": ["short detail phrase"],
      "parts": [{{"id": "part_id", "category": "surface|support|vehicle_part|unknown", "count": 1, "shape": {{}}}}],
      "orientation": {{"faces": "target_object_id"}}
    }}
  ],
  "relationships": [
    {{"subject": "object_id", "relation": "faces|left_of|right_of|behind|in_front_of|near|on_top_of|mounted_on|inside|around|aligned_with", "target": "object_id_or_scene_feature"}}
  ]
}}

Rules:
- Every named object in the user request must appear as its own object.
- Preserve quantities, sizes, attachment/mounting, placement, and orientation.
- Preserve meaningful modifiers as structured fields, not only in labels. Use shape, required_features, source_phrases, materials, style_details, and parts.
- If the prompt says "rounded corners", include shape.corner_style="rounded", required_features containing "rounded_corners", and source_phrases containing "rounded corners" on the relevant object.
- Relationship records may reference objects, but cannot replace object records.
- Use the OEB orientation standard for every asset and location: +X is front, -X is rear/back, -Y is left, +Y is right, +Z is up, and -Z is down.
- For standalone assets such as spaceships, vehicles, chairs, stools, beds, props, and characters, describe only the asset and its parts. Do not add a floor, wall, room, base plane, environment, or scene shell unless the user explicitly asks for a location or set.
- For standalone assets, use mounting values such as self, attached, surface, or support. Reserve floor, wall, and ceiling for actual locations, rooms, buildings, or environmental sets.
- Treat plain "plane" as an aircraft unless the request explicitly says geometric plane, floor plane, or ground plane.
- Use primitive-friendly categories. Do not request external assets.
- Use stable snake_case ids.
- Output only valid JSON.

User request: {request}
""".strip()


def repair_scene_plan_prompt(request: str, scene_plan: dict, named_objects: list[str]) -> str:
    return f"""
You are repairing an asset/location graph for a deterministic Blender studio harness.
Compare the original creative request to the parsed graph and return one corrected JSON graph. Do not include markdown.

Repair rules:
- Every named object from the request must be represented in objects.
- Preserve quantities such as two chairs or 3 trees.
- Preserve size hints like large, small, wide, tall.
- Preserve shape and style modifiers such as rounded corners, thin legs, brushed metal, tapered, curved, soft, and wide.
- Move modifiers out of labels into structured fields: shape, required_features, source_phrases, materials, style_details, and parts.
- If the request contains rounded corners, the repaired object must include shape.corner_style="rounded", required_features containing "rounded_corners", and source_phrases containing "rounded corners".
- Preserve attachment/mounting and placement hints like attached, on surface, rear wall, corner, on desk, background.
- Preserve relationships like facing, next to, left of, right of, mounted on.
- Use the OEB orientation standard for every repaired object: +X is front, -X is rear/back, -Y is left, +Y is right, +Z is up, and -Z is down.
- For standalone assets such as spaceships, vehicles, chairs, stools, beds, props, and characters, keep only the asset and its parts. Remove floors, walls, rooms, base planes, environment props, and scene shells unless the original request explicitly asks for a location or set.
- For standalone assets, prefer mounting values such as self, attached, surface, or support. Reserve floor, wall, and ceiling for actual locations, rooms, buildings, or environmental sets.
- Keep object ids stable when they are already good.
- Output only valid JSON in the same schema.

Original creative request: {request}

Possible named object hints from request: {json.dumps(named_objects)}

Current scene plan:
{json.dumps(scene_plan, indent=2)}
""".strip()


def legacy_spec_prompt(request: str) -> str:
    return f"""
You are the production-designer intake assistant for a deterministic Blender studio harness.
Turn the user's request into one strict JSON object. Do not include markdown.

User request: {request}
""".strip()


def ollama_generate(config: StudioChatLLMConfig, prompt: str) -> dict:
    payload = {
        "model": config.model,
        "prompt": prompt,
        "stream": False,
        "format": "json",
    }
    result = post_json(f"{config.ollama_url.rstrip('/')}/api/generate", payload, timeout=360)
    raw_response = result["response"]
    return {
        "prompt": prompt,
        "raw_response": raw_response,
        "parsed_response": extract_json(raw_response),
    }


def build_studio_chat_trace(request: str, config: StudioChatLLMConfig) -> dict:
    scene_trace = ollama_generate(config, scene_plan_prompt(request))
    scene_plan = scene_trace["parsed_response"]
    named_objects = named_object_candidates(request)

    repair_trace = None
    repaired_scene_plan = scene_plan
    try:
        repair_trace = ollama_generate(config, repair_scene_plan_prompt(request, scene_plan, named_objects))
        repaired_scene_plan = repair_trace["parsed_response"]
    except Exception:
        repair_trace = {
            "prompt": repair_scene_plan_prompt(request, scene_plan, named_objects),
            "raw_response": "",
            "parsed_response": scene_plan,
            "repair_failed": True,
        }

    repaired_scene_plan, detail_warnings = enrich_scene_plan_details(request, repaired_scene_plan)
    spec = derive_spec_from_scene_plan(request, repaired_scene_plan)
    return {
        "scene_plan_prompt": scene_trace["prompt"],
        "scene_plan_response": scene_trace["raw_response"],
        "parsed_scene_plan": ScenePlan.model_validate(scene_plan),
        "repair_prompt": repair_trace["prompt"],
        "repair_response": repair_trace["raw_response"],
        "repaired_scene_plan": ScenePlan.model_validate(repaired_scene_plan),
        "detail_validation_warnings": detail_warnings,
        "llm_prompt": legacy_spec_prompt(request),
        "raw_response": scene_trace["raw_response"],
        "parsed_response": scene_plan,
        "spec": spec,
    }
