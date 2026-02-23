"""Tests for dashboard route handler."""

from unittest.mock import AsyncMock, MagicMock, patch

from curate_web.routes.dashboard import dashboard


async def test_dashboard_renders_template() -> None:
    """Verify dashboard renders template."""
    request = MagicMock()
    request.app.state.templates = MagicMock()
    request.app.state.templates.TemplateResponse = MagicMock(return_value="<html>")
    request.app.state.cosmos = MagicMock()
    request.app.state.cosmos.database = MagicMock()

    with patch("curate_web.routes.dashboard.AgentRunRepository") as mock_repo_cls:
        mock_repo_cls.return_value.list_recent = AsyncMock(return_value=[])
        await dashboard(request)

    request.app.state.templates.TemplateResponse.assert_called_once_with(
        "dashboard.html",
        {"request": request, "recent_runs": []},
    )
