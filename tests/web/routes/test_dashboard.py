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

    with (
        patch("curate_web.routes.dashboard.EditionRepository") as mock_ed_cls,
        patch("curate_web.routes.dashboard.AgentRunRepository") as mock_runs_cls,
    ):
        mock_ed_cls.return_value.list_all = AsyncMock(return_value=[])
        mock_ed_cls.return_value.get_active = AsyncMock(return_value=None)
        mock_runs_cls.return_value.list_recent = AsyncMock(return_value=[])
        await dashboard(request)

    request.app.state.templates.TemplateResponse.assert_called_once_with(
        "dashboard.html",
        {
            "request": request,
            "editions": [],
            "active_edition": None,
            "recent_runs": [],
        },
    )
