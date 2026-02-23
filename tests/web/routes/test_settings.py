"""Tests for the settings routes."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from curate_web.routes.settings import (
    clear_personal_memories,
    clear_project_memories,
    list_personal_memories,
    list_project_memories,
    settings_page,
    toggle_memory,
)
from curate_web.services.health import ServiceHealth
from tests.web.routes.runtime_helpers import make_runtime

_MOCK_TOKEN_TOTALS = {"input_tokens": 100, "output_tokens": 50, "total_tokens": 150}


def _make_settings_namespace() -> SimpleNamespace:
    """Create a minimal settings namespace for health check dependencies."""
    return SimpleNamespace(
        app=SimpleNamespace(env="development"),
        foundry=SimpleNamespace(
            project_endpoint="https://test.services.ai.azure.com",
            model="gpt-4o",
            is_local=False,
            local_model=None,
        ),
        cosmos=SimpleNamespace(endpoint="https://localhost:8081", database="curate"),
        storage=SimpleNamespace(
            account_url="https://127.0.0.1:10000/devstoreaccount1",
            container="content",
        ),
        memory=SimpleNamespace(enabled=True),
        servicebus=SimpleNamespace(
            connection_string="",
            topic="events",
            subscription="web",
        ),
        monitor=SimpleNamespace(connection_string=""),
    )


def _make_request(
    *,
    memory_service: MagicMock | None = None,
    user: dict | None = None,
    settings: SimpleNamespace | None = None,
) -> MagicMock:
    """Create a mock request with app state."""
    request = MagicMock()
    request.app.state.memory_service = memory_service
    request.app.state.templates = MagicMock()
    request.app.state.settings = settings or _make_settings_namespace()
    request.app.state.cosmos = MagicMock()
    request.app.state.storage = MagicMock()
    request.app.state.start_time = MagicMock()
    request.app.state.runtime = make_runtime(
        cosmos=request.app.state.cosmos,
        settings=request.app.state.settings,
        templates=request.app.state.templates,
        storage=request.app.state.storage,
        memory_service=request.app.state.memory_service,
        start_time=request.app.state.start_time,
    )
    if user is not None:
        request.session = {"user": user}
    else:
        request.session = {}
    return request


@pytest.mark.unit
class TestSettingsPage:
    """Test the settings page rendering."""

    async def test_renders_without_memory_service(self) -> None:
        """Verify rendering when no memory service configured."""
        request = _make_request()
        healthy = ServiceHealth(name="Cosmos DB", healthy=True, latency_ms=5.0)
        mock_repo = MagicMock()
        mock_repo.aggregate_token_usage = AsyncMock(return_value=_MOCK_TOKEN_TOTALS)
        with (
            patch(
                "curate_web.routes.settings.check_all",
                new_callable=AsyncMock,
                return_value=[healthy],
            ),
            patch(
                "curate_web.routes.settings.get_agent_run_repository",
                return_value=mock_repo,
            ),
        ):
            await settings_page(request)
        request.app.state.templates.TemplateResponse.assert_called_once()
        call_args = request.app.state.templates.TemplateResponse.call_args
        assert call_args[0][0] == "settings.html"
        assert call_args[0][1]["memory_configured"] is False
        assert call_args[0][1]["memory_disabled_by_config"] is False
        token_usage = call_args[0][1]["token_usage"]
        assert token_usage.input_tokens == _MOCK_TOKEN_TOTALS["input_tokens"]
        assert token_usage.total_tokens == _MOCK_TOKEN_TOTALS["total_tokens"]

    async def test_renders_with_memory_service(self) -> None:
        """Verify rendering with memory service present."""
        service = MagicMock()
        service.enabled = True
        service.store_name = "test-store"
        service.list_memories = AsyncMock(return_value=[])
        request = _make_request(
            memory_service=service,
            user={"oid": "user-123"},
        )
        healthy = ServiceHealth(name="Cosmos DB", healthy=True, latency_ms=5.0)
        mock_repo = MagicMock()
        mock_repo.aggregate_token_usage = AsyncMock(return_value=_MOCK_TOKEN_TOTALS)
        with (
            patch(
                "curate_web.routes.settings.check_all",
                new_callable=AsyncMock,
                return_value=[healthy],
            ),
            patch(
                "curate_web.routes.settings.get_agent_run_repository",
                return_value=mock_repo,
            ),
        ):
            await settings_page(request)
        call_args = request.app.state.templates.TemplateResponse.call_args
        assert call_args[0][1]["memory_configured"] is True
        assert call_args[0][1]["memory_disabled_by_config"] is False
        assert call_args[0][1]["memory_enabled"] is True
        assert "token_usage" in call_args[0][1]

    async def test_renders_when_memory_disabled_by_config(self) -> None:
        """Verify rendering state when memory is disabled via environment config."""
        settings = _make_settings_namespace()
        settings.memory.enabled = False
        request = _make_request(settings=settings)
        healthy = ServiceHealth(name="Cosmos DB", healthy=True, latency_ms=5.0)
        mock_repo = MagicMock()
        mock_repo.aggregate_token_usage = AsyncMock(return_value=_MOCK_TOKEN_TOTALS)
        with (
            patch(
                "curate_web.routes.settings.check_all",
                new_callable=AsyncMock,
                return_value=[healthy],
            ),
            patch(
                "curate_web.routes.settings.get_agent_run_repository",
                return_value=mock_repo,
            ),
        ):
            await settings_page(request)
        call_args = request.app.state.templates.TemplateResponse.call_args
        assert call_args[0][1]["memory_configured"] is False
        assert call_args[0][1]["memory_disabled_by_config"] is True


@pytest.mark.unit
class TestToggleMemory:
    """Test the memory toggle endpoint."""

    async def test_toggles_memory_on(self) -> None:
        """Verify toggling memory on."""
        service = MagicMock()
        service.enabled = True
        request = _make_request(memory_service=service)
        await toggle_memory(request, enabled="true")
        service.set_enabled.assert_called_once_with(enabled=True)

    async def test_toggles_memory_off(self) -> None:
        """Verify toggling memory off."""
        service = MagicMock()
        service.enabled = False
        request = _make_request(memory_service=service)
        await toggle_memory(request, enabled="false")
        service.set_enabled.assert_called_once_with(enabled=False)


@pytest.mark.unit
class TestProjectMemories:
    """Test project memory endpoints."""

    async def test_list_project_memories(self) -> None:
        """Verify listing project-scoped memories."""
        service = MagicMock()
        service.enabled = True
        service.list_memories = AsyncMock(
            return_value=[{"memory_id": "m1", "content": "test"}]
        )
        request = _make_request(memory_service=service)
        await list_project_memories(request)
        service.list_memories.assert_called_once_with("project-editorial")

    async def test_clear_project_memories(self) -> None:
        """Verify clearing project-scoped memories."""
        service = MagicMock()
        service.clear_memories = AsyncMock(return_value=True)
        request = _make_request(memory_service=service)
        await clear_project_memories(request)
        service.clear_memories.assert_called_once_with("project-editorial")


@pytest.mark.unit
class TestPersonalMemories:
    """Test personal memory endpoints."""

    async def test_list_personal_memories_with_user(self) -> None:
        """Verify listing user-scoped memories."""
        service = MagicMock()
        service.enabled = True
        service.list_memories = AsyncMock(return_value=[])
        request = _make_request(
            memory_service=service,
            user={"oid": "user-abc"},
        )
        await list_personal_memories(request)
        service.list_memories.assert_called_once_with("user-user-abc")

    async def test_list_personal_memories_without_user(self) -> None:
        """Verify no-op when user is not in session."""
        service = MagicMock()
        service.enabled = True
        service.list_memories = AsyncMock(return_value=[])
        request = _make_request(memory_service=service)
        await list_personal_memories(request)
        service.list_memories.assert_not_called()

    async def test_clear_personal_memories(self) -> None:
        """Verify clearing user-scoped memories."""
        service = MagicMock()
        service.clear_memories = AsyncMock(return_value=True)
        request = _make_request(
            memory_service=service,
            user={"oid": "user-abc"},
        )
        await clear_personal_memories(request)
        service.clear_memories.assert_called_once_with("user-user-abc")
