from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job import Job
from app.models.worker import Worker


WORKER_UPDATE_EXCLUDED_STATES = {
    "draining",
    "ready_to_update",
    "applying",
    "force_requested",
    "failed",
}


def worker_can_claim_jobs(worker: Worker | None) -> bool:
    if not worker:
        return False
    return (worker.update_state or "idle") not in WORKER_UPDATE_EXCLUDED_STATES


async def worker_active_job_id(db: AsyncSession, worker_id: str) -> str | None:
    result = await db.execute(
        select(Job)
        .where(Job.assigned_worker_id == worker_id, Job.status == "running")
        .order_by(Job.updated_at.desc())
        .limit(1)
    )
    job = result.scalar_one_or_none()
    return str(job.id) if job else None
