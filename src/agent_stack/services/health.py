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
    from agent_framework.azure import AzureOpenAIChatClient
    from azure.cosmos.aio import DatabaseProxy

    from agent_stack.config import CosmosConfig, OpenAIConfig, StorageConfig
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
        # Read container properties as a minimal round-trip
        await container.read()
        latency = (time.monotonic() - start) * 1000
        return ServiceHealth(
            name="Azure Cosmos DB",
            healthy=True,
            latency_ms=round(latency, 1),
            detail=detail,
        )
    except (AzureError, OSError, RuntimeError) as exc:
        latency = (time.monotonic() - start) * 1000
        return ServiceHealth(
            name="Azure Cosmos DB",
            healthy=False,
            latency_ms=round(latency, 1),
            error=str(exc),
            detail=detail,
        )


async def check_openai(
    client: AzureOpenAIChatClient, config: OpenAIConfig
) -> ServiceHealth:
    """Probe Azure OpenAI with a minimal completion request."""
    detail = f"{config.endpoint} · {config.deployment}"
    start = time.monotonic()
    try:
        await client.get_response(
            messages=[Message(role="user", text="ping")],
            options={"max_tokens": 1},
        )
        latency = (time.monotonic() - start) * 1000
        return ServiceHealth(
            name="Azure OpenAI",
            healthy=True,
            latency_ms=round(latency, 1),
            detail=detail,
        )
    except (ChatClientException, OSError, RuntimeError, ValueError) as exc:
        latency = (time.monotonic() - start) * 1000
        raw = str(exc)
        if "max_tokens" in raw or "model output limit" in raw:
            return ServiceHealth(
                name="Azure OpenAI",
                healthy=True,
                latency_ms=round(latency, 1),
                detail=detail,
            )

        message = _clean_openai_error(raw)
        return ServiceHealth(
            name="Azure OpenAI",
            healthy=False,
            latency_ms=round(latency, 1),
            error=message,
            detail=detail,
        )


def _clean_openai_error(raw: str) -> str:
    """Extract a human-readable message from an Azure OpenAI exception."""
    if "Connection error" in raw:
        return "Connection error — check AZURE_OPENAI_ENDPOINT is reachable"

    # Strip the Python class repr prefix (e.g. "<class '...'>  service failed ...")
    if raw.startswith("<class "):
        idx = raw.find(">")
        if idx != -1:
            raw = (
                raw[idx + 1 :]
                .strip()
                .removeprefix("service failed to complete the prompt:")
                .strip()
            )

    # Try to pull the nested message from the error dict
    if "'message':" in raw:
        match = re.search(r"'message':\s*'([^']+)'", raw)
        if match:
            return match.group(1)

    return raw


def _storage_account_name(connection_string: str) -> str:
    """Extract the account name from a storage connection string."""
    for part in connection_string.split(";"):
        if part.strip().lower().startswith("accountname="):
            return part.split("=", 1)[1]
    return "unknown"


async def check_storage(
    storage: BlobStorageClient, config: StorageConfig
) -> ServiceHealth:
    """Probe Azure Storage with a lightweight container existence check."""
    account = _storage_account_name(config.connection_string)
    detail = f"{account} · {config.container}"
    start = time.monotonic()
    try:
        container = storage.get_container()
        await container.get_container_properties()
        latency = (time.monotonic() - start) * 1000
        return ServiceHealth(
            name="Azure Storage",
            healthy=True,
            latency_ms=round(latency, 1),
            detail=detail,
        )
    except (AzureError, OSError, RuntimeError) as exc:
        latency = (time.monotonic() - start) * 1000
        return ServiceHealth(
            name="Azure Storage",
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
    openai_client: AzureOpenAIChatClient,
    processor: ChangeFeedProcessor,
    cosmos_config: CosmosConfig,
    openai_config: OpenAIConfig,
    storage_health: StorageHealthConfig | None = None,
) -> list[ServiceHealth]:
    """Run all health probes and return results."""
    coros: list = [check_cosmos(database, cosmos_config)]
    if storage_health is not None:
        coros.append(check_storage(storage_health.client, storage_health.config))
    coros.append(check_openai(openai_client, openai_config))
    network_results = await asyncio.gather(*coros, return_exceptions=False)
    feed_result = check_change_feed(processor)
    return [*network_results, feed_result]
