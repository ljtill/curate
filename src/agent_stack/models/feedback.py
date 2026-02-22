"""Feedback document model — per-section editor comments."""

from __future__ import annotations

from agent_stack.models.base import DocumentBase


class Feedback(DocumentBase):
    """Structured editor feedback linked to an edition section."""

    edition_id: str
    section: str
    comment: str
    resolved: bool = False
    learn_from_feedback: bool = True
