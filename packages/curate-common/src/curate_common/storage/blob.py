"""Microsoft Azure Blob Storage client for uploading static newsletter files."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from azure.storage.blob import ContentSettings
from azure.storage.blob.aio import BlobServiceClient, ContainerClient

if TYPE_CHECKING:
    from azure.core.credentials_async import AsyncTokenCredential

    from curate_common.config import StorageConfig

logger = logging.getLogger(__name__)

_AZURITE_CONNECTION_STRING = (
    "DefaultEndpointsProtocol=http;"
    "AccountName=devstoreaccount1;"
    "AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq"
    "/K1SZFPTOtr/KBHBeksoGMGw==;"
    "BlobEndpoint=http://127.0.0.1:10000/devstoreaccount1"
)


class BlobStorageClient:
    """Upload rendered static files to Microsoft Azure Blob Storage's $web container."""

    def __init__(self, config: StorageConfig) -> None:
        """Initialize the blob storage client with connection config."""
        self._config = config
        self._service_client: BlobServiceClient | None = None
        self._credential: AsyncTokenCredential | None = None

    async def initialize(self) -> None:
        """Create the blob service client and ensure the target container exists."""
        if self._config.account_url.startswith("https://"):
            from azure.identity.aio import DefaultAzureCredential  # noqa: PLC0415

            self._credential = DefaultAzureCredential()
            self._service_client = BlobServiceClient(
                self._config.account_url, credential=self._credential
            )
        else:
            self._service_client = BlobServiceClient.from_connection_string(
                _AZURITE_CONNECTION_STRING
            )
        container = self._service_client.get_container_client(self._config.container)
        if not await container.exists():
            await container.create_container()

    async def close(self) -> None:
        """Close the underlying client."""
        if self._service_client:
            await self._service_client.close()
            self._service_client = None
        if self._credential:
            await self._credential.close()
            self._credential = None

    @property
    def service_client(self) -> BlobServiceClient | None:
        """Return the blob service client."""
        return self._service_client

    @service_client.setter
    def service_client(self, value: BlobServiceClient | None) -> None:
        self._service_client = value

    def get_container(self) -> ContainerClient:
        """Return the container client for the configured container."""
        if not self._service_client:
            msg = "BlobStorageClient not initialized"
            raise RuntimeError(msg)
        return self._service_client.get_container_client(self._config.container)

    async def upload_html(self, blob_name: str, content: str) -> None:
        """Upload an HTML file to the static site container."""
        container = self.get_container()
        blob = container.get_blob_client(blob_name)
        await blob.upload_blob(
            content.encode("utf-8"),
            overwrite=True,
            content_settings=ContentSettings(content_type="text/html; charset=utf-8"),
        )
        logger.debug("Uploaded %s to %s", blob_name, self._config.container)

    async def upload_css(self, blob_name: str, content: str) -> None:
        """Upload a CSS file to the static site container."""
        container = self.get_container()
        blob = container.get_blob_client(blob_name)
        await blob.upload_blob(
            content.encode("utf-8"),
            overwrite=True,
            content_settings=ContentSettings(content_type="text/css; charset=utf-8"),
        )
        logger.debug("Uploaded %s to %s", blob_name, self._config.container)
