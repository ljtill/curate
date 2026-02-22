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
            "recent_runs": [],
            "last_run": None,
            "is_running": False,
        }
    ]

    with (
        patch(
            "agent_stack.routes.agents.get_agents_page_data",
            new_callable=AsyncMock,
            return_value={"agents": fake_metadata, "running_stages": set()},
        ),
        patch("agent_stack.routes.agents.AgentRunRepository") as _mock_repo_cls,
    ):
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
    assert ctx["pipeline_available"] is True


async def test_agents_page_with_runs() -> None:
    """Verify agents page with runs."""
    request = MagicMock()
    request.app.state.templates = MagicMock()
    request.app.state.templates.TemplateResponse = MagicMock(return_value="<html>")
    request.app.state.cosmos = MagicMock()
    request.app.state.cosmos.database = MagicMock()
    request.app.state.processor = MagicMock()
    request.app.state.processor.orchestrator = MagicMock()

    mock_run = MagicMock()
    mock_run.id = "run-1"
    mock_run.status = "completed"
    mock_run.started_at = MagicMock()
    mock_run.completed_at = MagicMock()
    mock_run.usage = {"input_tokens": 100, "output_tokens": 50, "total_tokens": 150}
    mock_run.trigger_id = "link-abc"
    mock_run.input = {"status": "submitted", "message": "Fetch this URL"}
    mock_run.output = {"content": "I fetched the content."}

    fake_metadata = [
        {
            "name": "fetch",
            "description": "Fetches content",
            "tools": [],
            "options": {},
            "middleware": [],
            "instructions": {"preview": "", "full": ""},
            "recent_runs": [mock_run],
            "last_run": {
                "id": "run-1",
                "status": "completed",
                "started_at": mock_run.started_at,
                "completed_at": mock_run.completed_at,
                "usage": mock_run.usage,
                "trigger_id": "link-abc",
                "input": mock_run.input,
                "output": mock_run.output,
            },
            "is_running": False,
        }
    ]

    with (
        patch(
            "agent_stack.routes.agents.get_agents_page_data",
            new_callable=AsyncMock,
            return_value={"agents": fake_metadata, "running_stages": set()},
        ),
        patch("agent_stack.routes.agents.AgentRunRepository") as _mock_repo_cls,
    ):
        await agents_page(request)

    call_args = request.app.state.templates.TemplateResponse.call_args
    ctx = call_args[0][1]
    agent = ctx["agents"][0]
    assert agent["last_run"] is not None
    assert agent["last_run"]["status"] == "completed"
    assert agent["last_run"]["input"]["message"] == "Fetch this URL"
    assert agent["last_run"]["output"]["content"] == "I fetched the content."
    assert len(agent["recent_runs"]) == 1
    assert ctx["pipeline_available"] is True


async def test_agents_page_handles_unavailable_pipeline() -> None:
    """Verify agents page renders safely when pipeline is unavailable."""
    request = MagicMock()
    request.app.state.templates = MagicMock()
    request.app.state.templates.TemplateResponse = MagicMock(return_value="<html>")
    request.app.state.cosmos = MagicMock()
    request.app.state.cosmos.database = MagicMock()
    request.app.state.processor = None

    await agents_page(request)

    call_args = request.app.state.templates.TemplateResponse.call_args
    assert call_args[0][0] == "agents.html"
    ctx = call_args[0][1]
    assert ctx["agents"] == []
    assert ctx["running_stages"] == set()
    assert ctx["pipeline_available"] is False
