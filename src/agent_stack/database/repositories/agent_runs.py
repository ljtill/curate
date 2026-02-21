"""Repository for the agent_runs container (partitioned by /trigger_id)."""

from __future__ import annotations

from agent_stack.database.repositories.base import BaseRepository
from agent_stack.models.agent_run import AgentRun, AgentStage


class AgentRunRepository(BaseRepository[AgentRun]):
    """Provide data access for the agent_runs container."""

    container_name = "agent_runs"
    model_class = AgentRun

    async def get_by_trigger(self, trigger_id: str) -> list[AgentRun]:
        """Fetch all runs triggered by a specific document."""
        return await self.query(
            "SELECT * FROM c WHERE c.trigger_id = @trigger_id"
            " AND NOT IS_DEFINED(c.deleted_at)",
            [{"name": "@trigger_id", "value": trigger_id}],
        )

    async def get_by_stage(self, trigger_id: str, stage: AgentStage) -> list[AgentRun]:
        """Fetch runs for a specific stage and trigger."""
        return await self.query(
            "SELECT * FROM c"
            " WHERE c.trigger_id = @trigger_id"
            " AND c.stage = @stage"
            " AND NOT IS_DEFINED(c.deleted_at)",
            [
                {"name": "@trigger_id", "value": trigger_id},
                {"name": "@stage", "value": stage.value},
            ],
        )

    async def get_by_triggers(self, trigger_ids: list[str]) -> list[AgentRun]:
        """Fetch all runs for a list of trigger IDs."""
        if not trigger_ids:
            return []
        runs: list[AgentRun] = []
        for tid in trigger_ids:
            runs.extend(await self.get_by_trigger(tid))
        return sorted(runs, key=lambda r: r.started_at or r.created_at, reverse=True)

    async def list_recent(self, limit: int = 20) -> list[AgentRun]:
        """Fetch the most recent agent runs across all triggers."""
        return await self.query(
            "SELECT TOP @limit * FROM c"
            " WHERE NOT IS_DEFINED(c.deleted_at)"
            " ORDER BY c.started_at DESC",
            [{"name": "@limit", "value": limit}],
        )

    async def list_recent_by_stage(
        self, stage: AgentStage, limit: int = 5
    ) -> list[AgentRun]:
        """Fetch the most recent agent runs for a specific stage."""
        return await self.query(
            "SELECT TOP @limit * FROM c WHERE c.stage = @stage"
            " AND NOT IS_DEFINED(c.deleted_at) ORDER BY c.started_at DESC",
            [
                {"name": "@stage", "value": stage.value},
                {"name": "@limit", "value": limit},
            ],
        )
