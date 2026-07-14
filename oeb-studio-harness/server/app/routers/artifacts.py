from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import uuid

from app.database import get_db
from app.auth import require_worker, require_admin_or_worker
from app.models.artifact import Artifact
from app.models.job import Job
from app.models.audit import AuditEvent
from app.models.user import ApiToken
from app.schemas.artifact import ArtifactRegisterRequest, ArtifactSummary

router = APIRouter(prefix="/jobs", tags=["artifacts"])


@router.post("/{job_id}/artifacts", response_model=ArtifactSummary, status_code=status.HTTP_201_CREATED)
async def register_artifact(
    job_id: uuid.UUID,
    body: ArtifactRegisterRequest,
    db: AsyncSession = Depends(get_db),
    token: ApiToken = Depends(require_worker),
):
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.assigned_worker_id != token.worker_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not the assigned worker")

    artifact = Artifact(
        job_id=job_id,
        attempt_id=body.attempt_id,
        worker_id=token.worker_id,
        artifact_type=body.artifact_type,
        filename=body.filename,
        storage_path=body.storage_path,
        size_bytes=body.size_bytes,
        mime_type=body.mime_type,
        checksum_sha256=body.checksum_sha256,
        provenance=body.provenance,
    )
    db.add(artifact)
    db.add(AuditEvent(
        event_type="artifact.registered",
        actor_type="worker",
        actor_id=token.worker_id,
        resource_type="artifact",
        resource_id=str(artifact.id),
        details={
            "job_id": str(job_id),
            "artifact_type": body.artifact_type,
            "filename": body.filename,
            "checksum_sha256": body.checksum_sha256,
        },
    ))
    await db.commit()
    await db.refresh(artifact)
    return ArtifactSummary.model_validate(artifact)


@router.get("/{job_id}/artifacts", response_model=list[ArtifactSummary])
async def list_artifacts(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _caller: dict = Depends(require_admin_or_worker),
):
    result = await db.execute(
        select(Artifact)
        .where(Artifact.job_id == job_id)
        .order_by(Artifact.created_at)
    )
    return [ArtifactSummary.model_validate(a) for a in result.scalars().all()]
