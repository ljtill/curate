"""Tests for AgentRunRepository custom query methods."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from curate_common.database.repositories.agent_runs import AgentRunRepository
from curate_common.models.agent_run import AgentRun, AgentRunStatus, AgentStage

_EXPECTED_TRIGGER_COUNT = 2


class TestAgentRunRepository:
    """Test the Agent Run Repository."""

    @pytest.fixture
    def repo(self) -> AgentRunRepository:
        """Create a repo for testing."""
        mock_db = MagicMock()
        mock_container = AsyncMock()
        mock_db.get_container_client.return_value = mock_container
        return AgentRunRepository(mock_db)

    async def test_get_by_trigger(self, repo: AgentRunRepository) -> None:
        """Verify get by trigger."""
        run = AgentRun(
            stage=AgentStage.FETCH, trigger_id="link-1", status=AgentRunStatus.COMPLETED
        )
        repo.query = AsyncMock(return_value=[run])

        result = await repo.get_by_trigger("link-1")

        assert len(result) == 1
        assert result[0].trigger_id == "link-1"

    async def test_get_by_stage(self, repo: AgentRunRepository) -> None:
        """Verify get by stage."""
        repo.query = AsyncMock(return_value=[])

        result = await repo.get_by_stage("link-1", AgentStage.REVIEW)

        assert result == []
        call_args = repo.query.call_args
        assert "@stage" in call_args[0][0]

    async def test_get_by_triggers_empty_list(self, repo: AgentRunRepository) -> None:
        """Verify get by triggers empty list."""
        result = await repo.get_by_triggers([])

        assert result == []

    async def test_get_by_triggers_merges_results(
        self, repo: AgentRunRepository
    ) -> None:
        """Verify get by triggers merges results."""
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
        repo.query = AsyncMock(return_value=[run1, run2])

        result = await repo.get_by_triggers(["link-1", "link-2"])

        assert len(result) == _EXPECTED_TRIGGER_COUNT
        assert result[0].trigger_id == "link-2"
        repo.query.assert_awaited_once()
        query, params = repo.query.call_args.args
        assert "ARRAY_CONTAINS" in query
        assert params[0]["name"] == "@trigger_ids"
        assert params[0]["value"] == ["link-1", "link-2"]

    async def test_list_recent(self, repo: AgentRunRepository) -> None:
        """Verify list recent."""
        repo.query = AsyncMock(return_value=[])

        result = await repo.list_recent(10)

        assert result == []
        call_args = repo.query.call_args
        assert "@limit" in call_args[0][0]

    async def test_list_recent_by_stage(self, repo: AgentRunRepository) -> None:
        """Verify list recent by stage."""
        repo.query = AsyncMock(return_value=[])

        result = await repo.list_recent_by_stage(AgentStage.DRAFT, limit=3)

        assert result == []
        call_args = repo.query.call_args
        assert "@stage" in call_args[0][0]

    async def test_recover_orphaned_runs(self, repo: AgentRunRepository) -> None:
        """Verify recover_orphaned_runs transitions RUNNING runs to FAILED."""
        orphan = AgentRun(
            id="run-orphan",
            stage=AgentStage.FETCH,
            trigger_id="link-1",
            status=AgentRunStatus.RUNNING,
        )
        repo.query = AsyncMock(return_value=[orphan])
        repo.update = AsyncMock()

        count = await repo.recover_orphaned_runs()

        assert count == 1
        assert orphan.status == AgentRunStatus.FAILED
        assert orphan.completed_at is not None
        assert orphan.output == {"error": "Recovered after process restart"}
        repo.update.assert_called_once_with(orphan, "link-1")
