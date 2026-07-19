import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select, update
from pathlib import Path

from app.config import get_settings
from app.database import init_engine, get_engine
import app.models  # noqa: F401 — registers all ORM models with Base

log = logging.getLogger(__name__)


async def maintenance_loop() -> None:
    settings = get_settings()
    from app.database import _session_factory
    from app.models.worker import Worker
    from app.models.job import Job, JobLease, JobAttempt
    from app.services.artifact_prune import prune_old_review_render_artifacts

    last_review_render_prune: datetime | None = None

    while True:
        await asyncio.sleep(10)
        try:
            async with _session_factory() as db:
                now = datetime.now(timezone.utc)
                cutoff = now - timedelta(seconds=settings.worker_timeout_seconds)

                # Mark stale workers offline
                await db.execute(
                    update(Worker)
                    .where(Worker.last_heartbeat_at < cutoff, Worker.status != "offline")
                    .values(status="offline", updated_at=now)
                )

                # Find expired active leases
                expired_leases = await db.execute(
                    select(JobLease).where(JobLease.is_active.is_(True), JobLease.expires_at < now)
                )
                for lease in expired_leases.scalars().all():
                    await db.delete(lease)

                    # Close the running attempt
                    attempt_result = await db.execute(
                        select(JobAttempt)
                        .where(JobAttempt.id == lease.attempt_id)
                    )
                    attempt = attempt_result.scalar_one_or_none()
                    if attempt and attempt.status == "running":
                        attempt.status = "interrupted"
                        attempt.finished_at = now

                    # Return idempotent jobs to queue
                    job_result = await db.execute(select(Job).where(Job.id == lease.job_id))
                    job = job_result.scalar_one_or_none()
                    if job and job.status == "running":
                        if job.is_idempotent:
                            job.status = "pending"
                            job.assigned_worker_id = None
                        else:
                            job.status = "failed"
                        job.updated_at = now

                should_prune_review_renders = (
                    last_review_render_prune is None
                    or (
                        now - last_review_render_prune
                    ).total_seconds() >= settings.review_render_prune_interval_seconds
                )
                if should_prune_review_renders:
                    await prune_old_review_render_artifacts(db, now=now)
                    last_review_render_prune = now

                await db.commit()
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Error in maintenance loop")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    init_engine(settings.database_url)
    task = asyncio.create_task(maintenance_loop())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    engine = get_engine()
    if engine:
        await engine.dispose()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Studio Harness API",
        version="0.1.0",
        lifespan=lifespan,
    )

    static_dir = Path(__file__).parent / "static"
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    from app.routers.health import router as health_router
    from app.routers.dashboard import router as dashboard_router
    from app.routers.projects import router as projects_router
    from app.routers.workers import router as workers_router
    from app.routers.jobs import router as jobs_router
    from app.routers.artifacts import router as artifacts_router
    from app.routers.assets import router as assets_router
    from app.routers.scene_renders import router as scene_renders_router
    from app.routers.conversations import router as conversations_router
    from app.routers.debug import router as debug_router
    from app.routers.studio_chat import router as studio_chat_router
    from app.routers.review import router as review_router

    app.include_router(health_router)
    app.include_router(dashboard_router)
    app.include_router(review_router)
    app.include_router(projects_router, prefix="/api/v1")
    app.include_router(workers_router, prefix="/api/v1")
    app.include_router(jobs_router, prefix="/api/v1")
    app.include_router(artifacts_router, prefix="/api/v1")
    app.include_router(assets_router, prefix="/api/v1")
    app.include_router(scene_renders_router, prefix="/api/v1")
    app.include_router(conversations_router, prefix="/api/v1")
    app.include_router(debug_router, prefix="/api/v1")
    app.include_router(studio_chat_router, prefix="/api/v1")

    return app


app = create_app()
