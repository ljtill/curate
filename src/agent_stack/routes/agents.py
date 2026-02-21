"""Agents route — read-only view of the agent pipeline topology and configuration."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from agent_stack.agents.registry import get_agent_metadata
from agent_stack.database.repositories.agent_runs import AgentRunRepository

router = APIRouter(tags=["agents"])


@router.get("/agents", response_class=HTMLResponse)
async def agents_page(request: Request):
    """Render the Agents page showing pipeline topology and agent details."""
    templates = request.app.state.templates
    cosmos = request.app.state.cosmos
    orchestrator = request.app.state.processor._orchestrator

    agent_metadata = get_agent_metadata(orchestrator)

    runs_repo = AgentRunRepository(cosmos.database)
    recent_runs = await runs_repo.list_recent(50)

    # Group latest run per stage
    latest_by_stage: dict[str, dict] = {}
    running_stages: set[str] = set()
    for run in recent_runs:
        if run.stage not in latest_by_stage:
            latest_by_stage[run.stage] = {
                "status": run.status,
                "started_at": run.started_at,
                "completed_at": run.completed_at,
                "usage": run.usage,
                "trigger_id": run.trigger_id,
            }
        if run.status == "running":
            running_stages.add(run.stage)

    # Attach run info to agent metadata
    for agent in agent_metadata:
        stage = agent["name"]
        agent["last_run"] = latest_by_stage.get(stage)
        agent["is_running"] = stage in running_stages

    return templates.TemplateResponse(
        "agents.html",
        {
            "request": request,
            "agents": agent_metadata,
            "running_stages": running_stages,
        },
    )
