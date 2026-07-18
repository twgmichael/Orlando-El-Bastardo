from pathlib import Path
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.artifact import Artifact
from app.models.job import Job, JobAttempt

router = APIRouter(prefix="/review", tags=["review"])
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))

ASSET_REVIEW_VIEWS = ("front", "back", "left", "right", "top", "bottom", "action")


def _view_from_artifact(asset_id: str, filename: str) -> str | None:
    stem = Path(filename).stem
    prefix = f"{asset_id}_"
    if stem.startswith(prefix):
        view = stem[len(prefix):]
    else:
        view = stem.rsplit("_", 1)[-1]
    return view if view in ASSET_REVIEW_VIEWS else None


@router.get("/jobs/{job_id}", response_class=HTMLResponse)
async def review_job(job_id: uuid.UUID, request: Request, db: AsyncSession = Depends(get_db)):
    job_result = await db.execute(select(Job).where(Job.id == job_id))
    job = job_result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    artifact_result = await db.execute(
        select(Artifact).where(Artifact.job_id == job_id).order_by(Artifact.created_at)
    )
    artifacts = artifact_result.scalars().all()

    attempt_result = await db.execute(
        select(JobAttempt).where(JobAttempt.job_id == job_id).order_by(JobAttempt.attempt_number.desc())
    )
    attempts = attempt_result.scalars().all()

    return templates.TemplateResponse(request, "review_job.html", {
        "job": job,
        "artifacts": artifacts,
        "attempts": attempts,
    })


@router.get("/assets/{asset_id}", response_class=HTMLResponse)
async def review_asset(asset_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    jobs_result = await db.execute(
        select(Job)
        .where(
            Job.payload["job_type"].as_string() == "asset.review_render",
            Job.payload["asset_id"].as_string() == asset_id,
        )
        .order_by(Job.updated_at.desc())
    )
    jobs = jobs_result.scalars().all()
    if not jobs:
        raise HTTPException(status_code=404, detail="No review renders found for asset")

    latest_job = jobs[0]
    artifact_result = await db.execute(
        select(Artifact)
        .where(Artifact.job_id == latest_job.id)
        .order_by(Artifact.created_at)
    )
    artifacts = artifact_result.scalars().all()

    by_view: dict[str, Artifact] = {}
    for artifact in artifacts:
        if not artifact.mime_type or not artifact.mime_type.startswith("image/"):
            continue
        view = _view_from_artifact(asset_id, artifact.filename)
        if view:
            by_view[view] = artifact

    angle_views = ["front", "back", "left", "right", "top", "bottom"]
    action = by_view.get("action")
    return templates.TemplateResponse(request, "review_asset.html", {
        "asset_id": asset_id,
        "job": latest_job,
        "jobs": jobs[:10],
        "asset_path": (latest_job.payload or {}).get("asset_path"),
        "quality": (latest_job.payload or {}).get("quality"),
        "angle_views": angle_views,
        "by_view": by_view,
        "action": action,
    })


@router.get("/artifacts/{artifact_id}")
async def review_artifact(artifact_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Artifact).where(Artifact.id == artifact_id))
    artifact = result.scalar_one_or_none()
    if not artifact:
        raise HTTPException(status_code=404, detail="Artifact not found")

    path = Path(artifact.storage_path)
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Artifact file not available to this server")

    return FileResponse(path, media_type=artifact.mime_type, filename=artifact.filename)
