"""Dashboard route — pipeline overview."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from agent_stack.database.repositories.agent_runs import AgentRunRepository
from agent_stack.services.dashboard import get_dashboard_data

router = APIRouter(tags=["dashboard"])


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request) -> HTMLResponse:
    """Render the dashboard overview page."""
    templates = request.app.state.templates
    cosmos = request.app.state.cosmos
    runs_repo = AgentRunRepository(cosmos.database)
    data = await get_dashboard_data(runs_repo)
    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request, **data},
    )
