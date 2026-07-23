from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter(tags=["studio-chat-ui"])
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


@router.get("/studio-chat", response_class=HTMLResponse)
async def studio_chat_page(request: Request):
    return templates.TemplateResponse(request, "studio_chat.html", {})
