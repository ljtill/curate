"""Health check probes for external dependencies."""

from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from agent_framework import Message
from agent_framework.exceptions import ChatClientException
from azure.core.exceptions import AzureError

if TYPE_CHECKING:
    from agent_framework import BaseChatClient
    from azure.cosmos.aio import DatabaseProxy

    from agent_stack.config import CosmosConfig, FoundryConfig, StorageConfig
    from agent_stack.pipeline.change_feed import ChangeFeedProcessor
    from agent_stack.storage.blob import BlobStorageClient


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


async def check_openai(client: BaseChatClient, config: FoundryConfig) -> ServiceHealth:
    """Probe Microsoft Foundry with a minimal completion request."""
    detail = f"{config.project_endpoint} · {config.model}"
    start = time.monotonic()
    try:
        await client.get_response(
            messages=[Message(role="user", text="ping")],
        )
        latency = (time.monotonic() - start) * 1000
        return ServiceHealth(
            name="Foundry",
            healthy=True,
            latency_ms=round(latency, 1),
            detail=detail,
        )
    except (ChatClientException, OSError, RuntimeError, ValueError) as exc:
        latency = (time.monotonic() - start) * 1000
        raw = str(exc)
        if (
            "max_tokens" in raw
            or "max_output_tokens" in raw
            or "model output limit" in raw
        ):
            return ServiceHealth(
                name="Foundry",
                healthy=True,
                latency_ms=round(latency, 1),
                detail=detail,
            )

        message = _clean_openai_error(raw)
        return ServiceHealth(
            name="Foundry",
            healthy=False,
            latency_ms=round(latency, 1),
            error=message,
            detail=detail,
        )


def _clean_openai_error(raw: str) -> str:
    """Extract a human-readable message from a Microsoft Foundry exception."""
    if "Connection error" in raw:
        return "Connection error — check FOUNDRY_PROJECT_ENDPOINT is reachable"

    if raw.startswith("<class "):
        idx = raw.find(">")
        if idx != -1:
            raw = (
                raw[idx + 1 :]
                .strip()
                .removeprefix("service failed to complete the prompt:")
                .strip()
            )

    if "'message':" in raw:
        match = re.search(r"'message':\s*'([^']+)'", raw)
        if match:
            return match.group(1)

    return raw


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


def check_change_feed(processor: ChangeFeedProcessor) -> ServiceHealth:
    """Check whether the change feed background task is alive."""
    detail = "editions container"
    if processor.running and processor.task is not None and not processor.task.done():
        return ServiceHealth(name="Change Feed Processor", healthy=True, detail=detail)
    error = "Background task is not running"
    if processor.task is not None and processor.task.done():
        exc = processor.task.exception() if not processor.task.cancelled() else None
        error = str(exc) if exc else "Task finished unexpectedly"
    return ServiceHealth(
        name="Change Feed Processor", healthy=False, error=error, detail=detail
    )


@dataclass
class StorageHealthConfig:
    """Optional storage health check configuration."""

    client: BlobStorageClient
    config: StorageConfig


async def check_all(
    database: DatabaseProxy,
    openai_client: BaseChatClient | None,
    processor: ChangeFeedProcessor | None,
    cosmos_config: CosmosConfig,
    foundry_config: FoundryConfig,
    storage_health: StorageHealthConfig | None = None,
) -> list[ServiceHealth]:
    """Run all health probes and return results."""
    coros: list = [check_cosmos(database, cosmos_config)]
    if storage_health is not None:
        coros.append(check_storage(storage_health.client, storage_health.config))
    network_results = await asyncio.gather(*coros, return_exceptions=False)

    foundry_detail = (
        f"{foundry_config.project_endpoint or 'not configured'}"
        f" · {foundry_config.model or 'not configured'}"
    )
    if openai_client is not None and foundry_config.project_endpoint:
        openai_result = await check_openai(openai_client, foundry_config)
    else:
        openai_result = ServiceHealth(
            name="Foundry",
            healthy=False,
            error="FOUNDRY_PROJECT_ENDPOINT is not set",
            detail=foundry_detail,
        )

    if processor is not None:
        feed_result = check_change_feed(processor)
    else:
        feed_result = ServiceHealth(
            name="Change Feed Processor",
            healthy=False,
            error="Disabled because Foundry pipeline is unavailable",
            detail="editions container",
        )
    return [*network_results, openai_result, feed_result]
