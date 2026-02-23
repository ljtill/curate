"""Tests for agent runs route."""

from unittest.mock import AsyncMock, MagicMock, patch

from curate_web.routes.agent_runs import recent_runs
from tests.web.routes.runtime_helpers import make_runtime


class TestRecentRunsRoute:
    """Test the Recent Runs Route."""

    async def test_returns_recent_runs(self) -> None:
        """Verify returns recent runs."""
        request = MagicMock()
        request.app.state.templates = MagicMock()
        request.app.state.cosmos = MagicMock()
        request.app.state.runtime = make_runtime(
            cosmos=request.app.state.cosmos,
            templates=request.app.state.templates,
        )

        mock_repo = AsyncMock()
        mock_repo.list_recent.return_value = []

        with patch(
            "curate_web.routes.agent_runs.get_agent_run_repository",
            return_value=mock_repo,
        ):
            await recent_runs(request)

        mock_repo.list_recent.assert_called_once_with(20)
        request.app.state.templates.TemplateResponse.assert_called_once()
        call_args = request.app.state.templates.TemplateResponse.call_args
        assert call_args[0][0] == "partials/agent_run_item.html"
        assert "runs" in call_args[0][1]
