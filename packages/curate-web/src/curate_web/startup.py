"""Web application startup — initialization helpers for the lifespan context."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from curate_common.database.client import CosmosClient
from curate_common.storage.blob import BlobStorageClient
from curate_common.storage.renderer import StaticSiteRenderer
from curate_web.services.memory import MemoryService

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from curate_common.config import Settings
    from curate_common.database.repositories.editions import EditionRepository

logger = logging.getLogger(__name__)


@dataclass
class StorageComponents:
    """Blob storage client, render and upload callables."""

    client: BlobStorageClient
    render_fn: Callable[..., Awaitable]
    upload_fn: Callable[..., Awaitable]


@dataclass
class MemoryComponents:
    """Foundry Memory service and context providers."""

    service: MemoryService | None = None


async def init_database(settings: Settings) -> CosmosClient:
    """Initialize and return the Cosmos DB client."""
    cosmos = CosmosClient(settings.cosmos)
    await cosmos.initialize()
    return cosmos


async def init_storage(
    settings: Settings, editions_repo: EditionRepository
) -> StorageComponents:
    """Initialize blob storage, renderer, and return callables."""
    storage = BlobStorageClient(settings.storage)
    await storage.initialize()
    renderer = StaticSiteRenderer(editions_repo, storage)
    logger.info("Blob storage configured")
    return StorageComponents(
        client=storage,
        render_fn=renderer.render_edition,
        upload_fn=storage.upload_html,
    )


async def init_memory(settings: Settings) -> MemoryComponents:
    """Initialize Foundry Memory if configured and enabled."""
    if (
        settings.foundry.is_local
        or not settings.foundry.project_endpoint
        or not settings.memory.enabled
    ):
        return MemoryComponents()

    try:
        from azure.ai.projects import AIProjectClient  # noqa: PLC0415
        from azure.identity import DefaultAzureCredential  # noqa: PLC0415

        project_client = AIProjectClient(
            endpoint=settings.foundry.project_endpoint,
            credential=DefaultAzureCredential(),
        )
        memory_service = MemoryService(project_client, settings.memory)
        await memory_service.ensure_memory_store()
        logger.info(
            "Foundry Memory configured (store=%s)",
            settings.memory.memory_store_name,
        )
        return MemoryComponents(service=memory_service)
    except Exception:  # noqa: BLE001
        logger.warning(
            "Foundry Memory initialization failed, continuing without memory",
            exc_info=True,
        )
        return MemoryComponents()
