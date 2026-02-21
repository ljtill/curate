"""Tests for data models."""

import uuid
from datetime import UTC

from agent_stack.models import (
    AgentRun,
    AgentRunStatus,
    AgentStage,
    Edition,
    EditionStatus,
    Feedback,
    Link,
    LinkStatus,
)
from agent_stack.models.base import DocumentBase, _new_id, _utcnow


def test_new_id_generates_valid_uuid() -> None:
    """Verify new id generates valid uuid."""
    result = _new_id()
    parsed = uuid.UUID(result)
    assert str(parsed) == result


def test_utcnow_returns_utc() -> None:
    """Verify utcnow returns utc."""
    now = _utcnow()
    assert now.tzinfo == UTC


def test_document_base_defaults() -> None:
    """Verify document base defaults."""
    doc = DocumentBase()
    assert doc.id  # non-empty
    assert doc.created_at is not None
    assert doc.updated_at is not None
    assert doc.deleted_at is None


def test_document_base_unique_ids() -> None:
    """Verify document base unique ids."""
    doc1 = DocumentBase()
    doc2 = DocumentBase()
    assert doc1.id != doc2.id


def test_link_defaults() -> None:
    """Verify link defaults."""
    link = Link(url="https://example.com", edition_id="ed-1")
    assert link.status == LinkStatus.SUBMITTED
    assert link.title is None
    assert link.content is None
    assert link.review is None
    assert link.deleted_at is None
    assert link.id  # auto-generated


def test_edition_defaults() -> None:
    """Verify edition defaults."""
    edition = Edition()
    assert edition.status == EditionStatus.CREATED
    assert edition.content == {}
    assert edition.link_ids == []
    assert edition.published_at is None


def test_feedback_model() -> None:
    """Verify feedback model."""
    fb = Feedback(edition_id="ed-1", section="intro", comment="Needs more context")
    assert fb.resolved is False
    assert fb.edition_id == "ed-1"


def test_agent_run_model() -> None:
    """Verify agent run model."""
    run = AgentRun(stage=AgentStage.FETCH, trigger_id="link-1")
    assert run.status == AgentRunStatus.RUNNING
    assert run.completed_at is None


def test_link_status_enum() -> None:
    """Verify link status enum."""
    assert LinkStatus.SUBMITTED == "submitted"
    assert LinkStatus.FETCHING == "fetching"
    assert LinkStatus.REVIEWED == "reviewed"
    assert LinkStatus.DRAFTED == "drafted"


def test_edition_status_enum() -> None:
    """Verify edition status enum."""
    assert EditionStatus.CREATED == "created"
    assert EditionStatus.DRAFTING == "drafting"
    assert EditionStatus.IN_REVIEW == "in_review"
    assert EditionStatus.PUBLISHED == "published"
