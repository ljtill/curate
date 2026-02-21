"""Repository for the editions container (partitioned by /id)."""

from __future__ import annotations

from agent_stack.database.repositories.base import BaseRepository
from agent_stack.models.edition import Edition, EditionStatus


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
