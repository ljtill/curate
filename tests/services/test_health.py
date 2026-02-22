"""Tests for health check probes."""

from unittest.mock import AsyncMock, MagicMock

from agent_stack.config import CosmosConfig, OpenAIConfig, StorageConfig
from agent_stack.pipeline.change_feed import ChangeFeedProcessor
from agent_stack.services.health import (
    StorageHealthConfig,
    _clean_openai_error,
    _storage_account_name,
    check_all,
    check_change_feed,
    check_cosmos,
    check_openai,
    check_storage,
)

_cosmos_config = CosmosConfig(endpoint="https://localhost:8081", database="agent-stack")


async def test_check_cosmos_healthy() -> None:
    """Verify check cosmos healthy."""
    container = AsyncMock()
    database = MagicMock()
    database.get_container_client.return_value = container

    result = await check_cosmos(database, _cosmos_config)

    assert result.healthy is True
    assert result.name == "Azure Cosmos DB"
    assert result.latency_ms is not None
    assert result.error is None
    assert result.detail == "https://localhost:8081 · agent-stack"


async def test_check_cosmos_unhealthy() -> None:
    """Verify check cosmos unhealthy."""
    container = AsyncMock()
    container.read.side_effect = RuntimeError("Connection refused")
    database = MagicMock()
    database.get_container_client.return_value = container

    result = await check_cosmos(database, _cosmos_config)

    assert result.healthy is False
    assert "Connection refused" in result.error


_openai_config = OpenAIConfig(
    endpoint="https://myoai.openai.azure.com", deployment="gpt-4o"
)


async def test_check_openai_healthy() -> None:
    """Verify check openai healthy."""
    client = AsyncMock()
    client.get_response = AsyncMock(return_value=MagicMock())

    result = await check_openai(client, _openai_config)

    assert result.healthy is True
    assert result.name == "Azure OpenAI"
    assert result.latency_ms is not None
    assert result.error is None
    assert result.detail == "https://myoai.openai.azure.com · gpt-4o"


async def test_check_openai_unhealthy() -> None:
    """Verify check openai unhealthy."""
    client = AsyncMock()
    client.get_response = AsyncMock(
        side_effect=ConnectionError("nodename nor servname provided")
    )

    result = await check_openai(client, _openai_config)

    assert result.healthy is False
    assert "nodename" in result.error


_storage_config = StorageConfig(
    account_url="https://myaccount.blob.core.windows.net",
    container="$web",
)


async def test_check_storage_healthy() -> None:
    """Verify check storage healthy."""
    container = AsyncMock()
    storage = MagicMock()
    storage.get_container.return_value = container

    result = await check_storage(storage, _storage_config)

    assert result.healthy is True
    assert result.name == "Azure Storage"
    assert result.latency_ms is not None
    assert result.error is None
    assert result.detail == "myaccount · $web"


async def test_check_storage_unhealthy() -> None:
    """Verify check storage unhealthy."""
    container = AsyncMock()
    container.get_container_properties.side_effect = RuntimeError("Storage unavailable")
    storage = MagicMock()
    storage.get_container.return_value = container

    result = await check_storage(storage, _storage_config)

    assert result.healthy is False
    assert "Storage unavailable" in result.error


def _make_processor(
    *, running: bool, task_done: bool = False, task_exc: Exception | None = None
) -> None:
    processor = MagicMock(spec=ChangeFeedProcessor)
    processor.running = running
    if running or task_done:
        task = MagicMock()
        task.done.return_value = task_done
        task.cancelled.return_value = False
        task.exception.return_value = task_exc
        processor.task = task
    else:
        processor.task = None
    return processor


def test_check_change_feed_healthy() -> None:
    """Verify check change feed healthy."""
    processor = _make_processor(running=True, task_done=False)

    result = check_change_feed(processor)

    assert result.healthy is True
    assert result.name == "Change Feed Processor"


def test_check_change_feed_not_running() -> None:
    """Verify check change feed not running."""
    processor = _make_processor(running=False, task_done=False)

    result = check_change_feed(processor)

    assert result.healthy is False
    assert "not running" in result.error


def test_check_change_feed_task_crashed() -> None:
    """Verify check change feed task crashed."""
    processor = _make_processor(
        running=False, task_done=True, task_exc=RuntimeError("boom")
    )

    result = check_change_feed(processor)

    assert result.healthy is False
    assert "boom" in result.error


def test_check_change_feed_task_finished_unexpectedly() -> None:
    """Verify check change feed task finished unexpectedly."""
    processor = _make_processor(running=False, task_done=True, task_exc=None)

    result = check_change_feed(processor)

    assert result.healthy is False
    assert "unexpectedly" in result.error


async def test_check_openai_healthy_on_max_tokens_error() -> None:
    """Verify OpenAI is marked healthy when error mentions max_tokens."""
    client = AsyncMock()
    client.get_response = AsyncMock(side_effect=ValueError("max_tokens is too large"))

    result = await check_openai(client, _openai_config)

    assert result.healthy is True


def test_clean_openai_error_connection_error() -> None:
    """Verify connection error is cleaned to a helpful message."""
    result = _clean_openai_error("Connection error to https://example.com")

    assert "Connection error" in result
    assert "AZURE_OPENAI_ENDPOINT" in result


def test_clean_openai_error_class_repr_prefix() -> None:
    """Verify class repr prefix is stripped."""
    raw = (
        "<class 'openai.APIError'>  service failed to complete the prompt:"
        " something went wrong"
    )

    result = _clean_openai_error(raw)

    assert result == "something went wrong"


def test_clean_openai_error_nested_message() -> None:
    """Verify nested message dict is extracted."""
    raw = "Error: {'message': 'Rate limit exceeded', 'code': '429'}"

    result = _clean_openai_error(raw)

    assert result == "Rate limit exceeded"


def test_clean_openai_error_passthrough() -> None:
    """Verify unrecognized errors pass through unchanged."""
    raw = "Something totally unexpected"

    result = _clean_openai_error(raw)

    assert result == raw


def test_storage_account_name_extracts_name() -> None:
    """Verify account name is extracted from account URL."""
    url = "https://mystore.blob.core.windows.net"

    assert _storage_account_name(url) == "mystore"


def test_storage_account_name_unknown_fallback() -> None:
    """Verify 'unknown' is returned when account name is not found."""
    assert _storage_account_name("https://localhost:8081") == "unknown"


async def test_check_all_without_storage() -> None:
    """Verify check_all runs cosmos, openai, and change feed probes."""
    database = MagicMock()
    database.get_container_client.return_value = AsyncMock()
    openai_client = AsyncMock()
    openai_client.get_response = AsyncMock(return_value=MagicMock())
    processor = _make_processor(running=True, task_done=False)

    results = await check_all(
        database,
        openai_client,
        processor,
        _cosmos_config,
        _openai_config,
    )

    names = [r.name for r in results]
    assert "Azure Cosmos DB" in names
    assert "Azure OpenAI" in names
    assert "Change Feed Processor" in names
    assert "Azure Storage" not in names


async def test_check_all_with_storage() -> None:
    """Verify check_all includes storage when config is provided."""
    database = MagicMock()
    database.get_container_client.return_value = AsyncMock()
    openai_client = AsyncMock()
    openai_client.get_response = AsyncMock(return_value=MagicMock())
    processor = _make_processor(running=True, task_done=False)
    storage_client = MagicMock()
    storage_client.get_container.return_value = AsyncMock()
    storage_health = StorageHealthConfig(client=storage_client, config=_storage_config)

    results = await check_all(
        database,
        openai_client,
        processor,
        _cosmos_config,
        _openai_config,
        storage_health=storage_health,
    )

    names = [r.name for r in results]
    assert "Azure Storage" in names
