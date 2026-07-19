from pathlib import Path
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.models.artifact import Artifact
from app.models.job import Job, JobAttempt
from app.services.asset_review import (
    ANGLE_VIEWS,
    REVIEW_VIEWS,
    create_asset_review_render_job,
    image_artifacts_by_view,
    list_review_assets,
    missing_uploaded_views,
    resolve_review_asset,
)

router = APIRouter(prefix="/review", tags=["review"])
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))

ASSET_REVIEW_VIEWS = tuple(REVIEW_VIEWS)


def _view_from_artifact(asset_id: str, filename: str) -> str | None:
    stem = Path(filename).stem
    prefix = f"{asset_id}_"
    if stem.startswith(prefix):
        view = stem[len(prefix):]
    else:
        view = stem.rsplit("_", 1)[-1]
    return view if view in ASSET_REVIEW_VIEWS else None


def _artifact_file_path(artifact: Artifact) -> Path:
    path = Path(artifact.storage_path)
    if path.exists() and path.is_file():
        return path

    settings = get_settings()
    artifacts_root = Path(settings.artifacts_root)
    worker_prefix = settings.artifact_worker_path_prefix.strip()
    server_prefix = (settings.artifact_server_path_prefix or settings.artifacts_root).strip()
    if worker_prefix and server_prefix:
        try:
            relative = path.relative_to(worker_prefix)
            mapped = Path(server_prefix) / relative
            if mapped.exists() and mapped.is_file():
                return mapped
        except ValueError:
            pass

    # Workers may register their own mounted path, for example:
    # /mnt/oeb-project/.../oeb-studio-harness/artifacts/{job_id}/file.png
    # The API container can usually only see ARTIFACTS_ROOT. Preserve the tail
    # under the job id when the worker/server mount prefixes differ.
    parts = path.parts
    job_id = str(artifact.job_id)
    if job_id in parts:
        job_index = parts.index(job_id)
        mapped = artifacts_root.joinpath(*parts[job_index:])
        if mapped.exists() and mapped.is_file():
            return mapped

    return artifacts_root / job_id / artifact.filename


@router.get("/assets", response_class=HTMLResponse)
async def review_assets(request: Request, db: AsyncSession = Depends(get_db)):
    assets = await list_review_assets(db)
    return templates.TemplateResponse(request, "review_assets.html", {
        "assets": assets,
    })


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
    asset = await resolve_review_asset(db, asset_id=asset_id)
    jobs_result = await db.execute(
        select(Job)
        .where(
            Job.payload["job_type"].as_string() == "asset.review_render",
            Job.payload["asset_id"].as_string() == asset.asset_id,
        )
        .order_by(Job.updated_at.desc())
    )
    jobs = jobs_result.scalars().all()
    latest_job = jobs[0] if jobs else None
    artifacts: list[Artifact] = []
    by_view: dict[str, Artifact] = {}
    missing_views: list[str] = list(REVIEW_VIEWS)
    gallery_ready = False

    if latest_job:
        artifact_result = await db.execute(
            select(Artifact)
            .where(Artifact.job_id == latest_job.id)
            .order_by(Artifact.created_at)
        )
        artifacts = artifact_result.scalars().all()
        by_view = image_artifacts_by_view(asset.asset_id, artifacts)
        missing_views = missing_uploaded_views(latest_job, artifacts)
        gallery_ready = latest_job.status == "completed" and not missing_views

    action = by_view.get("action")
    return templates.TemplateResponse(request, "review_asset.html", {
        "asset_id": asset.asset_id,
        "asset_name": asset.name,
        "job": latest_job,
        "jobs": jobs[:10],
        "asset_path": (latest_job.payload or {}).get("asset_path") if latest_job else asset.asset_path,
        "quality": (latest_job.payload or {}).get("quality") if latest_job else "preview",
        "angle_views": list(ANGLE_VIEWS),
        "by_view": by_view,
        "action": action,
        "missing_views": missing_views,
        "gallery_ready": gallery_ready,
    })


@router.post("/assets/{asset_id}/renders")
async def submit_review_asset_render(asset_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    form = await request.form()
    asset = await resolve_review_asset(db, asset_id=asset_id)
    quality = str(form.get("quality") or "preview")
    if quality not in {"preview", "final"}:
        raise HTTPException(status_code=422, detail="quality must be preview or final")
    try:
        priority = int(form.get("priority") or 10)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="priority must be an integer") from exc
    preferred_worker_id = str(form.get("preferred_worker_id") or "").strip() or None
    require_gpu_cycles = str(form.get("require_gpu_cycles") or "").lower() in {"1", "true", "on", "yes"}
    job = await create_asset_review_render_job(
        db,
        asset=asset,
        views=REVIEW_VIEWS,
        quality=quality,
        priority=priority,
        preferred_worker_id=preferred_worker_id,
        require_gpu_cycles=require_gpu_cycles,
        actor_id="review-ui",
    )
    await db.commit()
    return RedirectResponse(
        url=f"/review/assets/{asset.asset_id}?submitted_job={job.id}",
        status_code=303,
    )


@router.get("/artifacts/{artifact_id}")
async def review_artifact(artifact_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Artifact).where(Artifact.id == artifact_id))
    artifact = result.scalar_one_or_none()
    if not artifact:
        raise HTTPException(status_code=404, detail="Artifact not found")

    path = _artifact_file_path(artifact)
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Artifact file not available to this server")

    return FileResponse(path, media_type=artifact.mime_type, filename=artifact.filename)
