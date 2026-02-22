"""Link document model — submitted URLs with processing status."""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from agent_stack.models.base import DocumentBase


class LinkStatus(StrEnum):
    """Enumerate processing statuses for a submitted link."""

    SUBMITTED = "submitted"
    FETCHING = "fetching"
    REVIEWED = "reviewed"
    DRAFTED = "drafted"
    FAILED = "failed"


class Link(DocumentBase):
    """A submitted URL tracked through the agent pipeline."""

    url: str
    title: str | None = None
    status: LinkStatus = LinkStatus.SUBMITTED
    content: str | None = None
    review: dict | None = None
    edition_id: str = Field(..., description="Associated edition (partition key)")
