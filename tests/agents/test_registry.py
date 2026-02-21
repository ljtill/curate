"""Tests for the agent registry — introspection utilities."""

from __future__ import annotations

from unittest.mock import MagicMock

from agent_stack.agents.registry import (
    _extract_instructions,
    _extract_middleware,
    _extract_options,
    _extract_tools,
    get_agent_metadata,
)

LONG_INSTRUCTIONS_LENGTH = 300
PREVIEW_MAX_LENGTH = 200
EXPECTED_PREVIEW_LENGTH = 201  # 200 chars + ellipsis character
EXPECTED_AGENT_COUNT = 6
EXPECTED_PARTIAL_AGENT_COUNT = 2
EXPECTED_TEMPERATURE = 0.7
EXPECTED_MAX_TOKENS = 4096


def _make_agent_obj(**inner_attrs: object) -> MagicMock:
    """Create a mock agent object with inner agent attributes set via setattr."""
    inner = MagicMock()
    for key, value in inner_attrs.items():
        setattr(inner, key, value)
    obj = MagicMock()
    obj.agent = inner
    return obj


class TestExtractTools:
    """Test suite for the _extract_tools function."""

    def test_extracts_callable_tools(self) -> None:
        """Verify callable tools are extracted with name and description."""

        def my_tool() -> None:
            """Fetch data from API."""

        agent_obj = _make_agent_obj(_tools=[my_tool])

        tools = _extract_tools(agent_obj)

        assert len(tools) == 1
        assert tools[0]["name"] == "my_tool"
        assert "Fetch data" in tools[0]["description"]

    def test_extracts_named_tools(self) -> None:
        """Verify named tool objects are extracted correctly."""

        class NamedTool:
            name = "save_data"
            description = "Saves data"

        agent_obj = _make_agent_obj(_tools=[NamedTool()])

        tools = _extract_tools(agent_obj)

        assert tools[0]["name"] == "save_data"
        assert tools[0]["description"] == "Saves data"

    def test_returns_empty_when_no_agent(self) -> None:
        """Verify empty list returned when no inner agent exists."""
        agent_obj = MagicMock(spec=[])
        assert _extract_tools(agent_obj) == []

    def test_returns_empty_when_no_tools(self) -> None:
        """Verify empty list returned when tools are None."""
        agent_obj = _make_agent_obj(_tools=None, tools=None)
        assert _extract_tools(agent_obj) == []

    def test_extracts_tools_from_default_options(self) -> None:
        """Agent Framework stores tools in default_options['tools']."""
        agent_obj = _make_agent_obj(_tools=None, tools=None)

        class FunctionTool:
            name = "fetch_url"
            description = "Fetch the raw HTML content of a URL."

        agent_obj.agent.default_options = {"tools": [FunctionTool()]}

        tools = _extract_tools(agent_obj)

        assert len(tools) == 1
        assert tools[0]["name"] == "fetch_url"
        assert "Fetch the raw HTML" in tools[0]["description"]


class TestExtractOptions:
    """Test suite for the _extract_options function."""

    def test_extracts_known_options(self) -> None:
        """Verify known options are extracted from agent defaults."""
        opts = MagicMock()
        opts.temperature = EXPECTED_TEMPERATURE
        opts.max_tokens = EXPECTED_MAX_TOKENS
        opts.top_p = None
        opts.response_format = None
        agent_obj = _make_agent_obj(_default_options=opts)

        result = _extract_options(agent_obj)

        assert result["temperature"] == EXPECTED_TEMPERATURE
        assert result["max_tokens"] == EXPECTED_MAX_TOKENS
        assert "top_p" not in result

    def test_returns_empty_when_no_agent(self) -> None:
        """Verify empty dict returned when no inner agent exists."""
        agent_obj = MagicMock(spec=[])
        assert _extract_options(agent_obj) == {}

    def test_returns_empty_when_no_options(self) -> None:
        """Verify empty dict returned when options are None."""
        agent_obj = _make_agent_obj(_default_options=None, default_options=None)
        assert _extract_options(agent_obj) == {}


class TestExtractMiddleware:
    """Test suite for the _extract_middleware function."""

    def test_extracts_middleware_class_names(self) -> None:
        """Verify middleware class names are extracted correctly."""

        class FakeMiddleware:
            pass

        agent_obj = _make_agent_obj(_middleware=[FakeMiddleware()])

        result = _extract_middleware(agent_obj)

        assert result == ["FakeMiddleware"]

    def test_returns_empty_when_no_agent(self) -> None:
        """Verify empty list returned when no inner agent exists."""
        agent_obj = MagicMock(spec=[])
        assert _extract_middleware(agent_obj) == []


class TestExtractInstructions:
    """Test suite for the _extract_instructions function."""

    def test_truncates_long_instructions(self) -> None:
        """Verify long instructions are truncated with ellipsis."""
        agent_obj = _make_agent_obj(_instructions="A" * LONG_INSTRUCTIONS_LENGTH)

        result = _extract_instructions(agent_obj, max_length=PREVIEW_MAX_LENGTH)

        assert len(result["preview"]) == EXPECTED_PREVIEW_LENGTH
        assert result["preview"].endswith("…")
        assert len(result["full"]) == LONG_INSTRUCTIONS_LENGTH

    def test_short_instructions_no_truncation(self) -> None:
        """Verify short instructions are not truncated."""
        agent_obj = _make_agent_obj(_instructions="Short prompt")

        result = _extract_instructions(agent_obj)

        assert result["preview"] == "Short prompt"
        assert result["full"] == "Short prompt"

    def test_returns_empty_when_no_agent(self) -> None:
        """Verify empty strings returned when no inner agent exists."""
        agent_obj = MagicMock(spec=[])
        result = _extract_instructions(agent_obj)
        assert result == {"preview": "", "full": ""}


class TestGetAgentMetadata:
    """Test suite for the get_agent_metadata function."""

    def test_returns_metadata_for_registered_agents(self) -> None:
        """Verify metadata is returned for all registered agents."""
        orchestrator = MagicMock()
        # Set up minimal agents
        for attr in ("fetch", "review", "draft", "edit", "publish"):
            agent = _make_agent_obj(
                _tools=[],
                _default_options=None,
                default_options=None,
                _middleware=[],
                _instructions="Do stuff",
            )
            setattr(orchestrator, attr, agent)

        result = get_agent_metadata(orchestrator)

        assert len(result) == EXPECTED_AGENT_COUNT
        names = [r["name"] for r in result]
        assert "fetch" in names
        assert "publish" in names

    def test_skips_none_agents(self) -> None:
        """Verify None agents are excluded from metadata."""
        orchestrator = MagicMock()
        orchestrator.fetch = None
        orchestrator.review = None
        orchestrator.draft = None
        orchestrator.edit = None
        agent = _make_agent_obj(
            _tools=[],
            _default_options=None,
            default_options=None,
            _middleware=[],
            _instructions="",
        )
        orchestrator.publish = agent

        result = get_agent_metadata(orchestrator)

        assert len(result) == EXPECTED_PARTIAL_AGENT_COUNT
        assert result[0]["name"] == "orchestrator"
        assert result[1]["name"] == "publish"
