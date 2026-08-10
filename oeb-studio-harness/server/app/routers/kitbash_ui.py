from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.audit import AuditEvent
from app.models.job import Job
from app.services.asset_review import ANGLE_VIEWS, REVIEW_VIEWS, image_artifacts_by_view
from app.services.kitbash_review import (
    apply_decision,
    create_kitbash_register_job,
    get_kitbash_set,
    list_kitbash_sets,
    mark_approval_dispatched,
)
from app.models.artifact import Artifact

router = APIRouter(prefix="/review", tags=["kitbash"])
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


@router.get("/kitbash", response_class=HTMLResponse)
async def review_kitbash(request: Request, db: AsyncSession = Depends(get_db)):
    sets = await list_kitbash_sets(db)
    return templates.TemplateResponse(request, "review_kitbash.html", {
        "sets": sets,
    })


@router.get("/kitbash/{canonical_id}", response_class=HTMLResponse)
async def review_kitbash_set(canonical_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    asset = await get_kitbash_set(db, canonical_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="Kitbash set not found")

    # The auto-created post_build_review job is a plain asset.review_render
    # job for this same canonical_id -- reuse the exact same gallery
    # lookup review.py's asset detail page already uses, rather than a
    # second rendering path for what's structurally the same artifact.
    jobs_result = await db.execute(
        select(Job)
        .where(
            Job.payload["job_type"].as_string() == "asset.review_render",
            Job.payload["asset_id"].as_string() == canonical_id,
        )
        .order_by(Job.updated_at.desc())
    )
    jobs = jobs_result.scalars().all()
    latest_job = jobs[0] if jobs else None
    by_view: dict[str, Artifact] = {}
    if latest_job:
        artifact_result = await db.execute(
            select(Artifact).where(Artifact.job_id == latest_job.id).order_by(Artifact.created_at)
        )
        by_view = image_artifacts_by_view(canonical_id, artifact_result.scalars().all())

    metadata = asset.asset_metadata or {}
    return templates.TemplateResponse(request, "review_kitbash_set.html", {
        "asset": asset,
        "canonical_id": canonical_id,
        "spec_path": metadata.get("spec_path"),
        "location_tag": metadata.get("location_tag"),
        "ticket_ref": metadata.get("ticket_ref"),
        "register_job_id": metadata.get("register_job_id"),
        "angle_views": list(ANGLE_VIEWS),
        "by_view": by_view,
        "action": by_view.get("action"),
    })


@router.post("/kitbash/{canonical_id}/decision")
async def decide_kitbash_set(canonical_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    asset = await get_kitbash_set(db, canonical_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="Kitbash set not found")

    form = await request.form()
    decision = str(form.get("decision") or "").strip()
    previous_status = asset.status
    try:
        apply_decision(asset, decision)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    register_job = None
    if decision == "approve":
        register_job = await create_kitbash_register_job(db, asset, actor_id="review-ui")
        mark_approval_dispatched(asset, str(register_job.id))

    db.add(AuditEvent(
        event_type="kitbash.reviewed",
        actor_type="user",
        actor_id="review-ui",
        resource_type="asset",
        resource_id=canonical_id,
        details={
            "decision": decision, "from_status": previous_status, "to_status": asset.status,
            "register_job_id": str(register_job.id) if register_job else None,
        },
    ))
    await db.commit()
    return RedirectResponse(url="/review/kitbash", status_code=303)
