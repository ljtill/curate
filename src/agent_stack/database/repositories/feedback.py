"""Repository for the feedback container (partitioned by /edition_id)."""

from __future__ import annotations

from agent_stack.database.repositories.base import BaseRepository
from agent_stack.models.feedback import Feedback


class FeedbackRepository(BaseRepository[Feedback]):
    """Provide data access for the feedback container."""

    container_name = "feedback"
    model_class = Feedback

    async def get_by_edition(self, edition_id: str) -> list[Feedback]:
        """Fetch all active feedback for a given edition."""
        return await self.query(
            "SELECT * FROM c WHERE c.edition_id = @edition_id"
            " AND NOT IS_DEFINED(c.deleted_at)",
            [{"name": "@edition_id", "value": edition_id}],
        )

    async def get_unresolved(self, edition_id: str) -> list[Feedback]:
        """Fetch unresolved feedback for a given edition."""
        return await self.query(
            "SELECT * FROM c WHERE c.edition_id = @edition_id"
            " AND c.resolved = false"
            " AND NOT IS_DEFINED(c.deleted_at)",
            [{"name": "@edition_id", "value": edition_id}],
        )
