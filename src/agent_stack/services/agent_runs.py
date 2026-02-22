"""Agent run query service — data retrieval and grouping for agent runs."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from agent_stack.agents.registry import get_agent_metadata
from agent_stack.models.agent_run import AgentRun, AgentStage

if TYPE_CHECKING:
    from agent_stack.database.repositories.agent_runs import AgentRunRepository
    from agent_stack.pipeline.orchestrator import PipelineOrchestrator


def group_runs_by_invocation(runs: list[AgentRun]) -> list[list[AgentRun]]:
    """Group a flat list of agent runs into pipeline invocations.

    Each orchestrator run marks the start of a new invocation. Stages that
    follow belong to that group until the next orchestrator run appears.
    """
    if not runs:
        return []

    groups: list[list[AgentRun]] = []
    for run in runs:
        if run.stage == "orchestrator" or not groups:
            groups.append([])
        groups[-1].append(run)
    return groups


def _run_to_dict(run: AgentRun) -> dict[str, Any]:
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


async def get_agents_page_data(
    orchestrator: PipelineOrchestrator,
    runs_repo: AgentRunRepository,
) -> dict[str, Any]:
    """Assemble agent metadata enriched with recent runs for the Agents page."""
    agent_metadata = get_agent_metadata(orchestrator)

    stages = [
        AgentStage.ORCHESTRATOR,
        AgentStage.FETCH,
        AgentStage.REVIEW,
        AgentStage.DRAFT,
        AgentStage.EDIT,
        AgentStage.PUBLISH,
    ]
    runs_by_stage: dict[str, list[AgentRun]] = {}
    running_stages: set[str] = set()
    for stage in stages:
        stage_runs = await runs_repo.list_recent_by_stage(stage, limit=5)
        runs_by_stage[stage.value] = stage_runs
        if any(r.status == "running" for r in stage_runs):
            running_stages.add(stage.value)

    for agent in agent_metadata:
        stage = agent["name"]
        stage_runs = runs_by_stage.get(stage, [])
        agent["recent_runs"] = stage_runs
        agent["last_run"] = _run_to_dict(stage_runs[0]) if stage_runs else None
        agent["is_running"] = stage in running_stages

    return {
        "agents": agent_metadata,
        "running_stages": running_stages,
    }
