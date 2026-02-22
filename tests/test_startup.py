"""Tests for startup initialization helpers."""

from unittest.mock import AsyncMock, MagicMock, patch

from agent_stack.startup import (
    MemoryComponents,
    StorageComponents,
    init_chat_client,
    init_database,
    init_memory,
    init_pipeline,
    init_storage,
)


async def test_init_database_initializes_and_returns_client() -> None:
    """Verify init_database creates and initializes a CosmosClient."""
    settings = MagicMock()
    with patch("agent_stack.startup.CosmosClient") as mock_cls:
        mock_cls.return_value.initialize = AsyncMock()
        result = await init_database(settings)

    mock_cls.assert_called_once_with(settings.cosmos)
    mock_cls.return_value.initialize.assert_awaited_once()
    assert result is mock_cls.return_value


def test_init_chat_client_local() -> None:
    """Verify local Foundry creates a chat client."""
    settings = MagicMock()
    settings.foundry.is_local = True
    with patch("agent_stack.startup.create_chat_client") as mock_create:
        mock_create.return_value = MagicMock()
        result = init_chat_client(settings)

    assert result is mock_create.return_value


def test_init_chat_client_none_when_no_endpoint() -> None:
    """Verify None is returned when no endpoint is configured."""
    settings = MagicMock()
    settings.foundry.is_local = False
    settings.foundry.project_endpoint = ""
    result = init_chat_client(settings)
    assert result is None


async def test_init_storage_returns_components() -> None:
    """Verify init_storage returns StorageComponents with callables."""
    settings = MagicMock()
    editions_repo = MagicMock()
    with (
        patch("agent_stack.startup.BlobStorageClient") as mock_blob,
        patch("agent_stack.startup.StaticSiteRenderer") as mock_renderer,
    ):
        mock_blob.return_value.initialize = AsyncMock()
        result = await init_storage(settings, editions_repo)

    assert isinstance(result, StorageComponents)
    assert result.client is mock_blob.return_value
    assert result.render_fn is mock_renderer.return_value.render_edition
    assert result.upload_fn is mock_blob.return_value.upload_html


async def test_init_memory_disabled_when_local() -> None:
    """Verify memory returns empty components when using Foundry Local."""
    settings = MagicMock()
    settings.foundry.is_local = True
    result = await init_memory(settings)
    assert isinstance(result, MemoryComponents)
    assert result.service is None
    assert result.context_providers is None


async def test_init_pipeline_creates_processor() -> None:
    """Verify init_pipeline creates orchestrator, recovers runs, starts processor."""
    chat_client = MagicMock()
    cosmos = MagicMock()
    editions_repo = MagicMock()
    storage = StorageComponents(
        client=MagicMock(),
        render_fn=AsyncMock(),
        upload_fn=AsyncMock(),
    )
    memory = MemoryComponents()

    with (
        patch("agent_stack.startup.PipelineOrchestrator"),
        patch("agent_stack.startup.AgentRunRepository") as mock_runs_repo,
        patch("agent_stack.startup.ChangeFeedProcessor") as mock_feed,
    ):
        mock_runs_repo.return_value.recover_orphaned_runs = AsyncMock(return_value=0)
        mock_feed.return_value.start = AsyncMock()
        result = await init_pipeline(
            chat_client, cosmos, editions_repo, storage, memory
        )

    assert result.processor is mock_feed.return_value
    mock_feed.return_value.start.assert_awaited_once()
