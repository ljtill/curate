"""Tests for the settings routes."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from agent_stack.routes.settings import (
    clear_personal_memories,
    clear_project_memories,
    list_personal_memories,
    list_project_memories,
    settings_page,
    toggle_memory,
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
    if settings is not None:
        request.app.state.settings = settings
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
        await settings_page(request)
        request.app.state.templates.TemplateResponse.assert_called_once()
        call_args = request.app.state.templates.TemplateResponse.call_args
        assert call_args[0][0] == "settings.html"
        assert call_args[0][1]["memory_configured"] is False
        assert call_args[0][1]["memory_disabled_by_config"] is False

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
        await settings_page(request)
        call_args = request.app.state.templates.TemplateResponse.call_args
        assert call_args[0][1]["memory_configured"] is True
        assert call_args[0][1]["memory_disabled_by_config"] is False
        assert call_args[0][1]["memory_enabled"] is True

    async def test_renders_when_memory_disabled_by_config(self) -> None:
        """Verify rendering state when memory is disabled via environment config."""
        request = _make_request(
            settings=SimpleNamespace(
                foundry=SimpleNamespace(
                    project_endpoint="https://test.services.ai.azure.com"
                ),
                memory=SimpleNamespace(enabled=False),
            )
        )
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
