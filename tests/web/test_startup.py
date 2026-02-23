"""Tests for web startup initialization helpers."""

from unittest.mock import AsyncMock, MagicMock, patch

from curate_web.startup import (
    MemoryComponents,
    StorageComponents,
    init_database,
    init_memory,
    init_storage,
)


async def test_init_database_initializes_and_returns_client() -> None:
    """Verify init_database creates and initializes a CosmosClient."""
    settings = MagicMock()
    with patch("curate_web.startup.CosmosClient") as mock_cls:
        mock_cls.return_value.initialize = AsyncMock()
        result = await init_database(settings)

    mock_cls.assert_called_once_with(settings.cosmos)
    mock_cls.return_value.initialize.assert_awaited_once()
    assert result is mock_cls.return_value


async def test_init_storage_returns_components() -> None:
    """Verify init_storage returns StorageComponents with callables."""
    settings = MagicMock()
    editions_repo = MagicMock()
    with (
        patch("curate_web.startup.BlobStorageClient") as mock_blob,
        patch("curate_web.startup.StaticSiteRenderer") as mock_renderer,
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
