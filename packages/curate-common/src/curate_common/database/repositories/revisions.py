"""Repository for the revisions container (partitioned by /edition_id)."""

from __future__ import annotations

from curate_common.database.repositories.base import BaseRepository
from curate_common.models.revision import Revision


class RevisionRepository(BaseRepository[Revision]):
    """Provide data access for the revisions container."""

    container_name = "revisions"
    model_class = Revision

    async def list_by_edition(self, edition_id: str) -> list[Revision]:
        """Return all revisions for an edition ordered by sequence ascending."""
        return await self.query(
            "SELECT * FROM c WHERE c.edition_id = @edition_id"
            " AND NOT IS_DEFINED(c.deleted_at)"
            " ORDER BY c.sequence ASC",
            [{"name": "@edition_id", "value": edition_id}],
        )

    async def get_latest(self, edition_id: str) -> Revision | None:
        """Return the most recent revision for an edition, or None."""
        results = await self.query(
            "SELECT * FROM c WHERE c.edition_id = @edition_id"
            " AND NOT IS_DEFINED(c.deleted_at)"
            " ORDER BY c.sequence DESC OFFSET 0 LIMIT 1",
            [{"name": "@edition_id", "value": edition_id}],
        )
        return results[0] if results else None

    async def next_sequence(self, edition_id: str) -> int:
        """Return the next sequence number for a new revision."""
        current_max = 0
        async for value in self._container.query_items(
            "SELECT VALUE MAX(c.sequence) FROM c"
            " WHERE c.edition_id = @edition_id"
            " AND NOT IS_DEFINED(c.deleted_at)",
            parameters=[{"name": "@edition_id", "value": edition_id}],
        ):
            if isinstance(value, int | float | str):
                current_max = int(value)
        return current_max + 1
