"""Helpers for constructing typed route runtime objects in tests."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

from curate_web.events import EventManager
from curate_web.runtime import WebRuntime


def make_runtime(  # noqa: PLR0913
    *,
    cosmos: object | None = None,
    settings: object | None = None,
    templates: object | None = None,
    storage: object | None = None,
    memory_service: object | None = None,
    start_time: datetime | None = None,
    event_manager: EventManager | None = None,
    event_publisher: object | None = None,
    event_consumer: object | None = None,
    realtime_enabled: bool = False,
) -> WebRuntime:
    """Return a minimally configured ``WebRuntime`` for route tests."""
    cosmos_obj = cosmos or MagicMock()
    return WebRuntime(
        cosmos=cosmos_obj,
        settings=settings or MagicMock(),
        templates=templates or MagicMock(),
        storage=storage or MagicMock(),
        memory_service=memory_service,
        start_time=start_time or datetime.now(UTC),
        event_manager=event_manager or EventManager(),
        event_publisher=event_publisher,
        event_consumer=event_consumer,
        realtime_enabled=realtime_enabled,
    )
