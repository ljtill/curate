"""Tests for the SSE event manager."""

import pytest

from curate_web.events import EventManager


@pytest.fixture(autouse=True)
def reset_event_manager() -> None:
    """Reset the singleton between tests."""
    EventManager.instance = None
    yield
    EventManager.instance = None


def test_get_instance_returns_singleton() -> None:
    """Verify get instance returns singleton."""
    mgr1 = EventManager.get_instance()
    mgr2 = EventManager.get_instance()
    assert mgr1 is mgr2


async def test_publish_to_empty_queues() -> None:
    """Verify publish to empty queues."""
    mgr = EventManager.get_instance()
    await mgr.publish("test", {"key": "value"})
