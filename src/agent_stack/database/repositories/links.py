"""Repository for the links container (partitioned by /edition_id)."""

from __future__ import annotations

from agent_stack.database.repositories.base import BaseRepository
from agent_stack.models.link import Link, LinkStatus


class LinkRepository(BaseRepository[Link]):
    """Provide data access for the links container."""

    container_name = "links"
    model_class = Link

    async def get_by_edition(self, edition_id: str) -> list[Link]:
        """Fetch all active links for a given edition."""
        return await self.query(
            "SELECT * FROM c WHERE c.edition_id = @edition_id"
            " AND NOT IS_DEFINED(c.deleted_at)",
            [{"name": "@edition_id", "value": edition_id}],
        )

    async def get_by_status(self, edition_id: str, status: LinkStatus) -> list[Link]:
        """Fetch links with a specific status within an edition."""
        return await self.query(
            "SELECT * FROM c WHERE c.edition_id = @edition_id"
            " AND c.status = @status"
            " AND NOT IS_DEFINED(c.deleted_at)",
            [
                {"name": "@edition_id", "value": edition_id},
                {"name": "@status", "value": status.value},
            ],
        )
