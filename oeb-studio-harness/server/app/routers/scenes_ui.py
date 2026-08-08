from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.asset import Asset

router = APIRouter(prefix="/review", tags=["scenes"])
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


@router.get("/scenes", response_class=HTMLResponse)
async def review_scenes(request: Request, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Asset).where(Asset.kind == "scene").order_by(Asset.canonical_id)
    )
    scenes = result.scalars().all()
    return templates.TemplateResponse(request, "review_scenes.html", {
        "scenes": scenes,
    })
