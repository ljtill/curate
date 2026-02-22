"""Tests for the FoundryMemoryProvider context provider."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from agent_stack.agents.memory import FoundryMemoryProvider


@pytest.fixture
def mock_project_client() -> MagicMock:
    """Create a mock AIProjectClient."""
    client = MagicMock()
    client.memory_stores = MagicMock()
    return client


@pytest.fixture
def provider(mock_project_client: MagicMock) -> FoundryMemoryProvider:
    """Create a FoundryMemoryProvider with mocked client."""
    return FoundryMemoryProvider(
        project_client=mock_project_client,
        memory_store_name="test-store",
        scope="project-editorial",
    )


@pytest.fixture
def disabled_provider(mock_project_client: MagicMock) -> FoundryMemoryProvider:
    """Create a disabled FoundryMemoryProvider."""
    return FoundryMemoryProvider(
        project_client=mock_project_client,
        memory_store_name="test-store",
        scope="project-editorial",
        enabled=False,
    )


@pytest.fixture
def mock_context() -> MagicMock:
    """Create a mock SessionContext."""
    ctx = MagicMock()
    msg = MagicMock()
    msg.text = "Test input message"
    ctx.input_messages = [msg]
    ctx.extend_instructions = MagicMock()
    ctx.response = None
    return ctx


@pytest.fixture
def mock_session() -> MagicMock:
    """Create a mock AgentSession."""
    session = MagicMock()
    session.state = {}
    return session


@pytest.mark.unit
class TestFoundryMemoryProviderInit:
    """Test provider initialization."""

    def test_source_id(self, provider: FoundryMemoryProvider) -> None:
        """Verify the default source ID."""
        assert provider.source_id == "foundry_memory"

    def test_enabled_by_default(self, provider: FoundryMemoryProvider) -> None:
        """Verify provider is enabled by default."""
        assert provider.enabled is True

    def test_disabled_when_configured(
        self, disabled_provider: FoundryMemoryProvider
    ) -> None:
        """Verify provider respects enabled=False."""
        assert disabled_provider.enabled is False


@pytest.mark.unit
class TestBeforeRun:
    """Test memory search and injection before agent runs."""

    async def test_skips_when_disabled(
        self,
        disabled_provider: FoundryMemoryProvider,
        mock_context: MagicMock,
        mock_session: MagicMock,
    ) -> None:
        """Verify before_run is a no-op when disabled."""
        await disabled_provider.before_run(
            agent=MagicMock(),
            session=mock_session,
            context=mock_context,
            state={},
        )
        mock_context.extend_instructions.assert_not_called()

    async def test_injects_memories_when_found(
        self,
        provider: FoundryMemoryProvider,
        mock_project_client: MagicMock,
        mock_context: MagicMock,
        mock_session: MagicMock,
    ) -> None:
        """Verify memories are injected as instructions."""
        memory_item = MagicMock()
        memory_item.memory_id = "mem-1"
        memory_item.content = "Prefer concise signal descriptions"
        memory_result = MagicMock()
        memory_result.memory_item = memory_item

        search_response = MagicMock()
        search_response.memories = [memory_result]
        mock_project_client.memory_stores.search_memories.return_value = search_response

        await provider.before_run(
            agent=MagicMock(),
            session=mock_session,
            context=mock_context,
            state={},
        )

        mock_context.extend_instructions.assert_called_once()
        call_args = mock_context.extend_instructions.call_args
        assert call_args[0][0] == "foundry_memory"
        assert "Prefer concise signal descriptions" in call_args[0][1]

    async def test_handles_search_failure_gracefully(
        self,
        provider: FoundryMemoryProvider,
        mock_project_client: MagicMock,
        mock_context: MagicMock,
        mock_session: MagicMock,
    ) -> None:
        """Verify search errors are caught gracefully."""
        mock_project_client.memory_stores.search_memories.side_effect = Exception(
            "Connection timeout"
        )

        # Should not raise
        await provider.before_run(
            agent=MagicMock(),
            session=mock_session,
            context=mock_context,
            state={},
        )
        mock_context.extend_instructions.assert_not_called()


@pytest.mark.unit
class TestAfterRun:
    """Test memory capture after agent runs."""

    async def test_skips_when_disabled(
        self,
        disabled_provider: FoundryMemoryProvider,
        mock_project_client: MagicMock,
        mock_context: MagicMock,
        mock_session: MagicMock,
    ) -> None:
        """Verify after_run is a no-op when disabled."""
        await disabled_provider.after_run(
            agent=MagicMock(),
            session=mock_session,
            context=mock_context,
            state={},
        )
        mock_project_client.memory_stores.begin_update_memories.assert_not_called()

    async def test_skips_when_skip_memory_capture_set(
        self,
        provider: FoundryMemoryProvider,
        mock_project_client: MagicMock,
        mock_context: MagicMock,
        mock_session: MagicMock,
    ) -> None:
        """Verify capture is skipped when state flag is set."""
        await provider.after_run(
            agent=MagicMock(),
            session=mock_session,
            context=mock_context,
            state={"skip_memory_capture": True},
        )
        mock_project_client.memory_stores.begin_update_memories.assert_not_called()

    async def test_sends_conversation_for_extraction(
        self,
        provider: FoundryMemoryProvider,
        mock_project_client: MagicMock,
        mock_context: MagicMock,
        mock_session: MagicMock,
    ) -> None:
        """Verify conversation is sent for memory extraction."""
        response_msg = MagicMock()
        response_msg.text = "Agent response text"
        mock_context.response = MagicMock()
        mock_context.response.messages = [response_msg]

        await provider.after_run(
            agent=MagicMock(),
            session=mock_session,
            context=mock_context,
            state={},
        )

        mock_project_client.memory_stores.begin_update_memories.assert_called_once()

    async def test_handles_update_failure_gracefully(
        self,
        provider: FoundryMemoryProvider,
        mock_project_client: MagicMock,
        mock_context: MagicMock,
        mock_session: MagicMock,
    ) -> None:
        """Verify update errors are caught gracefully."""
        mock_project_client.memory_stores.begin_update_memories.side_effect = Exception(
            "Service unavailable"
        )

        # Should not raise
        await provider.after_run(
            agent=MagicMock(),
            session=mock_session,
            context=mock_context,
            state={},
        )
