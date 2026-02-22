"""Agent run document model — execution logs per pipeline stage."""

from __future__ import annotations

from datetime import datetime  # noqa: TC003 - required at runtime by Pydantic
from enum import StrEnum

from agent_stack.models.base import DocumentBase


class AgentStage(StrEnum):
    """Enumerate pipeline stages an agent can execute."""

    ORCHESTRATOR = "orchestrator"
    FETCH = "fetch"
    REVIEW = "review"
    DRAFT = "draft"
    EDIT = "edit"
    PUBLISH = "publish"


class AgentRunStatus(StrEnum):
    """Enumerate possible statuses for an agent run."""

    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class AgentRun(DocumentBase):
    """Execution log for a single agent pipeline stage."""

    stage: AgentStage
    trigger_id: str
    status: AgentRunStatus = AgentRunStatus.RUNNING
    input: dict | None = None
    output: dict | None = None
    usage: dict | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
