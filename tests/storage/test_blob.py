"""Tests for BlobStorageClient."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_stack.config import StorageConfig
from agent_stack.storage.blob import BlobStorageClient


class TestBlobStorageClient:
    """Test the Blob Storage Client."""

    @pytest.fixture
    def config(self) -> StorageConfig:
        """Create a config for testing."""
        return StorageConfig(
            account_url="https://test.blob.core.windows.net",
            container="$web",
        )

    @pytest.fixture
    def client(self, config: StorageConfig) -> BlobStorageClient:
        """Create a mock client."""
        return BlobStorageClient(config)

    async def test_initialize_creates_service_client(
        self, client: BlobStorageClient
    ) -> None:
        """Verify initialize creates service client."""
        with (
            patch("agent_stack.storage.blob.BlobServiceClient") as mock_bsc_cls,
            patch("agent_stack.storage.blob.DefaultAzureCredential") as mock_cred_cls,
        ):
            mock_service = MagicMock()
            mock_container = AsyncMock()
            mock_container.exists.return_value = True
            mock_service.get_container_client.return_value = mock_container
            mock_bsc_cls.return_value = mock_service

            await client.initialize()

            mock_bsc_cls.assert_called_once_with(
                "https://test.blob.core.windows.net",
                credential=mock_cred_cls.return_value,
            )
            mock_container.exists.assert_awaited_once()

    async def test_initialize_creates_container_if_missing(
        self, client: BlobStorageClient
    ) -> None:
        """Verify initialize creates container if missing."""
        with (
            patch("agent_stack.storage.blob.BlobServiceClient") as mock_bsc_cls,
            patch("agent_stack.storage.blob.DefaultAzureCredential"),
        ):
            mock_service = MagicMock()
            mock_container = AsyncMock()
            mock_container.exists.return_value = False
            mock_service.get_container_client.return_value = mock_container
            mock_bsc_cls.return_value = mock_service

            await client.initialize()

            mock_container.create_container.assert_awaited_once()

    async def test_close_closes_client(self, client: BlobStorageClient) -> None:
        """Verify close closes client."""
        mock_service = AsyncMock()
        client.service_client = mock_service

        await client.close()

        mock_service.close.assert_awaited_once()
        assert client.service_client is None

    async def test_close_noop_when_not_initialized(
        self, client: BlobStorageClient
    ) -> None:
        """Verify close noop when not initialized."""
        await client.close()

    def test_get_container_raises_when_not_initialized(
        self, client: BlobStorageClient
    ) -> None:
        """Verify get container raises when not initialized."""
        with pytest.raises(RuntimeError, match="not initialized"):
            client.get_container()

    async def test_upload_html(self, client: BlobStorageClient) -> None:
        """Verify upload html."""
        mock_service = MagicMock()
        mock_container = MagicMock()
        mock_blob = AsyncMock()
        mock_container.get_blob_client.return_value = mock_blob
        mock_service.get_container_client.return_value = mock_container
        client.service_client = mock_service

        await client.upload_html("index.html", "<html>Test</html>")

        mock_blob.upload_blob.assert_awaited_once()
        call_args = mock_blob.upload_blob.call_args
        assert call_args[0][0] == b"<html>Test</html>"
        assert call_args[1]["overwrite"] is True

    async def test_upload_css(self, client: BlobStorageClient) -> None:
        """Verify upload css."""
        mock_service = MagicMock()
        mock_container = MagicMock()
        mock_blob = AsyncMock()
        mock_container.get_blob_client.return_value = mock_blob
        mock_service.get_container_client.return_value = mock_container
        client.service_client = mock_service

        await client.upload_css("style.css", "body { color: red; }")

        mock_blob.upload_blob.assert_awaited_once()
        call_args = mock_blob.upload_blob.call_args
        assert call_args[0][0] == b"body { color: red; }"
