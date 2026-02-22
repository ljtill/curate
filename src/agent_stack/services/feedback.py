"""Feedback business logic — submit editor comments."""

from __future__ import annotations

from typing import TYPE_CHECKING

from agent_stack.models.feedback import Feedback

if TYPE_CHECKING:
    from agent_stack.database.repositories.feedback import FeedbackRepository


async def submit_feedback(
    edition_id: str,
    section: str,
    comment: str,
    feedback_repo: FeedbackRepository,
) -> Feedback:
    """Create a feedback document for an edition section."""
    feedback = Feedback(edition_id=edition_id, section=section, comment=comment)
    await feedback_repo.create(feedback)
    return feedback
