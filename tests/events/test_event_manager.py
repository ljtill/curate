"""Tests for the EventManager SSE singleton."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_stack.events import EventManager


@pytest.fixture(autouse=True)
def reset_event_manager() -> None:
    """Reset the EventManager singleton between tests."""
    EventManager.instance = None
    yield
    EventManager.instance = None


class TestEventManagerPublish:
    """Test the Event Manager Publish."""

    async def test_publish_broadcasts_to_all_queues(self) -> None:
        """Verify publish broadcasts to all queues."""
        manager = EventManager.get_instance()
        q1: asyncio.Queue = asyncio.Queue()
        q2: asyncio.Queue = asyncio.Queue()
        manager.queues.extend([q1, q2])

        await manager.publish("status", {"stage": "fetch"})

        msg1 = q1.get_nowait()
        msg2 = q2.get_nowait()
        assert msg1["event"] == "status"
        assert json.loads(msg1["data"])["stage"] == "fetch"
        assert msg2 == msg1

    async def test_publish_with_string_data(self) -> None:
        """Verify publish with string data."""
        manager = EventManager.get_instance()
        q: asyncio.Queue = asyncio.Queue()
        manager.queues.append(q)

        await manager.publish("ping", "hello")

        msg = q.get_nowait()
        assert msg["data"] == "hello"

    async def test_publish_with_no_subscribers(self) -> None:
        """Verify publish with no subscribers."""
        manager = EventManager.get_instance()
        await manager.publish("test", {"ok": True})


class TestEventManagerEventGenerator:
    """Test the Event Manager Event Generator."""

    async def test_yields_queued_messages(self) -> None:
        """Verify yields queued messages."""
        manager = EventManager.get_instance()
        request = MagicMock()
        request.is_disconnected = AsyncMock(side_effect=[False, True])

        gen = manager.event_generator(request)
        msg = {"event": "test", "data": "payload"}

        async def _produce() -> None:
            await asyncio.sleep(0.01)
            for q in manager.queues:
                await q.put(msg)

        task = asyncio.create_task(_produce())
        result = await gen.__anext__()
        task.cancel()

        assert result["event"] == "test"
        assert result["data"] == "payload"

    async def test_skips_on_timeout_and_rechecks(self) -> None:
        """Verify timeout doesn't yield; loop rechecks disconnect."""
        manager = EventManager.get_instance()
        request = MagicMock()
        request.is_disconnected = AsyncMock(side_effect=[False, True])

        gen = manager.event_generator(request)

        with (
            patch("agent_stack.events.asyncio.wait_for", side_effect=TimeoutError),
            pytest.raises(StopAsyncIteration),
        ):
            await gen.__anext__()

    async def test_removes_queue_on_disconnect(self) -> None:
        """Verify removes queue on disconnect."""
        manager = EventManager.get_instance()
        request = MagicMock()
        request.is_disconnected = AsyncMock(return_value=True)

        gen = manager.event_generator(request)
        with pytest.raises(StopAsyncIteration):
            await gen.__anext__()

        assert len(manager.queues) == 0


class TestEventManagerCreateResponse:
    """Test the Event Manager Create Response."""

    def test_creates_sse_response(self) -> None:
        """Verify creates sse response."""
        manager = EventManager.get_instance()
        request = MagicMock()

        with patch("agent_stack.events.EventSourceResponse") as mock_sse_cls:
            result = manager.create_response(request)
            mock_sse_cls.assert_called_once()
            assert result == mock_sse_cls.return_value
