"""Tests for orchestrator tool definitions and feedback context propagation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from curate_worker.pipeline.orchestrator import PipelineOrchestrator
from curate_worker.pipeline.tools import feedback_ctx

if TYPE_CHECKING:
    from collections.abc import Generator

pytestmark = pytest.mark.unit


@pytest.fixture
def _mock_agents() -> Generator[None]:
    """Patch all agent classes so importing the orchestrator doesn't fail."""
    with (
        patch("curate_worker.pipeline.orchestrator.FetchAgent"),
        patch("curate_worker.pipeline.orchestrator.ReviewAgent"),
        patch("curate_worker.pipeline.orchestrator.DraftAgent"),
        patch("curate_worker.pipeline.orchestrator.EditAgent"),
        patch("curate_worker.pipeline.orchestrator.PublishAgent"),
        patch("curate_worker.pipeline.orchestrator.Agent"),
    ):
        yield


@pytest.fixture
def orchestrator(
    _mock_agents: None,
) -> PipelineOrchestrator:
    """Build a PipelineOrchestrator with mocked sub-agents."""
    client = MagicMock()
    events = MagicMock()
    events.publish = AsyncMock()
    orch = PipelineOrchestrator(
        client,
        AsyncMock(),
        AsyncMock(),
        AsyncMock(),
        AsyncMock(),
        event_publisher=events,
    )
    orch._agent = MagicMock()  # noqa: SLF001
    orch._agent.run = AsyncMock(return_value=MagicMock(text="done"))  # noqa: SLF001
    orch._agent.create_session = MagicMock(  # noqa: SLF001
        return_value=MagicMock(state={})
    )
    orch._runs = MagicMock()  # noqa: SLF001
    orch._runs.create_orchestrator_run = AsyncMock()  # noqa: SLF001
    orch._runs.publish_run_event = AsyncMock()  # noqa: SLF001

    # Set up edit sub-agent mock
    edit_session = MagicMock(state={})
    orch.edit = MagicMock()
    orch.edit.agent = MagicMock()
    orch.edit.agent.create_session = MagicMock(return_value=edit_session)
    orch.edit.agent.run = AsyncMock(
        return_value=MagicMock(text="edited", usage_details=None)
    )
    return orch


class TestEditToolFeedbackContext:
    """Verify _edit_tool reads the feedback_ctx contextvar correctly."""

    async def test_skip_memory_capture_propagated(
        self, orchestrator: PipelineOrchestrator
    ) -> None:
        """When learn_from_feedback=False, skip flag reaches edit session."""
        ctx_token = feedback_ctx.set(
            {
                "skip_memory_capture": True,
                "section": "signals",
                "comment": "Too verbose",
            }
        )
        try:
            await orchestrator._edit_tool("Edit edition ed-1")  # noqa: SLF001
        finally:
            feedback_ctx.reset(ctx_token)

        session = orchestrator.edit.agent.create_session.return_value
        assert session.state.get("skip_memory_capture") is True
        # Task should NOT be enriched when memory capture is skipped
        call_task = orchestrator.edit.agent.run.call_args[0][0]
        assert "Too verbose" not in call_task

    async def test_feedback_enriches_task_when_learning(
        self, orchestrator: PipelineOrchestrator
    ) -> None:
        """When learn_from_feedback=True, feedback content is appended to task."""
        ctx_token = feedback_ctx.set(
            {
                "skip_memory_capture": False,
                "section": "deep_dive",
                "comment": "Add code examples",
            }
        )
        try:
            await orchestrator._edit_tool("Edit edition ed-1")  # noqa: SLF001
        finally:
            feedback_ctx.reset(ctx_token)

        session = orchestrator.edit.agent.create_session.return_value
        assert "skip_memory_capture" not in session.state
        call_task = orchestrator.edit.agent.run.call_args[0][0]
        assert "deep_dive" in call_task
        assert "Add code examples" in call_task

    async def test_no_ctx_passes_task_unchanged(
        self, orchestrator: PipelineOrchestrator
    ) -> None:
        """When no feedback_ctx is set (e.g. non-feedback edit), task is unchanged."""
        assert feedback_ctx.get() is None
        await orchestrator._edit_tool("Edit edition ed-1")  # noqa: SLF001

        call_task = orchestrator.edit.agent.run.call_args[0][0]
        assert call_task == "Edit edition ed-1"

    async def test_session_always_created(
        self, orchestrator: PipelineOrchestrator
    ) -> None:
        """_edit_tool always creates an explicit session."""
        await orchestrator._edit_tool("Edit edition ed-1")  # noqa: SLF001
        orchestrator.edit.agent.create_session.assert_called_once()
        orchestrator.edit.agent.run.assert_called_once()
        # Verify session was passed
        call_kwargs = orchestrator.edit.agent.run.call_args
        assert call_kwargs[1].get("session") is not None


class TestFeedbackCtxLifecycle:
    """Verify feedback_ctx is set and reset around orchestrator runs."""

    async def test_ctx_set_during_feedback_processing(
        self, orchestrator: PipelineOrchestrator
    ) -> None:
        """feedback_ctx is set before agent.run and reset after."""
        captured_ctx: list[dict[str, Any] | None] = []

        async def capture_run(_msg: str, /, **_kwargs: Any) -> MagicMock:
            captured_ctx.append(feedback_ctx.get())
            return MagicMock(text="done", usage_details=None)

        orchestrator._agent.run = capture_run  # noqa: SLF001

        await orchestrator.handle_feedback_change(
            {
                "id": "fb-1",
                "edition_id": "ed-1",
                "section": "signals",
                "comment": "Be concise",
                "resolved": False,
                "learn_from_feedback": True,
            }
        )

        assert len(captured_ctx) == 1
        ctx = captured_ctx[0]
        assert ctx is not None
        assert ctx["skip_memory_capture"] is False
        assert ctx["section"] == "signals"
        assert ctx["comment"] == "Be concise"
        # After completion, ctx should be reset
        assert feedback_ctx.get() is None

    async def test_ctx_skip_when_learn_disabled(
        self, orchestrator: PipelineOrchestrator
    ) -> None:
        """feedback_ctx has skip_memory_capture=True when learn_from_feedback=False."""
        captured_ctx: list[dict[str, Any] | None] = []

        async def capture_run(_msg: str, /, **_kwargs: Any) -> MagicMock:
            captured_ctx.append(feedback_ctx.get())
            return MagicMock(text="done", usage_details=None)

        orchestrator._agent.run = capture_run  # noqa: SLF001

        await orchestrator.handle_feedback_change(
            {
                "id": "fb-2",
                "edition_id": "ed-1",
                "section": "toolkit",
                "comment": "Remove entry",
                "resolved": False,
                "learn_from_feedback": False,
            }
        )

        ctx = captured_ctx[0]
        assert ctx is not None
        assert ctx["skip_memory_capture"] is True

    async def test_ctx_reset_on_error(self, orchestrator: PipelineOrchestrator) -> None:
        """feedback_ctx is reset even if the orchestrator run fails."""
        orchestrator._agent.run = AsyncMock(  # noqa: SLF001
            side_effect=RuntimeError("boom")
        )

        await orchestrator.handle_feedback_change(
            {
                "id": "fb-3",
                "edition_id": "ed-1",
                "section": "signals",
                "comment": "Fix typo",
                "resolved": False,
            }
        )

        assert feedback_ctx.get() is None
