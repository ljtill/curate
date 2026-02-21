"""Integration tests for the pipeline orchestrator routing and agent run logging."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_stack.models.agent_run import AgentRunStatus
from agent_stack.models.link import Link, LinkStatus
from agent_stack.pipeline.orchestrator import PipelineOrchestrator

_EXPECTED_LINK_GET_COUNT = 3

_MockRepos = tuple[AsyncMock, AsyncMock, AsyncMock, AsyncMock]


@pytest.fixture
def mock_repos() -> _MockRepos:
    """Create mock repositories for integration testing."""
    links = AsyncMock()
    editions = AsyncMock()
    feedback = AsyncMock()
    agent_runs = AsyncMock()
    return links, editions, feedback, agent_runs


@pytest.fixture
def orchestrator(mock_repos: tuple[AsyncMock, AsyncMock, AsyncMock, AsyncMock]) -> None:
    """Create a PipelineOrchestrator with mocked dependencies."""
    links, editions, feedback, agent_runs = mock_repos
    client = MagicMock()

    with (
        patch("agent_stack.pipeline.orchestrator.FetchAgent"),
        patch("agent_stack.pipeline.orchestrator.ReviewAgent"),
        patch("agent_stack.pipeline.orchestrator.DraftAgent"),
        patch("agent_stack.pipeline.orchestrator.EditAgent"),
        patch("agent_stack.pipeline.orchestrator.PublishAgent"),
        patch("agent_stack.pipeline.orchestrator.EventManager") as mock_events_cls,
    ):
        mock_events = AsyncMock()
        mock_events_cls.get_instance.return_value = mock_events

    return PipelineOrchestrator(client, links, editions, feedback, agent_runs)


@pytest.mark.asyncio
async def test_handle_link_change_submitted(
    orchestrator: PipelineOrchestrator, mock_repos: _MockRepos
) -> None:
    """Test that a submitted link triggers the fetch agent and logs a run."""
    links, _, _, agent_runs = mock_repos
    link = Link(
        id="link-1",
        url="https://example.com",
        edition_id="ed-1",
        status=LinkStatus.SUBMITTED,
    )
    links.get.return_value = link

    orchestrator.fetch = AsyncMock()
    orchestrator.fetch.run = AsyncMock(
        return_value={"usage": None, "message": "test", "response": "ok"}
    )

    await orchestrator.handle_link_change(
        {
            "id": "link-1",
            "edition_id": "ed-1",
            "status": "submitted",
        }
    )

    links.get.assert_called_with("link-1", "ed-1")
    assert (
        links.get.call_count == _EXPECTED_LINK_GET_COUNT
    )  # initial fetch + fail check + SSE publish
    agent_runs.create.assert_called_once()
    orchestrator.fetch.run.assert_called_once_with(link)


@pytest.mark.asyncio
async def test_handle_link_change_drafted_is_noop(
    orchestrator: PipelineOrchestrator, mock_repos: _MockRepos
) -> None:
    """Test that a drafted link does not trigger any agent."""
    links, _, _, agent_runs = mock_repos
    link = Link(
        id="link-2",
        url="https://example.com",
        edition_id="ed-1",
        status=LinkStatus.DRAFTED,
    )
    links.get.return_value = link

    await orchestrator.handle_link_change(
        {
            "id": "link-2",
            "edition_id": "ed-1",
            "status": "drafted",
        }
    )

    agent_runs.create.assert_not_called()


@pytest.mark.asyncio
async def test_handle_link_change_not_found(
    orchestrator: PipelineOrchestrator, mock_repos: _MockRepos
) -> None:
    """Test that a missing link is handled gracefully."""
    links, _, _, agent_runs = mock_repos
    links.get.return_value = None

    await orchestrator.handle_link_change(
        {
            "id": "missing",
            "edition_id": "ed-1",
            "status": "submitted",
        }
    )

    agent_runs.create.assert_not_called()


@pytest.mark.asyncio
async def test_handle_feedback_change_triggers_edit(
    orchestrator: PipelineOrchestrator, mock_repos: _MockRepos
) -> None:
    """Test that new feedback triggers the edit agent."""
    _, _, _, agent_runs = mock_repos

    orchestrator.edit = AsyncMock()
    orchestrator.edit.run = AsyncMock(
        return_value={"usage": None, "message": "test", "response": "ok"}
    )

    await orchestrator.handle_feedback_change(
        {
            "id": "fb-1",
            "edition_id": "ed-1",
            "resolved": False,
        }
    )

    agent_runs.create.assert_called_once()
    orchestrator.edit.run.assert_called_once_with("ed-1")


@pytest.mark.asyncio
async def test_handle_feedback_change_resolved_is_noop(
    orchestrator: PipelineOrchestrator, mock_repos: _MockRepos
) -> None:
    """Test that resolved feedback does not trigger any agent."""
    _, _, _, agent_runs = mock_repos

    await orchestrator.handle_feedback_change(
        {
            "id": "fb-2",
            "edition_id": "ed-1",
            "resolved": True,
        }
    )

    agent_runs.create.assert_not_called()


@pytest.mark.asyncio
async def test_agent_run_logged_on_failure(
    orchestrator: PipelineOrchestrator, mock_repos: _MockRepos
) -> None:
    """Test that a failed agent run is logged with FAILED status."""
    links, _, _, agent_runs = mock_repos
    link = Link(
        id="link-3",
        url="https://example.com",
        edition_id="ed-1",
        status=LinkStatus.SUBMITTED,
    )
    links.get.return_value = link

    orchestrator.fetch = AsyncMock()
    orchestrator.fetch.run = AsyncMock(side_effect=RuntimeError("LLM unavailable"))

    await orchestrator.handle_link_change(
        {
            "id": "link-3",
            "edition_id": "ed-1",
            "status": "submitted",
        }
    )

    # Agent run should be created, then updated with FAILED status
    agent_runs.create.assert_called_once()
    agent_runs.update.assert_called_once()
    updated_run = agent_runs.update.call_args[0][0]
    assert updated_run.status == AgentRunStatus.FAILED
    assert updated_run.completed_at is not None
