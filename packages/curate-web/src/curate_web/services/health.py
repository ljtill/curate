"""Health check probes for external dependencies."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from azure.core.exceptions import AzureError

if TYPE_CHECKING:
    from azure.cosmos.aio import DatabaseProxy

    from curate_common.config import (
        CosmosConfig,
        FoundryConfig,
        ServiceBusConfig,
        StorageConfig,
    )
    from curate_common.storage.blob import BlobStorageClient


@dataclass
class ServiceHealth:
    """Result of a single dependency health probe."""

    name: str
    healthy: bool
    latency_ms: float | None = None
    error: str | None = None
    detail: str | None = None


async def check_cosmos(database: DatabaseProxy, config: CosmosConfig) -> ServiceHealth:
    """Probe Cosmos DB with a lightweight read."""
    detail = f"{config.endpoint} · {config.database}"
    start = time.monotonic()
    try:
        container = database.get_container_client("editions")
        await container.read()
        latency = (time.monotonic() - start) * 1000
        return ServiceHealth(
            name="Cosmos DB",
            healthy=True,
            latency_ms=round(latency, 1),
            detail=detail,
        )
    except (AzureError, OSError, RuntimeError) as exc:
        latency = (time.monotonic() - start) * 1000
        return ServiceHealth(
            name="Cosmos DB",
            healthy=False,
            latency_ms=round(latency, 1),
            error=str(exc),
            detail=detail,
        )


def _check_foundry_config(config: FoundryConfig) -> ServiceHealth:
    """Report Foundry configuration status (web cannot probe LLM directly)."""
    detail = (
        f"{config.project_endpoint or 'not configured'}"
        f" · {config.model or 'not configured'}"
    )
    if config.is_local:
        return ServiceHealth(
            name="Foundry",
            healthy=True,
            detail=f"Foundry Local · {config.local_model}",
        )
    if config.project_endpoint and config.model:
        return ServiceHealth(
            name="Foundry",
            healthy=True,
            detail=detail,
        )
    return ServiceHealth(
        name="Foundry",
        healthy=False,
        error="FOUNDRY_PROJECT_ENDPOINT or FOUNDRY_MODEL is not set",
        detail=detail,
    )


def _storage_account_name(account_url: str) -> str:
    """Extract the account name from a storage account URL."""
    from urllib.parse import urlparse  # noqa: PLC0415

    try:
        parsed = urlparse(account_url)
        host = parsed.hostname or ""
        if ".blob." in host:
            return host.split(".")[0]
        parts = parsed.path.strip("/").split("/")
        if parts and parts[0]:
            return parts[0]
    except Exception:  # noqa: BLE001
        return "unknown"
    return "unknown"


async def check_storage(
    storage: BlobStorageClient, config: StorageConfig
) -> ServiceHealth:
    """Probe Microsoft Azure Storage with a lightweight container existence check."""
    account = _storage_account_name(config.account_url)
    detail = f"{account} · {config.container}"
    start = time.monotonic()
    try:
        container = storage.get_container()
        await container.get_container_properties()
        latency = (time.monotonic() - start) * 1000
        return ServiceHealth(
            name="Storage",
            healthy=True,
            latency_ms=round(latency, 1),
            detail=detail,
        )
    except (AzureError, OSError, RuntimeError) as exc:
        latency = (time.monotonic() - start) * 1000
        return ServiceHealth(
            name="Storage",
            healthy=False,
            latency_ms=round(latency, 1),
            error=str(exc),
            detail=detail,
        )


async def check_servicebus(config: ServiceBusConfig) -> ServiceHealth:
    """Probe Service Bus with a lightweight management operation."""
    detail = f"{config.topic_name} · {config.subscription_name}"
    if not config.connection_string:
        return ServiceHealth(
            name="Service Bus",
            healthy=False,
            error="AZURE_SERVICEBUS_CONNECTION_STRING is not set",
            detail=detail,
        )
    start = time.monotonic()
    try:
        from azure.servicebus.aio import ServiceBusClient  # noqa: PLC0415

        async with ServiceBusClient.from_connection_string(
            config.connection_string
        ) as client:
            receiver = client.get_subscription_receiver(
                topic_name=config.topic_name,
                subscription_name=config.subscription_name,
                max_wait_time=1,
            )
            async with receiver:
                pass
        latency = (time.monotonic() - start) * 1000
        return ServiceHealth(
            name="Service Bus",
            healthy=True,
            latency_ms=round(latency, 1),
            detail=detail,
        )
    except (AzureError, OSError, RuntimeError) as exc:
        latency = (time.monotonic() - start) * 1000
        return ServiceHealth(
            name="Service Bus",
            healthy=False,
            latency_ms=round(latency, 1),
            error=str(exc),
            detail=detail,
        )


@dataclass
class StorageHealthConfig:
    """Optional storage health check configuration."""

    client: BlobStorageClient
    config: StorageConfig


async def check_all(
    database: DatabaseProxy,
    cosmos_config: CosmosConfig,
    foundry_config: FoundryConfig,
    storage_health: StorageHealthConfig | None = None,
    servicebus_config: ServiceBusConfig | None = None,
) -> list[ServiceHealth]:
    """Run all health probes and return results."""
    coros: list = [check_cosmos(database, cosmos_config)]
    if storage_health is not None:
        coros.append(check_storage(storage_health.client, storage_health.config))
    if servicebus_config is not None:
        coros.append(check_servicebus(servicebus_config))
    network_results = await asyncio.gather(*coros, return_exceptions=False)

    foundry_result = _check_foundry_config(foundry_config)

    return [*network_results, foundry_result]
