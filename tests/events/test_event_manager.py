"""Tests for the EventManager SSE singleton."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_stack.events import EventManager


@pytest.fixture(autouse=True)
def reset_event_manager():
    """Reset the EventManager singleton between tests."""
    EventManager._instance = None
    yield
    EventManager._instance = None


@pytest.mark.unit
class TestEventManagerPublish:
    async def test_publish_broadcasts_to_all_queues(self):
        manager = EventManager.get_instance()
        q1: asyncio.Queue = asyncio.Queue()
        q2: asyncio.Queue = asyncio.Queue()
        manager._queues.extend([q1, q2])

        await manager.publish("status", {"stage": "fetch"})

        msg1 = q1.get_nowait()
        msg2 = q2.get_nowait()
        assert msg1["event"] == "status"
        assert json.loads(msg1["data"])["stage"] == "fetch"
        assert msg2 == msg1

    async def test_publish_with_string_data(self):
        manager = EventManager.get_instance()
        q: asyncio.Queue = asyncio.Queue()
        manager._queues.append(q)

        await manager.publish("ping", "hello")

        msg = q.get_nowait()
        assert msg["data"] == "hello"

    async def test_publish_with_no_subscribers(self):
        manager = EventManager.get_instance()
        await manager.publish("test", {"ok": True})


@pytest.mark.unit
class TestEventManagerEventGenerator:
    async def test_yields_queued_messages(self):
        manager = EventManager.get_instance()
        request = MagicMock()
        request.is_disconnected = AsyncMock(side_effect=[False, True])

        gen = manager._event_generator(request)
        msg = {"event": "test", "data": "payload"}

        async def _produce():
            await asyncio.sleep(0.01)
            for q in manager._queues:
                await q.put(msg)

        task = asyncio.create_task(_produce())
        result = await gen.__anext__()
        task.cancel()

        assert result["event"] == "test"
        assert result["data"] == "payload"

    async def test_sends_ping_on_timeout(self):
        manager = EventManager.get_instance()
        request = MagicMock()
        request.is_disconnected = AsyncMock(side_effect=[False, True])

        gen = manager._event_generator(request)

        with patch("agent_stack.events.asyncio.wait_for", side_effect=TimeoutError):
            result = await gen.__anext__()

        assert result["event"] == "ping"

    async def test_removes_queue_on_disconnect(self):
        manager = EventManager.get_instance()
        request = MagicMock()
        request.is_disconnected = AsyncMock(return_value=True)

        gen = manager._event_generator(request)
        with pytest.raises(StopAsyncIteration):
            await gen.__anext__()

        assert len(manager._queues) == 0


@pytest.mark.unit
class TestEventManagerCreateResponse:
    def test_creates_sse_response(self):
        manager = EventManager.get_instance()
        request = MagicMock()

        with patch("agent_stack.events.EventSourceResponse") as MockSSE:
            result = manager.create_response(request)
            MockSSE.assert_called_once()
            assert result == MockSSE.return_value
