"""Agents route — read-only view of the agent pipeline topology and configuration."""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from curate_common.database.repositories.agent_runs import AgentRunRepository
from curate_web.auth.middleware import require_authenticated_user
from curate_web.services.agent_runs import get_agents_page_data

router = APIRouter(tags=["agents"], dependencies=[Depends(require_authenticated_user)])
logger = logging.getLogger(__name__)


@router.get("/agents", response_class=HTMLResponse)
async def agents_page(request: Request) -> HTMLResponse:
    """Render the Agents page showing pipeline topology and agent details."""
    started_at = time.monotonic()
    templates = request.app.state.templates
    cosmos = request.app.state.cosmos
    runs_repo = AgentRunRepository(cosmos.database)
    data = await get_agents_page_data(runs_repo)

    logger.info(
        "Agents page loaded — agents=%d running_stages=%d duration_ms=%.0f",
        len(data["agents"]),
        len(data["running_stages"]),
        (time.monotonic() - started_at) * 1000,
    )

    return templates.TemplateResponse(
        "agents.html",
        {
            "request": request,
            **data,
            "pipeline_available": True,
        },
    )
