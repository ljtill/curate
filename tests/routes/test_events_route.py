"""Tests for SSE events route."""

from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.unit
class TestEventsRoute:
    async def test_returns_sse_response(self):
        from agent_stack.routes.events import events

        request = MagicMock()
        mock_manager = MagicMock()
        mock_response = MagicMock()
        mock_manager.create_response.return_value = mock_response

        with patch("agent_stack.routes.events.EventManager") as MockEM:
            MockEM.get_instance.return_value = mock_manager

            result = await events(request)

        assert result == mock_response
        mock_manager.create_response.assert_called_once_with(request)
