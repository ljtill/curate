"""Tests for the agent registry — introspection utilities."""

from unittest.mock import MagicMock

import pytest

from agent_stack.agents.registry import (
    _extract_instructions,
    _extract_middleware,
    _extract_options,
    _extract_tools,
    get_agent_metadata,
)


@pytest.mark.unit
class TestExtractTools:
    def test_extracts_callable_tools(self):
        agent_obj = MagicMock()

        def my_tool():
            """Fetches data from API."""
            pass

        agent_obj._agent._tools = [my_tool]

        tools = _extract_tools(agent_obj)

        assert len(tools) == 1
        assert tools[0]["name"] == "my_tool"
        assert "Fetches data" in tools[0]["description"]

    def test_extracts_named_tools(self):
        agent_obj = MagicMock()

        class NamedTool:
            name = "save_data"
            description = "Saves data"

        agent_obj._agent._tools = [NamedTool()]

        tools = _extract_tools(agent_obj)

        assert tools[0]["name"] == "save_data"
        assert tools[0]["description"] == "Saves data"

    def test_returns_empty_when_no_agent(self):
        agent_obj = MagicMock(spec=[])
        assert _extract_tools(agent_obj) == []

    def test_returns_empty_when_no_tools(self):
        agent_obj = MagicMock()
        agent_obj._agent._tools = None
        agent_obj._agent.tools = None
        assert _extract_tools(agent_obj) == []


@pytest.mark.unit
class TestExtractOptions:
    def test_extracts_known_options(self):
        agent_obj = MagicMock()
        opts = MagicMock()
        opts.temperature = 0.7
        opts.max_tokens = 4096
        opts.top_p = None
        opts.response_format = None
        agent_obj._agent._default_options = opts

        result = _extract_options(agent_obj)

        assert result["temperature"] == 0.7
        assert result["max_tokens"] == 4096
        assert "top_p" not in result

    def test_returns_empty_when_no_agent(self):
        agent_obj = MagicMock(spec=[])
        assert _extract_options(agent_obj) == {}

    def test_returns_empty_when_no_options(self):
        agent_obj = MagicMock()
        agent_obj._agent._default_options = None
        agent_obj._agent.default_options = None
        assert _extract_options(agent_obj) == {}


@pytest.mark.unit
class TestExtractMiddleware:
    def test_extracts_middleware_class_names(self):
        agent_obj = MagicMock()

        class FakeMiddleware:
            pass

        agent_obj._agent._middleware = [FakeMiddleware()]

        result = _extract_middleware(agent_obj)

        assert result == ["FakeMiddleware"]

    def test_returns_empty_when_no_agent(self):
        agent_obj = MagicMock(spec=[])
        assert _extract_middleware(agent_obj) == []


@pytest.mark.unit
class TestExtractInstructions:
    def test_truncates_long_instructions(self):
        agent_obj = MagicMock()
        agent_obj._agent._instructions = "A" * 300

        result = _extract_instructions(agent_obj, max_length=200)

        assert len(result["preview"]) == 201  # 200 chars + ellipsis
        assert result["preview"].endswith("…")
        assert len(result["full"]) == 300

    def test_short_instructions_no_truncation(self):
        agent_obj = MagicMock()
        agent_obj._agent._instructions = "Short prompt"

        result = _extract_instructions(agent_obj)

        assert result["preview"] == "Short prompt"
        assert result["full"] == "Short prompt"

    def test_returns_empty_when_no_agent(self):
        agent_obj = MagicMock(spec=[])
        result = _extract_instructions(agent_obj)
        assert result == {"preview": "", "full": ""}


@pytest.mark.unit
class TestGetAgentMetadata:
    def test_returns_metadata_for_registered_agents(self):
        orchestrator = MagicMock()
        # Set up minimal agents
        for attr in ("_fetch", "_review", "_draft", "_edit", "_publish"):
            agent = MagicMock()
            agent._agent._tools = []
            agent._agent._default_options = None
            agent._agent.default_options = None
            agent._agent._middleware = []
            agent._agent._instructions = "Do stuff"
            setattr(orchestrator, attr, agent)

        result = get_agent_metadata(orchestrator)

        assert len(result) == 5
        names = [r["name"] for r in result]
        assert "fetch" in names
        assert "publish" in names

    def test_skips_none_agents(self):
        orchestrator = MagicMock()
        orchestrator._fetch = None
        orchestrator._review = None
        orchestrator._draft = None
        orchestrator._edit = None
        agent = MagicMock()
        agent._agent._tools = []
        agent._agent._default_options = None
        agent._agent.default_options = None
        agent._agent._middleware = []
        agent._agent._instructions = ""
        orchestrator._publish = agent

        result = get_agent_metadata(orchestrator)

        assert len(result) == 1
        assert result[0]["name"] == "publish"
