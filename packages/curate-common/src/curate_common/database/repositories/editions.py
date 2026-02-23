"""Repository for the editions container (partitioned by /id)."""

from __future__ import annotations

from curate_common.database.repositories.base import BaseRepository
from curate_common.models.edition import Edition, EditionStatus


class EditionRepository(BaseRepository[Edition]):
    """Provide data access for the editions container."""

    container_name = "editions"
    model_class = Edition

    async def get_active(self) -> Edition | None:
        """Return the current active (non-published) edition, if any."""
        query = (
            "SELECT * FROM c WHERE c.status != @published"
            " AND NOT IS_DEFINED(c.deleted_at)"
            " ORDER BY c.created_at DESC OFFSET 0 LIMIT 1"
        )
        results = await self.query(
            query,
            [{"name": "@published", "value": EditionStatus.PUBLISHED.value}],
        )
        return results[0] if results else None

    async def list_all(self) -> list[Edition]:
        """Return all active editions ordered by creation date descending."""
        return await self.query(
            "SELECT * FROM c WHERE NOT IS_DEFINED(c.deleted_at)"
            " ORDER BY c.created_at DESC",
        )

    async def list_unpublished(self) -> list[Edition]:
        """Return non-published, non-deleted editions.

        Ordered by creation date descending.
        """
        return await self.query(
            "SELECT * FROM c WHERE c.status != @published"
            " AND NOT IS_DEFINED(c.deleted_at)"
            " ORDER BY c.created_at DESC",
            [{"name": "@published", "value": EditionStatus.PUBLISHED.value}],
        )

    async def list_published(self) -> list[Edition]:
        """Return all published editions."""
        return await self.query(
            "SELECT * FROM c WHERE c.status = @status"
            " AND NOT IS_DEFINED(c.deleted_at)"
            " ORDER BY c.published_at DESC",
            [{"name": "@status", "value": EditionStatus.PUBLISHED.value}],
        )

    async def next_issue_number(self) -> int:
        """Return the next sequential issue number for a new edition."""
        current_max = 0
        async for value in self._container.query_items(
            "SELECT VALUE MAX(c.content.issue_number) FROM c"
            " WHERE NOT IS_DEFINED(c.deleted_at)"
            " AND IS_NUMBER(c.content.issue_number)",
        ):
            if value is not None:
                current_max = int(value)  # ty: ignore[invalid-argument-type]
        return current_max + 1

    async def count_by_status(self) -> dict[str, int]:
        """Return the number of active editions grouped by status."""
        counts: dict[str, int] = {}
        async for item in self._container.query_items(
            "SELECT c.status FROM c WHERE NOT IS_DEFINED(c.deleted_at)",
        ):
            status = item["status"]
            counts[status] = counts.get(status, 0) + 1
        return counts
