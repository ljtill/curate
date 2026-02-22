"""Tests for orchestrator token-usage persistence and pipeline logic."""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_stack.models.link import LinkStatus
from agent_stack.pipeline.orchestrator import PipelineOrchestrator
from agent_stack.pipeline.runs import RunManager

if TYPE_CHECKING:
    from collections.abc import Callable

    from agent_stack.models.agent_run import AgentRun
    from agent_stack.models.link import Link


@pytest.fixture
def mock_repos() -> tuple[AsyncMock, AsyncMock, AsyncMock, AsyncMock]:
    """Return (links, editions, feedback, agent_runs) mock repos."""
    return AsyncMock(), AsyncMock(), AsyncMock(), AsyncMock()


@pytest.fixture
def orchestrator(
    mock_repos: tuple[AsyncMock, AsyncMock, AsyncMock, AsyncMock],
) -> PipelineOrchestrator:
    """Create a PipelineOrchestrator with all external deps mocked."""
    links, editions, feedback, runs = mock_repos
    client = MagicMock()
    with (
        patch("agent_stack.pipeline.orchestrator.Agent"),
        patch("agent_stack.pipeline.orchestrator.FetchAgent"),
        patch("agent_stack.pipeline.orchestrator.ReviewAgent"),
        patch("agent_stack.pipeline.orchestrator.DraftAgent"),
        patch("agent_stack.pipeline.orchestrator.EditAgent"),
        patch("agent_stack.pipeline.orchestrator.PublishAgent"),
        patch("agent_stack.pipeline.orchestrator.load_prompt", return_value=""),
    ):
        orch = PipelineOrchestrator(client, links, editions, feedback, runs)
        orch._runs = MagicMock()  # noqa: SLF001
        orch._runs.create_orchestrator_run = AsyncMock()  # noqa: SLF001
        orch._runs.publish_run_event = AsyncMock()  # noqa: SLF001
        return orch


class TestNormalizeUsage:
    """Tests for RunManager.normalize_usage static helper."""

    def test_none_returns_none(self) -> None:
        """Return None when input is None."""
        assert RunManager.normalize_usage(None) is None

    def test_empty_dict_returns_none(self) -> None:
        """Return None for an empty dict (all zeros)."""
        assert RunManager.normalize_usage({}) is None

    def test_normalizes_framework_keys(self) -> None:
        """Translate framework key names to the app schema."""
        raw = {
            "input_token_count": 100,
            "output_token_count": 50,
            "total_token_count": 150,
        }
        expected = {"input_tokens": 100, "output_tokens": 50, "total_tokens": 150}
        result = RunManager.normalize_usage(raw)
        assert result == expected

    def test_computes_total_when_missing(self) -> None:
        """Derive total_tokens from input + output when not provided."""
        raw = {"input_token_count": 80, "output_token_count": 20}
        result = RunManager.normalize_usage(raw)
        assert result is not None
        expected_total = 100
        assert result["total_tokens"] == expected_total


class TestHandleLinkChangeUsage:
    """Verify handle_link_change persists token usage on the orchestrator run."""

    async def test_usage_persisted_on_success(
        self,
        orchestrator: PipelineOrchestrator,
        mock_repos: tuple[AsyncMock, AsyncMock, AsyncMock, AsyncMock],
        make_link: Callable[..., Link],
    ) -> None:
        """Orchestrator run stores normalized usage from the LLM response."""
        links, _editions, _feedback, runs = mock_repos
        link = make_link(id="l-1", status="submitted")
        links.get.return_value = link

        response = MagicMock()
        response.text = "done"
        response.usage_details = {
            "input_token_count": 200,
            "output_token_count": 80,
            "total_token_count": 280,
        }
        orchestrator._agent.run = AsyncMock(return_value=response)  # noqa: SLF001

        await orchestrator.handle_link_change(
            {"id": "l-1", "edition_id": "ed-1", "status": "submitted"}
        )

        saved_run = runs.update.call_args[0][0]
        assert saved_run.usage is not None
        expected = {"input_tokens": 200, "output_tokens": 80, "total_tokens": 280}
        assert saved_run.usage == expected

    async def test_usage_none_when_response_has_no_details(
        self,
        orchestrator: PipelineOrchestrator,
        mock_repos: tuple[AsyncMock, AsyncMock, AsyncMock, AsyncMock],
        make_link: Callable[..., Link],
    ) -> None:
        """Usage stays None when the LLM response has no usage_details."""
        links, _editions, _feedback, runs = mock_repos
        link = make_link(id="l-2", status="submitted")
        links.get.return_value = link

        response = MagicMock()
        response.text = "done"
        response.usage_details = None
        orchestrator._agent.run = AsyncMock(return_value=response)  # noqa: SLF001

        await orchestrator.handle_link_change(
            {"id": "l-2", "edition_id": "ed-1", "status": "submitted"}
        )

        saved_run = runs.update.call_args[0][0]
        assert saved_run.usage is None


class TestRecordStageCompleteUsage:
    """Verify record_stage_complete persists token usage when provided."""

    async def test_usage_set_when_tokens_provided(
        self,
        orchestrator: PipelineOrchestrator,
        mock_repos: tuple[AsyncMock, AsyncMock, AsyncMock, AsyncMock],
        make_agent_run: Callable[..., AgentRun],
    ) -> None:
        """Stage run stores usage dict when token counts are non-zero."""
        links, _editions, _feedback, runs = mock_repos
        run = make_agent_run(id="run-1", trigger_id="l-1")
        runs.get.return_value = run
        links.get.return_value = None

        result = json.loads(
            await orchestrator.record_stage_complete(
                run_id="run-1",
                trigger_id="l-1",
                status="completed",
                input_tokens=500,
                output_tokens=120,
                total_tokens=620,
            )
        )

        assert result["status"] == "completed"
        expected = {"input_tokens": 500, "output_tokens": 120, "total_tokens": 620}
        assert run.usage == expected

    async def test_usage_none_when_no_tokens_provided(
        self,
        orchestrator: PipelineOrchestrator,
        mock_repos: tuple[AsyncMock, AsyncMock, AsyncMock, AsyncMock],
        make_agent_run: Callable[..., AgentRun],
    ) -> None:
        """Stage run leaves usage as None when no tokens are passed."""
        links, _editions, _feedback, runs = mock_repos
        run = make_agent_run(id="run-2", trigger_id="l-1")
        runs.get.return_value = run
        links.get.return_value = None

        await orchestrator.record_stage_complete(
            run_id="run-2",
            trigger_id="l-1",
            status="completed",
        )

        assert run.usage is None

    async def test_total_tokens_computed_when_omitted(
        self,
        orchestrator: PipelineOrchestrator,
        mock_repos: tuple[AsyncMock, AsyncMock, AsyncMock, AsyncMock],
        make_agent_run: Callable[..., AgentRun],
    ) -> None:
        """Total tokens is computed from input + output when not provided."""
        links, _editions, _feedback, runs = mock_repos
        run = make_agent_run(id="run-3", trigger_id="l-1")
        runs.get.return_value = run
        links.get.return_value = None

        await orchestrator.record_stage_complete(
            run_id="run-3",
            trigger_id="l-1",
            status="completed",
            input_tokens=300,
            output_tokens=100,
        )

        assert run.usage is not None
        expected_total = 400
        assert run.usage["total_tokens"] == expected_total


class TestClaimLink:
    """Tests for _claim_link guard logic."""

    async def test_returns_none_when_already_processing(
        self,
        orchestrator: PipelineOrchestrator,
    ) -> None:
        """Return None when the link is already being processed."""
        orchestrator._processing_links.add("l-1")  # noqa: SLF001

        result = await orchestrator._claim_link("l-1", "ed-1", "submitted")  # noqa: SLF001
        assert result is None

    async def test_returns_none_when_link_is_failed(
        self,
        orchestrator: PipelineOrchestrator,
        mock_repos: tuple[AsyncMock, AsyncMock, AsyncMock, AsyncMock],
        make_link: Callable[..., Link],
    ) -> None:
        """Return None when the link status is FAILED."""
        links, *_ = mock_repos
        links.get.return_value = make_link(id="l-1", status=LinkStatus.FAILED)

        result = await orchestrator._claim_link("l-1", "ed-1", "submitted")  # noqa: SLF001
        assert result is None

    async def test_returns_none_when_status_not_submitted(
        self,
        orchestrator: PipelineOrchestrator,
        mock_repos: tuple[AsyncMock, AsyncMock, AsyncMock, AsyncMock],
        make_link: Callable[..., Link],
    ) -> None:
        """Return None when the event status is not SUBMITTED."""
        links, *_ = mock_repos
        links.get.return_value = make_link(id="l-1", status=LinkStatus.REVIEWED)

        result = await orchestrator._claim_link("l-1", "ed-1", "reviewed")  # noqa: SLF001
        assert result is None

    async def test_returns_none_when_link_status_mismatches_event(
        self,
        orchestrator: PipelineOrchestrator,
        mock_repos: tuple[AsyncMock, AsyncMock, AsyncMock, AsyncMock],
        make_link: Callable[..., Link],
    ) -> None:
        """Return None when the link has advanced past the event status."""
        links, *_ = mock_repos
        links.get.return_value = make_link(id="l-1", status=LinkStatus.DRAFTED)

        result = await orchestrator._claim_link("l-1", "ed-1", "submitted")  # noqa: SLF001
        assert result is None


class TestHandleLinkChangeRetry:
    """Tests for handle_link_change retry logic."""

    async def test_retries_on_failure_succeeds_on_second_attempt(
        self,
        orchestrator: PipelineOrchestrator,
        mock_repos: tuple[AsyncMock, AsyncMock, AsyncMock, AsyncMock],
        make_link: Callable[..., Link],
    ) -> None:
        """Verify retry succeeds on second attempt after first failure."""
        links, _editions, _feedback, runs = mock_repos
        link = make_link(id="l-retry", status="submitted")
        links.get.return_value = link

        response = MagicMock()
        response.text = "ok"
        response.usage_details = None
        orchestrator._agent.run = AsyncMock(  # noqa: SLF001
            side_effect=[RuntimeError("transient"), response],
        )

        sleep_patch = "agent_stack.pipeline.orchestrator.asyncio.sleep"
        with patch(sleep_patch, new_callable=AsyncMock):
            await orchestrator.handle_link_change(
                {"id": "l-retry", "edition_id": "ed-1", "status": "submitted"}
            )

        saved_run = runs.update.call_args[0][0]
        assert saved_run.status == "completed"

    async def test_marks_failed_after_max_retries(
        self,
        orchestrator: PipelineOrchestrator,
        mock_repos: tuple[AsyncMock, AsyncMock, AsyncMock, AsyncMock],
        make_link: Callable[..., Link],
    ) -> None:
        """Verify the run is marked FAILED after all retries are exhausted."""
        links, _editions, _feedback, runs = mock_repos
        link = make_link(id="l-fail", status="submitted")
        links.get.return_value = link

        orchestrator._agent.run = AsyncMock(  # noqa: SLF001
            side_effect=RuntimeError("persistent error"),
        )

        sleep_patch = "agent_stack.pipeline.orchestrator.asyncio.sleep"
        with patch(sleep_patch, new_callable=AsyncMock):
            await orchestrator.handle_link_change(
                {"id": "l-fail", "edition_id": "ed-1", "status": "submitted"}
            )

        saved_run = runs.update.call_args[0][0]
        assert saved_run.status == "failed"


class TestGetEditionLock:
    """Tests for _get_edition_lock."""

    async def test_returns_same_lock_for_same_edition(
        self,
        orchestrator: PipelineOrchestrator,
    ) -> None:
        """The same lock object is returned for the same edition_id."""
        lock1 = await orchestrator._get_edition_lock("ed-1")  # noqa: SLF001
        lock2 = await orchestrator._get_edition_lock("ed-1")  # noqa: SLF001
        assert lock1 is lock2


class TestHandleFeedbackChangeLock:
    """Tests for handle_feedback_change edition lock serialization."""

    async def test_serializes_concurrent_feedback(
        self,
        orchestrator: PipelineOrchestrator,
        mock_repos: tuple[AsyncMock, AsyncMock, AsyncMock, AsyncMock],
    ) -> None:
        """Concurrent calls for the same edition are serialized by the lock."""
        *_, _runs = mock_repos
        order: list[str] = []

        async def _slow_run(_msg: str, **_kwargs: object) -> MagicMock:
            order.append("start")
            await asyncio.sleep(0.05)
            order.append("end")
            resp = MagicMock()
            resp.text = "done"
            resp.usage_details = None
            return resp

        orchestrator._agent.run = AsyncMock(side_effect=_slow_run)  # noqa: SLF001

        await asyncio.gather(
            orchestrator.handle_feedback_change(
                {"id": "fb-1", "edition_id": "ed-1", "resolved": False}
            ),
            orchestrator.handle_feedback_change(
                {"id": "fb-2", "edition_id": "ed-1", "resolved": False}
            ),
        )

        assert order == ["start", "end", "start", "end"]


class TestHandlePublishFailure:
    """Tests for handle_publish error handling."""

    async def test_records_run_and_handles_failure(
        self,
        orchestrator: PipelineOrchestrator,
        mock_repos: tuple[AsyncMock, AsyncMock, AsyncMock, AsyncMock],
    ) -> None:
        """Verify handle_publish records the run and sets FAILED on error."""
        _links, _editions, _feedback, runs = mock_repos
        orchestrator._agent.run = AsyncMock(  # noqa: SLF001
            side_effect=RuntimeError("publish boom"),
        )

        await orchestrator.handle_publish("ed-1")

        saved_run = runs.update.call_args[0][0]
        assert saved_run.status == "failed"
        assert saved_run.output == {"error": "Orchestrator failed"}
