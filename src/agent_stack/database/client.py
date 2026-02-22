"""Async Cosmos DB client initialization."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, ClassVar, cast

from azure.cosmos import PartitionKey
from azure.cosmos.aio import CosmosClient as AzureCosmosClient
from azure.cosmos.aio import DatabaseProxy

if TYPE_CHECKING:
    from azure.core.credentials_async import AsyncTokenCredential

    from agent_stack.config import CosmosConfig

logger = logging.getLogger(__name__)

_EMULATOR_KEY = (
    "C2y6yDjf5/R+ob0N8A7Cgv30VRDJIWEHLM"
    "+4QDU5DE2nQ9nDuVTqobD4b8mGGyPMbIZnqyMsEcaGQy67XIw/Jw=="
)


class CosmosClient:
    """Manages the async Cosmos DB client and database reference."""

    def __init__(self, config: CosmosConfig) -> None:
        """Initialize the Cosmos DB client wrapper with connection config."""
        self._config = config
        self._client: AzureCosmosClient | None = None
        self._credential: AsyncTokenCredential | None = None
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
        if self._config.endpoint.startswith("https://"):
            from azure.identity.aio import DefaultAzureCredential  # noqa: PLC0415

            self._credential = DefaultAzureCredential()
            self._client = AzureCosmosClient(
                self._config.endpoint, credential=self._credential
            )
        else:
            self._client = AzureCosmosClient(
                self._config.endpoint, credential=_EMULATOR_KEY
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
        logger.info(
            "Cosmos DB initialized — endpoint=%s database=%s",
            self._config.endpoint,
            self._config.database,
        )

    async def close(self) -> None:
        """Close the underlying client."""
        if self._client:
            await self._client.close()
            self._client = None
            self._database = None
        if self._credential:
            await self._credential.close()
            self._credential = None
        logger.info("Cosmos DB client closed")

    @property
    def database(self) -> DatabaseProxy:
        """Return the database proxy, raising if not yet initialized."""
        if self._database is None:
            msg = "CosmosClient not initialized — call initialize() first"
            raise RuntimeError(msg)
        return self._database
