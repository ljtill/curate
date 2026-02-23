"""Base repository with shared Cosmos DB query helpers."""

from __future__ import annotations

import logging
import os
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from azure.cosmos.exceptions import CosmosHttpResponseError

from curate_common.models.base import DocumentBase

if TYPE_CHECKING:
    from azure.cosmos.aio import ContainerProxy, DatabaseProxy

logger = logging.getLogger(__name__)


class BaseRepository[T: DocumentBase]:
    """Generic async repository for a Cosmos DB container."""

    container_name: str
    model_class: type[T]

    def __init__(self, database: DatabaseProxy) -> None:
        """Initialize the repository with a Cosmos DB database reference."""
        self._container: ContainerProxy = database.get_container_client(
            self.container_name
        )
        self._slow_operation_ms = int(os.environ.get("APP_SLOW_REPOSITORY_MS", "250"))

    def _log_operation(
        self,
        operation: str,
        started_at: float,
        *,
        item_id: str | None = None,
        outcome: str | None = None,
        result_count: int | None = None,
        parameter_count: int | None = None,
    ) -> None:
        duration_ms = (time.monotonic() - started_at) * 1000
        details: list[str] = []
        if item_id is not None:
            details.append(f"item_id={item_id}")
        if outcome is not None:
            details.append(f"outcome={outcome}")
        if result_count is not None:
            details.append(f"results={result_count}")
        if parameter_count is not None:
            details.append(f"params={parameter_count}")
        detail_text = " ".join(details) if details else "details=none"
        message = "Repository operation — container=%s op=%s duration_ms=%.0f %s"
        if duration_ms >= self._slow_operation_ms:
            logger.warning(
                "Slow repository operation — container=%s op=%s duration_ms=%.0f %s",
                self.container_name,
                operation,
                duration_ms,
                detail_text,
            )
            return
        logger.debug(
            message,
            self.container_name,
            operation,
            duration_ms,
            detail_text,
        )

    async def create(self, item: T) -> T:
        """Create a new document."""
        started_at = time.monotonic()
        body = item.model_dump(mode="json", exclude_none=True)
        await self._container.create_item(body=body)
        self._log_operation("create", started_at, item_id=item.id, outcome="created")
        logger.debug(
            "Document created — container=%s id=%s", self.container_name, item.id
        )
        return item

    async def get(self, item_id: str, partition_key: str) -> T | None:
        """Read a single document by id and partition key.

        Returns None if soft-deleted.
        """
        started_at = time.monotonic()
        try:
            data: dict[str, Any] = await self._container.read_item(
                item=item_id, partition_key=partition_key
            )
        except CosmosHttpResponseError:
            self._log_operation("get", started_at, item_id=item_id, outcome="not_found")
            return None
        if data.get("deleted_at") is not None:
            self._log_operation(
                "get", started_at, item_id=item_id, outcome="soft_deleted"
            )
            return None
        self._log_operation("get", started_at, item_id=item_id, outcome="found")
        return self.model_class.model_validate(data)

    async def update(self, item: T, _partition_key: str) -> T:
        """Replace an existing document, updating the timestamp."""
        started_at = time.monotonic()
        item.updated_at = datetime.now(UTC)
        body = item.model_dump(mode="json", exclude_none=True)
        # The SDK extracts the partition key from the document body automatically;
        # passing it as a kwarg leaks it through the HTTP pipeline to aiohttp.
        await self._container.replace_item(item=item.id, body=body)
        self._log_operation("update", started_at, item_id=item.id, outcome="updated")
        logger.debug(
            "Document updated — container=%s id=%s", self.container_name, item.id
        )
        return item

    async def soft_delete(self, item: T, partition_key: str) -> T:
        """Soft-delete a document by setting deleted_at."""
        logger.debug(
            "Document soft-deleted — container=%s id=%s", self.container_name, item.id
        )
        item.deleted_at = datetime.now(UTC)
        return await self.update(item, partition_key)

    async def query(
        self, query: str, parameters: list[dict[str, Any]] | None = None
    ) -> list[T]:
        """Run a parameterized query, filtering out soft-deleted documents."""
        started_at = time.monotonic()
        params = parameters or []
        results = [
            self.model_class.model_validate(item)
            async for item in self._container.query_items(
                query=query, parameters=params
            )
            if item.get("deleted_at") is None
        ]
        self._log_operation(
            "query",
            started_at,
            outcome="ok",
            result_count=len(results),
            parameter_count=len(params),
        )
        return results
