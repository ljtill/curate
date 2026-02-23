"""Tests for the MemoryService."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from curate_common.config import FoundryMemoryConfig
from curate_web.services.memory import MemoryService


@pytest.fixture
def memory_config() -> FoundryMemoryConfig:
    """Create a test memory config."""
    return FoundryMemoryConfig(
        memory_store_name="test-store",
        chat_model="gpt-4.1-mini",
        embedding_model="text-embedding-3-small",
    )


@pytest.fixture
def disabled_config() -> FoundryMemoryConfig:
    """Create a disabled memory config."""
    return FoundryMemoryConfig(
        memory_store_name="test-store",
        chat_model="gpt-4.1-mini",
        embedding_model="text-embedding-3-small",
        enabled=False,
    )


@pytest.fixture
def mock_project_client() -> MagicMock:
    """Create a mock AIProjectClient."""
    client = MagicMock()
    client.memory_stores = MagicMock()
    return client


@pytest.fixture
def service(
    mock_project_client: MagicMock, memory_config: FoundryMemoryConfig
) -> MemoryService:
    """Create a MemoryService with mocked client."""
    return MemoryService(mock_project_client, memory_config)


@pytest.fixture
def disabled_service(
    mock_project_client: MagicMock, disabled_config: FoundryMemoryConfig
) -> MemoryService:
    """Create a disabled MemoryService."""
    return MemoryService(mock_project_client, disabled_config)


@pytest.mark.unit
class TestMemoryServiceInit:
    """Test service initialization."""

    def test_enabled_by_default(self, service: MemoryService) -> None:
        """Verify service is enabled by default."""
        assert service.enabled is True

    def test_disabled_when_configured(self, disabled_service: MemoryService) -> None:
        """Verify service respects enabled=False."""
        assert disabled_service.enabled is False

    def test_store_name(self, service: MemoryService) -> None:
        """Verify store name matches config."""
        assert service.store_name == "test-store"


@pytest.mark.unit
class TestToggle:
    """Test enable/disable toggle."""

    def test_toggle_off(self, service: MemoryService) -> None:
        """Verify toggling memory off."""
        service.set_enabled(enabled=False)
        assert service.enabled is False

    def test_toggle_on(self, disabled_service: MemoryService) -> None:
        """Verify toggling memory on."""
        disabled_service.set_enabled(enabled=True)
        assert disabled_service.enabled is True


@pytest.mark.unit
class TestEnsureMemoryStore:
    """Test memory store creation."""

    async def test_skips_when_disabled(
        self,
        disabled_service: MemoryService,
        mock_project_client: MagicMock,
    ) -> None:
        """Verify store creation is skipped when disabled."""
        await disabled_service.ensure_memory_store()
        mock_project_client.memory_stores.create.assert_not_called()

    async def test_creates_store_when_enabled(
        self,
        service: MemoryService,
        mock_project_client: MagicMock,
    ) -> None:
        """Verify store is created when enabled."""
        await service.ensure_memory_store()
        mock_project_client.memory_stores.create.assert_called_once()

    async def test_handles_creation_failure(
        self,
        service: MemoryService,
        mock_project_client: MagicMock,
    ) -> None:
        """Verify creation errors are caught gracefully."""
        mock_project_client.memory_stores.create.side_effect = Exception(
            "Already exists"
        )
        # Should not raise
        await service.ensure_memory_store()


@pytest.mark.unit
class TestListMemories:
    """Test memory listing."""

    async def test_returns_empty_when_disabled(
        self, disabled_service: MemoryService
    ) -> None:
        """Verify empty list when disabled."""
        result = await disabled_service.list_memories("test-scope")
        assert result == []

    async def test_returns_memories(
        self,
        service: MemoryService,
        mock_project_client: MagicMock,
    ) -> None:
        """Verify memories are returned from the store."""
        memory_item = MagicMock()
        memory_item.memory_id = "mem-1"
        memory_item.content = "Editorial preference"
        memory_result = MagicMock()
        memory_result.memory_item = memory_item

        response = MagicMock()
        response.memories = [memory_result]
        mock_project_client.memory_stores.search_memories.return_value = response

        result = await service.list_memories("test-scope")
        assert len(result) == 1
        assert result[0]["memory_id"] == "mem-1"
        assert result[0]["content"] == "Editorial preference"


@pytest.mark.unit
class TestClearMemories:
    """Test memory clearing."""

    async def test_returns_false_when_disabled(
        self, disabled_service: MemoryService
    ) -> None:
        """Verify False when disabled."""
        result = await disabled_service.clear_memories("test-scope")
        assert result is False

    async def test_clears_scope(
        self,
        service: MemoryService,
        mock_project_client: MagicMock,
    ) -> None:
        """Verify scope is cleared successfully."""
        result = await service.clear_memories("test-scope")
        assert result is True
        mock_project_client.memory_stores.delete_scope.assert_called_once_with(
            name="test-store",
            scope="test-scope",
        )

    async def test_handles_clear_failure(
        self,
        service: MemoryService,
        mock_project_client: MagicMock,
    ) -> None:
        """Verify clear errors return False."""
        mock_project_client.memory_stores.delete_scope.side_effect = Exception("Error")
        result = await service.clear_memories("test-scope")
        assert result is False
