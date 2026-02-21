"""Agents route — read-only view of the agent pipeline topology and configuration."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from agent_stack.agents.registry import get_agent_metadata
from agent_stack.database.repositories.agent_runs import AgentRunRepository
from agent_stack.models.agent_run import AgentRun, AgentStage

router = APIRouter(tags=["agents"])


@router.get("/agents", response_class=HTMLResponse)
async def agents_page(request: Request) -> HTMLResponse:
    """Render the Agents page showing pipeline topology and agent details."""
    templates = request.app.state.templates
    cosmos = request.app.state.cosmos
    orchestrator = request.app.state.processor.orchestrator

    agent_metadata = get_agent_metadata(orchestrator)

    runs_repo = AgentRunRepository(cosmos.database)

    # Fetch recent runs per stage
    stages = [
        AgentStage.FETCH,
        AgentStage.REVIEW,
        AgentStage.DRAFT,
        AgentStage.EDIT,
        AgentStage.PUBLISH,
    ]
    runs_by_stage: dict[str, list] = {}
    running_stages: set[str] = set()
    for stage in stages:
        stage_runs = await runs_repo.list_recent_by_stage(stage, limit=5)
        runs_by_stage[stage.value] = stage_runs
        if any(r.status == "running" for r in stage_runs):
            running_stages.add(stage.value)

    # Attach run info to agent metadata
    for agent in agent_metadata:
        stage = agent["name"]
        stage_runs = runs_by_stage.get(stage, [])
        agent["recent_runs"] = stage_runs
        agent["last_run"] = _run_to_dict(stage_runs[0]) if stage_runs else None
        agent["is_running"] = stage in running_stages

    return templates.TemplateResponse(
        "agents.html",
        {
            "request": request,
            "agents": agent_metadata,
            "running_stages": running_stages,
        },
    )


def _run_to_dict(run: AgentRun) -> dict:
    """Convert an AgentRun to a template-friendly dict."""
    return {
        "id": run.id,
        "status": run.status,
        "started_at": run.started_at,
        "completed_at": run.completed_at,
        "usage": run.usage,
        "trigger_id": run.trigger_id,
        "input": run.input,
        "output": run.output,
    }
