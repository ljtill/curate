"""AgentRun lifecycle management for the pipeline orchestrator."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from curate_common.models.agent_run import AgentRun, AgentStage

if TYPE_CHECKING:
    from curate_common.database.repositories.agent_runs import AgentRunRepository
    from curate_common.events import EventPublisher


class RunManager:
    """Encapsulates creation and event-publishing for AgentRun records."""

    def __init__(
        self,
        agent_runs_repo: AgentRunRepository,
        events: EventPublisher,
    ) -> None:
        """Initialize with repository and event publisher."""
        self._agent_runs_repo = agent_runs_repo
        self._events = events

    async def create_orchestrator_run(
        self, trigger_id: str, input_data: dict
    ) -> AgentRun:
        """Create an agent run record for the orchestrator itself."""
        run = AgentRun(
            stage=AgentStage.ORCHESTRATOR,
            trigger_id=trigger_id,
            input=input_data,
            started_at=datetime.now(UTC),
        )
        await self._agent_runs_repo.create(run)
        await self._events.publish(
            "agent-run-start",
            {
                "id": run.id,
                "stage": run.stage,
                "trigger_id": run.trigger_id,
                "status": run.status,
                "started_at": (run.started_at.isoformat() if run.started_at else None),
            },
        )
        return run

    async def publish_run_event(self, run: AgentRun) -> None:
        """Publish an SSE event when a run completes or fails."""
        await self._events.publish(
            "agent-run-complete",
            {
                "id": run.id,
                "stage": run.stage,
                "trigger_id": run.trigger_id,
                "status": run.status,
                "output": run.output,
                "started_at": (run.started_at.isoformat() if run.started_at else None),
                "completed_at": (
                    run.completed_at.isoformat() if run.completed_at else None
                ),
            },
        )

    @staticmethod
    def normalize_usage(usage: dict | None) -> dict | None:
        """Normalize framework usage_details to a consistent schema."""
        if not usage:
            return None
        input_tokens = usage.get("input_token_count", 0) or 0
        output_tokens = usage.get("output_token_count", 0) or 0
        return {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": usage.get("total_token_count", 0)
            or input_tokens + output_tokens,
        }
