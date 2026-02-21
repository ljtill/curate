"""Azure Blob Storage client for uploading static newsletter files."""

from __future__ import annotations

import logging

from azure.storage.blob import ContentSettings
from azure.storage.blob.aio import BlobServiceClient, ContainerClient

from agent_stack.config import StorageConfig

logger = logging.getLogger(__name__)


class BlobStorageClient:
    """Uploads rendered static files to Azure Blob Storage's $web container."""

    def __init__(self, config: StorageConfig) -> None:
        self._config = config
        self._service_client: BlobServiceClient | None = None

    async def initialize(self) -> None:
        """Create the blob service client and ensure the target container exists."""
        self._service_client = BlobServiceClient.from_connection_string(self._config.connection_string)
        container = self._service_client.get_container_client(self._config.container)
        if not await container.exists():
            await container.create_container()

    async def close(self) -> None:
        """Close the underlying client."""
        if self._service_client:
            await self._service_client.close()
            self._service_client = None

    def _get_container(self) -> ContainerClient:
        if not self._service_client:
            raise RuntimeError("BlobStorageClient not initialized")
        return self._service_client.get_container_client(self._config.container)

    async def upload_html(self, blob_name: str, content: str) -> None:
        """Upload an HTML file to the static site container."""
        container = self._get_container()
        blob = container.get_blob_client(blob_name)
        await blob.upload_blob(
            content.encode("utf-8"),
            overwrite=True,
            content_settings=ContentSettings(content_type="text/html; charset=utf-8"),
        )
        logger.info("Uploaded %s to %s", blob_name, self._config.container)

    async def upload_css(self, blob_name: str, content: str) -> None:
        """Upload a CSS file to the static site container."""
        container = self._get_container()
        blob = container.get_blob_client(blob_name)
        await blob.upload_blob(
            content.encode("utf-8"),
            overwrite=True,
            content_settings=ContentSettings(content_type="text/css; charset=utf-8"),
        )
        logger.info("Uploaded %s to %s", blob_name, self._config.container)
