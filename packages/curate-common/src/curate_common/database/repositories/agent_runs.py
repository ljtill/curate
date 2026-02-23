"""Repository for the agent_runs container (partitioned by /edition_id)."""

from __future__ import annotations

from datetime import UTC, datetime

from curate_common.database.repositories.base import BaseRepository
from curate_common.models.agent_run import AgentRun, AgentRunStatus, AgentStage


class AgentRunRepository(BaseRepository[AgentRun]):
    """Provide data access for the agent_runs container."""

    container_name = "agent_runs"
    model_class = AgentRun

    async def list_by_edition(self, edition_id: str) -> list[AgentRun]:
        """Fetch all runs for a specific edition."""
        runs = await self.query(
            "SELECT * FROM c WHERE c.edition_id = @edition_id"
            " AND NOT IS_DEFINED(c.deleted_at)",
            [{"name": "@edition_id", "value": edition_id}],
        )
        return sorted(runs, key=lambda r: r.started_at or r.created_at, reverse=True)

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
        runs = await self.query(
            "SELECT * FROM c WHERE ARRAY_CONTAINS(@trigger_ids, c.trigger_id)"
            " AND NOT IS_DEFINED(c.deleted_at)",
            [{"name": "@trigger_ids", "value": trigger_ids}],
        )
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

    async def count_by_status(self, limit: int = 100) -> dict[str, int]:
        """Return recent run counts grouped by status."""
        counts: dict[str, int] = {}
        async for item in self._container.query_items(
            "SELECT TOP @limit c.status FROM c"
            " WHERE NOT IS_DEFINED(c.deleted_at)"
            " ORDER BY c.started_at DESC",
            parameters=[{"name": "@limit", "value": limit}],
        ):
            status = item["status"]
            counts[status] = counts.get(status, 0) + 1
        return counts

    async def aggregate_token_usage(self, limit: int = 100) -> dict[str, int]:
        """Return total token usage across recent runs."""
        totals = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
        async for item in self._container.query_items(
            "SELECT TOP @limit c.usage FROM c"
            " WHERE c.usage != null"
            " AND NOT IS_DEFINED(c.deleted_at)"
            " ORDER BY c.started_at DESC",
            parameters=[{"name": "@limit", "value": limit}],
        ):
            usage = item.get("usage") or {}
            totals["input_tokens"] += usage.get("input_tokens", 0)
            totals["output_tokens"] += usage.get("output_tokens", 0)
            totals["total_tokens"] += usage.get("total_tokens", 0)
        return totals

    async def recover_orphaned_runs(self) -> int:
        """Transition any RUNNING runs without a completed_at to FAILED.

        Called on startup to clean up runs orphaned by a prior crash.
        """
        orphaned = await self.query(
            "SELECT * FROM c WHERE c.status = @status"
            " AND NOT IS_DEFINED(c.completed_at)"
            " AND NOT IS_DEFINED(c.deleted_at)",
            [{"name": "@status", "value": AgentRunStatus.RUNNING.value}],
        )
        for run in orphaned:
            run.status = AgentRunStatus.FAILED
            run.completed_at = datetime.now(UTC)
            run.output = {"error": "Recovered after process restart"}
            await self.update(run, run.edition_id)
        return len(orphaned)

    async def clear_all(self) -> int:
        """Soft-delete all non-deleted agent runs. Return count cleared."""
        runs = await self.query(
            "SELECT * FROM c WHERE NOT IS_DEFINED(c.deleted_at)",
            [],
        )
        for run in runs:
            await self.soft_delete(run, run.edition_id)
        return len(runs)

    async def list_recent_failures(self, limit: int = 5) -> list[AgentRun]:
        """Fetch the most recent failed agent runs."""
        return await self.query(
            "SELECT TOP @limit * FROM c WHERE c.status = @status"
            " AND NOT IS_DEFINED(c.deleted_at) ORDER BY c.started_at DESC",
            [
                {"name": "@status", "value": AgentRunStatus.FAILED.value},
                {"name": "@limit", "value": limit},
            ],
        )
