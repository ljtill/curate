"""Feedback business logic — submit editor comments."""

from __future__ import annotations

from typing import TYPE_CHECKING

from curate_common.models.feedback import Feedback

if TYPE_CHECKING:
    from curate_common.database.repositories.feedback import FeedbackRepository


async def submit_feedback(
    edition_id: str,
    section: str,
    comment: str,
    feedback_repo: FeedbackRepository,
    *,
    learn_from_feedback: bool = True,
) -> Feedback:
    """Create a feedback document for an edition section."""
    feedback = Feedback(
        edition_id=edition_id,
        section=section,
        comment=comment,
        learn_from_feedback=learn_from_feedback,
    )
    await feedback_repo.create(feedback)
    return feedback
