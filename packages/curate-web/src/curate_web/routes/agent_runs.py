"""Agent runs routes — API endpoints for agent activity data."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from curate_common.database.repositories.agent_runs import AgentRunRepository
from curate_web.auth.middleware import require_authenticated_user

router = APIRouter(
    prefix="/runs",
    tags=["agent-runs"],
    dependencies=[Depends(require_authenticated_user)],
)


@router.get("/recent", response_class=HTMLResponse)
async def recent_runs(request: Request) -> HTMLResponse:
    """Return recent agent runs as an HTML partial for the dashboard."""
    templates = request.app.state.templates
    cosmos = request.app.state.cosmos
    runs_repo = AgentRunRepository(cosmos.database)
    runs = await runs_repo.list_recent(20)
    return templates.TemplateResponse(
        "partials/agent_run_item.html",
        {"request": request, "runs": runs},
    )
