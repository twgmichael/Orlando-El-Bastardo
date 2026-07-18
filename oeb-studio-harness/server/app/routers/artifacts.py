import hashlib
import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import uuid

from app.database import get_db
from app.config import get_settings
from app.auth import require_worker, require_admin_or_worker
from app.models.artifact import Artifact
from app.models.job import Job
from app.models.audit import AuditEvent
from app.models.user import ApiToken
from app.schemas.artifact import ArtifactRegisterRequest, ArtifactSummary

router = APIRouter(prefix="/jobs", tags=["artifacts"])


def _safe_filename(filename: str) -> str:
    name = Path(filename).name
    if not name or name in {".", ".."}:
        raise HTTPException(status_code=422, detail="Invalid artifact filename")
    return name


async def _assigned_job(job_id: uuid.UUID, db: AsyncSession, token: ApiToken) -> Job:
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.assigned_worker_id != token.worker_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not the assigned worker")
    return job


def _artifact_public_url(settings, artifact_id: uuid.UUID) -> str:
    base = settings.artifact_public_base_url.strip().rstrip("/")
    return f"{base}/review/artifacts/{artifact_id}" if base else f"/review/artifacts/{artifact_id}"


def _parse_review_metadata(raw: str | None) -> dict:
    if not raw:
        return {}
    try:
        metadata = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid review_metadata_json: {exc}") from exc
    if not isinstance(metadata, dict):
        raise HTTPException(status_code=422, detail="review_metadata_json must be an object")
    return metadata


@router.post("/{job_id}/artifacts", response_model=ArtifactSummary, status_code=status.HTTP_201_CREATED)
async def register_artifact(
    job_id: uuid.UUID,
    body: ArtifactRegisterRequest,
    db: AsyncSession = Depends(get_db),
    token: ApiToken = Depends(require_worker),
):
    await _assigned_job(job_id, db, token)

    settings = get_settings()
    artifact = Artifact(
        job_id=job_id,
        attempt_id=body.attempt_id,
        worker_id=token.worker_id,
        artifact_type=body.artifact_type,
        filename=body.filename,
        storage_path=body.storage_path,
        public_url=body.public_url,
        size_bytes=body.size_bytes,
        mime_type=body.mime_type,
        checksum_sha256=body.checksum_sha256,
        provenance=body.provenance,
        review_metadata=body.review_metadata,
    )
    db.add(artifact)
    await db.flush()
    if not artifact.public_url:
        artifact.public_url = _artifact_public_url(settings, artifact.id)
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
            "public_url": artifact.public_url,
        },
    ))
    await db.commit()
    await db.refresh(artifact)
    return ArtifactSummary.model_validate(artifact)


@router.post("/{job_id}/artifact-files", response_model=ArtifactSummary, status_code=status.HTTP_201_CREATED)
async def upload_artifact_file(
    job_id: uuid.UUID,
    request: Request,
    artifact_type: str,
    filename: str,
    mime_type: str | None = None,
    checksum_sha256: str | None = None,
    provenance: str = "uploaded",
    review_metadata_json: str | None = None,
    db: AsyncSession = Depends(get_db),
    token: ApiToken = Depends(require_worker),
):
    await _assigned_job(job_id, db, token)

    settings = get_settings()
    safe_name = _safe_filename(filename)
    content = await request.body()
    if not content:
        raise HTTPException(status_code=422, detail="Artifact upload body is empty")

    digest = hashlib.sha256(content).hexdigest()
    if checksum_sha256 and checksum_sha256 != digest:
        raise HTTPException(status_code=422, detail="Artifact checksum mismatch")

    dest_dir = Path(settings.artifacts_root) / str(job_id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / safe_name
    dest.write_bytes(content)

    artifact = Artifact(
        job_id=job_id,
        worker_id=token.worker_id,
        artifact_type=artifact_type,
        filename=safe_name,
        storage_path=str(dest),
        size_bytes=len(content),
        mime_type=mime_type or "application/octet-stream",
        checksum_sha256=digest,
        provenance=provenance,
        review_metadata=_parse_review_metadata(review_metadata_json),
    )
    db.add(artifact)
    await db.flush()
    artifact.public_url = _artifact_public_url(settings, artifact.id)
    db.add(AuditEvent(
        event_type="artifact.uploaded",
        actor_type="worker",
        actor_id=token.worker_id,
        resource_type="artifact",
        resource_id=str(artifact.id),
        details={
            "job_id": str(job_id),
            "artifact_type": artifact_type,
            "filename": safe_name,
            "checksum_sha256": digest,
            "public_url": artifact.public_url,
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
