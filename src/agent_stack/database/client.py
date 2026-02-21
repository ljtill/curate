"""Async Cosmos DB client initialization."""

from __future__ import annotations

from typing import cast

from azure.cosmos import PartitionKey
from azure.cosmos.aio import CosmosClient as AzureCosmosClient
from azure.cosmos.aio import DatabaseProxy

from agent_stack.config import CosmosConfig


class CosmosClient:
    """Manages the async Cosmos DB client and database reference."""

    def __init__(self, config: CosmosConfig) -> None:
        self._config = config
        self._client: AzureCosmosClient | None = None
        self._database: DatabaseProxy | None = None

    _CONTAINERS: list[tuple[str, str]] = [
        ("editions", "/id"),
        ("links", "/edition_id"),
        ("feedback", "/edition_id"),
        ("agent_runs", "/trigger_id"),
    ]

    async def initialize(self) -> None:
        """Create the client and ensure the database and containers exist."""
        self._client = AzureCosmosClient(self._config.endpoint, credential=self._config.key)
        db = cast(DatabaseProxy, await self._client.create_database_if_not_exists(self._config.database))
        for name, partition_key in self._CONTAINERS:
            await db.create_container_if_not_exists(id=name, partition_key=PartitionKey(path=partition_key))
        self._database = db

    async def close(self) -> None:
        """Close the underlying client."""
        if self._client:
            await self._client.close()
            self._client = None
            self._database = None

    @property
    def database(self) -> DatabaseProxy:
        if self._database is None:
            raise RuntimeError("CosmosClient not initialized — call initialize() first")
        return self._database
