from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pathlib import Path

from app.database import get_db
from app.models.worker import Worker, WorkerCapability
from app.models.job import Job
from app.models.audit import AuditEvent

router = APIRouter(tags=["dashboard"])
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, db: AsyncSession = Depends(get_db)):
    workers_result = await db.execute(select(Worker).order_by(Worker.status, Worker.id))
    workers = workers_result.scalars().all()

    caps_result = await db.execute(select(WorkerCapability))
    caps_by_worker: dict[str, list[str]] = {}
    for c in caps_result.scalars().all():
        caps_by_worker.setdefault(c.worker_id, []).append(c.capability)

    jobs_result = await db.execute(
        select(Job).order_by(Job.status, Job.priority.desc(), Job.created_at.desc()).limit(50)
    )
    jobs = jobs_result.scalars().all()

    counts_result = await db.execute(
        select(Job.status, func.count()).group_by(Job.status)
    )
    job_counts = dict(counts_result.all())

    audit_result = await db.execute(
        select(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(20)
    )
    audit_events = audit_result.scalars().all()

    return templates.TemplateResponse(request, "dashboard.html", {
        "workers": workers,
        "caps_by_worker": caps_by_worker,
        "jobs": jobs,
        "job_counts": job_counts,
        "audit_events": audit_events,
    })
