"""Tests for the status route."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_stack.routes.status import status


@pytest.mark.unit
class TestStatusRoute:
    """Test the Status Route."""

    async def test_renders_status_page(self) -> None:
        """Verify renders status page."""
        request = MagicMock()
        request.app.state.cosmos = MagicMock()
        request.app.state.settings = MagicMock()
        request.app.state.processor = MagicMock()
        request.app.state.storage = MagicMock()
        request.app.state.templates = MagicMock()

        mock_results = [{"name": "cosmos", "status": "healthy"}]

        with (
            patch("agent_stack.routes.status.create_chat_client"),
            patch(
                "agent_stack.routes.status.check_all",
                new_callable=AsyncMock,
                return_value=mock_results,
            ),
        ):
            await status(request)

        request.app.state.templates.TemplateResponse.assert_called_once()
        call_args = request.app.state.templates.TemplateResponse.call_args
        assert call_args[0][0] == "status.html"
        assert call_args[0][1]["checks"] == mock_results

    async def test_handles_missing_storage(self) -> None:
        """Verify handles missing storage."""
        request = MagicMock()
        request.app.state.cosmos = MagicMock()
        request.app.state.settings = MagicMock()
        request.app.state.processor = MagicMock()
        request.app.state.storage = None
        # getattr with default should return None
        del request.app.state.storage
        request.app.state.templates = MagicMock()

        with (
            patch("agent_stack.routes.status.create_chat_client"),
            patch(
                "agent_stack.routes.status.check_all",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            await status(request)

        request.app.state.templates.TemplateResponse.assert_called_once()
