"""Service Bus consumer — receives pipeline events and feeds SSE EventManager."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from curate_common.config import ServiceBusConfig
    from curate_web.events import EventManager

logger = logging.getLogger(__name__)


class ServiceBusConsumer:
    """Receives events from Azure Service Bus and forwards to local EventManager."""

    def __init__(self, config: ServiceBusConfig, event_manager: EventManager) -> None:
        """Initialize with Service Bus config and local event manager."""
        self._config = config
        self._event_manager = event_manager
        self._task: asyncio.Task | None = None
        self._running = False

    async def start(self) -> None:
        """Start the background consumer task."""
        self._running = True
        self._task = asyncio.create_task(self._consume())
        logger.info("Service Bus consumer started — topic=%s", self._config.topic_name)

    async def stop(self) -> None:
        """Stop the background consumer task."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        logger.info("Service Bus consumer stopped")

    async def _consume(self) -> None:
        """Consume messages from Service Bus subscription."""
        from azure.servicebus.aio import ServiceBusClient  # noqa: PLC0415

        try:
            client = ServiceBusClient.from_connection_string(
                self._config.connection_string
            )
            async with client:
                receiver = client.get_subscription_receiver(
                    topic_name=self._config.topic_name,
                    subscription_name=self._config.subscription_name,
                )
                async with receiver:
                    while self._running:
                        messages = await receiver.receive_messages(
                            max_message_count=10, max_wait_time=5
                        )
                        for message in messages:
                            try:
                                body = str(message)
                                payload = json.loads(body)
                                event_type = payload.get("event", "unknown")
                                data = payload.get("data", "")
                                await self._event_manager.publish(event_type, data)
                                await receiver.complete_message(message)
                            except Exception:  # noqa: BLE001
                                logger.warning(
                                    "Failed to process Service Bus message",
                                    exc_info=True,
                                )
                                await receiver.abandon_message(message)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            logger.warning(
                "Service Bus consumer error, will not reconnect",
                exc_info=True,
            )
