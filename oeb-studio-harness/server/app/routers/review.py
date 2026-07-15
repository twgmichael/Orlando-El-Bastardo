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
