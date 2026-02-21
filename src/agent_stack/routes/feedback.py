"""Feedback routes — submit per-section editor comments."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse

from agent_stack.database.repositories.feedback import FeedbackRepository
from agent_stack.models.feedback import Feedback

router = APIRouter(tags=["feedback"])


@router.post("/editions/{edition_id}/feedback")
async def submit_feedback(
    request: Request,
    edition_id: str,
    section: Annotated[str, Form(...)],
    comment: Annotated[str, Form(...)],
) -> RedirectResponse:
    """Submit editor feedback for a specific section of an edition."""
    cosmos = request.app.state.cosmos
    repo = FeedbackRepository(cosmos.database)
    feedback = Feedback(edition_id=edition_id, section=section, comment=comment)
    await repo.create(feedback)
    return RedirectResponse(f"/editions/{edition_id}", status_code=303)
