import json
import re
from pathlib import PurePosixPath

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_admin
from app.database import get_db
from app.models.audit import AuditEvent
from app.models.job import Job
from app.schemas.conversation import (
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


def _slugify_asset_id(text: str) -> str:
    words = re.findall(r"[a-z0-9]+", text.lower())
    useful = [w for w in words if w not in {"a", "an", "the", "me", "make", "build", "from", "with"}]
    stem = "_".join(useful[:4]) or "primitive_asset"
    return f"asset_{stem}_A"


def _text_has_any(text: str, words: tuple[str, ...]) -> bool:
    return any(word in text for word in words)


def _infer_kind(creative_request: str) -> str:
    text = creative_request.lower()
    if _text_has_any(text, ("office", "park", "room", "street", "alley", "forest", "set", "location")):
        return "location"
    if _text_has_any(text, ("chair", "desk", "lamp", "table", "prop")) and not _text_has_any(text, ("room", "office")):
        return "prop"
    if _text_has_any(text, ("ship", "spaceship", "fighter", "vehicle", "craft", "car", "truck")):
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
    return FIGHTER_COMPONENTS


def _request_wants_station(creative_request: str) -> bool:
    text = creative_request.lower()
    station_words = ("station", "orbital", "habitat", "window", "ring", "dock", "solar")
    return any(word in text for word in station_words)


def _components_look_like_fighter(components: list[str]) -> bool:
    text = " ".join(components).lower()
    fighter_words = ("wedge", "cockpit", "wing", "engine", "tail", "fin", "nose")
    return sum(1 for word in fighter_words if word in text) >= 3


def _normalize_spec_for_request(creative_request: str, spec: PrimitiveBuildSpec) -> PrimitiveBuildSpec:
    inferred_kind = _infer_kind(creative_request)
    if spec.canonical_id.startswith("ship_") and inferred_kind != "vehicle":
        spec.canonical_id = _slugify_asset_id(creative_request)
    if spec.kind == "ship" and inferred_kind != "vehicle":
        spec.kind = inferred_kind
    if spec.kind not in {"asset", "location", "prop", "vehicle", "character", "set"}:
        spec.kind = inferred_kind
    if not spec.components:
        spec.components = _default_components_for(creative_request)
    if _request_wants_station(creative_request) and _components_look_like_fighter(spec.components):
        spec.components = STATION_COMPONENTS
    if inferred_kind == "location" and _components_look_like_fighter(spec.components):
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
    asset_path = PurePosixPath("assets") / f"{spec.kind}s" / f"{spec.canonical_id}.glb"
    preview_path = PurePosixPath("renders") / "asset_previews" / f"{spec.canonical_id}.png"
    manifest_path = PurePosixPath("out") / "asset_builds" / f"{spec.canonical_id}.json"
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
    payload = _build_job_payload(body.creative_request, spec)
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
