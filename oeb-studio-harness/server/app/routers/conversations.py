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


def _slugify_asset_id(text: str) -> str:
    words = re.findall(r"[a-z0-9]+", text.lower())
    useful = [w for w in words if w not in {"a", "an", "the", "me", "make", "build", "from", "with"}]
    stem = "_".join(useful[:4]) or "primitive_asset"
    return f"ship_{stem}_A"


def _proposal_from_request(creative_request: str) -> PrimitiveBuildSpec:
    return PrimitiveBuildSpec(
        canonical_id=_slugify_asset_id(creative_request),
        name="Primitive Ship Concept",
        kind="ship",
        style=creative_request,
        components=[
            "wedge nose",
            "compact dark cockpit",
            "low main hull",
            "two swept wings",
            "two large rear engines",
            "crooked tail fin",
            "asymmetric greebles",
        ],
    )


def _build_job_payload(creative_request: str, spec: PrimitiveBuildSpec) -> dict:
    asset_path = PurePosixPath("assets") / "ships" / f"{spec.canonical_id}.glb"
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
            "cwd": ".",
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
    payload = _build_job_payload(body.creative_request, body.spec)
    job = Job(
        title=payload["title"],
        description=payload["description"],
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
            "canonical_id": body.spec.canonical_id,
            "review_url": review_url,
        },
    ))
    await db.commit()
    await db.refresh(job)
    return ConversationJobResponse(
        job=JobSummary.model_validate(job),
        review_url=review_url,
        spec=body.spec,
    )
