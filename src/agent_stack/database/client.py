"""Async Cosmos DB client initialization."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar, cast

from azure.cosmos import PartitionKey
from azure.cosmos.aio import CosmosClient as AzureCosmosClient
from azure.cosmos.aio import DatabaseProxy
from azure.identity.aio import DefaultAzureCredential

if TYPE_CHECKING:
    from agent_stack.config import CosmosConfig


class CosmosClient:
    """Manages the async Cosmos DB client and database reference."""

    def __init__(self, config: CosmosConfig) -> None:
        """Initialize the Cosmos DB client wrapper with connection config."""
        self._config = config
        self._client: AzureCosmosClient | None = None
        self._credential: DefaultAzureCredential | None = None
        self._database: DatabaseProxy | None = None

    _CONTAINERS: ClassVar[list[tuple[str, str]]] = [
        ("editions", "/id"),
        ("links", "/edition_id"),
        ("feedback", "/edition_id"),
        ("agent_runs", "/trigger_id"),
        ("metadata", "/id"),
    ]

    async def initialize(self) -> None:
        """Create the client and ensure the database and containers exist."""
        self._credential = DefaultAzureCredential()
        self._client = AzureCosmosClient(
            self._config.endpoint, credential=self._credential
        )
        db = cast(
            "DatabaseProxy",
            await self._client.create_database_if_not_exists(self._config.database),
        )
        for name, partition_key in self._CONTAINERS:
            await db.create_container_if_not_exists(
                id=name, partition_key=PartitionKey(path=partition_key)
            )
        self._database = db

    async def close(self) -> None:
        """Close the underlying client."""
        if self._client:
            await self._client.close()
            self._client = None
            self._database = None
        if self._credential:
            await self._credential.close()
            self._credential = None

    @property
    def database(self) -> DatabaseProxy:
        """Return the database proxy, raising if not yet initialized."""
        if self._database is None:
            msg = "CosmosClient not initialized — call initialize() first"
            raise RuntimeError(msg)
        return self._database
