"""Integration tests for the pipeline orchestrator routing and agent run logging."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from curate_common.models.link import Link, LinkStatus
from curate_worker.pipeline.orchestrator import PipelineOrchestrator

pytestmark = pytest.mark.integration

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
def orchestrator(
    mock_repos: tuple[AsyncMock, AsyncMock, AsyncMock, AsyncMock],
) -> PipelineOrchestrator:
    """Create a PipelineOrchestrator with mocked dependencies."""
    links, editions, feedback, agent_runs = mock_repos
    client = MagicMock()
    mock_events = MagicMock()
    mock_events.publish = AsyncMock()

    with (
        patch("curate_worker.pipeline.orchestrator.FetchAgent"),
        patch("curate_worker.pipeline.orchestrator.ReviewAgent"),
        patch("curate_worker.pipeline.orchestrator.DraftAgent"),
        patch("curate_worker.pipeline.orchestrator.EditAgent"),
        patch("curate_worker.pipeline.orchestrator.PublishAgent"),
        patch("curate_worker.pipeline.orchestrator.Agent"),
    ):
        orch = PipelineOrchestrator(
            client,
            links,
            editions,
            feedback,
            agent_runs,
            event_publisher=mock_events,
        )
        orch._agent = MagicMock()  # noqa: SLF001
        orch._agent.run = AsyncMock(  # noqa: SLF001
            return_value=MagicMock(text="done")
        )
        orch._runs = MagicMock()  # noqa: SLF001
        orch._runs.create_orchestrator_run = AsyncMock()  # noqa: SLF001
        orch._runs.publish_run_event = AsyncMock()  # noqa: SLF001
        return orch


async def test_handle_link_change_submitted(
    orchestrator: PipelineOrchestrator, mock_repos: _MockRepos
) -> None:
    """Test that a submitted link invokes the orchestrator agent."""
    links, _, _, _ = mock_repos
    link = Link(
        id="link-1",
        url="https://example.com",
        edition_id="ed-1",
        status=LinkStatus.SUBMITTED,
    )
    links.get.return_value = link

    await orchestrator.handle_link_change(
        {
            "id": "link-1",
            "edition_id": "ed-1",
            "status": "submitted",
        }
    )

    links.get.assert_called_with("link-1", "ed-1")
    orchestrator.agent.run.assert_called_once()
    call_args = orchestrator.agent.run.call_args[0][0]
    assert "link-1" in call_args
    assert "ed-1" in call_args
    assert "https://example.com" in call_args


async def test_handle_link_change_drafted_is_noop(
    orchestrator: PipelineOrchestrator, mock_repos: _MockRepos
) -> None:
    """Test that a drafted link does not trigger any agent."""
    links, _, _, _ = mock_repos
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

    orchestrator.agent.run.assert_not_called()


async def test_handle_link_change_not_found(
    orchestrator: PipelineOrchestrator, mock_repos: _MockRepos
) -> None:
    """Test that a missing link is handled gracefully."""
    links, _, _, _ = mock_repos
    links.get.return_value = None

    await orchestrator.handle_link_change(
        {
            "id": "missing",
            "edition_id": "ed-1",
            "status": "submitted",
        }
    )

    orchestrator.agent.run.assert_not_called()


async def test_handle_feedback_change_triggers_agent(
    orchestrator: PipelineOrchestrator,
    mock_repos: _MockRepos,  # noqa: ARG001
) -> None:
    """Test that new feedback invokes the orchestrator agent."""
    await orchestrator.handle_feedback_change(
        {
            "id": "fb-1",
            "edition_id": "ed-1",
            "resolved": False,
        }
    )

    orchestrator.agent.run.assert_called_once()
    call_args = orchestrator.agent.run.call_args[0][0]
    assert "ed-1" in call_args
    assert "fb-1" in call_args


async def test_handle_feedback_change_resolved_is_noop(
    orchestrator: PipelineOrchestrator,
    mock_repos: _MockRepos,  # noqa: ARG001
) -> None:
    """Test that resolved feedback does not trigger any agent."""
    await orchestrator.handle_feedback_change(
        {
            "id": "fb-2",
            "edition_id": "ed-1",
            "resolved": True,
        }
    )

    orchestrator.agent.run.assert_not_called()


async def test_handle_publish_invokes_agent(
    orchestrator: PipelineOrchestrator,
) -> None:
    """Test that handle_publish invokes the orchestrator agent."""
    await orchestrator.handle_publish("ed-1")

    orchestrator.agent.run.assert_called_once()
    call_args = orchestrator.agent.run.call_args[0][0]
    assert "ed-1" in call_args
    assert "publish" in call_args.lower()


async def test_handle_link_change_stale_event_skipped(
    orchestrator: PipelineOrchestrator, mock_repos: _MockRepos
) -> None:
    """Test that stale events are skipped when link has advanced."""
    links, _, _, _ = mock_repos
    link = Link(
        id="link-4",
        url="https://example.com",
        edition_id="ed-1",
        status=LinkStatus.DRAFTED,
    )
    links.get.return_value = link

    await orchestrator.handle_link_change(
        {
            "id": "link-4",
            "edition_id": "ed-1",
            "status": "submitted",
        }
    )

    orchestrator.agent.run.assert_not_called()


async def test_handle_link_change_dispatches_to_orchestrator_agent(
    orchestrator: PipelineOrchestrator, mock_repos: _MockRepos
) -> None:
    """Integration: handle_link_change creates a run and dispatches to the agent."""
    links, _, _, runs = mock_repos
    link = Link(
        id="link-int",
        url="https://example.com/article",
        edition_id="ed-1",
        status=LinkStatus.SUBMITTED,
    )
    links.get.return_value = link

    response = MagicMock()
    response.text = "pipeline complete"
    response.usage_details = None
    orchestrator._agent.run = AsyncMock(return_value=response)  # noqa: SLF001

    await orchestrator.handle_link_change(
        {"id": "link-int", "edition_id": "ed-1", "status": "submitted"}
    )

    orchestrator._agent.run.assert_called_once()  # noqa: SLF001
    orchestrator._runs.create_orchestrator_run.assert_called_once()  # noqa: SLF001
    runs.update.assert_called_once()
    saved_run = runs.update.call_args[0][0]
    assert saved_run.status == "completed"
