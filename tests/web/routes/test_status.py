"""Tests for the status route."""

from unittest.mock import AsyncMock, MagicMock, patch

from curate_web.routes.status import status
from tests.web.routes.runtime_helpers import make_runtime


class TestStatusRoute:
    """Test the Status Route."""

    async def test_renders_status_page(self) -> None:
        """Verify renders status page."""
        request = MagicMock()
        request.app.state.cosmos = MagicMock()
        request.app.state.settings = MagicMock()
        request.app.state.storage = MagicMock()
        request.app.state.templates = MagicMock()
        request.app.state.runtime = make_runtime(
            cosmos=request.app.state.cosmos,
            settings=request.app.state.settings,
            storage=request.app.state.storage,
            templates=request.app.state.templates,
            start_time=MagicMock(),
        )

        mock_results = [{"name": "cosmos", "status": "healthy"}]

        with patch(
            "curate_web.routes.status.check_all",
            new_callable=AsyncMock,
            return_value=mock_results,
        ):
            await status(request)

        request.app.state.templates.TemplateResponse.assert_called_once()
        call_args = request.app.state.templates.TemplateResponse.call_args
        assert call_args[0][0] == "status.html"
        assert call_args[0][1]["checks"] == mock_results

    async def test_renders_status_page_without_foundry_config(self) -> None:
        """Verify status renders when Foundry is not configured."""
        request = MagicMock()
        request.app.state.cosmos = MagicMock()
        request.app.state.settings = MagicMock()
        request.app.state.settings.foundry.project_endpoint = ""
        request.app.state.storage = MagicMock()
        request.app.state.templates = MagicMock()
        request.app.state.runtime = make_runtime(
            cosmos=request.app.state.cosmos,
            settings=request.app.state.settings,
            storage=request.app.state.storage,
            templates=request.app.state.templates,
            start_time=MagicMock(),
        )

        mock_results = [{"name": "Foundry", "healthy": False}]

        with patch(
            "curate_web.routes.status.check_all",
            new_callable=AsyncMock,
            return_value=mock_results,
        ):
            await status(request)

        request.app.state.templates.TemplateResponse.assert_called_once()
        call_args = request.app.state.templates.TemplateResponse.call_args
        assert call_args[0][0] == "status.html"
        assert call_args[0][1]["checks"] == mock_results
