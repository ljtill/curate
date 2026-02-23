"""SSE event manager for real-time dashboard updates."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from typing import TYPE_CHECKING, Any

from sse_starlette.sse import EventSourceResponse

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from fastapi import Request

logger = logging.getLogger(__name__)
_QUEUE_MAXSIZE = 200


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
        message = {
            "event": event_type,
            "data": json.dumps(data) if isinstance(data, dict) else data,
        }
        logger.debug("SSE publish event=%s clients=%d", event_type, len(self.queues))
        for queue in self.queues:
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                with contextlib.suppress(asyncio.QueueEmpty):
                    queue.get_nowait()
                with contextlib.suppress(asyncio.QueueFull):
                    queue.put_nowait(message)
                logger.warning("SSE queue full, dropping oldest event")

    async def event_generator(self, request: Request) -> AsyncGenerator[dict[str, str]]:
        """Generate SSE events for a single client connection."""
        queue: asyncio.Queue = asyncio.Queue(maxsize=_QUEUE_MAXSIZE)
        self.queues.append(queue)
        client = request.client.host if request.client else "unknown"
        logger.debug(
            "SSE client connected — client=%s active_connections=%d",
            client,
            len(self.queues),
        )
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    message = await asyncio.wait_for(queue.get(), timeout=1.0)
                    yield message
                except TimeoutError:
                    pass
        finally:
            self.queues.remove(queue)
            logger.debug(
                "SSE client disconnected — client=%s active_connections=%d",
                client,
                len(self.queues),
            )

    def create_response(self, request: Request) -> EventSourceResponse:
        """Create an SSE response for a client."""
        return EventSourceResponse(
            self.event_generator(request),
            ping=5,
            send_timeout=5,
        )
