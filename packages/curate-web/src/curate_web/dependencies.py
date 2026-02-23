"""Typed repository providers for web routes."""

from __future__ import annotations

from typing import TYPE_CHECKING

from curate_common.database.repositories.agent_runs import AgentRunRepository
from curate_common.database.repositories.editions import EditionRepository
from curate_common.database.repositories.feedback import FeedbackRepository
from curate_common.database.repositories.links import LinkRepository
from curate_common.database.repositories.revisions import RevisionRepository

if TYPE_CHECKING:
    from curate_web.runtime import WebRuntime


def get_agent_run_repository(runtime: WebRuntime) -> AgentRunRepository:
    """Return an agent-run repository bound to the runtime database."""
    return AgentRunRepository(runtime.cosmos.database)


def get_edition_repository(runtime: WebRuntime) -> EditionRepository:
    """Return an edition repository bound to the runtime database."""
    return EditionRepository(runtime.cosmos.database)


def get_feedback_repository(runtime: WebRuntime) -> FeedbackRepository:
    """Return a feedback repository bound to the runtime database."""
    return FeedbackRepository(runtime.cosmos.database)


def get_link_repository(runtime: WebRuntime) -> LinkRepository:
    """Return a link repository bound to the runtime database."""
    return LinkRepository(runtime.cosmos.database)


def get_revision_repository(runtime: WebRuntime) -> RevisionRepository:
    """Return a revision repository bound to the runtime database."""
    return RevisionRepository(runtime.cosmos.database)
