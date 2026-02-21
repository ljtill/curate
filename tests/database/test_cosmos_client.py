"""Tests for the Cosmos DB client."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_stack.config import CosmosConfig
from agent_stack.database.client import CosmosClient


@pytest.mark.unit
class TestCosmosClient:
    @pytest.fixture
    def config(self):
        return CosmosConfig(endpoint="https://localhost:8081", key="test-key", database="test-db")

    @pytest.fixture
    def client(self, config):
        return CosmosClient(config)

    async def test_initialize_creates_db_and_containers(self, client):
        with patch("agent_stack.database.client.AzureCosmosClient") as MockAzure:
            mock_azure = AsyncMock()
            mock_db = AsyncMock()
            mock_azure.create_database_if_not_exists.return_value = mock_db
            MockAzure.return_value = mock_azure

            await client.initialize()

            mock_azure.create_database_if_not_exists.assert_called_once_with("test-db")
            assert mock_db.create_container_if_not_exists.call_count == 4

    async def test_close_cleans_up(self, client):
        mock_azure = AsyncMock()
        client._client = mock_azure
        client._database = MagicMock()

        await client.close()

        mock_azure.close.assert_awaited_once()
        assert client._client is None
        assert client._database is None

    async def test_close_noop_when_not_initialized(self, client):
        await client.close()  # Should not raise

    def test_database_property_raises_when_not_initialized(self, client):
        with pytest.raises(RuntimeError, match="not initialized"):
            _ = client.database

    async def test_database_property_returns_after_init(self, client):
        with patch("agent_stack.database.client.AzureCosmosClient") as MockAzure:
            mock_azure = AsyncMock()
            mock_db = AsyncMock()
            mock_azure.create_database_if_not_exists.return_value = mock_db
            MockAzure.return_value = mock_azure

            await client.initialize()

            assert client.database == mock_db
