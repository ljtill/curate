"""Tests for dashboard route handler."""

from unittest.mock import AsyncMock, MagicMock, patch

from curate_web.routes.dashboard import dashboard
from tests.web.routes.runtime_helpers import make_runtime


async def test_dashboard_renders_template() -> None:
    """Verify dashboard renders template."""
    request = MagicMock()
    request.app.state.templates = MagicMock()
    request.app.state.templates.TemplateResponse = MagicMock(return_value="<html>")
    request.app.state.cosmos = MagicMock()
    request.app.state.cosmos.database = MagicMock()
    request.app.state.runtime = make_runtime(
        cosmos=request.app.state.cosmos,
        templates=request.app.state.templates,
    )

    mock_ed_repo = AsyncMock()
    mock_ed_repo.list_all.return_value = []
    mock_ed_repo.get_active.return_value = None
    mock_runs_repo = AsyncMock()
    mock_runs_repo.list_recent.return_value = []

    with (
        patch(
            "curate_web.routes.dashboard.get_edition_repository",
            return_value=mock_ed_repo,
        ),
        patch(
            "curate_web.routes.dashboard.get_agent_run_repository",
            return_value=mock_runs_repo,
        ),
    ):
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
