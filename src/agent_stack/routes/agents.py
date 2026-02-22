"""Agents route — read-only view of the agent pipeline topology and configuration."""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from agent_stack.database.repositories.agent_runs import AgentRunRepository
from agent_stack.services.agent_runs import get_agents_page_data

router = APIRouter(tags=["agents"])
logger = logging.getLogger(__name__)


@router.get("/agents", response_class=HTMLResponse)
async def agents_page(request: Request) -> HTMLResponse:
    """Render the Agents page showing pipeline topology and agent details."""
    started_at = time.monotonic()
    templates = request.app.state.templates
    cosmos = request.app.state.cosmos
    processor = request.app.state.processor
    if processor is None:
        logger.warning(
            "Agents page requested while pipeline is unavailable "
            "(FOUNDRY_PROJECT_ENDPOINT not configured)"
        )
        return templates.TemplateResponse(
            "agents.html",
            {
                "request": request,
                "agents": [],
                "running_stages": set(),
                "pipeline_available": False,
            },
        )
    orchestrator = processor.orchestrator
    runs_repo = AgentRunRepository(cosmos.database)
    data = await get_agents_page_data(orchestrator, runs_repo)

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
