"""Tests for agents route handler."""

from unittest.mock import AsyncMock, MagicMock, patch

from agent_stack.routes.agents import agents_page


async def test_agents_page_renders_template() -> None:
    """Verify agents page renders template."""
    request = MagicMock()
    request.app.state.templates = MagicMock()
    request.app.state.templates.TemplateResponse = MagicMock(return_value="<html>")
    request.app.state.cosmos = MagicMock()
    request.app.state.cosmos.database = MagicMock()
    request.app.state.processor = MagicMock()
    request.app.state.processor.orchestrator = MagicMock()

    fake_metadata = [
        {
            "name": "fetch",
            "description": "Fetches content",
            "tools": [{"name": "fetch_url", "description": "Fetch a URL"}],
            "options": {},
            "middleware": ["TokenTrackingMiddleware"],
            "instructions": {
                "preview": "You are the Fetch agent…",
                "full": "You are the Fetch agent...",
            },
        }
    ]

    with (
        patch(
            "agent_stack.routes.agents.get_agent_metadata", return_value=fake_metadata
        ),
        patch("agent_stack.routes.agents.AgentRunRepository") as mock_repo_cls,
    ):
        mock_repo_cls.return_value.list_recent_by_stage = AsyncMock(return_value=[])
        await agents_page(request)

    call_args = request.app.state.templates.TemplateResponse.call_args
    assert call_args[0][0] == "agents.html"
    ctx = call_args[0][1]
    assert ctx["request"] is request
    assert len(ctx["agents"]) == 1
    assert ctx["agents"][0]["name"] == "fetch"
    assert ctx["agents"][0]["last_run"] is None
    assert ctx["agents"][0]["is_running"] is False
    assert ctx["agents"][0]["recent_runs"] == []


async def test_agents_page_with_runs() -> None:
    """Verify agents page with runs."""
    request = MagicMock()
    request.app.state.templates = MagicMock()
    request.app.state.templates.TemplateResponse = MagicMock(return_value="<html>")
    request.app.state.cosmos = MagicMock()
    request.app.state.cosmos.database = MagicMock()
    request.app.state.processor = MagicMock()
    request.app.state.processor.orchestrator = MagicMock()

    fake_metadata = [
        {
            "name": "fetch",
            "description": "Fetches content",
            "tools": [],
            "options": {},
            "middleware": [],
            "instructions": {"preview": "", "full": ""},
        }
    ]

    mock_run = MagicMock()
    mock_run.id = "run-1"
    mock_run.status = "completed"
    mock_run.started_at = MagicMock()
    mock_run.completed_at = MagicMock()
    mock_run.usage = {"input_tokens": 100, "output_tokens": 50, "total_tokens": 150}
    mock_run.trigger_id = "link-abc"
    mock_run.input = {"status": "submitted", "message": "Fetch this URL"}
    mock_run.output = {"content": "I fetched the content."}

    with (
        patch(
            "agent_stack.routes.agents.get_agent_metadata", return_value=fake_metadata
        ),
        patch("agent_stack.routes.agents.AgentRunRepository") as mock_repo_cls,
    ):
        mock_repo_cls.return_value.list_recent_by_stage = AsyncMock(
            return_value=[mock_run]
        )
        await agents_page(request)

    call_args = request.app.state.templates.TemplateResponse.call_args
    ctx = call_args[0][1]
    agent = ctx["agents"][0]
    assert agent["last_run"] is not None
    assert agent["last_run"]["status"] == "completed"
    assert agent["last_run"]["input"]["message"] == "Fetch this URL"
    assert agent["last_run"]["output"]["content"] == "I fetched the content."
    assert len(agent["recent_runs"]) == 1
