"""Health check probes for external dependencies."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

from agent_framework import Message
from agent_framework.azure import AzureOpenAIChatClient
from azure.cosmos.aio import DatabaseProxy

from agent_stack.pipeline.change_feed import ChangeFeedProcessor
from agent_stack.storage.blob import BlobStorageClient


@dataclass
class ServiceHealth:
    """Result of a single dependency health probe."""

    name: str
    healthy: bool
    latency_ms: float | None = None
    error: str | None = None


async def check_cosmos(database: DatabaseProxy) -> ServiceHealth:
    """Probe Cosmos DB with a lightweight read."""
    start = time.monotonic()
    try:
        container = database.get_container_client("editions")
        # Read container properties as a minimal round-trip
        await container.read()
        latency = (time.monotonic() - start) * 1000
        return ServiceHealth(name="Azure Cosmos DB", healthy=True, latency_ms=round(latency, 1))
    except Exception as exc:
        latency = (time.monotonic() - start) * 1000
        return ServiceHealth(name="Azure Cosmos DB", healthy=False, latency_ms=round(latency, 1), error=str(exc))


async def check_openai(client: AzureOpenAIChatClient) -> ServiceHealth:
    """Probe Azure OpenAI with a minimal completion request."""
    start = time.monotonic()
    try:
        await client.get_response(
            messages=[Message(role="user", text="ping")],
            options={"max_tokens": 1},
        )
        latency = (time.monotonic() - start) * 1000
        return ServiceHealth(name="Azure OpenAI", healthy=True, latency_ms=round(latency, 1))
    except Exception as exc:
        latency = (time.monotonic() - start) * 1000
        raw = str(exc)

        # A max_tokens / output limit error means the API is reachable — treat as healthy
        if "max_tokens" in raw or "model output limit" in raw:
            return ServiceHealth(name="Azure OpenAI", healthy=True, latency_ms=round(latency, 1))

        message = _clean_openai_error(raw)
        return ServiceHealth(name="Azure OpenAI", healthy=False, latency_ms=round(latency, 1), error=message)


def _clean_openai_error(raw: str) -> str:
    """Extract a human-readable message from an Azure OpenAI exception."""
    if "Connection error" in raw:
        return "Connection error — check AZURE_OPENAI_ENDPOINT is reachable"

    # Strip the Python class repr prefix (e.g. "<class '...'>  service failed ...")
    if raw.startswith("<class "):
        idx = raw.find(">")
        if idx != -1:
            raw = raw[idx + 1 :].strip().removeprefix("service failed to complete the prompt:").strip()

    # Try to pull the nested message from the error dict
    if "'message':" in raw:
        import re

        match = re.search(r"'message':\s*'([^']+)'", raw)
        if match:
            return match.group(1)

    return raw


async def check_storage(storage: BlobStorageClient) -> ServiceHealth:
    """Probe Azure Storage with a lightweight container existence check."""
    start = time.monotonic()
    try:
        container = storage._get_container()
        await container.get_container_properties()
        latency = (time.monotonic() - start) * 1000
        return ServiceHealth(name="Azure Storage", healthy=True, latency_ms=round(latency, 1))
    except Exception as exc:
        latency = (time.monotonic() - start) * 1000
        return ServiceHealth(name="Azure Storage", healthy=False, latency_ms=round(latency, 1), error=str(exc))


def check_change_feed(processor: ChangeFeedProcessor) -> ServiceHealth:
    """Check whether the change feed background task is alive."""
    if processor._running and processor._task is not None and not processor._task.done():
        return ServiceHealth(name="Change Feed Processor", healthy=True)
    error = "Background task is not running"
    if processor._task is not None and processor._task.done():
        exc = processor._task.exception() if not processor._task.cancelled() else None
        error = str(exc) if exc else "Task finished unexpectedly"
    return ServiceHealth(name="Change Feed Processor", healthy=False, error=error)


async def check_all(
    database: DatabaseProxy,
    openai_client: AzureOpenAIChatClient,
    processor: ChangeFeedProcessor,
    storage: BlobStorageClient | None = None,
) -> list[ServiceHealth]:
    """Run all health probes and return results."""
    coros: list = [check_cosmos(database), check_openai(openai_client)]
    if storage is not None:
        coros.append(check_storage(storage))
    network_results = await asyncio.gather(*coros, return_exceptions=False)
    feed_result = check_change_feed(processor)
    return [*network_results, feed_result]
