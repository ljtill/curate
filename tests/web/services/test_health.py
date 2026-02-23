"""Tests for health check probes."""

from unittest.mock import AsyncMock, MagicMock

from curate_common.config import CosmosConfig, FoundryConfig, StorageConfig
from curate_web.services.health import (
    StorageHealthConfig,
    _check_foundry_config,
    _storage_account_name,
    check_all,
    check_cosmos,
    check_storage,
)

_cosmos_config = CosmosConfig(endpoint="https://localhost:8081", database="curate")


async def test_check_cosmos_healthy() -> None:
    """Verify check cosmos healthy."""
    container = AsyncMock()
    database = MagicMock()
    database.get_container_client.return_value = container

    result = await check_cosmos(database, _cosmos_config)

    assert result.healthy is True
    assert result.name == "Cosmos DB"
    assert result.latency_ms is not None
    assert result.error is None
    assert result.detail == "https://localhost:8081 · curate"


async def test_check_cosmos_unhealthy() -> None:
    """Verify check cosmos unhealthy."""
    container = AsyncMock()
    container.read.side_effect = RuntimeError("Connection refused")
    database = MagicMock()
    database.get_container_client.return_value = container

    result = await check_cosmos(database, _cosmos_config)

    assert result.healthy is False
    assert "Connection refused" in result.error


_foundry_config = FoundryConfig(
    project_endpoint="https://myoai.openai.azure.com", model="gpt-4o"
)


def test_check_foundry_config_healthy() -> None:
    """Verify Foundry reports healthy when endpoint and model are set."""
    result = _check_foundry_config(_foundry_config)

    assert result.healthy is True
    assert result.name == "Foundry"
    assert "myoai.openai.azure.com" in result.detail


def test_check_foundry_config_unhealthy() -> None:
    """Verify Foundry reports unhealthy when endpoint is missing."""
    config = FoundryConfig(project_endpoint="", model="")

    result = _check_foundry_config(config)

    assert result.healthy is False
    assert "not set" in result.error


def test_check_foundry_config_local() -> None:
    """Verify Foundry reports healthy for local provider."""
    config = FoundryConfig(provider="local", local_model="phi-4-mini")

    result = _check_foundry_config(config)

    assert result.healthy is True
    assert "Foundry Local" in result.detail


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
    assert result.name == "Storage"
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


def test_storage_account_name_extracts_name() -> None:
    """Verify account name is extracted from account URL."""
    url = "https://mystore.blob.core.windows.net"

    assert _storage_account_name(url) == "mystore"


def test_storage_account_name_unknown_fallback() -> None:
    """Verify 'unknown' is returned when account name is not found."""
    assert _storage_account_name("https://localhost:8081") == "unknown"


async def test_check_all_without_storage() -> None:
    """Verify check_all runs cosmos and foundry probes."""
    database = MagicMock()
    database.get_container_client.return_value = AsyncMock()

    results = await check_all(
        database,
        _cosmos_config,
        _foundry_config,
    )

    names = [r.name for r in results]
    assert "Cosmos DB" in names
    assert "Foundry" in names
    assert "Storage" not in names


async def test_check_all_with_storage() -> None:
    """Verify check_all includes storage when config is provided."""
    database = MagicMock()
    database.get_container_client.return_value = AsyncMock()
    storage_client = MagicMock()
    storage_client.get_container.return_value = AsyncMock()
    storage_health = StorageHealthConfig(client=storage_client, config=_storage_config)

    results = await check_all(
        database,
        _cosmos_config,
        _foundry_config,
        storage_health=storage_health,
    )

    names = [r.name for r in results]
    assert "Storage" in names


async def test_check_all_with_foundry_unconfigured() -> None:
    """Verify check_all reports unconfigured Foundry."""
    database = MagicMock()
    database.get_container_client.return_value = AsyncMock()
    config = FoundryConfig(project_endpoint="", model="")

    results = await check_all(
        database,
        _cosmos_config,
        config,
    )

    by_name = {result.name: result for result in results}
    assert by_name["Foundry"].healthy is False
    assert "not set" in (by_name["Foundry"].error or "")
