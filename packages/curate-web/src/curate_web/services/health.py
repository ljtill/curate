"""Health check probes for external dependencies."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from azure.core.exceptions import AzureError

_EMULATOR_HOSTS = {"localhost", "127.0.0.1", "host.docker.internal"}


def _is_emulator_url(url: str) -> bool:
    """Return True if the URL points to a local emulator."""
    from urllib.parse import urlparse  # noqa: PLC0415

    try:
        hostname = urlparse(url).hostname or ""
    except Exception:  # noqa: BLE001
        return False
    return hostname in _EMULATOR_HOSTS


def _is_emulator_conn_str(connection_string: str) -> bool:
    """Return True if the connection string targets a local emulator."""
    lower = connection_string.lower()
    return any(host in lower for host in _EMULATOR_HOSTS)


if TYPE_CHECKING:
    from azure.cosmos.aio import DatabaseProxy

    from curate_common.config import (
        CosmosConfig,
        FoundryConfig,
        MonitorConfig,
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
    source: str | None = None


async def check_cosmos(database: DatabaseProxy, config: CosmosConfig) -> ServiceHealth:
    """Probe Cosmos DB with a lightweight read."""
    detail = f"{config.endpoint} · {config.database}"
    source = "Emulator" if _is_emulator_url(config.endpoint) else "Cloud"
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
            source=source,
        )
    except (AzureError, OSError, RuntimeError) as exc:
        latency = (time.monotonic() - start) * 1000
        return ServiceHealth(
            name="Cosmos DB",
            healthy=False,
            latency_ms=round(latency, 1),
            error=str(exc),
            detail=detail,
            source=source,
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
    source = "Emulator" if _is_emulator_url(config.account_url) else "Cloud"
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
            source=source,
        )
    except (AzureError, OSError, RuntimeError) as exc:
        latency = (time.monotonic() - start) * 1000
        return ServiceHealth(
            name="Storage",
            healthy=False,
            latency_ms=round(latency, 1),
            error=str(exc),
            detail=detail,
            source=source,
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
    source = "Emulator" if _is_emulator_conn_str(config.connection_string) else "Cloud"
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
            source=source,
        )
    except (AzureError, OSError, RuntimeError) as exc:
        latency = (time.monotonic() - start) * 1000
        return ServiceHealth(
            name="Service Bus",
            healthy=False,
            latency_ms=round(latency, 1),
            error=str(exc),
            detail=detail,
            source=source,
        )


def _check_monitor_config(config: MonitorConfig | None) -> ServiceHealth:
    """Report Application Insights configuration status."""
    if not config or not config.connection_string:
        return ServiceHealth(
            name="Application Insights",
            healthy=False,
            error="AZURE_APPLICATIONINSIGHTS_CONNECTION_STRING is not set",
        )
    return ServiceHealth(
        name="Application Insights",
        healthy=True,
        detail="Connected",
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
    monitor_config: MonitorConfig | None = None,
) -> list[ServiceHealth]:
    """Run all health probes and return results."""
    coros: list = [check_cosmos(database, cosmos_config)]
    if storage_health is not None:
        coros.append(check_storage(storage_health.client, storage_health.config))
    if servicebus_config is not None:
        coros.append(check_servicebus(servicebus_config))
    network_results = await asyncio.gather(*coros, return_exceptions=False)

    foundry_result = _check_foundry_config(foundry_config)
    monitor_result = _check_monitor_config(monitor_config)

    return [*network_results, foundry_result, monitor_result]
