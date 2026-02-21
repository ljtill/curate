"""Tests for BlobStorageClient."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_stack.config import StorageConfig
from agent_stack.storage.blob import BlobStorageClient


@pytest.mark.unit
class TestBlobStorageClient:
    @pytest.fixture
    def config(self):
        return StorageConfig(
            connection_string="DefaultEndpointsProtocol=https;AccountName=test",
            container="$web",
        )

    @pytest.fixture
    def client(self, config):
        return BlobStorageClient(config)

    async def test_initialize_creates_service_client(self, client):
        with patch("agent_stack.storage.blob.BlobServiceClient") as MockBSC:
            mock_service = MagicMock()
            mock_container = AsyncMock()
            mock_container.exists.return_value = True
            mock_service.get_container_client.return_value = mock_container
            MockBSC.from_connection_string.return_value = mock_service

            await client.initialize()

            MockBSC.from_connection_string.assert_called_once()
            mock_container.exists.assert_awaited_once()

    async def test_initialize_creates_container_if_missing(self, client):
        with patch("agent_stack.storage.blob.BlobServiceClient") as MockBSC:
            mock_service = MagicMock()
            mock_container = AsyncMock()
            mock_container.exists.return_value = False
            mock_service.get_container_client.return_value = mock_container
            MockBSC.from_connection_string.return_value = mock_service

            await client.initialize()

            mock_container.create_container.assert_awaited_once()

    async def test_close_closes_client(self, client):
        mock_service = AsyncMock()
        client._service_client = mock_service

        await client.close()

        mock_service.close.assert_awaited_once()
        assert client._service_client is None

    async def test_close_noop_when_not_initialized(self, client):
        await client.close()  # Should not raise

    def test_get_container_raises_when_not_initialized(self, client):
        with pytest.raises(RuntimeError, match="not initialized"):
            client._get_container()

    async def test_upload_html(self, client):
        mock_service = MagicMock()
        mock_container = MagicMock()
        mock_blob = AsyncMock()
        mock_container.get_blob_client.return_value = mock_blob
        mock_service.get_container_client.return_value = mock_container
        client._service_client = mock_service

        await client.upload_html("index.html", "<html>Test</html>")

        mock_blob.upload_blob.assert_awaited_once()
        call_args = mock_blob.upload_blob.call_args
        assert call_args[0][0] == b"<html>Test</html>"
        assert call_args[1]["overwrite"] is True

    async def test_upload_css(self, client):
        mock_service = MagicMock()
        mock_container = MagicMock()
        mock_blob = AsyncMock()
        mock_container.get_blob_client.return_value = mock_blob
        mock_service.get_container_client.return_value = mock_container
        client._service_client = mock_service

        await client.upload_css("style.css", "body { color: red; }")

        mock_blob.upload_blob.assert_awaited_once()
        call_args = mock_blob.upload_blob.call_args
        assert call_args[0][0] == b"body { color: red; }"
