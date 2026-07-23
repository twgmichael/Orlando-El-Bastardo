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
jobs, invent unavailable assets, or add scene shells for standalone assets. Cone
tips point +Z by default; "pointing down" is rotation [3.141592654, 0, 0].
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

PRIMITIVE_SHAPE_RESOLVER_PROMPT = """You are the OEB primitive shape resolver.
Convert the user's creative request and assistant draft JSON into a strict
PrimitiveRegistry v0.1 build spec. Use only registry primitive types, material
names, transforms, and numeric params. Cone tips point +Z by default; "pointing
down" is rotation [3.141592654, 0, 0]. Do not write Blender code or invent APIs.
When a request is vague, set needs_clarification true with one short question.
When art direction is ambiguous, set escalation_reason. Return only JSON with:
version, needs_clarification, clarification_question, escalation_reason,
asset_kind, canonical_id, name, primitives."""


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
    StudioChatPreset(
        id="primitive_shape_resolver",
        label="Primitive Resolver",
        description="Resolve creative requests into PrimitiveRegistry v0.1 specs.",
        system_prompt=PRIMITIVE_SHAPE_RESOLVER_PROMPT,
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


PRIMITIVE_REGISTRY_V01 = {
    "version": "0.1",
    "primitive_types": {
        "box": {
            "aliases": ["cube", "block", "rectangular_prism"],
            "params": {},
        },
        "sphere": {
            "aliases": ["ball", "orb"],
            "params": {"radius": {"min": 0.01, "max": 20.0, "default": 0.5}},
        },
        "cylinder": {
            "aliases": ["tube", "post", "column"],
            "params": {
                "radius": {"min": 0.01, "max": 20.0, "default": 0.35},
                "depth": {"min": 0.01, "max": 40.0, "default": 1.0},
                "vertices": {"min": 3, "max": 128, "default": 32},
            },
        },
        "cone": {
            "aliases": ["traffic_cone", "spike"],
            "params": {
                "radius": {"min": 0.01, "max": 20.0, "default": 0.4},
                "depth": {"min": 0.01, "max": 40.0, "default": 1.0},
                "vertices": {"min": 3, "max": 128, "default": 32},
            },
        },
        "torus": {
            "aliases": ["ring", "donut"],
            "params": {
                "major_radius": {"min": 0.01, "max": 20.0, "default": 0.45},
                "minor_radius": {"min": 0.005, "max": 5.0, "default": 0.08},
            },
        },
        "plane": {
            "aliases": ["flat_plane", "ground_plane", "surface"],
            "params": {},
        },
        "wedge": {
            "aliases": ["ramp", "triangular_prism"],
            "params": {},
        },
    },
    "materials": [
        "neutral",
        "blue",
        "red",
        "green",
        "yellow",
        "orange",
        "purple",
        "black",
        "white",
        "gray",
        "metal",
        "wood",
        "glass",
    ],
    "transform": {
        "location": {"length": 3, "min": -50.0, "max": 50.0},
        "rotation": {"length": 3, "min": -6.283185307, "max": 6.283185307},
        "scale": {"length": 3, "min": 0.01, "max": 20.0},
    },
}
PRIMITIVE_ALIASES = {
    alias: primitive_type
    for primitive_type, config in PRIMITIVE_REGISTRY_V01["primitive_types"].items()
    for alias in [primitive_type, *config.get("aliases", [])]
}
PRIMITIVE_TYPES = set(PRIMITIVE_ALIASES)
CANONICAL_PRIMITIVE_TYPES = set(PRIMITIVE_REGISTRY_V01["primitive_types"])
DIRECTIONAL_PRIMITIVE_TYPES = {"cone"}
PRIMITIVE_DIRECTION_ROTATIONS = {
    "up": [0.0, 0.0, 0.0],
    "down": [3.141592654, 0.0, 0.0],
    "front": [0.0, 1.570796327, 0.0],
    "rear": [0.0, -1.570796327, 0.0],
    "back": [0.0, -1.570796327, 0.0],
    "left": [1.570796327, 0.0, 0.0],
    "right": [-1.570796327, 0.0, 0.0],
}
MATERIAL_COLOR_WORDS = {
    "blue",
    "red",
    "green",
    "yellow",
    "orange",
    "purple",
    "black",
    "white",
    "gray",
    "grey",
    "metal",
    "metallic",
    "wood",
    "glass",
}


def _balanced_json_object(text: str) -> str | None:
    start = text.find("{")
    if start == -1:
        return None

    depth = 0
    in_string = False
    escaped = False
    for index, char in enumerate(text[start:], start=start):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return None


def parse_assistant_json(text: str) -> dict[str, Any]:
    try:
        parsed = extract_json(text)
    except json.JSONDecodeError as exc:
        balanced = _balanced_json_object(text)
        if not balanced:
            raise ValueError(f"assistant response is not valid JSON: {exc}") from exc
        try:
            parsed = json.loads(balanced)
        except json.JSONDecodeError:
            raise ValueError(f"assistant response is not valid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ValueError("assistant response JSON must be an object")
    return parsed


def _first_text_value(*values: Any, fallback: str = "") -> str:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return fallback


def primitive_registry() -> dict[str, Any]:
    return json.loads(json.dumps(PRIMITIVE_REGISTRY_V01))


def canonical_primitive_type(value: Any) -> str | None:
    key = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    return PRIMITIVE_ALIASES.get(key)


def _coerce_float(value: Any, field: str, min_value: float, max_value: float) -> float:
    try:
        coerced = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be numeric") from exc
    if coerced < min_value or coerced > max_value:
        raise ValueError(f"{field} must be between {min_value} and {max_value}")
    return coerced


def _coerce_int(value: Any, field: str, min_value: int, max_value: int) -> int:
    try:
        coerced = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be an integer") from exc
    if coerced < min_value or coerced > max_value:
        raise ValueError(f"{field} must be between {min_value} and {max_value}")
    return coerced


def _coerce_vec3(value: Any, field: str, default: list[float], min_value: float, max_value: float) -> list[float]:
    if value is None:
        return default.copy()
    if not isinstance(value, list) or len(value) != 3:
        raise ValueError(f"{field} must be a 3-number array")
    return [_coerce_float(item, f"{field}[{idx}]", min_value, max_value) for idx, item in enumerate(value)]


def _safe_id(value: Any, fallback: str) -> str:
    raw = str(value or fallback).strip().lower()
    safe = re.sub(r"[^a-z0-9_]+", "_", raw).strip("_")
    if not safe or not re.match(r"^[a-z][a-z0-9_]{0,63}$", safe):
        safe = fallback
    return safe[:64]


def _normalize_material(value: Any) -> str:
    material = _material_color_from_text(str(value or "")) or str(value or "").strip().lower()
    if material == "grey":
        material = "gray"
    if material == "metallic":
        material = "metal"
    if material in PRIMITIVE_REGISTRY_V01["materials"]:
        return material
    raise ValueError(f"material must be one of: {', '.join(PRIMITIVE_REGISTRY_V01['materials'])}")


def _normalize_primitive_params(primitive_type: str, params: Any) -> dict[str, Any]:
    if params is None:
        params = {}
    if not isinstance(params, dict):
        raise ValueError("primitive params must be an object")
    normalized: dict[str, Any] = {}
    allowed = PRIMITIVE_REGISTRY_V01["primitive_types"][primitive_type].get("params", {})
    for key, bounds in allowed.items():
        if key not in params:
            continue
        if key == "vertices":
            normalized[key] = _coerce_int(params[key], f"params.{key}", int(bounds["min"]), int(bounds["max"]))
        else:
            normalized[key] = _coerce_float(params[key], f"params.{key}", float(bounds["min"]), float(bounds["max"]))
    unknown = sorted(set(params) - set(allowed))
    if unknown:
        raise ValueError(f"unsupported params for {primitive_type}: {', '.join(unknown)}")
    return normalized


def _orientation_direction_near_primitive(text: str, primitive_type: str, ordinal: int = 0) -> str | None:
    aliases = [
        alias
        for alias, canonical_type in PRIMITIVE_ALIASES.items()
        if canonical_type == primitive_type
    ]
    alias_pattern = "|".join(re.escape(alias).replace("_", r"[\s_-]+") for alias in sorted(aliases, key=len, reverse=True))
    if not alias_pattern:
        return None
    mentions = list(re.finditer(rf"\b(?:{alias_pattern})s?\b", text.lower()))
    if not mentions:
        return None
    mention = mentions[min(ordinal, len(mentions) - 1)]
    nearby = text.lower()[max(0, mention.start() - 80): mention.end() + 120]
    if re.search(r"\b(pointing|facing|oriented|orient|tip|apex)\s+(?:straight\s+)?down\b", nearby):
        return "down"
    if re.search(r"\b(pointing|facing|oriented|orient|tip|apex)\s+(?:straight\s+)?up\b", nearby):
        return "up"
    if re.search(r"\b(pointing|facing|oriented|orient)\s+(?:toward\s+)?(?:the\s+)?front\b", nearby):
        return "front"
    if re.search(r"\b(pointing|facing|oriented|orient)\s+(?:toward\s+)?(?:the\s+)?(?:rear|back)\b", nearby):
        return "back"
    if re.search(r"\b(pointing|facing|oriented|orient)\s+(?:toward\s+)?(?:the\s+)?left\b", nearby):
        return "left"
    if re.search(r"\b(pointing|facing|oriented|orient)\s+(?:toward\s+)?(?:the\s+)?right\b", nearby):
        return "right"
    return None


def _apply_explicit_orientation_hints(primitives: list[dict[str, Any]], creative_request: str) -> list[dict[str, Any]]:
    type_counts: dict[str, int] = {}
    for primitive in primitives:
        primitive_type = primitive["type"]
        ordinal = type_counts.get(primitive_type, 0)
        type_counts[primitive_type] = ordinal + 1
        if primitive_type not in DIRECTIONAL_PRIMITIVE_TYPES:
            continue
        direction = _orientation_direction_near_primitive(creative_request, primitive_type, ordinal)
        if direction is None:
            continue
        primitive["transform"] = {
            **primitive["transform"],
            "rotation": PRIMITIVE_DIRECTION_ROTATIONS[direction].copy(),
        }
        primitive["orientation"] = {
            "source": "creative_request",
            "direction": "rear" if direction == "back" else direction,
            "applied_rotation": primitive["transform"]["rotation"],
        }
    return primitives


def validate_primitive_spec(payload: dict[str, Any], creative_request: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("primitive resolver output must be an object")
    primitives = payload.get("primitives")
    if not isinstance(primitives, list) or not primitives:
        raise ValueError("primitive resolver output must include non-empty primitives")

    normalized_primitives: list[dict[str, Any]] = []
    for idx, primitive in enumerate(primitives):
        if not isinstance(primitive, dict):
            raise ValueError(f"primitives[{idx}] must be an object")
        primitive_type = canonical_primitive_type(primitive.get("type"))
        if not primitive_type:
            allowed = ", ".join(sorted(CANONICAL_PRIMITIVE_TYPES))
            raise ValueError(f"primitives[{idx}].type must be one of: {allowed}")
        transform = primitive.get("transform") if isinstance(primitive.get("transform"), dict) else {}
        normalized_primitives.append({
            "id": _safe_id(primitive.get("id"), f"{primitive_type}_{idx + 1}"),
            "type": primitive_type,
            "label": str(primitive.get("label")).strip() if primitive.get("label") else None,
            "material": _normalize_material(primitive.get("material") or "neutral"),
            "transform": {
                "location": _coerce_vec3(transform.get("location"), "transform.location", [0.0, 0.0, 0.5], -50.0, 50.0),
                "rotation": _coerce_vec3(transform.get("rotation"), "transform.rotation", [0.0, 0.0, 0.0], -6.283185307, 6.283185307),
                "scale": _coerce_vec3(transform.get("scale"), "transform.scale", [1.0, 1.0, 1.0], 0.01, 20.0),
            },
            "params": _normalize_primitive_params(primitive_type, primitive.get("params")),
        })

    normalized_primitives = _apply_explicit_orientation_hints(normalized_primitives, creative_request)

    primary_type = normalized_primitives[0]["type"]
    primary_material = normalized_primitives[0]["material"]
    material_slug = "" if primary_material == "neutral" else f"_{primary_material}"
    default_id = f"prop_{primary_type}{material_slug}_A"
    canonical_id = _safe_id(payload.get("canonical_id"), default_id)
    name = _first_text_value(
        payload.get("name"),
        fallback=f"{primary_material.title()} {primary_type.title()}" if material_slug else f"{primary_type.title()} Primitive",
    )
    asset_kind = _first_text_value(payload.get("asset_kind"), payload.get("kind"), fallback="prop")
    if asset_kind not in {"asset", "prop", "vehicle", "location", "set", "character"}:
        raise ValueError("asset_kind must be asset, prop, vehicle, location, set, or character")

    return {
        "version": "0.1",
        "needs_clarification": bool(payload.get("needs_clarification", False)),
        "clarification_question": payload.get("clarification_question"),
        "escalation_reason": payload.get("escalation_reason"),
        "asset_kind": asset_kind,
        "canonical_id": canonical_id,
        "name": name,
        "style": _first_text_value(payload.get("style"), fallback=creative_request),
        "primitives": normalized_primitives,
    }


def _primitive_payload_from_parsed(parsed: dict[str, Any], creative_request: str) -> dict[str, Any] | None:
    build_job = parsed.get("build_job") if isinstance(parsed.get("build_job"), dict) else {}
    source = build_job.get("spec") if isinstance(build_job.get("spec"), dict) else build_job
    if isinstance(source, dict) and isinstance(source.get("primitives"), list):
        return {
            "asset_kind": source.get("asset_kind") or source.get("kind") or build_job.get("asset_kind") or parsed.get("asset_kind") or "prop",
            "canonical_id": source.get("canonical_id") or build_job.get("canonical_id") or parsed.get("canonical_id"),
            "name": source.get("name") or build_job.get("name") or parsed.get("name"),
            "style": source.get("style") or build_job.get("style") or parsed.get("style") or creative_request,
            "primitives": source["primitives"],
        }
    primitive_type = _primitive_type_from_payload(parsed)
    if not primitive_type:
        return None
    material = _material_color_from_payload(parsed) or _material_color_from_text(creative_request) or "neutral"
    canonical_type = canonical_primitive_type(primitive_type) or primitive_type
    return {
        "asset_kind": build_job.get("asset_kind") or build_job.get("kind") or parsed.get("kind") or "prop",
        "canonical_id": build_job.get("canonical_id") or parsed.get("canonical_id"),
        "name": build_job.get("name") or parsed.get("name"),
        "style": build_job.get("style") or parsed.get("style") or creative_request,
        "primitives": [
            {
                "id": canonical_type,
                "type": canonical_type,
                "label": f"{material} {canonical_type}" if material != "neutral" else canonical_type,
                "material": material,
                "transform": {"location": [0, 0, 0.5], "rotation": [0, 0, 0], "scale": [1, 1, 1]},
                "params": {},
            }
        ],
    }


def _primitive_type_from_payload(payload: dict[str, Any]) -> str | None:
    action = str(payload.get("action") or "").lower()
    build_job = payload.get("build_job") if isinstance(payload.get("build_job"), dict) else {}
    candidates = [
        build_job.get("type"),
        build_job.get("primitive"),
        payload.get("type"),
        payload.get("primitive"),
    ]
    if "sphere" in action:
        candidates.append("sphere")
    for candidate in candidates:
        value = canonical_primitive_type(candidate)
        if value:
            return value
    return None


def _material_color_from_payload(payload: dict[str, Any]) -> str | None:
    build_job = payload.get("build_job") if isinstance(payload.get("build_job"), dict) else {}
    spec = build_job.get("spec") if isinstance(build_job.get("spec"), dict) else {}
    candidates = [
        build_job.get("material"),
        build_job.get("color"),
        payload.get("material"),
        payload.get("color"),
    ]
    for source in (build_job, spec, payload):
        materials = source.get("materials") if isinstance(source, dict) else None
        if isinstance(materials, dict):
            candidates.extend(materials.values())
        style_details = source.get("style_details") if isinstance(source, dict) else None
        if isinstance(style_details, list):
            candidates.extend(style_details)
    for candidate in candidates:
        color = _material_color_from_text(str(candidate or ""))
        if color:
            return color
    return None


def _material_color_from_text(text: str) -> str | None:
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    for token in tokens:
        if token in MATERIAL_COLOR_WORDS:
            if token == "grey":
                return "gray"
            if token == "metallic":
                return "metal"
            return token
    return None


def _primitive_mentions_from_text(text: str) -> list[dict[str, Any]]:
    words = list(re.finditer(r"[a-z0-9]+", text.lower()))
    mentions: list[dict[str, Any]] = []
    for idx, match in enumerate(words):
        token = match.group(0)
        primitive_type = canonical_primitive_type(token)
        if not primitive_type and token.endswith("s"):
            primitive_type = canonical_primitive_type(token[:-1])
        if not primitive_type:
            continue
        color = None
        for prev in reversed(words[max(0, idx - 4):idx]):
            prev_token = prev.group(0)
            if prev_token in MATERIAL_COLOR_WORDS:
                color = "gray" if prev_token == "grey" else "metal" if prev_token == "metallic" else prev_token
                break
        mentions.append({
            "type": primitive_type,
            "color": color or "neutral",
            "direction": _orientation_direction_near_primitive(text, primitive_type, len([
                mention for mention in mentions if mention["type"] == primitive_type
            ])),
            "start": match.start(),
        })
    return mentions


def _primitive_type_from_text(text: str) -> str | None:
    mentions = _primitive_mentions_from_text(text)
    if mentions:
        return mentions[0]["type"]
    return None


def _primitive_type_from_messages(messages: list[StudioChatMessage] | None) -> str | None:
    if not messages:
        return None
    for message in reversed(messages):
        primitive_type = _primitive_type_from_text(message.content)
        if primitive_type:
            return primitive_type
        match = re.search(r"\bprop_(sphere|cube|box|cylinder|cone|torus|plane|wedge)\b", message.content.lower())
        if match:
            return canonical_primitive_type(match.group(1))
    return None


def _fallback_payload_from_intent(
    creative_request: str,
    messages: list[StudioChatMessage] | None,
    reason: str,
) -> dict[str, Any]:
    primitive_mentions = _primitive_mentions_from_text(creative_request)
    unique_mentions = []
    seen_keys = set()
    for mention in primitive_mentions:
        key = (mention["type"], mention["color"])
        if key not in seen_keys:
            unique_mentions.append(mention)
            seen_keys.add(key)
    if len(unique_mentions) > 1:
        stacked = text_has_any(creative_request, ("top", "above", "stack", "stacked", "vertical"))
        primitives = []
        current_top = 0.0
        for idx, mention in enumerate(unique_mentions):
            primitive_type = mention["type"]
            material_color = mention["color"]
            radius = 0.5 if primitive_type == "sphere" else None
            depth = 1.0
            if stacked:
                if primitive_type == "sphere":
                    z = current_top + radius
                    current_top = z + radius
                else:
                    z = current_top + (depth / 2)
                    current_top = z + (depth / 2)
            else:
                z = 0.5
            primitive: dict[str, Any] = {
                "id": f"{primitive_type}_{idx + 1}",
                "type": primitive_type,
                "label": f"{material_color} {primitive_type}" if material_color != "neutral" else primitive_type,
                "material": material_color,
                "transform": {"location": [0.0, 0.0, z], "rotation": [0.0, 0.0, 0.0], "scale": [1.0, 1.0, 1.0]},
                "params": {},
            }
            if primitive_type == "sphere":
                primitive["params"]["radius"] = radius
            if primitive_type in {"cone", "cylinder"}:
                primitive["params"]["depth"] = depth
            primitives.append(primitive)

        primary = unique_mentions[0]
        color_slug = f"_{primary['color']}" if primary["color"] != "neutral" else ""
        return {
            "action": "fallback_intent",
            "confidence": 65,
            "clarification_question": None,
            "escalation_reason": None,
            "fallback_reason": reason,
            "build_job": {
                "asset_kind": "prop",
                "canonical_id": f"prop_{primary['type']}{color_slug}_compound_A",
                "name": "Compound Primitive",
                "style": creative_request,
                "primitives": primitives,
            },
        }

    primitive_type = _primitive_type_from_text(creative_request) or _primitive_type_from_messages(messages)
    if not primitive_type:
        raise ValueError(
            "assistant response was malformed and the prompt did not identify a buildable primitive"
        )
    material_color = _material_color_from_text(creative_request)
    build_job: dict[str, Any] = {
        "type": primitive_type,
        "asset_kind": "prop",
        "canonical_id": f"prop_{primitive_type}_{material_color}_A" if material_color else f"prop_{primitive_type}_A",
        "name": f"{material_color.title()} {primitive_type.title()}" if material_color else primitive_type.title(),
    }
    if material_color:
        build_job["materials"] = {"primary": material_color}
        build_job["style_details"] = [material_color]
    return {
        "action": "fallback_intent",
        "confidence": 60,
        "clarification_question": None,
        "escalation_reason": None,
        "fallback_reason": reason,
        "build_job": build_job,
    }


def _scene_plan_for_primitive(
    primitive_type: str,
    creative_request: str,
    material_color: str | None = None,
) -> dict[str, Any]:
    label = f"{material_color} {primitive_type}" if material_color else primitive_type
    scene_object = {
        "id": primitive_type,
        "label": label,
        "category": primitive_type,
        "count": 1,
        "placement": "center",
        "shape": {"primary_form": primitive_type},
        "source_phrases": [creative_request],
    }
    if material_color:
        scene_object["materials"] = {"primary": material_color}
        scene_object["style_details"] = [material_color]
    return {
        "scene_type": f"{primitive_type}_asset",
        "style": creative_request,
        "objects": [scene_object],
        "relationships": [],
    }


def _resolver_payload(
    creative_request: str,
    assistant_response: str,
    registry: dict[str, Any],
    validation_error: str | None = None,
    previous_response: dict[str, Any] | None = None,
) -> dict[str, Any]:
    user_content = {
        "creative_request": creative_request,
        "assistant_json_or_text": assistant_response,
        "primitive_registry": registry,
    }
    if validation_error:
        user_content["validation_error"] = validation_error
    if previous_response:
        user_content["previous_response"] = previous_response
    return {
        "messages": [
            {"role": "system", "content": PRIMITIVE_SHAPE_RESOLVER_PROMPT},
            {"role": "user", "content": json.dumps(user_content, indent=2)},
        ],
        "stream": False,
        "options": {"temperature": 0.1, "num_predict": 2048},
    }


def resolve_primitive_spec(
    ollama_url: str,
    model: str,
    creative_request: str,
    assistant_json: str,
    max_retries: int = 1,
) -> dict[str, Any]:
    retries = max(0, min(int(max_retries), 2))
    registry = primitive_registry()
    attempts: list[dict[str, Any]] = []
    validation_error: str | None = None
    previous_response: dict[str, Any] | None = None

    for attempt in range(retries + 1):
        payload = _resolver_payload(
            creative_request,
            assistant_json,
            registry,
            validation_error=validation_error,
            previous_response=previous_response,
        )
        payload["model"] = model
        raw_response = post_json(f"{ollama_url.rstrip('/')}/api/chat", payload, timeout=120)
        message = raw_response.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str):
            validation_error = "resolver response did not include message.content"
            attempts.append({
                "attempt": attempt + 1,
                "request": payload,
                "error": validation_error,
                "raw": raw_response,
            })
            continue
        try:
            parsed = parse_assistant_json(content)
            resolved = validate_primitive_spec(parsed, creative_request)
            attempts.append({
                "attempt": attempt + 1,
                "request": payload,
                "raw": raw_response,
                "content": content,
                "parsed": parsed,
                "resolved": resolved,
            })
            return {
                "ok": True,
                "source": "ollama_resolver",
                "attempts": attempts,
                "resolved": resolved,
                "registry_version": registry["version"],
            }
        except ValueError as exc:
            validation_error = str(exc)
            previous_response = {"content": content}
            attempts.append({
                "attempt": attempt + 1,
                "request": payload,
                "raw": raw_response,
                "error": validation_error,
                "content": content,
            })

    return {
        "ok": False,
        "source": "ollama_resolver",
        "attempts": attempts,
        "error": validation_error or "resolver failed",
        "registry_version": registry["version"],
    }


def _spec_from_resolved_primitive(
    creative_request: str,
    resolved: dict[str, Any],
) -> PrimitiveBuildSpec:
    primitive_types = [primitive["type"] for primitive in resolved["primitives"]]
    scene_plan = {
        "scene_type": "primitive_asset",
        "style": resolved.get("style") or creative_request,
        "objects": [
            {
                "id": primitive["id"],
                "label": primitive.get("label") or primitive["type"],
                "category": primitive["type"],
                "count": 1,
                "placement": "center",
                "shape": {"primary_form": primitive["type"]},
                "materials": {"primary": primitive.get("material", "neutral")},
                "source_phrases": [creative_request],
                "orientation": primitive.get("orientation", {}),
            }
            for primitive in resolved["primitives"]
        ],
        "relationships": [],
    }
    return PrimitiveBuildSpec.model_validate({
        "canonical_id": resolved["canonical_id"],
        "name": resolved["name"],
        "kind": resolved["asset_kind"],
        "style": resolved.get("style") or creative_request,
        "creative_request": creative_request,
        "build_method": "blender_primitives",
        "primitives": resolved["primitives"],
        "components": primitive_types,
        "scene_plan": scene_plan,
        "repaired_scene_plan": scene_plan,
        "deliverables": ["glb", "preview_render", "asset_review_renders", "review_page"],
    })


def build_spec_with_primitive_resolver(
    creative_request: str,
    assistant_response: str,
    messages: list[StudioChatMessage] | None = None,
    ollama_url: str | None = None,
    model: str | None = None,
    resolver_retries: int = 1,
) -> tuple[PrimitiveBuildSpec, dict[str, Any], dict[str, Any] | None]:
    try:
        parsed = parse_assistant_json(assistant_response)
    except ValueError:
        parsed = _fallback_payload_from_intent(
            creative_request,
            messages,
            reason="assistant_json_invalid",
        )

    direct_payload = _primitive_payload_from_parsed(parsed, creative_request)
    if direct_payload:
        try:
            resolved = validate_primitive_spec(direct_payload, creative_request)
            return _spec_from_resolved_primitive(creative_request, resolved), parsed, {
                "ok": True,
                "source": "fallback_intent" if parsed.get("action") == "fallback_intent" else "assistant_json",
                "resolved": resolved,
                "registry_version": PRIMITIVE_REGISTRY_V01["version"],
            }
        except ValueError:
            pass

    resolver_output: dict[str, Any] | None = None
    if ollama_url and model:
        resolver_output = resolve_primitive_spec(
            ollama_url,
            model,
            creative_request,
            assistant_response,
            max_retries=resolver_retries,
        )
        if resolver_output.get("ok") and isinstance(resolver_output.get("resolved"), dict):
            return (
                _spec_from_resolved_primitive(creative_request, resolver_output["resolved"]),
                parsed,
                resolver_output,
            )

    spec, legacy_parsed = build_spec_from_assistant_response(creative_request, assistant_response, messages)
    if resolver_output is None:
        resolver_output = {
            "ok": False,
            "source": "legacy_fallback",
            "error": "resolver not configured",
            "registry_version": PRIMITIVE_REGISTRY_V01["version"],
        }
    return spec, legacy_parsed, resolver_output


def build_spec_from_assistant_response(
    creative_request: str,
    assistant_response: str,
    messages: list[StudioChatMessage] | None = None,
) -> tuple[PrimitiveBuildSpec, dict[str, Any]]:
    try:
        parsed = parse_assistant_json(assistant_response)
    except ValueError:
        parsed = _fallback_payload_from_intent(
            creative_request,
            messages,
            reason="assistant_json_invalid",
        )
    build_job = parsed.get("build_job") if isinstance(parsed.get("build_job"), dict) else {}
    spec_source = build_job.get("spec") if isinstance(build_job.get("spec"), dict) else None
    if spec_source is None:
        spec_source = build_job if build_job else parsed

    primitive_type = _primitive_type_from_payload(parsed)
    if primitive_type:
        material_color = _material_color_from_payload(parsed) or _material_color_from_text(creative_request)
        scene_plan = _scene_plan_for_primitive(primitive_type, creative_request, material_color)
        canonical_id = _first_text_value(
            spec_source.get("canonical_id") if isinstance(spec_source, dict) else None,
            build_job.get("canonical_id"),
            parsed.get("canonical_id"),
            fallback=f"prop_{primitive_type}_{material_color}_A" if material_color else f"prop_{primitive_type}_A",
        )
        name = _first_text_value(
            spec_source.get("name") if isinstance(spec_source, dict) else None,
            build_job.get("name"),
            parsed.get("name"),
            fallback=f"{material_color.title()} {primitive_type.title()}" if material_color else f"{primitive_type.title()} Test A",
        )
        spec_payload = {
            "canonical_id": canonical_id,
            "name": name,
            "kind": _first_text_value(
                build_job.get("asset_kind"),
                build_job.get("kind"),
                parsed.get("asset_kind"),
                parsed.get("kind"),
                fallback="prop",
            ),
            "style": _first_text_value(
                spec_source.get("style") if isinstance(spec_source, dict) else None,
                build_job.get("style"),
                parsed.get("style"),
                fallback=creative_request,
            ),
            "creative_request": creative_request,
            "build_method": "blender_primitives",
            "components": [primitive_type],
            "scene_plan": scene_plan,
            "repaired_scene_plan": scene_plan,
            "deliverables": ["glb", "preview_render", "asset_review_renders", "review_page"],
        }
        return PrimitiveBuildSpec.model_validate(spec_payload), parsed

    if not isinstance(spec_source, dict):
        raise ValueError("assistant response does not contain a build_job or spec object")
    normalized = normalize_spec(creative_request, dict(spec_source))
    return PrimitiveBuildSpec.model_validate(normalized), parsed


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
