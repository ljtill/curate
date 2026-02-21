"""Tests for EditAgent tool methods."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_stack.agents.edit import EditAgent
from agent_stack.models.edition import Edition
from agent_stack.models.feedback import Feedback


@pytest.fixture
def repos() -> tuple[AsyncMock, AsyncMock, object]:
    """Create mock repository instances."""
    return AsyncMock(), AsyncMock()  # editions_repo, feedback_repo


@pytest.fixture
def edit_agent(repos: tuple[AsyncMock, AsyncMock]) -> tuple[EditAgent, object, object]:
    """Create a edit agent for testing."""
    editions_repo, feedback_repo = repos
    client = MagicMock()
    with patch("agent_stack.agents.edit.Agent"):
        return EditAgent(client, editions_repo, feedback_repo)


@pytest.mark.asyncio
async def test_get_edition_content(edit_agent: EditAgent, repos: tuple[AsyncMock, AsyncMock]) -> None:
    """Verify get edition content."""
    editions_repo, _ = repos
    edition = Edition(id="ed-1", content={"title": "Test"})
    editions_repo.get.return_value = edition

    result = json.loads(await edit_agent.get_edition_content("ed-1"))
    assert result["title"] == "Test"


@pytest.mark.asyncio
async def test_get_feedback_returns_unresolved(edit_agent: EditAgent, repos: tuple[AsyncMock, AsyncMock]) -> None:
    """Verify get feedback returns unresolved."""
    _, feedback_repo = repos
    items = [
        Feedback(id="fb-1", edition_id="ed-1", section="intro", comment="Fix this"),
        Feedback(id="fb-2", edition_id="ed-1", section="outro", comment="Rewrite"),
    ]
    feedback_repo.get_unresolved.return_value = items

    result = json.loads(await edit_agent.get_feedback("ed-1"))
    assert len(result) == 2
    assert result[0]["section"] == "intro"
    assert result[1]["comment"] == "Rewrite"


@pytest.mark.asyncio
async def test_save_edit_updates_content(edit_agent: EditAgent, repos: tuple[AsyncMock, AsyncMock]) -> None:
    """Verify save edit updates content."""
    editions_repo, _ = repos
    edition = Edition(id="ed-1", content={"old": True})
    editions_repo.get.return_value = edition

    content = json.dumps({"new": True})
    result = json.loads(await edit_agent.save_edit("ed-1", content))

    assert result["status"] == "edited"
    assert edition.content == {"new": True}
    editions_repo.update.assert_called_once()


@pytest.mark.asyncio
async def test_resolve_feedback_marks_resolved(edit_agent: EditAgent, repos: tuple[AsyncMock, AsyncMock]) -> None:
    """Verify resolve feedback marks resolved."""
    _, feedback_repo = repos
    fb = Feedback(id="fb-1", edition_id="ed-1", section="intro", comment="Fix", resolved=False)
    feedback_repo.get.return_value = fb

    result = json.loads(await edit_agent.resolve_feedback("fb-1", "ed-1"))

    assert result["status"] == "resolved"
    assert fb.resolved is True
    feedback_repo.update.assert_called_once()


@pytest.mark.asyncio
async def test_resolve_feedback_not_found(edit_agent: EditAgent, repos: tuple[AsyncMock, AsyncMock]) -> None:
    """Verify resolve feedback not found."""
    _, feedback_repo = repos
    feedback_repo.get.return_value = None

    result = json.loads(await edit_agent.resolve_feedback("missing", "ed-1"))
    assert "error" in result
