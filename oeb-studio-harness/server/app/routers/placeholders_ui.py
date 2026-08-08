from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.audit import AuditEvent
from app.services.placeholder_review import (
    apply_decision,
    get_placeholder_asset,
    list_placeholder_assets,
)

router = APIRouter(prefix="/review", tags=["placeholders"])
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


@router.get("/placeholders", response_class=HTMLResponse)
async def review_placeholders(request: Request, db: AsyncSession = Depends(get_db)):
    placeholders = await list_placeholder_assets(db)
    return templates.TemplateResponse(request, "review_placeholders.html", {
        "placeholders": placeholders,
    })


@router.post("/placeholders/{canonical_id}/decision")
async def decide_placeholder(canonical_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    asset = await get_placeholder_asset(db, canonical_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="Placeholder not found")

    form = await request.form()
    decision = str(form.get("decision") or "").strip()
    previous_status = asset.status
    try:
        apply_decision(asset, decision)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    db.add(AuditEvent(
        event_type="placeholder.reviewed",
        actor_type="user",
        actor_id="review-ui",
        resource_type="asset",
        resource_id=canonical_id,
        details={"decision": decision, "from_status": previous_status, "to_status": asset.status},
    ))
    await db.commit()
    return RedirectResponse(url="/review/placeholders", status_code=303)
