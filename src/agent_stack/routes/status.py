"""Status route — dependency health checks."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from agent_stack.agents.llm import create_chat_client
from agent_stack.services.health import check_all

router = APIRouter(tags=["status"])


@router.get("/status", response_class=HTMLResponse)
async def status(request: Request):
    """Render the status page with live health probe results."""
    cosmos = request.app.state.cosmos
    settings = request.app.state.settings
    processor = request.app.state.processor
    chat_client = create_chat_client(settings.openai)

    results = await check_all(cosmos.database, chat_client, processor)

    templates = request.app.state.templates
    return templates.TemplateResponse(
        "status.html",
        {"request": request, "checks": results},
    )
