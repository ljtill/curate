"""Tests for SSE events route."""

from unittest.mock import MagicMock, patch

import pytest

from agent_stack.routes.events import events


@pytest.mark.unit
class TestEventsRoute:
    """Test the Events Route."""

    async def test_returns_sse_response(self) -> None:
        """Verify returns sse response."""
        request = MagicMock()
        mock_manager = MagicMock()
        mock_response = MagicMock()
        mock_manager.create_response.return_value = mock_response

        with patch("agent_stack.routes.events.EventManager") as mock_em_cls:
            mock_em_cls.get_instance.return_value = mock_manager

            result = await events(request)

        assert result == mock_response
        mock_manager.create_response.assert_called_once_with(request)
