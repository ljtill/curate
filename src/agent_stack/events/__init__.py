"""SSE event manager for real-time dashboard updates."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING, Any

from sse_starlette.sse import EventSourceResponse

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from fastapi import Request

logger = logging.getLogger(__name__)


class EventManager:
    """Manages SSE connections and broadcasts events to all connected clients."""

    instance: EventManager | None = None

    def __init__(self) -> None:
        """Initialize the event manager with an empty subscriber list."""
        self.queues: list[asyncio.Queue] = []

    @classmethod
    def get_instance(cls) -> EventManager:
        """Return the singleton EventManager instance, creating it if needed."""
        if cls.instance is None:
            cls.instance = cls()
        return cls.instance

    async def publish(self, event_type: str, data: dict[str, Any] | str) -> None:
        """Broadcast an event to all connected SSE clients."""
        message = {"event": event_type, "data": json.dumps(data) if isinstance(data, dict) else data}
        for queue in self.queues:
            await queue.put(message)

    async def event_generator(self, request: Request) -> AsyncGenerator[dict[str, str]]:
        """Generate SSE events for a single client connection."""
        queue: asyncio.Queue = asyncio.Queue()
        self.queues.append(queue)
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    message = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield message
                except TimeoutError:
                    yield {"event": "ping", "data": ""}
        finally:
            self.queues.remove(queue)

    def create_response(self, request: Request) -> EventSourceResponse:
        """Create an SSE response for a client."""
        return EventSourceResponse(self.event_generator(request))
