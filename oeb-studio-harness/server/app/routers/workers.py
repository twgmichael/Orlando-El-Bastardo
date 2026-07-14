from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from datetime import datetime, timezone

from app.database import get_db
from app.auth import require_enrollment, require_worker, require_admin_or_worker, generate_token
from app.models.worker import Worker, WorkerCapability
from app.models.user import ApiToken
from app.models.audit import AuditEvent
from app.schemas.worker import (
    WorkerRegisterRequest,
    WorkerRegisterResponse,
    WorkerHeartbeatRequest,
    WorkerHeartbeatResponse,
    WorkerDetail,
)

router = APIRouter(prefix="/workers", tags=["workers"])


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
        worker.status = "online"
        worker.resources = body.resources
        worker.updated_at = now
    else:
        worker = Worker(
            id=body.worker_id,
            platform=body.platform,
            agent_version=body.agent_version,
            status="online",
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
        details={"platform": body.platform, "capabilities": body.capabilities},
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
    worker.last_heartbeat_at = now
    worker.updated_at = now
    await db.commit()

    return WorkerHeartbeatResponse(acknowledged=True, server_time=now)


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
            status=w.status,
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
        status=worker.status,
        capabilities=caps,
        resources=worker.resources,
        last_heartbeat_at=worker.last_heartbeat_at,
        registered_at=worker.registered_at,
    )
