import json
import re
from datetime import datetime, timezone
from pathlib import PurePosixPath

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_admin
from app.database import get_db
from app.models.audit import AuditEvent
from app.models.job import Job
from app.schemas.conversation import (
    ConversationAcceptRequest,
    ConversationAcceptResponse,
    ConversationJobRequest,
    ConversationJobResponse,
    ConversationProposalRequest,
    ConversationProposalResponse,
    PrimitiveBuildSpec,
)
from app.schemas.job import JobSummary

router = APIRouter(prefix="/conversations", tags=["conversations"])

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

STATION_COMPONENTS = [
    "central habitat hub",
    "large observation window",
    "outer ring modules",
    "four docking arms",
    "antenna mast",
    "solar panel arrays",
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


SLUG_SKIP_WORDS = {
    "a", "an", "the", "me", "make", "build", "create", "from", "with", "of",
    "and", "that", "looks", "look", "like", "as", "one",
}


def _preserved_shape_phrase(text: str) -> str:
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


def _slug_kind_prefix(text: str) -> str:
    if _text_has_any(text, ("ship", "spaceship", "fighter", "craft")):
        return "ship"
    return {
        "vehicle": "vehicle",
        "location": "location",
        "prop": "prop",
        "character": "character",
        "set": "location",
    }.get(_infer_kind(text), "asset")


def _slugify_asset_id(text: str) -> str:
    prefix = _slug_kind_prefix(text)
    shape = _preserved_shape_phrase(text)
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


def _text_has_any(text: str, words: tuple[str, ...]) -> bool:
    tokens = set(re.findall(r"[a-z0-9]+", text.lower()))
    return any(word in tokens for word in words)


def _is_aircraft_request(text: str) -> bool:
    tokens = set(re.findall(r"[a-z0-9]+", text.lower()))
    if tokens & {"aircraft", "airplane", "aeroplane", "jet", "biplane"}:
        return True
    surface_qualifiers = {"floor", "ground", "geometric", "geometry", "flat", "math", "mathematical"}
    return "plane" in tokens and not (tokens & surface_qualifiers)


def _infer_kind(creative_request: str) -> str:
    text = creative_request.lower()
    if _text_has_any(text, ("office", "park", "room", "street", "alley", "forest", "set", "location", "bay", "clinic", "medical", "lab", "garage", "hangar")):
        return "location"
    if _text_has_any(text, ("chair", "desk", "lamp", "table", "prop", "rack", "shelf")) and not _text_has_any(text, ("room", "office")):
        return "prop"
    if _is_aircraft_request(text) or _text_has_any(text, ("ship", "spaceship", "fighter", "vehicle", "craft", "car", "truck", "rover", "motorcycle", "motorbike", "bike")):
        return "vehicle"
    return "asset"


def _default_components_for(creative_request: str) -> list[str]:
    text = creative_request.lower()
    if _text_has_any(text, ("office", "desk", "chair", "lamp", "workspace")):
        return OFFICE_COMPONENTS
    if _text_has_any(text, ("park", "tree", "path", "trail", "bench", "grass", "garden")):
        return PARK_COMPONENTS
    station_words = ("station", "orbital", "habitat", "window", "ring", "dock", "solar")
    if any(word in text for word in station_words):
        return STATION_COMPONENTS
    if _is_aircraft_request(text):
        return AIRCRAFT_COMPONENTS
    if _text_has_any(text, ("motorcycle", "motorbike", "bike")) and not _text_has_any(text, ("rack", "stand")):
        return TWO_WHEELED_VEHICLE_COMPONENTS
    if _infer_kind(creative_request) == "vehicle":
        return FIGHTER_COMPONENTS
    return ["primary structure", "secondary feature", "detail element"]


def _normalize_spec_for_request(creative_request: str, spec: PrimitiveBuildSpec) -> PrimitiveBuildSpec:
    inferred_kind = _infer_kind(creative_request)
    shape = _preserved_shape_phrase(creative_request)
    if (
        (spec.canonical_id.startswith("ship_") and inferred_kind != "vehicle")
        or (spec.canonical_id.startswith("asset_") and inferred_kind != "asset")
        or (shape and shape not in spec.canonical_id)
    ):
        spec.canonical_id = _slugify_asset_id(creative_request)
    if spec.kind in {"asset", "ship"} and inferred_kind != "asset":
        spec.kind = inferred_kind
    if spec.kind not in {"asset", "location", "prop", "vehicle", "character", "set"}:
        spec.kind = inferred_kind
    if not spec.components:
        spec.components = _default_components_for(creative_request)
    elif _is_aircraft_request(creative_request):
        component_text = " ".join(spec.components).lower()
        aircraft_part_words = ("wing", "fuselage", "nose", "tail", "engine", "cockpit")
        if not any(word in component_text for word in aircraft_part_words):
            spec.components = _default_components_for(creative_request)
    return spec


def _proposal_from_request(creative_request: str) -> PrimitiveBuildSpec:
    return PrimitiveBuildSpec(
        canonical_id=_slugify_asset_id(creative_request),
        name="Primitive Asset Concept",
        kind=_infer_kind(creative_request),
        style=creative_request,
        components=_default_components_for(creative_request),
    )


def _build_job_payload(creative_request: str, spec: PrimitiveBuildSpec) -> dict:
    spec.creative_request = creative_request
    job_root = PurePosixPath("jobs") / "{job_id}"
    asset_path = job_root / "assets" / f"{spec.kind}s" / f"{spec.canonical_id}.glb"
    preview_path = job_root / "renders" / "asset_previews" / f"{spec.canonical_id}.png"
    manifest_path = job_root / "out" / "asset_builds" / f"{spec.canonical_id}.json"
    spec_json = spec.model_dump_json()

    return {
        "title": f"Build {spec.canonical_id} primitive {spec.kind}",
        "description": creative_request,
        "required_capabilities": ["blender.command_line"],
        "policy": "run_anywhere",
        "payload": {
            "tool": "primitive_asset_builder",
            "script_file": "tools/primitive_asset_builder.py",
            "cwd": "{workspace_root}",
            "output_path": f"{{output_root}}/{preview_path}",
            "artifact_paths": [
                f"{{output_root}}/{asset_path}",
                f"{{output_root}}/{preview_path}",
                f"{{output_root}}/{manifest_path}",
            ],
            "artifact_type": "asset_build",
            "script_args": [
                "--spec-json",
                spec_json,
                "--output",
                f"{{output_root}}/{asset_path}",
                "--preview-output",
                f"{{output_root}}/{preview_path}",
                "--manifest-output",
                f"{{output_root}}/{manifest_path}",
            ],
            "conversation": {
                "creative_request": creative_request,
                "spec": json.loads(spec_json),
            },
        },
    }


@router.post("/accept", response_model=ConversationAcceptResponse, dependencies=[Depends(require_admin)])
async def accept_prompt(body: ConversationAcceptRequest, db: AsyncSession = Depends(get_db)):
    accepted_at = datetime.now(timezone.utc)
    db.add(AuditEvent(
        event_type="conversation.prompt_accepted",
        actor_type="user",
        actor_id="admin",
        resource_type="conversation",
        resource_id=None,
        details={
            "creative_request": body.creative_request,
        },
    ))
    await db.commit()
    return ConversationAcceptResponse(
        creative_request=body.creative_request,
        accepted_at=accepted_at,
    )


@router.post("/proposals", response_model=ConversationProposalResponse,
             dependencies=[Depends(require_admin)])
async def propose_build(body: ConversationProposalRequest):
    spec = _proposal_from_request(body.creative_request)
    return ConversationProposalResponse(
        creative_request=body.creative_request,
        spec=spec,
        job_payload=_build_job_payload(body.creative_request, spec),
    )


@router.post("/jobs", response_model=ConversationJobResponse, dependencies=[Depends(require_admin)])
async def create_conversation_job(body: ConversationJobRequest, db: AsyncSession = Depends(get_db)):
    spec = _normalize_spec_for_request(body.creative_request, body.spec)
    if body.scene_plan and not spec.scene_plan:
        spec.scene_plan = body.scene_plan
    if body.repaired_scene_plan and not spec.repaired_scene_plan:
        spec.repaired_scene_plan = body.repaired_scene_plan
    payload = _build_job_payload(body.creative_request, spec)
    payload["payload"]["conversation"] = {
        **payload["payload"]["conversation"],
        "llm_prompt": body.llm_prompt,
        "scene_plan_prompt": body.scene_plan_prompt,
        "scene_plan_response": body.scene_plan_response,
        "repair_prompt": body.repair_prompt,
        "repair_response": body.repair_response,
        "scene_plan": body.scene_plan.model_dump() if body.scene_plan else None,
        "repaired_scene_plan": body.repaired_scene_plan.model_dump() if body.repaired_scene_plan else None,
        "detail_validation_warnings": body.detail_validation_warnings,
    }
    job = Job(
        title=payload["title"],
        description=payload["description"],
        llm_response=body.llm_response,
        required_capabilities=payload["required_capabilities"],
        policy=body.policy,
        priority=body.priority,
        payload=payload["payload"],
        is_idempotent=True,
    )
    db.add(job)
    await db.flush()

    review_url = f"/review/jobs/{job.id}"
    job.payload = {
        **job.payload,
        "review_url": review_url,
    }
    db.add(AuditEvent(
        event_type="conversation.job_created",
        actor_type="user",
        actor_id="admin",
        resource_type="job",
        resource_id=str(job.id),
        details={
            "canonical_id": spec.canonical_id,
            "review_url": review_url,
            "has_llm_response": body.llm_response is not None,
        },
    ))
    await db.commit()
    await db.refresh(job)
    return ConversationJobResponse(
        job=JobSummary.model_validate(job),
        review_url=review_url,
        spec=spec,
    )
