"""Service Bus event publisher — sends pipeline events to Azure Service Bus."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from azure.servicebus.aio import ServiceBusClient, ServiceBusSender

if TYPE_CHECKING:
    from curate_common.config import ServiceBusConfig

logger = logging.getLogger(__name__)


class ServiceBusPublisher:
    """Publishes pipeline events to an Azure Service Bus topic.

    Degrades gracefully when the connection string is not configured —
    logs a single warning at startup and silently skips all publishes.
    """

    def __init__(self, config: ServiceBusConfig) -> None:
        """Initialize with Service Bus configuration."""
        self._config = config
        self._client: ServiceBusClient | None = None
        self._sender: ServiceBusSender | None = None
        self._disabled = not config.connection_string
        if self._disabled:
            logger.warning(
                "AZURE_SERVICEBUS_CONNECTION_STRING is not set — "
                "pipeline events will not be published"
            )

    async def _ensure_sender(self) -> ServiceBusSender:
        """Lazily create the Service Bus client and sender."""
        if self._sender is None:
            self._client = ServiceBusClient.from_connection_string(
                self._config.connection_string
            )
            self._sender = self._client.get_topic_sender(
                topic_name=self._config.topic_name
            )
        return self._sender

    async def publish(self, event_type: str, data: dict[str, Any] | str) -> None:
        """Send an event message to the Service Bus topic."""
        if self._disabled:
            return

        from azure.servicebus import ServiceBusMessage  # noqa: PLC0415

        try:
            sender = await self._ensure_sender()
            message_body = json.dumps(
                {
                    "event": event_type,
                    "data": data if isinstance(data, str) else json.dumps(data),
                }
            )
            message = ServiceBusMessage(
                body=message_body,
                application_properties={"event_type": event_type},
            )
            await sender.send_messages(message)
            logger.debug("Published event=%s to Service Bus", event_type)
        except Exception:  # noqa: BLE001
            logger.warning(
                "Failed to publish event=%s to Service Bus",
                event_type,
                exc_info=True,
            )

    async def close(self) -> None:
        """Close the Service Bus client."""
        if self._sender:
            await self._sender.close()
        if self._client:
            await self._client.close()
