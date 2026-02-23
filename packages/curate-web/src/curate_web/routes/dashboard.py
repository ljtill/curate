"""Dashboard route — edition hub overview."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from curate_common.database.repositories.agent_runs import AgentRunRepository
from curate_common.database.repositories.editions import EditionRepository
from curate_web.auth.middleware import require_authenticated_user
from curate_web.runtime import get_runtime
from curate_web.services.dashboard import get_dashboard_data

router = APIRouter(
    tags=["dashboard"], dependencies=[Depends(require_authenticated_user)]
)


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request) -> HTMLResponse:
    """Render the dashboard overview page."""
    runtime = get_runtime(request)
    editions_repo = EditionRepository(runtime.cosmos.database)
    runs_repo = AgentRunRepository(runtime.cosmos.database)
    data = await get_dashboard_data(editions_repo, runs_repo)
    return runtime.templates.TemplateResponse(
        "dashboard.html",
        {"request": request, **data},
    )


@router.post("/activity/clear")
async def clear_activity(request: Request) -> RedirectResponse:
    """Clear all recent agent activity."""
    runtime = get_runtime(request)
    runs_repo = AgentRunRepository(runtime.cosmos.database)
    await runs_repo.clear_all()
    return RedirectResponse(url="/", status_code=303)
