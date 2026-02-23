"""Feedback routes — submit per-section editor comments."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse

import curate_web.services.feedback as feedback_svc
from curate_common.database.repositories.feedback import FeedbackRepository
from curate_web.auth.middleware import require_authenticated_user

router = APIRouter(
    tags=["feedback"], dependencies=[Depends(require_authenticated_user)]
)

logger = logging.getLogger(__name__)


@router.post("/editions/{edition_id}/feedback")
async def submit_feedback(
    request: Request,
    edition_id: str,
    section: Annotated[str, Form(...)],
    comment: Annotated[str, Form(...)],
    learn_from_feedback: Annotated[str | None, Form()] = None,
) -> RedirectResponse:
    """Submit editor feedback for a specific section of an edition."""
    cosmos = request.app.state.cosmos
    repo = FeedbackRepository(cosmos.database)
    learn = learn_from_feedback == "true"
    await feedback_svc.submit_feedback(
        edition_id, section, comment, repo, learn_from_feedback=learn
    )
    logger.info(
        "Feedback submitted — edition=%s section=%s learn=%s",
        edition_id,
        section,
        learn,
    )
    return RedirectResponse(f"/editions/{edition_id}", status_code=303)
