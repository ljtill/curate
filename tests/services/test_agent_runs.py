"""Tests for agent_runs service functions."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from agent_stack.services.agent_runs import (
    get_agents_page_data,
    group_runs_by_invocation,
)


class TestGroupRunsByInvocation:
    """Tests for group_runs_by_invocation."""

    def test_empty_list(self) -> None:
        """Return empty list for empty input."""
        assert group_runs_by_invocation([]) == []

    def test_single_orchestrator_run(self) -> None:
        """Single orchestrator run creates one group."""
        run = MagicMock()
        run.stage = "orchestrator"
        result = group_runs_by_invocation([run])
        assert len(result) == 1
        assert result[0] == [run]

    def test_orchestrator_then_stages(self) -> None:
        """Orchestrator followed by stage runs forms one group."""
        orch = MagicMock()
        orch.stage = "orchestrator"
        fetch = MagicMock()
        fetch.stage = "fetch"
        review = MagicMock()
        review.stage = "review"
        result = group_runs_by_invocation([orch, fetch, review])
        assert len(result) == 1
        assert result[0] == [orch, fetch, review]

    _EXPECTED_GROUPS = 2

    def test_multiple_invocations(self) -> None:
        """Multiple orchestrator runs split into separate groups."""
        orch1 = MagicMock()
        orch1.stage = "orchestrator"
        fetch1 = MagicMock()
        fetch1.stage = "fetch"
        orch2 = MagicMock()
        orch2.stage = "orchestrator"
        fetch2 = MagicMock()
        fetch2.stage = "fetch"
        result = group_runs_by_invocation([orch1, fetch1, orch2, fetch2])
        assert len(result) == self._EXPECTED_GROUPS
        assert result[0] == [orch1, fetch1]
        assert result[1] == [orch2, fetch2]

    def test_stages_without_leading_orchestrator(self) -> None:
        """Stage runs without a leading orchestrator still form a group."""
        fetch = MagicMock()
        fetch.stage = "fetch"
        review = MagicMock()
        review.stage = "review"
        result = group_runs_by_invocation([fetch, review])
        assert len(result) == 1
        assert result[0] == [fetch, review]


class TestGetAgentsPageData:
    """Tests for get_agents_page_data."""

    async def test_returns_agents_and_running_stages(self) -> None:
        """Verify returned dict contains agents and running_stages keys."""
        orchestrator = MagicMock()
        runs_repo = MagicMock()
        runs_repo.list_recent_by_stage = AsyncMock(return_value=[])

        fake_metadata = [
            {
                "name": "fetch",
                "description": "Fetches content",
                "tools": [],
                "options": {},
                "middleware": [],
                "instructions": {"preview": "", "full": ""},
            }
        ]

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "agent_stack.services.agent_runs.get_agent_metadata",
                lambda _: fake_metadata,
            )
            result = await get_agents_page_data(orchestrator, runs_repo)

        assert "agents" in result
        assert "running_stages" in result
        assert len(result["agents"]) == 1
        assert result["agents"][0]["recent_runs"] == []
        assert result["agents"][0]["last_run"] is None
        assert result["agents"][0]["is_running"] is False
