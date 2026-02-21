"""Tests for orchestrator routing logic."""

from agent_stack.models.agent_run import AgentStage
from agent_stack.models.link import LinkStatus
from agent_stack.pipeline.orchestrator import PipelineOrchestrator


class TestDetermineStage:
    """Test the status-to-stage routing logic without needing real DB or LLM."""

    def test_submitted_routes_to_fetch(self):
        stage = PipelineOrchestrator._determine_stage_for_link(None, LinkStatus.SUBMITTED)
        assert stage == AgentStage.FETCH

    def test_fetching_routes_to_review(self):
        stage = PipelineOrchestrator._determine_stage_for_link(None, LinkStatus.FETCHING)
        assert stage == AgentStage.REVIEW

    def test_reviewed_routes_to_draft(self):
        stage = PipelineOrchestrator._determine_stage_for_link(None, LinkStatus.REVIEWED)
        assert stage == AgentStage.DRAFT

    def test_drafted_routes_to_none(self):
        stage = PipelineOrchestrator._determine_stage_for_link(None, LinkStatus.DRAFTED)
        assert stage is None

    def test_unknown_status_routes_to_none(self):
        stage = PipelineOrchestrator._determine_stage_for_link(None, "unknown")
        assert stage is None

    def test_failed_routes_to_none(self):
        stage = PipelineOrchestrator._determine_stage_for_link(None, LinkStatus.FAILED)
        assert stage is None
