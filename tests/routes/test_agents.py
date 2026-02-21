"""Tests for agents route handler."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_stack.routes.agents import agents_page


@pytest.mark.asyncio
async def test_agents_page_renders_template():
    request = MagicMock()
    request.app.state.templates = MagicMock()
    request.app.state.templates.TemplateResponse = MagicMock(return_value="<html>")
    request.app.state.cosmos = MagicMock()
    request.app.state.cosmos.database = MagicMock()
    request.app.state.processor = MagicMock()
    request.app.state.processor._orchestrator = MagicMock()

    fake_metadata = [
        {
            "name": "fetch",
            "description": "Fetches content",
            "tools": [{"name": "fetch_url", "description": "Fetch a URL"}],
            "options": {"temperature": 0.0},
            "middleware": ["TokenTrackingMiddleware"],
            "instructions": {"preview": "You are the Fetch agent…", "full": "You are the Fetch agent..."},
        }
    ]

    with (
        patch("agent_stack.routes.agents.get_agent_metadata", return_value=fake_metadata),
        patch("agent_stack.routes.agents.AgentRunRepository") as mock_repo_cls,
    ):
        mock_repo_cls.return_value.list_recent = AsyncMock(return_value=[])
        await agents_page(request)

    call_args = request.app.state.templates.TemplateResponse.call_args
    assert call_args[0][0] == "agents.html"
    ctx = call_args[0][1]
    assert ctx["request"] is request
    assert len(ctx["agents"]) == 1
    assert ctx["agents"][0]["name"] == "fetch"
    assert ctx["agents"][0]["last_run"] is None
    assert ctx["agents"][0]["is_running"] is False
