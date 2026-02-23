"""Typed runtime dependency container for web routes and services."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime

    from fastapi import Request
    from fastapi.templating import Jinja2Templates

    from curate_common.config import Settings
    from curate_common.database.client import CosmosClient
    from curate_common.events import EventPublisher
    from curate_common.storage.blob import BlobStorageClient
    from curate_web.events import EventManager
    from curate_web.events.consumer import ServiceBusConsumer
    from curate_web.services.memory import MemoryService


@dataclass
class WebRuntime:
    """Shared runtime dependencies initialized during app lifespan."""

    cosmos: CosmosClient
    settings: Settings
    templates: Jinja2Templates
    storage: BlobStorageClient
    memory_service: MemoryService | None
    start_time: datetime
    event_manager: EventManager
    event_publisher: EventPublisher | None = None
    event_consumer: ServiceBusConsumer | None = None
    realtime_enabled: bool = False


def get_runtime(request: Request) -> WebRuntime:
    """Return typed runtime dependencies from ``request.app.state``."""
    runtime = getattr(request.app.state, "runtime", None)
    if not isinstance(runtime, WebRuntime):
        msg = "WebRuntime is not initialized on app.state.runtime"
        raise TypeError(msg)
    return runtime
