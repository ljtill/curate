"""Dashboard route — pipeline overview."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from curate_common.database.repositories.agent_runs import AgentRunRepository
from curate_web.auth.middleware import require_authenticated_user
from curate_web.services.dashboard import get_dashboard_data

router = APIRouter(
    tags=["dashboard"], dependencies=[Depends(require_authenticated_user)]
)


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
