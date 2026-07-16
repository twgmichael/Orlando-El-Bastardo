import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_admin
from app.database import get_db
from app.models.artifact import Artifact
from app.models.job import Job, JobAttempt
from app.models.project import Project
from app.models.worker import Worker, WorkerCapability
from app.schemas.debug import (
    DebugArtifactRecord,
    DebugAttemptRecord,
    DebugJobRecord,
    DebugJobTrace,
    DebugPromptLoop,
    StudioArtifactState,
    StudioAttemptState,
    StudioJobBuckets,
    StudioJobState,
    StudioProjectState,
    StudioStateResponse,
    StudioWorkerState,
)

router = APIRouter(prefix="/debug", tags=["debug"])


def _conversation_from_payload(payload: dict | None) -> dict:
    if not isinstance(payload, dict):
        return {}
    conversation = payload.get("conversation")
    return conversation if isinstance(conversation, dict) else {}


def _prompt_loop(job: Job) -> DebugPromptLoop:
    payload = job.payload if isinstance(job.payload, dict) else {}
    conversation = _conversation_from_payload(payload)
    spec = payload.get("spec") if isinstance(payload.get("spec"), dict) else None
    if spec is None and isinstance(conversation.get("spec"), dict):
        spec = conversation["spec"]

    return DebugPromptLoop(
        creative_request=conversation.get("creative_request") or job.description,
        llm_prompt=conversation.get("llm_prompt"),
        llm_response=conversation.get("llm_response") or job.llm_response,
        scene_plan_prompt=conversation.get("scene_plan_prompt"),
        scene_plan_response=conversation.get("scene_plan_response"),
        scene_plan=conversation.get("scene_plan"),
        repair_prompt=conversation.get("repair_prompt"),
        repair_response=conversation.get("repair_response"),
        repaired_scene_plan=conversation.get("repaired_scene_plan"),
        detail_validation_warnings=conversation.get("detail_validation_warnings") or [],
        primitive_spec=spec,
        script_file=payload.get("script_file"),
        script_args=payload.get("script_args") or [],
    )


def _canonical_id(job: Job) -> str | None:
    payload = job.payload if isinstance(job.payload, dict) else {}
    spec = payload.get("spec")
    if isinstance(spec, dict) and spec.get("canonical_id"):
        return str(spec["canonical_id"])
    if payload.get("canonical_id"):
        return str(payload["canonical_id"])
    return None


def _creative_request(job: Job) -> str | None:
    conversation = _conversation_from_payload(job.payload)
    if conversation.get("creative_request"):
        return str(conversation["creative_request"])
    return job.description


def _failure_reason(attempt: JobAttempt | None) -> str | None:
    if not attempt or not isinstance(attempt.output_summary, dict):
        return None
    reason = attempt.output_summary.get("reason")
    return str(reason) if reason else None


def _trace_url(job_id: uuid.UUID) -> str:
    return f"/api/v1/debug/jobs/{job_id}/trace"


def _job_state(job: Job, latest_attempts: dict[uuid.UUID, JobAttempt]) -> StudioJobState:
    latest_attempt = latest_attempts.get(job.id)
    return StudioJobState(
        id=job.id,
        title=job.title,
        description=job.description,
        status=job.status,
        project_id=job.project_id,
        canonical_id=_canonical_id(job),
        creative_request=_creative_request(job),
        assigned_worker_id=job.assigned_worker_id,
        preferred_worker_id=job.preferred_worker_id,
        required_capabilities=job.required_capabilities,
        priority=job.priority,
        created_at=job.created_at,
        updated_at=job.updated_at,
        last_attempt_status=latest_attempt.status if latest_attempt else None,
        last_failure_reason=_failure_reason(latest_attempt),
        review_url=f"/review/jobs/{job.id}",
        trace_url=_trace_url(job.id),
    )


@router.get("/jobs/{job_id}/trace", response_model=DebugJobTrace, dependencies=[Depends(require_admin)])
async def get_job_trace(job_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    job_result = await db.execute(select(Job).where(Job.id == job_id))
    job = job_result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    attempt_result = await db.execute(
        select(JobAttempt)
        .where(JobAttempt.job_id == job_id)
        .order_by(JobAttempt.attempt_number)
    )
    attempts = attempt_result.scalars().all()

    artifact_result = await db.execute(
        select(Artifact)
        .where(Artifact.job_id == job_id)
        .order_by(Artifact.created_at)
    )
    artifacts = artifact_result.scalars().all()

    artifact_records = []
    for artifact in artifacts:
        artifact_records.append(DebugArtifactRecord(
            id=artifact.id,
            job_id=artifact.job_id,
            attempt_id=artifact.attempt_id,
            worker_id=artifact.worker_id,
            artifact_type=artifact.artifact_type,
            filename=artifact.filename,
            storage_path=artifact.storage_path,
            size_bytes=artifact.size_bytes,
            mime_type=artifact.mime_type,
            checksum_sha256=artifact.checksum_sha256,
            provenance=artifact.provenance,
            created_at=artifact.created_at,
            review_url=f"/review/artifacts/{artifact.id}",
        ))

    return DebugJobTrace(
        job=DebugJobRecord.model_validate(job),
        prompt_loop=_prompt_loop(job),
        conversation=_conversation_from_payload(job.payload),
        attempts=[DebugAttemptRecord.model_validate(attempt) for attempt in attempts],
        artifacts=artifact_records,
        review_url=f"/review/jobs/{job.id}",
    )


@router.get("/studio-state", response_model=StudioStateResponse, dependencies=[Depends(require_admin)])
async def get_studio_state(
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=20, ge=1, le=100),
):
    now = datetime.now(timezone.utc)

    projects_result = await db.execute(
        select(Project)
        .where(Project.status == "active")
        .order_by(Project.updated_at.desc())
        .limit(limit)
    )
    projects = projects_result.scalars().all()

    workers_result = await db.execute(select(Worker).order_by(Worker.id))
    workers = workers_result.scalars().all()

    caps_result = await db.execute(select(WorkerCapability).order_by(WorkerCapability.worker_id))
    caps_by_worker: dict[str, list[str]] = {}
    for capability in caps_result.scalars().all():
        caps_by_worker.setdefault(capability.worker_id, []).append(capability.capability)

    running_jobs_result = await db.execute(select(Job).where(Job.status == "running"))
    running_jobs = running_jobs_result.scalars().all()
    current_job_by_worker = {
        job.assigned_worker_id: job.id
        for job in running_jobs
        if job.assigned_worker_id
    }

    job_queries = {
        "queued": (
            select(Job)
            .where(Job.status == "pending")
            .order_by(Job.priority.desc(), Job.created_at.asc())
            .limit(limit)
        ),
        "running": (
            select(Job)
            .where(Job.status == "running")
            .order_by(Job.updated_at.desc())
            .limit(limit)
        ),
        "recent_completed": (
            select(Job)
            .where(Job.status == "completed")
            .order_by(Job.updated_at.desc())
            .limit(limit)
        ),
        "recent_failed": (
            select(Job)
            .where(Job.status == "failed")
            .order_by(Job.updated_at.desc())
            .limit(limit)
        ),
    }

    jobs_by_bucket: dict[str, list[Job]] = {}
    job_ids: set[uuid.UUID] = set()
    for bucket, query in job_queries.items():
        result = await db.execute(query)
        bucket_jobs = result.scalars().all()
        jobs_by_bucket[bucket] = bucket_jobs
        job_ids.update(job.id for job in bucket_jobs)

    recent_attempts_result = await db.execute(
        select(JobAttempt)
        .order_by(JobAttempt.started_at.desc())
        .limit(limit)
    )
    recent_attempts = recent_attempts_result.scalars().all()
    job_ids.update(attempt.job_id for attempt in recent_attempts)

    latest_attempts: dict[uuid.UUID, JobAttempt] = {}
    if job_ids:
        attempts_result = await db.execute(
            select(JobAttempt)
            .where(JobAttempt.job_id.in_(job_ids))
            .order_by(JobAttempt.job_id, JobAttempt.attempt_number.desc())
        )
        for attempt in attempts_result.scalars().all():
            latest_attempts.setdefault(attempt.job_id, attempt)

    recent_artifacts_result = await db.execute(
        select(Artifact)
        .order_by(Artifact.created_at.desc())
        .limit(limit)
    )
    recent_artifacts = recent_artifacts_result.scalars().all()

    job_buckets = StudioJobBuckets(
        queued=[_job_state(job, latest_attempts) for job in jobs_by_bucket["queued"]],
        running=[_job_state(job, latest_attempts) for job in jobs_by_bucket["running"]],
        recent_completed=[_job_state(job, latest_attempts) for job in jobs_by_bucket["recent_completed"]],
        recent_failed=[_job_state(job, latest_attempts) for job in jobs_by_bucket["recent_failed"]],
    )

    worker_states = [
        StudioWorkerState(
            id=worker.id,
            platform=worker.platform,
            agent_version=worker.agent_version,
            status=worker.status,
            capabilities=caps_by_worker.get(worker.id, []),
            resources=worker.resources,
            current_job_id=current_job_by_worker.get(worker.id),
            last_heartbeat_at=worker.last_heartbeat_at,
            registered_at=worker.registered_at,
            updated_at=worker.updated_at,
        )
        for worker in workers
    ]

    attempt_states = [
        StudioAttemptState(
            id=attempt.id,
            job_id=attempt.job_id,
            worker_id=attempt.worker_id,
            attempt_number=attempt.attempt_number,
            status=attempt.status,
            started_at=attempt.started_at,
            finished_at=attempt.finished_at,
            failure_reason=_failure_reason(attempt),
            trace_url=_trace_url(attempt.job_id),
        )
        for attempt in recent_attempts
    ]

    artifact_states = [
        StudioArtifactState(
            id=artifact.id,
            job_id=artifact.job_id,
            attempt_id=artifact.attempt_id,
            worker_id=artifact.worker_id,
            artifact_type=artifact.artifact_type,
            filename=artifact.filename,
            size_bytes=artifact.size_bytes,
            mime_type=artifact.mime_type,
            created_at=artifact.created_at,
            review_url=f"/review/artifacts/{artifact.id}",
            trace_url=_trace_url(artifact.job_id),
        )
        for artifact in recent_artifacts
    ]

    all_job_states = (
        job_buckets.queued
        + job_buckets.running
        + job_buckets.recent_completed
        + job_buckets.recent_failed
    )
    review_links = [job.review_url for job in all_job_states]
    debug_links = [job.trace_url for job in all_job_states]

    return StudioStateResponse(
        generated_at=now,
        projects=[StudioProjectState.model_validate(project) for project in projects],
        workers=worker_states,
        jobs=job_buckets,
        recent_attempts=attempt_states,
        recent_artifacts=artifact_states,
        review_links=review_links,
        debug_links=debug_links,
    )
