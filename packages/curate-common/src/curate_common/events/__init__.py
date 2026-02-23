"""Event publishing protocol for cross-service communication."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class EventPublisher(Protocol):
    """Protocol for publishing pipeline events to connected consumers."""

    async def publish(self, event_type: str, data: dict[str, Any] | str) -> None:
        """Broadcast an event to all connected consumers."""
        ...
