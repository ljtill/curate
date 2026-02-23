"""Tests for the data-driven agent registry."""

from __future__ import annotations

from curate_common.agents.registry import get_agent_metadata

EXPECTED_AGENT_COUNT = 6


class TestGetAgentMetadata:
    """Test suite for the get_agent_metadata function."""

    def test_returns_metadata_for_all_agents(self) -> None:
        """Verify metadata is returned for all pipeline agents."""
        result = get_agent_metadata()

        assert len(result) == EXPECTED_AGENT_COUNT
        names = [r["name"] for r in result]
        assert "orchestrator" in names
        assert "fetch" in names
        assert "review" in names
        assert "draft" in names
        assert "edit" in names
        assert "publish" in names

    def test_each_agent_has_required_fields(self) -> None:
        """Verify each agent entry has the expected keys."""
        result = get_agent_metadata()

        for agent in result:
            assert "name" in agent
            assert "description" in agent
            assert "tools" in agent
            assert "middleware" in agent
            assert isinstance(agent["tools"], list)
            assert isinstance(agent["middleware"], list)

    def test_returns_deep_copy(self) -> None:
        """Verify mutation of result doesn't affect the source data."""
        result1 = get_agent_metadata()
        result1[0]["name"] = "mutated"

        result2 = get_agent_metadata()
        assert result2[0]["name"] == "orchestrator"

    def test_orchestrator_has_expected_tools(self) -> None:
        """Verify the orchestrator has sub-agent tools registered."""
        result = get_agent_metadata()
        orchestrator = next(a for a in result if a["name"] == "orchestrator")

        tool_names = [t["name"] for t in orchestrator["tools"]]
        assert "fetch" in tool_names
        assert "review" in tool_names
        assert "draft" in tool_names
        assert "edit" in tool_names
        assert "publish" in tool_names
