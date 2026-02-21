"""Tests for AgentRunRepository custom query methods."""

from datetime import UTC
from unittest.mock import AsyncMock, MagicMock

import pytest

from agent_stack.database.repositories.agent_runs import AgentRunRepository
from agent_stack.models.agent_run import AgentRun, AgentRunStatus, AgentStage


@pytest.mark.unit
class TestAgentRunRepository:
    @pytest.fixture
    def repo(self):
        mock_db = MagicMock()
        mock_container = AsyncMock()
        mock_db.get_container_client.return_value = mock_container
        return AgentRunRepository(mock_db)

    async def test_get_by_trigger(self, repo):
        run = AgentRun(stage=AgentStage.FETCH, trigger_id="link-1", status=AgentRunStatus.COMPLETED)
        repo.query = AsyncMock(return_value=[run])

        result = await repo.get_by_trigger("link-1")

        assert len(result) == 1
        assert result[0].trigger_id == "link-1"

    async def test_get_by_stage(self, repo):
        repo.query = AsyncMock(return_value=[])

        result = await repo.get_by_stage("link-1", AgentStage.REVIEW)

        assert result == []
        call_args = repo.query.call_args
        assert "@stage" in call_args[0][0]

    async def test_get_by_triggers_empty_list(self, repo):
        result = await repo.get_by_triggers([])

        assert result == []

    async def test_get_by_triggers_merges_results(self, repo):
        from datetime import datetime

        run1 = AgentRun(
            stage=AgentStage.FETCH,
            trigger_id="link-1",
            status=AgentRunStatus.COMPLETED,
            started_at=datetime(2025, 1, 1, tzinfo=UTC),
        )
        run2 = AgentRun(
            stage=AgentStage.REVIEW,
            trigger_id="link-2",
            status=AgentRunStatus.COMPLETED,
            started_at=datetime(2025, 1, 2, tzinfo=UTC),
        )
        repo.query = AsyncMock(side_effect=[[run1], [run2]])

        result = await repo.get_by_triggers(["link-1", "link-2"])

        assert len(result) == 2
        # Sorted by started_at descending
        assert result[0].trigger_id == "link-2"

    async def test_list_recent(self, repo):
        repo.query = AsyncMock(return_value=[])

        result = await repo.list_recent(10)

        assert result == []
        call_args = repo.query.call_args
        assert "@limit" in call_args[0][0]

    async def test_list_recent_by_stage(self, repo):
        repo.query = AsyncMock(return_value=[])

        result = await repo.list_recent_by_stage(AgentStage.DRAFT, limit=3)

        assert result == []
        call_args = repo.query.call_args
        assert "@stage" in call_args[0][0]
