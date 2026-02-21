"""Base repository with shared Cosmos DB query helpers."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from azure.cosmos.exceptions import CosmosHttpResponseError

from agent_stack.models.base import DocumentBase

if TYPE_CHECKING:
    from azure.cosmos.aio import ContainerProxy, DatabaseProxy


class BaseRepository[T: DocumentBase]:
    """Generic async repository for a Cosmos DB container."""

    container_name: str
    model_class: type[T]

    def __init__(self, database: DatabaseProxy) -> None:
        """Initialize the repository with a Cosmos DB database reference."""
        self._container: ContainerProxy = database.get_container_client(
            self.container_name
        )

    async def create(self, item: T) -> T:
        """Create a new document."""
        body = item.model_dump(mode="json", exclude_none=True)
        await self._container.create_item(body=body)
        return item

    async def get(self, item_id: str, partition_key: str) -> T | None:
        """Read a single document by id and partition key.

        Returns None if soft-deleted.
        """
        try:
            data: dict[str, Any] = await self._container.read_item(
                item=item_id, partition_key=partition_key
            )
        except CosmosHttpResponseError:
            return None
        if data.get("deleted_at") is not None:
            return None
        return self.model_class.model_validate(data)

    async def update(self, item: T, _partition_key: str) -> T:
        """Replace an existing document, updating the timestamp."""
        item.updated_at = datetime.now(UTC)
        body = item.model_dump(mode="json", exclude_none=True)
        # The SDK extracts the partition key from the document body automatically;
        # passing it as a kwarg leaks it through the HTTP pipeline to aiohttp.
        await self._container.replace_item(item=item.id, body=body)
        return item

    async def soft_delete(self, item: T, partition_key: str) -> T:
        """Soft-delete a document by setting deleted_at."""
        item.deleted_at = datetime.now(UTC)
        return await self.update(item, partition_key)

    async def query(
        self, query: str, parameters: list[dict[str, Any]] | None = None
    ) -> list[T]:
        """Run a parameterized query, filtering out soft-deleted documents."""
        return [
            self.model_class.model_validate(item)
            async for item in self._container.query_items(
                query=query, parameters=parameters or []
            )
            if item.get("deleted_at") is None
        ]
