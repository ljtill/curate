"""Tests for health check probes."""

from unittest.mock import AsyncMock, MagicMock, patch

from curate_common.config import (
    CosmosConfig,
    FoundryConfig,
    ServiceBusConfig,
    StorageConfig,
)
from curate_web.services.health import (
    StorageHealthConfig,
    _check_foundry_config,
    _storage_account_name,
    check_all,
    check_cosmos,
    check_servicebus,
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


_servicebus_config = ServiceBusConfig(
    connection_string="Endpoint=sb://test.servicebus.windows.net/;SharedAccessKeyName=key;SharedAccessKey=abc",
    topic_name="pipeline-events",
    subscription_name="web-consumer",
)


async def test_check_servicebus_not_configured() -> None:
    """Verify Service Bus reports unhealthy when connection string is empty."""
    config = ServiceBusConfig(
        connection_string="",
        topic_name="t",
        subscription_name="s",
    )

    result = await check_servicebus(config)

    assert result.healthy is False
    assert result.name == "Service Bus"
    assert "not set" in result.error


async def test_check_servicebus_healthy() -> None:
    """Verify Service Bus reports healthy when connection succeeds."""
    mock_receiver = MagicMock()
    mock_receiver.__aenter__ = AsyncMock(return_value=mock_receiver)
    mock_receiver.__aexit__ = AsyncMock(return_value=False)
    mock_client = MagicMock()
    mock_client.get_subscription_receiver.return_value = mock_receiver
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch(
        "azure.servicebus.aio.ServiceBusClient",
    ) as mock_cls:
        mock_cls.from_connection_string.return_value = mock_client
        result = await check_servicebus(_servicebus_config)

    assert result.healthy is True
    assert result.name == "Service Bus"
    assert result.latency_ms is not None
    assert result.detail == "pipeline-events · web-consumer"


async def test_check_servicebus_unhealthy() -> None:
    """Verify Service Bus reports unhealthy when connection fails."""
    from azure.core.exceptions import AzureError as _AzureError  # noqa: PLC0415

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get_subscription_receiver.side_effect = _AzureError(
        "Connection refused",
    )

    with patch(
        "azure.servicebus.aio.ServiceBusClient",
    ) as mock_cls:
        mock_cls.from_connection_string.return_value = mock_client
        result = await check_servicebus(_servicebus_config)

    assert result.healthy is False
    assert "Connection refused" in result.error


async def test_check_all_with_servicebus() -> None:
    """Verify check_all includes Service Bus when config is provided."""
    database = MagicMock()
    database.get_container_client.return_value = AsyncMock()

    sb_config = ServiceBusConfig(
        connection_string="",
        topic_name="t",
        subscription_name="s",
    )

    results = await check_all(
        database,
        _cosmos_config,
        _foundry_config,
        servicebus_config=sb_config,
    )

    names = [r.name for r in results]
    assert "Service Bus" in names
