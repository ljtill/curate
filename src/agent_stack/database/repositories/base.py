"""Base repository with shared Cosmos DB query helpers."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from azure.cosmos.aio import ContainerProxy, DatabaseProxy

from agent_stack.models.base import DocumentBase


class BaseRepository[T: DocumentBase]:
    """Generic async repository for a Cosmos DB container."""

    container_name: str
    model_class: type[T]

    def __init__(self, database: DatabaseProxy) -> None:
        self._container: ContainerProxy = database.get_container_client(self.container_name)

    async def create(self, item: T) -> T:
        """Create a new document."""
        body = item.model_dump(mode="json", exclude_none=True)
        await self._container.create_item(body=body)
        return item

    async def get(self, item_id: str, partition_key: str) -> T | None:
        """Read a single document by id and partition key, returning None if soft-deleted."""
        try:
            data: dict[str, Any] = await self._container.read_item(item=item_id, partition_key=partition_key)
        except Exception:
            return None
        if data.get("deleted_at") is not None:
            return None
        return self.model_class.model_validate(data)

    async def update(self, item: T, partition_key: str) -> T:
        """Replace an existing document, updating the timestamp."""
        item.updated_at = datetime.now(UTC)
        body = item.model_dump(mode="json", exclude_none=True)
        await self._container.replace_item(item=item.id, body=body, partition_key=partition_key)
        return item

    async def soft_delete(self, item: T, partition_key: str) -> T:
        """Soft-delete a document by setting deleted_at."""
        item.deleted_at = datetime.now(UTC)
        return await self.update(item, partition_key)

    async def query(self, query: str, parameters: list[dict[str, Any]] | None = None) -> list[T]:
        """Run a parameterized query, filtering out soft-deleted documents."""
        items: list[T] = []
        async for item in self._container.query_items(query=query, parameters=parameters or []):
            if item.get("deleted_at") is None:
                items.append(self.model_class.model_validate(item))
        return items
