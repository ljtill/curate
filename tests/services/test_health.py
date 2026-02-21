"""Tests for health check probes."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from agent_stack.config import CosmosConfig, OpenAIConfig, StorageConfig
from agent_stack.pipeline.change_feed import ChangeFeedProcessor
from agent_stack.services.health import (
    check_change_feed,
    check_cosmos,
    check_openai,
    check_storage,
)

# --- Cosmos DB ---

_cosmos_config = CosmosConfig(endpoint="https://localhost:8081", key="", database="agent-stack")


@pytest.mark.asyncio
async def test_check_cosmos_healthy():
    container = AsyncMock()
    database = MagicMock()
    database.get_container_client.return_value = container

    result = await check_cosmos(database, _cosmos_config)

    assert result.healthy is True
    assert result.name == "Azure Cosmos DB"
    assert result.latency_ms is not None
    assert result.error is None
    assert result.detail == "https://localhost:8081 · agent-stack"


@pytest.mark.asyncio
async def test_check_cosmos_unhealthy():
    container = AsyncMock()
    container.read.side_effect = RuntimeError("Connection refused")
    database = MagicMock()
    database.get_container_client.return_value = container

    result = await check_cosmos(database, _cosmos_config)

    assert result.healthy is False
    assert "Connection refused" in result.error


# --- Azure OpenAI ---

_openai_config = OpenAIConfig(endpoint="https://myoai.openai.azure.com", deployment="gpt-4o")


@pytest.mark.asyncio
async def test_check_openai_healthy():
    client = AsyncMock()
    client.get_response = AsyncMock(return_value=MagicMock())

    result = await check_openai(client, _openai_config)

    assert result.healthy is True
    assert result.name == "Azure OpenAI"
    assert result.latency_ms is not None
    assert result.error is None
    assert result.detail == "https://myoai.openai.azure.com · gpt-4o"


@pytest.mark.asyncio
async def test_check_openai_unhealthy():
    client = AsyncMock()
    client.get_response = AsyncMock(side_effect=ConnectionError("nodename nor servname provided"))

    result = await check_openai(client, _openai_config)

    assert result.healthy is False
    assert "nodename" in result.error


# --- Azure Storage ---

_storage_config = StorageConfig(
    connection_string="DefaultEndpointsProtocol=https;AccountName=myaccount;AccountKey=secret;EndpointSuffix=core.windows.net",
    container="$web",
)


@pytest.mark.asyncio
async def test_check_storage_healthy():
    container = AsyncMock()
    storage = MagicMock()
    storage._get_container.return_value = container

    result = await check_storage(storage, _storage_config)

    assert result.healthy is True
    assert result.name == "Azure Storage"
    assert result.latency_ms is not None
    assert result.error is None
    assert result.detail == "myaccount · $web"


@pytest.mark.asyncio
async def test_check_storage_unhealthy():
    container = AsyncMock()
    container.get_container_properties.side_effect = RuntimeError("Storage unavailable")
    storage = MagicMock()
    storage._get_container.return_value = container

    result = await check_storage(storage, _storage_config)

    assert result.healthy is False
    assert "Storage unavailable" in result.error


# --- Change Feed Processor ---


def _make_processor(running: bool, task_done: bool = False, task_exc: Exception | None = None):
    processor = MagicMock(spec=ChangeFeedProcessor)
    processor._running = running
    if running or task_done:
        task = MagicMock()
        task.done.return_value = task_done
        task.cancelled.return_value = False
        task.exception.return_value = task_exc
        processor._task = task
    else:
        processor._task = None
    return processor


def test_check_change_feed_healthy():
    processor = _make_processor(running=True, task_done=False)

    result = check_change_feed(processor)

    assert result.healthy is True
    assert result.name == "Change Feed Processor"


def test_check_change_feed_not_running():
    processor = _make_processor(running=False, task_done=False)

    result = check_change_feed(processor)

    assert result.healthy is False
    assert "not running" in result.error


def test_check_change_feed_task_crashed():
    processor = _make_processor(running=False, task_done=True, task_exc=RuntimeError("boom"))

    result = check_change_feed(processor)

    assert result.healthy is False
    assert "boom" in result.error


def test_check_change_feed_task_finished_unexpectedly():
    processor = _make_processor(running=False, task_done=True, task_exc=None)

    result = check_change_feed(processor)

    assert result.healthy is False
    assert "unexpectedly" in result.error
