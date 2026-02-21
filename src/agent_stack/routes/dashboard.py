"""Dashboard route — pipeline overview."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from agent_stack.database.repositories.agent_runs import AgentRunRepository

router = APIRouter(tags=["dashboard"])


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request) -> HTMLResponse:
    """Render the dashboard overview page."""
    templates = request.app.state.templates
    cosmos = request.app.state.cosmos
    runs_repo = AgentRunRepository(cosmos.database)
    recent_runs = await runs_repo.list_recent(5)
    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "recent_runs": recent_runs},
    )
