from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime, timezone, timedelta
import uuid

from app.database import get_db
from app.auth import require_admin, require_worker, require_admin_or_worker
from app.config import get_settings
from app.models.artifact import Artifact
from app.models.job import Job, JobAttempt, JobLease
from app.models.worker import Worker, WorkerCapability
from app.models.audit import AuditEvent
from app.models.user import ApiToken
from app.services.asset_review import (
    asset_review_gallery_url,
    create_asset_review_render_job as create_review_render_job_record,
    missing_uploaded_views,
    resolve_review_asset,
)
from app.services.worker_updates import worker_can_claim_jobs
from app.schemas.job import (
    AssetReviewRenderRequest,
    JobCreateRequest,
    JobSummary,
    ClaimResponse,
    LeaseDetail,
    JobCompleteRequest,
    JobFailRequest,
    JobProgressRequest,
    AttemptSummary,
)

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.post("/asset-review-renders", response_model=JobSummary, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(require_admin)])
async def create_asset_review_render_job(
    body: AssetReviewRenderRequest,
    db: AsyncSession = Depends(get_db),
):
    asset = await resolve_review_asset(
        db,
        asset_query=body.asset_name,
        asset_id=body.asset_id,
        asset_path=body.asset_path,
    )
    job = await create_review_render_job_record(
        db,
        asset=asset,
        views=body.views,
        quality=body.quality,
        output_namespace=body.output_namespace,
        artifact_prefix=body.artifact_prefix,
        priority=body.priority,
        preferred_worker_id=body.preferred_worker_id,
        width=body.width,
        height=body.height,
        samples=body.samples,
        output_path=body.output_path,
        require_gpu_cycles=body.require_gpu_cycles,
        actor_id="admin",
    )
    await db.commit()
    await db.refresh(job)
    return JobSummary.model_validate(job)


@router.post("", response_model=JobSummary, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(require_admin)])
async def create_job(body: JobCreateRequest, db: AsyncSession = Depends(get_db)):
    job = Job(
        title=body.title,
        description=body.description,
        llm_response=body.llm_response,
        project_id=body.project_id,
        required_capabilities=body.required_capabilities,
        policy=body.policy,
        preferred_worker_id=body.preferred_worker_id,
        priority=body.priority,
        payload=body.payload,
        is_idempotent=body.is_idempotent,
    )
    db.add(job)
    db.add(AuditEvent(
        event_type="job.created",
        actor_type="user",
        actor_id="admin",
        resource_type="job",
        resource_id=str(job.id),
        details={"title": job.title, "required_capabilities": job.required_capabilities},
    ))

    # preview_now_final_later: create a run_anywhere preview sibling immediately
    # and a wait_for_preferred_worker final sibling that stays queued.
    if body.policy == "preview_now_final_later":
        preview_caps = [c for c in (body.required_capabilities or []) if "preview" in c or "light" in c] \
                       or body.required_capabilities
        final_caps = body.required_capabilities

        preview_job = Job(
            title=f"{body.title} [preview]",
            description=body.description,
            llm_response=body.llm_response,
            project_id=body.project_id,
            required_capabilities=preview_caps,
            policy="run_anywhere",
            priority=body.priority + 1,
            payload={**body.payload, "_preview": True},
            is_idempotent=True,
        )
        final_job = Job(
            title=f"{body.title} [final]",
            description=body.description,
            llm_response=body.llm_response,
            project_id=body.project_id,
            required_capabilities=final_caps,
            policy="wait_for_preferred_worker",
            preferred_worker_id=body.preferred_worker_id,
            priority=body.priority,
            payload={**body.payload, "_preview": False},
            is_idempotent=True,
        )
        # Link siblings to each other (set after both have IDs via flush)
        db.add(preview_job)
        db.add(final_job)
        await db.flush()
        preview_job.sibling_job_id = final_job.id
        final_job.sibling_job_id = preview_job.id
        job.sibling_job_id = preview_job.id  # original job points to preview

        db.add(AuditEvent(
            event_type="job.preview_final_split",
            actor_type="user",
            actor_id="admin",
            resource_type="job",
            resource_id=str(job.id),
            details={"preview_job_id": str(preview_job.id), "final_job_id": str(final_job.id)},
        ))

    await db.commit()
    await db.refresh(job)
    return JobSummary.model_validate(job)


@router.get("", response_model=list[JobSummary])
async def list_jobs(
    job_status: str | None = None,
    db: AsyncSession = Depends(get_db),
    _caller: dict = Depends(require_admin_or_worker),
):
    query = select(Job)
    if job_status:
        query = query.where(Job.status == job_status)
    query = query.order_by(Job.priority.desc(), Job.created_at.asc())
    result = await db.execute(query)
    return [JobSummary.model_validate(j) for j in result.scalars().all()]


@router.get("/eligible", response_model=list[JobSummary])
async def list_eligible_jobs(
    db: AsyncSession = Depends(get_db),
    token: ApiToken = Depends(require_worker),
):
    worker_result = await db.execute(select(Worker).where(Worker.id == token.worker_id))
    worker = worker_result.scalar_one_or_none()
    if not worker_can_claim_jobs(worker):
        return []

    caps_result = await db.execute(
        select(WorkerCapability.capability).where(WorkerCapability.worker_id == token.worker_id)
    )
    worker_caps = set(caps_result.scalars().all())

    jobs_result = await db.execute(
        select(Job)
        .where(Job.status == "pending")
        .order_by(Job.priority.desc(), Job.created_at.asc())
    )
    pending = jobs_result.scalars().all()

    def is_eligible(j: Job) -> bool:
        if not all(cap in worker_caps for cap in (j.required_capabilities or [])):
            return False
        # wait_for_preferred_worker: only the preferred worker may claim it
        if j.policy == "wait_for_preferred_worker" and j.preferred_worker_id:
            return j.preferred_worker_id == token.worker_id
        return True

    eligible = [j for j in pending if is_eligible(j)]
    return [JobSummary.model_validate(j) for j in eligible]


@router.get("/{job_id}", response_model=JobSummary)
async def get_job(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _caller: dict = Depends(require_admin_or_worker),
):
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobSummary.model_validate(job)


@router.post("/{job_id}/claim", response_model=ClaimResponse)
async def claim_job(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    token: ApiToken = Depends(require_worker),
):
    settings = get_settings()
    now = datetime.now(timezone.utc)

    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != "pending":
        raise HTTPException(status_code=409, detail=f"Job is not claimable (status={job.status})")

    worker_result = await db.execute(select(Worker).where(Worker.id == token.worker_id))
    worker = worker_result.scalar_one_or_none()
    if not worker_can_claim_jobs(worker):
        update_state = (worker.update_state if worker else "unknown")
        raise HTTPException(
            status_code=409,
            detail=f"Worker is not claimable while update_state={update_state}",
        )

    # Verify capabilities
    caps_result = await db.execute(
        select(WorkerCapability.capability).where(WorkerCapability.worker_id == token.worker_id)
    )
    worker_caps = set(caps_result.scalars().all())
    missing = [c for c in (job.required_capabilities or []) if c not in worker_caps]
    if missing:
        raise HTTPException(status_code=409, detail=f"Worker missing capabilities: {missing}")

    # Count prior attempts for this job
    count_result = await db.execute(
        select(func.count()).where(JobAttempt.job_id == job_id)
    )
    attempt_number = (count_result.scalar() or 0) + 1

    attempt = JobAttempt(
        job_id=job_id,
        worker_id=token.worker_id,
        attempt_number=attempt_number,
        status="running",
        started_at=now,
    )
    db.add(attempt)
    await db.flush()  # get attempt.id

    lease = JobLease(
        job_id=job_id,
        attempt_id=attempt.id,
        worker_id=token.worker_id,
        granted_at=now,
        expires_at=now + timedelta(seconds=settings.job_lease_seconds),
        last_renewed_at=now,
    )
    db.add(lease)

    job.status = "running"
    job.assigned_worker_id = token.worker_id
    job.updated_at = now

    db.add(AuditEvent(
        event_type="job.claimed",
        actor_type="worker",
        actor_id=token.worker_id,
        resource_type="job",
        resource_id=str(job_id),
        details={"attempt_number": attempt_number},
    ))

    await db.commit()
    await db.refresh(job)
    await db.refresh(lease)
    await db.refresh(attempt)

    return ClaimResponse(
        job=JobSummary.model_validate(job),
        lease=LeaseDetail.model_validate(lease),
    )


@router.post("/{job_id}/renew-lease", response_model=LeaseDetail)
async def renew_lease(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    token: ApiToken = Depends(require_worker),
):
    settings = get_settings()
    now = datetime.now(timezone.utc)

    result = await db.execute(
        select(JobLease).where(JobLease.job_id == job_id, JobLease.is_active.is_(True))
    )
    lease = result.scalar_one_or_none()
    if not lease:
        raise HTTPException(status_code=404, detail="No active lease for this job")
    if lease.worker_id != token.worker_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Lease belongs to different worker")

    lease.expires_at = now + timedelta(seconds=settings.job_lease_seconds)
    lease.last_renewed_at = now
    await db.commit()
    await db.refresh(lease)
    return LeaseDetail.model_validate(lease)


@router.post("/{job_id}/progress", response_model=AttemptSummary)
async def report_job_progress(
    job_id: uuid.UUID,
    body: JobProgressRequest,
    db: AsyncSession = Depends(get_db),
    token: ApiToken = Depends(require_worker),
):
    now = datetime.now(timezone.utc)

    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.assigned_worker_id != token.worker_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not the assigned worker")
    if job.status != "running":
        raise HTTPException(status_code=409, detail=f"Job is not running (status={job.status})")

    attempt_result = await db.execute(
        select(JobAttempt)
        .where(JobAttempt.job_id == job_id, JobAttempt.worker_id == token.worker_id)
        .order_by(JobAttempt.attempt_number.desc())
    )
    attempt = attempt_result.scalars().first()
    if not attempt:
        raise HTTPException(status_code=404, detail="No active attempt found")

    summary = dict(attempt.output_summary or {})
    progress = dict(body.progress or {})
    progress["updated_at"] = now.isoformat()
    summary["progress"] = progress
    attempt.output_summary = summary
    job.updated_at = now
    await db.commit()
    await db.refresh(attempt)
    return AttemptSummary.model_validate(attempt)


@router.post("/{job_id}/complete", response_model=JobSummary)
async def complete_job(
    job_id: uuid.UUID,
    body: JobCompleteRequest,
    db: AsyncSession = Depends(get_db),
    token: ApiToken = Depends(require_worker),
):
    now = datetime.now(timezone.utc)

    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.assigned_worker_id != token.worker_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not the assigned worker")

    # Release lease (delete so job_id unique constraint allows future reclaims)
    lease_result = await db.execute(
        select(JobLease).where(JobLease.job_id == job_id, JobLease.is_active.is_(True))
    )
    lease = lease_result.scalar_one_or_none()
    if lease:
        await db.delete(lease)

    # Close attempt
    attempt_result = await db.execute(
        select(JobAttempt)
        .where(JobAttempt.job_id == job_id, JobAttempt.worker_id == token.worker_id)
        .order_by(JobAttempt.attempt_number.desc())
    )
    attempt = attempt_result.scalars().first()
    if attempt:
        attempt.status = "completed"
        attempt.finished_at = now
        attempt.log_output = body.log_output
        attempt.output_summary = body.output_summary

    if (job.payload or {}).get("job_type") == "asset.review_render":
        artifacts_result = await db.execute(select(Artifact).where(Artifact.job_id == job_id))
        missing_views = missing_uploaded_views(job, artifacts_result.scalars().all())
        if missing_views:
            summary = dict(body.output_summary or {})
            summary["gallery_ready"] = False
            summary["missing_views"] = missing_views
            if (job.payload or {}).get("asset_id"):
                summary["gallery_url"] = asset_review_gallery_url((job.payload or {})["asset_id"])
            if attempt:
                attempt.status = "failed"
                attempt.output_summary = summary
            job.status = "failed"
            job.updated_at = now
            db.add(AuditEvent(
                event_type="job.asset_review_render.gallery_not_ready",
                actor_type="worker",
                actor_id=token.worker_id,
                resource_type="job",
                resource_id=str(job_id),
                details={"missing_views": missing_views},
            ))
            await db.commit()
            await db.refresh(job)
            return JobSummary.model_validate(job)

    job.status = "completed"
    job.updated_at = now

    db.add(AuditEvent(
        event_type="job.completed",
        actor_type="worker",
        actor_id=token.worker_id,
        resource_type="job",
        resource_id=str(job_id),
    ))

    await db.commit()
    await db.refresh(job)
    return JobSummary.model_validate(job)


@router.post("/{job_id}/fail", response_model=JobSummary)
async def fail_job(
    job_id: uuid.UUID,
    body: JobFailRequest,
    db: AsyncSession = Depends(get_db),
    token: ApiToken = Depends(require_worker),
):
    now = datetime.now(timezone.utc)

    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.assigned_worker_id != token.worker_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not the assigned worker")

    # Release lease (delete so job_id unique constraint allows future reclaims)
    lease_result = await db.execute(
        select(JobLease).where(JobLease.job_id == job_id, JobLease.is_active.is_(True))
    )
    lease = lease_result.scalar_one_or_none()
    if lease:
        await db.delete(lease)

    # Close attempt
    attempt_result = await db.execute(
        select(JobAttempt)
        .where(JobAttempt.job_id == job_id, JobAttempt.worker_id == token.worker_id)
        .order_by(JobAttempt.attempt_number.desc())
    )
    attempt = attempt_result.scalars().first()
    if attempt:
        attempt.status = "failed"
        attempt.finished_at = now
        attempt.log_output = body.log_output
        summary = dict(body.output_summary or {})
        summary["reason"] = body.reason
        attempt.output_summary = summary

    # Return ordinary idempotent jobs to the queue. Review renders have a strict
    # upload contract, so artifact failures must remain visible as failed jobs.
    is_asset_review = (job.payload or {}).get("job_type") == "asset.review_render"
    if job.is_idempotent and not is_asset_review:
        job.status = "pending"
        job.assigned_worker_id = None
    else:
        job.status = "failed"
    job.updated_at = now

    db.add(AuditEvent(
        event_type="job.failed",
        actor_type="worker",
        actor_id=token.worker_id,
        resource_type="job",
        resource_id=str(job_id),
        details={"reason": body.reason, "requeued": job.is_idempotent and not is_asset_review},
    ))

    await db.commit()
    await db.refresh(job)
    return JobSummary.model_validate(job)


@router.get("/{job_id}/attempts", response_model=list[AttemptSummary])
async def list_attempts(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _caller: dict = Depends(require_admin_or_worker),
):
    result = await db.execute(
        select(JobAttempt)
        .where(JobAttempt.job_id == job_id)
        .order_by(JobAttempt.attempt_number)
    )
    return [AttemptSummary.model_validate(a) for a in result.scalars().all()]
