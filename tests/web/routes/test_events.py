"""Tests for the SSE events route."""

from unittest.mock import MagicMock

import pytest

from curate_web.routes.events import events
from tests.web.routes.runtime_helpers import make_runtime


async def test_events_uses_runtime_manager() -> None:
    """Verify /events always uses the runtime-managed EventManager."""
    request = MagicMock()
    manager = MagicMock()
    manager.create_response = MagicMock(return_value=MagicMock())
    request.app.state.runtime = make_runtime(event_manager=manager)

    response = await events(request)

    manager.create_response.assert_called_once_with(request)
    assert response is manager.create_response.return_value


async def test_events_requires_runtime() -> None:
    """Verify /events raises when app runtime is missing."""
    request = MagicMock()
    with pytest.raises(TypeError, match="WebRuntime is not initialized"):
        await events(request)
