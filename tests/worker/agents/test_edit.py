"""Tests for EditAgent tool methods."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from curate_common.models.edition import Edition
from curate_common.models.feedback import Feedback
from curate_worker.agents.edit import EditAgent


@pytest.fixture
def repos() -> tuple[AsyncMock, AsyncMock, object]:
    """Create mock repository instances."""
    return AsyncMock(), AsyncMock()


@pytest.fixture
def edit_agent(repos: tuple[AsyncMock, AsyncMock]) -> tuple[EditAgent, object, object]:
    """Create a edit agent for testing."""
    editions_repo, feedback_repo = repos
    client = MagicMock()
    with patch("curate_worker.agents.edit.Agent"):
        return EditAgent(client, editions_repo, feedback_repo)


async def test_get_edition_content(
    edit_agent: EditAgent, repos: tuple[AsyncMock, AsyncMock]
) -> None:
    """Verify get edition content."""
    editions_repo, _ = repos
    edition = Edition(id="ed-1", content={"title": "Test"})
    editions_repo.get.return_value = edition

    result = json.loads(await edit_agent.get_edition_content("ed-1"))
    assert result["title"] == "Test"


_EXPECTED_FEEDBACK_COUNT = 2


async def test_get_feedback_returns_unresolved(
    edit_agent: EditAgent, repos: tuple[AsyncMock, AsyncMock]
) -> None:
    """Verify get feedback returns unresolved."""
    _, feedback_repo = repos
    items = [
        Feedback(id="fb-1", edition_id="ed-1", section="intro", comment="Fix this"),
        Feedback(id="fb-2", edition_id="ed-1", section="outro", comment="Rewrite"),
    ]
    feedback_repo.get_unresolved.return_value = items

    result = json.loads(await edit_agent.get_feedback("ed-1"))
    assert len(result) == _EXPECTED_FEEDBACK_COUNT
    assert result[0]["section"] == "intro"
    assert result[1]["comment"] == "Rewrite"


async def test_save_edit_updates_content(
    edit_agent: EditAgent, repos: tuple[AsyncMock, AsyncMock]
) -> None:
    """Verify save edit updates content."""
    editions_repo, _ = repos
    edition = Edition(id="ed-1", content={"old": True})
    editions_repo.get.return_value = edition

    content = json.dumps({"new": True})
    result = json.loads(await edit_agent.save_edit("ed-1", content))

    assert result["status"] == "edited"
    assert edition.content == {"new": True}
    editions_repo.update.assert_called_once()


async def test_resolve_feedback_marks_resolved(
    edit_agent: EditAgent, repos: tuple[AsyncMock, AsyncMock]
) -> None:
    """Verify resolve feedback marks resolved."""
    _, feedback_repo = repos
    fb = Feedback(
        id="fb-1", edition_id="ed-1", section="intro", comment="Fix", resolved=False
    )
    feedback_repo.get.return_value = fb

    result = json.loads(await edit_agent.resolve_feedback("fb-1", "ed-1"))

    assert result["status"] == "resolved"
    assert fb.resolved is True
    feedback_repo.update.assert_called_once()


async def test_resolve_feedback_not_found(
    edit_agent: EditAgent, repos: tuple[AsyncMock, AsyncMock]
) -> None:
    """Verify resolve feedback not found."""
    _, feedback_repo = repos
    feedback_repo.get.return_value = None

    result = json.loads(await edit_agent.resolve_feedback("missing", "ed-1"))
    assert "error" in result


async def test_save_edit_invalid_json_returns_error(
    edit_agent: EditAgent, repos: tuple[AsyncMock, AsyncMock]
) -> None:
    """Verify save_edit with invalid JSON content returns an error."""
    editions_repo, _ = repos
    edition = Edition(id="ed-1", content={"old": True})
    editions_repo.get.return_value = edition

    result = json.loads(await edit_agent.save_edit("ed-1", "{not valid json"))
    assert result["error"] == "Invalid JSON content"
    editions_repo.update.assert_not_called()


async def test_save_edit_valid_json_succeeds(
    edit_agent: EditAgent, repos: tuple[AsyncMock, AsyncMock]
) -> None:
    """Verify save_edit with valid JSON content succeeds."""
    editions_repo, _ = repos
    edition = Edition(id="ed-1", content={})
    editions_repo.get.return_value = edition

    content = json.dumps({"headline": "Hello World"})
    result = json.loads(await edit_agent.save_edit("ed-1", content))

    assert result["status"] == "edited"
    assert edition.content == {"headline": "Hello World"}
    editions_repo.update.assert_called_once()


async def test_run_raises_on_failure(
    edit_agent: EditAgent,
) -> None:
    """Verify run() re-raises exceptions from the inner agent."""
    edit_agent._agent.run = AsyncMock(  # noqa: SLF001
        side_effect=RuntimeError("LLM error"),
    )

    with pytest.raises(RuntimeError, match="LLM error"):
        await edit_agent.run("ed-1")
