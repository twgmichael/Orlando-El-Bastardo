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
from app.services.studio_chat import (
    default_components_for as _default_components_for,
    infer_kind as _infer_kind,
    is_aircraft_request as _is_aircraft_request,
    preserved_shape_phrase as _preserved_shape_phrase,
    slug_kind_prefix as _slug_kind_prefix,
    slugify_asset_id as _slugify_asset_id,
    text_has_any as _text_has_any,
)

router = APIRouter(prefix="/conversations", tags=["conversations"])

# Component lists, SLUG_SKIP_WORDS, and the heuristic functions used to be
# duplicated here byte-for-byte from app.services.studio_chat. Consolidated
# to the single canonical implementation imported above so the two callers
# can't drift again; see docs/planning/REVIEW-AUDIT.md section 9.


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
