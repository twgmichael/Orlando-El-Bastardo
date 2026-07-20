from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from datetime import datetime, timezone

from app.database import get_db
from app.auth import require_enrollment, require_worker, require_admin, require_admin_or_worker, generate_token
from app.models.worker import Worker, WorkerCapability
from app.models.user import ApiToken
from app.models.audit import AuditEvent
from app.schemas.worker import (
    WorkerRegisterRequest,
    WorkerRegisterResponse,
    WorkerHeartbeatRequest,
    WorkerHeartbeatResponse,
    WorkerUpdateRequest,
    WorkerUpdateResponse,
    WorkerDetail,
)
from app.services.worker_updates import worker_active_job_id

router = APIRouter(prefix="/workers", tags=["workers"])
WORKER_UPDATE_ERROR_MAX_LENGTH = 512


def _worker_update_error(value: str | None) -> str | None:
    if not value:
        return None
    if len(value) <= WORKER_UPDATE_ERROR_MAX_LENGTH:
        return value
    return value[: WORKER_UPDATE_ERROR_MAX_LENGTH - 3] + "..."


@router.post("/register", response_model=WorkerRegisterResponse, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(require_enrollment)])
async def register_worker(body: WorkerRegisterRequest, db: AsyncSession = Depends(get_db)):
    now = datetime.now(timezone.utc)

    result = await db.execute(select(Worker).where(Worker.id == body.worker_id))
    worker = result.scalar_one_or_none()

    if worker:
        # Revoke existing tokens for this worker
        existing_tokens = await db.execute(
            select(ApiToken).where(ApiToken.worker_id == body.worker_id, ApiToken.is_revoked.is_(False))
        )
        for t in existing_tokens.scalars().all():
            t.is_revoked = True

        worker.platform = body.platform
        worker.agent_version = body.agent_version
        worker.git_sha = body.git_sha
        worker.status = "online"
        worker.resources = body.resources
        worker.current_job_id = None
        if worker.update_state in {"ready_to_update", "applying", "force_requested"}:
            target_matches = not worker.update_target_git_sha or worker.update_target_git_sha == body.git_sha
            if target_matches:
                worker.update_state = "complete"
                worker.update_last_error = None
            else:
                worker.update_state = "failed"
                worker.update_last_error = (
                    f"Worker registered git_sha={body.git_sha or 'unknown'}, "
                    f"expected {worker.update_target_git_sha}"
                )
        elif worker.update_state in {"complete", "failed"}:
            worker.update_state = "idle"
        worker.updated_at = now
    else:
        worker = Worker(
            id=body.worker_id,
            platform=body.platform,
            agent_version=body.agent_version,
            git_sha=body.git_sha,
            status="online",
            current_job_id=None,
            update_state="idle",
            resources=body.resources,
            registered_at=now,
            updated_at=now,
        )
        db.add(worker)

    # Replace capabilities
    await db.execute(delete(WorkerCapability).where(WorkerCapability.worker_id == body.worker_id))
    for cap in body.capabilities:
        db.add(WorkerCapability(worker_id=body.worker_id, capability=cap))

    # Issue new worker token
    plain_token, token_hash = generate_token()
    db.add(ApiToken(
        name=f"worker:{body.worker_id}",
        token_hash=token_hash,
        token_type="worker",
        worker_id=body.worker_id,
    ))

    db.add(AuditEvent(
        event_type="worker.registered",
        actor_type="worker",
        actor_id=body.worker_id,
        resource_type="worker",
        resource_id=body.worker_id,
        details={
            "platform": body.platform,
            "agent_version": body.agent_version,
            "git_sha": body.git_sha,
            "capabilities": body.capabilities,
        },
    ))

    await db.commit()
    await db.refresh(worker)

    return WorkerRegisterResponse(
        worker_id=worker.id,
        worker_token=plain_token,
        registered_at=worker.registered_at,
    )


@router.post("/{worker_id}/heartbeat", response_model=WorkerHeartbeatResponse)
async def heartbeat(
    worker_id: str,
    body: WorkerHeartbeatRequest,
    db: AsyncSession = Depends(get_db),
    token: ApiToken = Depends(require_worker),
):
    if token.worker_id != worker_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Token does not match worker")

    result = await db.execute(select(Worker).where(Worker.id == worker_id))
    worker = result.scalar_one_or_none()
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")

    now = datetime.now(timezone.utc)
    worker.status = body.status
    worker.current_job_id = body.current_job_id
    if body.git_sha is not None:
        worker.git_sha = body.git_sha
    if body.update_last_error:
        worker.update_last_error = _worker_update_error(body.update_last_error)
        worker.update_state = "failed"
    elif body.update_state in {"idle", "applying", "complete", "failed"}:
        worker.update_state = body.update_state
    elif worker.update_state == "draining" and not body.current_job_id and body.status != "busy":
        worker.update_state = "ready_to_update"
    worker.last_heartbeat_at = now
    worker.updated_at = now
    await db.commit()

    return WorkerHeartbeatResponse(
        acknowledged=True,
        server_time=now,
        update_state=worker.update_state,
        update_mode=worker.update_mode,
        update_target_git_sha=worker.update_target_git_sha,
    )


@router.post("/{worker_id}/update", response_model=WorkerUpdateResponse,
             dependencies=[Depends(require_admin)])
async def request_worker_update(
    worker_id: str,
    body: WorkerUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Worker).where(Worker.id == worker_id))
    worker = result.scalar_one_or_none()
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")

    active_job_id = await worker_active_job_id(db, worker_id)
    if body.mode == "update_if_idle" and active_job_id:
        raise HTTPException(
            status_code=409,
            detail=f"Worker is running job {active_job_id}; use drain_then_update or force_update",
        )

    now = datetime.now(timezone.utc)
    worker.update_mode = body.mode
    worker.update_target_git_sha = body.target_git_sha
    worker.update_requested_at = now
    worker.update_last_error = None

    if body.mode == "force_update":
        worker.update_state = "force_requested"
        message = "Force update requested; active jobs may be interrupted by the worker updater."
    elif active_job_id:
        worker.update_state = "draining"
        message = f"Worker is draining; update will be ready after job {active_job_id} finishes."
    else:
        worker.update_state = "ready_to_update"
        message = "Worker is idle; update is ready to apply."

    worker.updated_at = now
    db.add(AuditEvent(
        event_type="worker.update_requested",
        actor_type="user",
        actor_id="admin",
        resource_type="worker",
        resource_id=worker_id,
        details={
            "mode": body.mode,
            "target_git_sha": body.target_git_sha,
            "active_job_id": active_job_id,
            "update_state": worker.update_state,
        },
    ))
    await db.commit()
    await db.refresh(worker)

    return WorkerUpdateResponse(
        worker_id=worker.id,
        update_state=worker.update_state,
        update_mode=worker.update_mode or body.mode,
        update_target_git_sha=worker.update_target_git_sha,
        current_job_id=worker.current_job_id or active_job_id,
        message=message,
    )


@router.get("", response_model=list[WorkerDetail])
async def list_workers(
    db: AsyncSession = Depends(get_db),
    _caller: dict = Depends(require_admin_or_worker),
):
    workers_result = await db.execute(select(Worker).order_by(Worker.id))
    workers = workers_result.scalars().all()

    caps_result = await db.execute(select(WorkerCapability))
    all_caps = caps_result.scalars().all()

    caps_by_worker: dict[str, list[str]] = {}
    for c in all_caps:
        caps_by_worker.setdefault(c.worker_id, []).append(c.capability)

    return [
        WorkerDetail(
            id=w.id,
            platform=w.platform,
            agent_version=w.agent_version,
            git_sha=w.git_sha,
            status=w.status,
            current_job_id=w.current_job_id,
            update_state=w.update_state,
            update_mode=w.update_mode,
            update_target_git_sha=w.update_target_git_sha,
            update_requested_at=w.update_requested_at,
            update_last_error=w.update_last_error,
            capabilities=caps_by_worker.get(w.id, []),
            resources=w.resources,
            last_heartbeat_at=w.last_heartbeat_at,
            registered_at=w.registered_at,
        )
        for w in workers
    ]


@router.get("/{worker_id}", response_model=WorkerDetail)
async def get_worker(
    worker_id: str,
    db: AsyncSession = Depends(get_db),
    _caller: dict = Depends(require_admin_or_worker),
):
    result = await db.execute(select(Worker).where(Worker.id == worker_id))
    worker = result.scalar_one_or_none()
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")

    caps_result = await db.execute(
        select(WorkerCapability).where(WorkerCapability.worker_id == worker_id)
    )
    caps = [c.capability for c in caps_result.scalars().all()]

    return WorkerDetail(
        id=worker.id,
        platform=worker.platform,
        agent_version=worker.agent_version,
        git_sha=worker.git_sha,
        status=worker.status,
        current_job_id=worker.current_job_id,
        update_state=worker.update_state,
        update_mode=worker.update_mode,
        update_target_git_sha=worker.update_target_git_sha,
        update_requested_at=worker.update_requested_at,
        update_last_error=worker.update_last_error,
        capabilities=caps,
        resources=worker.resources,
        last_heartbeat_at=worker.last_heartbeat_at,
        registered_at=worker.registered_at,
    )
