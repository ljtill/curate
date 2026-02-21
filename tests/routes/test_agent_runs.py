"""Tests for agent runs route."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_stack.routes.agent_runs import recent_runs


@pytest.mark.unit
class TestRecentRunsRoute:
    """Test the Recent Runs Route."""

    async def test_returns_recent_runs(self) -> None:
        """Verify returns recent runs."""
        request = MagicMock()
        request.app.state.templates = MagicMock()
        request.app.state.cosmos = MagicMock()

        mock_repo = AsyncMock()
        mock_repo.list_recent.return_value = []

        with patch("agent_stack.routes.agent_runs.AgentRunRepository", return_value=mock_repo):
            await recent_runs(request)

        mock_repo.list_recent.assert_called_once_with(20)
        request.app.state.templates.TemplateResponse.assert_called_once()
        call_args = request.app.state.templates.TemplateResponse.call_args
        assert call_args[0][0] == "partials/agent_run_item.html"
        assert "runs" in call_args[0][1]
