from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import case, func, select
from pathlib import Path

from app.database import get_db
from app.models.worker import Worker, WorkerCapability
from app.models.job import Job
from app.models.audit import AuditEvent

router = APIRouter(tags=["dashboard"])
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))

COMPLETED_PAGE_SIZE = 25
AUDIT_PAGE_SIZE = 10


def _job_review_url(job: Job) -> str:
    payload = job.payload or {}
    if payload.get("job_type") == "asset.review_render" and payload.get("asset_id"):
        return f"/review/assets/{payload['asset_id']}"
    return f"/review/jobs/{job.id}"


def _worker_display_id(worker: Worker) -> str:
    resources = worker.resources or {}
    ip_address = (
        resources.get("ip_address")
        or resources.get("primary_ip")
        or resources.get("host_ip")
    )
    return f"{worker.id} ({ip_address})" if ip_address else worker.id


templates.env.globals["job_review_url"] = _job_review_url
templates.env.globals["worker_display_id"] = _worker_display_id


@router.get("/", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    completed_page: int = 0,
    audit_page: int = 0,
    db: AsyncSession = Depends(get_db),
):
    completed_page = max(completed_page, 0)
    audit_page = max(audit_page, 0)
    now = datetime.now(timezone.utc)
    recent_cutoff = now - timedelta(days=1)

    worker_status_order = case(
        (Worker.status == "busy", 0),
        (Worker.status == "online", 1),
        (Worker.status == "offline", 3),
        else_=2,
    )
    workers_result = await db.execute(select(Worker).order_by(worker_status_order, Worker.id))
    workers = workers_result.scalars().all()

    caps_result = await db.execute(select(WorkerCapability))
    caps_by_worker: dict[str, list[str]] = {}
    for c in caps_result.scalars().all():
        caps_by_worker.setdefault(c.worker_id, []).append(c.capability)

    active_status_order = case(
        (Job.status == "running", 0),
        (Job.status == "pending", 1),
        else_=2,
    )
    active_result = await db.execute(
        select(Job)
        .where(Job.status.in_(["pending", "running"]))
        .order_by(active_status_order, Job.priority.desc(), Job.created_at.asc())
    )
    active_jobs = active_result.scalars().all()

    failed_result = await db.execute(
        select(Job)
        .where(Job.status == "failed", Job.updated_at >= recent_cutoff)
        .order_by(Job.updated_at.desc())
    )
    failed_jobs = failed_result.scalars().all()

    if completed_page == 0:
        completed_query = (
            select(Job)
            .where(Job.status == "completed", Job.updated_at >= recent_cutoff)
            .order_by(Job.updated_at.desc())
        )
        completed_label = "last 24 hours"
    else:
        completed_query = (
            select(Job)
            .where(Job.status == "completed", Job.updated_at < recent_cutoff)
            .order_by(Job.updated_at.desc())
            .offset((completed_page - 1) * COMPLETED_PAGE_SIZE)
            .limit(COMPLETED_PAGE_SIZE)
        )
        completed_label = f"archive page {completed_page}"

    completed_result = await db.execute(completed_query)
    completed_jobs = completed_result.scalars().all()

    older_completed_count_result = await db.execute(
        select(func.count()).where(Job.status == "completed", Job.updated_at < recent_cutoff)
    )
    older_completed_count = older_completed_count_result.scalar() or 0
    has_next_completed_page = completed_page > 0 and (
        completed_page * COMPLETED_PAGE_SIZE < older_completed_count
    )

    counts_result = await db.execute(
        select(Job.status, func.count()).group_by(Job.status)
    )
    job_counts = dict(counts_result.all())

    audit_result = await db.execute(
        select(AuditEvent)
        .order_by(AuditEvent.created_at.desc())
        .offset(audit_page * AUDIT_PAGE_SIZE)
        .limit(AUDIT_PAGE_SIZE)
    )
    audit_events = audit_result.scalars().all()

    audit_count_result = await db.execute(select(func.count()).select_from(AuditEvent))
    audit_count = audit_count_result.scalar() or 0
    has_next_audit_page = (audit_page + 1) * AUDIT_PAGE_SIZE < audit_count

    return templates.TemplateResponse(request, "dashboard.html", {
        "workers": workers,
        "caps_by_worker": caps_by_worker,
        "active_jobs": active_jobs,
        "failed_jobs": failed_jobs,
        "completed_jobs": completed_jobs,
        "completed_label": completed_label,
        "completed_page": completed_page,
        "has_older_completed": older_completed_count > 0,
        "has_next_completed_page": has_next_completed_page,
        "job_counts": job_counts,
        "audit_events": audit_events,
        "audit_page": audit_page,
        "has_next_audit_page": has_next_audit_page,
    })
