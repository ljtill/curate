"""Agent runs routes — API endpoints for agent activity data."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from agent_stack.database.repositories.agent_runs import AgentRunRepository

router = APIRouter(prefix="/runs", tags=["agent-runs"])


@router.get("/recent", response_class=HTMLResponse)
async def recent_runs(request: Request) -> HTMLResponse:
    """Return recent agent runs as an HTML partial for the dashboard."""
    templates = request.app.state.templates
    cosmos = request.app.state.cosmos
    repo = AgentRunRepository(cosmos.database)
    runs = await repo.list_recent(20)
    return templates.TemplateResponse(
        "partials/agent_run_item.html",
        {"request": request, "runs": runs},
    )
