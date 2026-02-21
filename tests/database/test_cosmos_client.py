"""Tests for the Cosmos DB client."""

from unittest.mock import AsyncMock, patch

import pytest

from agent_stack.config import CosmosConfig
from agent_stack.database.client import CosmosClient

_EXPECTED_CONTAINER_COUNT = 4


@pytest.mark.unit
class TestCosmosClient:
    """Test the Cosmos Client."""

    @pytest.fixture
    def config(self) -> tuple[CosmosConfig, object, object]:
        """Create a config for testing."""
        return CosmosConfig(endpoint="https://localhost:8081", key="test-key", database="test-db")

    @pytest.fixture
    def client(self, config: CosmosConfig) -> CosmosClient:
        """Create a mock client."""
        return CosmosClient(config)

    async def test_initialize_creates_db_and_containers(self, client: CosmosClient) -> None:
        """Verify initialize creates db and containers."""
        with patch("agent_stack.database.client.AzureCosmosClient") as mock_azure_cls:
            mock_azure = AsyncMock()
            mock_db = AsyncMock()
            mock_azure.create_database_if_not_exists.return_value = mock_db
            mock_azure_cls.return_value = mock_azure

            await client.initialize()

            mock_azure.create_database_if_not_exists.assert_called_once_with("test-db")
            assert mock_db.create_container_if_not_exists.call_count == _EXPECTED_CONTAINER_COUNT

    async def test_close_cleans_up(self, client: CosmosClient) -> None:
        """Verify close cleans up."""
        with patch("agent_stack.database.client.AzureCosmosClient") as mock_azure_cls:
            mock_azure = AsyncMock()
            mock_db = AsyncMock()
            mock_azure.create_database_if_not_exists.return_value = mock_db
            mock_azure_cls.return_value = mock_azure

            await client.initialize()
            await client.close()

            mock_azure.close.assert_awaited_once()
            with pytest.raises(RuntimeError, match="not initialized"):
                _ = client.database

    async def test_close_noop_when_not_initialized(self, client: CosmosClient) -> None:
        """Verify close noop when not initialized."""
        await client.close()  # Should not raise

    def test_database_property_raises_when_not_initialized(self, client: CosmosClient) -> None:
        """Verify database property raises when not initialized."""
        with pytest.raises(RuntimeError, match="not initialized"):
            _ = client.database

    async def test_database_property_returns_after_init(self, client: CosmosClient) -> None:
        """Verify database property returns after init."""
        with patch("agent_stack.database.client.AzureCosmosClient") as mock_azure_cls:
            mock_azure = AsyncMock()
            mock_db = AsyncMock()
            mock_azure.create_database_if_not_exists.return_value = mock_db
            mock_azure_cls.return_value = mock_azure

            await client.initialize()

            assert client.database == mock_db
