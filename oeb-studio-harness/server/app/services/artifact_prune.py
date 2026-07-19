from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.artifact import Artifact
from app.models.audit import AuditEvent
from app.models.job import Job
from app.services.asset_review import list_review_assets

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReviewRenderPruneResult:
    cutoff: datetime
    protected_jobs: int
    artifacts_deleted: int
    files_deleted: int
    bytes_deleted: int


def _artifact_file_path(artifact: Artifact) -> Path:
    settings = get_settings()
    path = Path(artifact.storage_path)
    if path.exists() and path.is_file():
        return path

    artifacts_root = Path(settings.artifacts_root)
    worker_prefix = settings.artifact_worker_path_prefix.strip()
    server_prefix = (settings.artifact_server_path_prefix or settings.artifacts_root).strip()
    if worker_prefix and server_prefix:
        try:
            mapped = Path(server_prefix) / path.relative_to(worker_prefix)
            if mapped.exists() and mapped.is_file():
                return mapped
        except ValueError:
            pass

    job_id = str(artifact.job_id)
    if job_id in path.parts:
        mapped = artifacts_root.joinpath(*path.parts[path.parts.index(job_id):])
        if mapped.exists() and mapped.is_file():
            return mapped

    return artifacts_root / job_id / artifact.filename


def _is_under_artifacts_root(path: Path) -> bool:
    try:
        path.resolve().relative_to(Path(get_settings().artifacts_root).resolve())
    except ValueError:
        return False
    return True


async def _latest_completed_review_job_ids_by_active_asset(db: AsyncSession) -> set:
    active_asset_ids = {asset.asset_id for asset in await list_review_assets(db)}
    if not active_asset_ids:
        return set()

    result = await db.execute(
        select(Job)
        .where(
            Job.payload["job_type"].as_string() == "asset.review_render",
            Job.payload["asset_id"].as_string().in_(active_asset_ids),
            Job.status == "completed",
        )
        .order_by(Job.payload["asset_id"].as_string(), Job.updated_at.desc())
    )
    protected: set = set()
    seen_assets: set[str] = set()
    for job in result.scalars().all():
        asset_id = (job.payload or {}).get("asset_id")
        if asset_id in seen_assets:
            continue
        protected.add(job.id)
        seen_assets.add(asset_id)
    return protected


async def prune_old_review_render_artifacts(
    db: AsyncSession,
    *,
    older_than_days: int | None = None,
    now: datetime | None = None,
) -> ReviewRenderPruneResult:
    settings = get_settings()
    retention_days = settings.review_render_retention_days if older_than_days is None else older_than_days
    current_time = now or datetime.now(timezone.utc)
    cutoff = current_time - timedelta(days=retention_days)
    protected_job_ids = await _latest_completed_review_job_ids_by_active_asset(db)

    result = await db.execute(
        select(Artifact, Job)
        .join(Job, Artifact.job_id == Job.id)
        .where(
            Job.payload["job_type"].as_string() == "asset.review_render",
            Artifact.created_at < cutoff,
        )
        .order_by(Artifact.created_at)
    )

    artifacts_deleted = 0
    files_deleted = 0
    bytes_deleted = 0
    for artifact, _job in result.all():
        if artifact.job_id in protected_job_ids:
            continue
        if artifact.mime_type and not artifact.mime_type.startswith("image/"):
            continue

        path = _artifact_file_path(artifact)
        if path.exists() and path.is_file() and _is_under_artifacts_root(path):
            size = path.stat().st_size
            try:
                path.unlink()
            except OSError:
                log.exception("Failed to delete old review render artifact file: %s", path)
            else:
                files_deleted += 1
                bytes_deleted += size

        await db.delete(artifact)
        artifacts_deleted += 1

    db.add(AuditEvent(
        event_type="artifact.review_render.pruned",
        actor_type="system",
        actor_id="maintenance",
        resource_type="artifact",
        resource_id="review-render-retention",
        details={
            "cutoff": cutoff.isoformat(),
            "protected_jobs": len(protected_job_ids),
            "artifacts_deleted": artifacts_deleted,
            "files_deleted": files_deleted,
            "bytes_deleted": bytes_deleted,
        },
    ))
    return ReviewRenderPruneResult(
        cutoff=cutoff,
        protected_jobs=len(protected_job_ids),
        artifacts_deleted=artifacts_deleted,
        files_deleted=files_deleted,
        bytes_deleted=bytes_deleted,
    )
