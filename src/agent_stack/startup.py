"""Application startup — initialization helpers for the lifespan context."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from agent_stack.agents.llm import create_chat_client
from agent_stack.agents.memory import FoundryMemoryProvider
from agent_stack.database.client import CosmosClient
from agent_stack.database.repositories.agent_runs import AgentRunRepository
from agent_stack.database.repositories.feedback import FeedbackRepository
from agent_stack.database.repositories.links import LinkRepository
from agent_stack.pipeline.change_feed import ChangeFeedProcessor
from agent_stack.pipeline.orchestrator import PipelineOrchestrator
from agent_stack.services.memory import MemoryService
from agent_stack.storage.blob import BlobStorageClient
from agent_stack.storage.renderer import StaticSiteRenderer

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from agent_framework import BaseChatClient

    from agent_stack.config import Settings
    from agent_stack.database.repositories.editions import EditionRepository

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
    context_providers: list | None = None


@dataclass
class PipelineComponents:
    """Pipeline orchestrator and change feed processor."""

    processor: ChangeFeedProcessor | None = None


async def init_database(settings: Settings) -> CosmosClient:
    """Initialize and return the Cosmos DB client."""
    cosmos = CosmosClient(settings.cosmos)
    await cosmos.initialize()
    return cosmos


def init_chat_client(settings: Settings) -> BaseChatClient | None:
    """Create the LLM chat client based on configuration."""
    if settings.foundry.is_local:
        client = create_chat_client(settings.foundry)
        logger.info("Using Foundry Local — model=%s", settings.foundry.local_model)
        return client

    if not settings.foundry.project_endpoint:
        logger.warning(
            "FOUNDRY_PROJECT_ENDPOINT is not set — agent pipeline will be unavailable"
        )
        return None

    if not settings.foundry.model:
        logger.warning(
            "FOUNDRY_MODEL is not set for cloud provider — "
            "agent pipeline will be unavailable"
        )
        return None

    try:
        return create_chat_client(settings.foundry)
    except ValueError as exc:
        logger.warning(
            "Foundry chat client initialization failed (%s) — "
            "agent pipeline will be unavailable",
            exc,
        )
        return None


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
        context_providers = [
            FoundryMemoryProvider(
                project_client,
                settings.memory.memory_store_name,
                scope="project-editorial",
            ),
        ]
        logger.info(
            "Foundry Memory configured (store=%s)",
            settings.memory.memory_store_name,
        )
        return MemoryComponents(
            service=memory_service,
            context_providers=context_providers,
        )
    except Exception:  # noqa: BLE001
        logger.warning(
            "Foundry Memory initialization failed, continuing without memory",
            exc_info=True,
        )
        return MemoryComponents()


async def init_pipeline(
    chat_client: BaseChatClient,
    cosmos: CosmosClient,
    editions_repo: EditionRepository,
    storage_components: StorageComponents,
    memory_components: MemoryComponents,
) -> PipelineComponents:
    """Create the orchestrator, recover orphaned runs, and start the change feed."""
    orchestrator = PipelineOrchestrator(
        client=chat_client,
        links_repo=LinkRepository(cosmos.database),
        editions_repo=editions_repo,
        feedback_repo=FeedbackRepository(cosmos.database),
        agent_runs_repo=AgentRunRepository(cosmos.database),
        render_fn=storage_components.render_fn,
        upload_fn=storage_components.upload_fn,
        context_providers=memory_components.context_providers,
    )

    agent_runs_repo = AgentRunRepository(cosmos.database)
    recovered = await agent_runs_repo.recover_orphaned_runs()
    if recovered:
        logger.info("Recovered %d orphaned agent runs from prior crash", recovered)

    processor = ChangeFeedProcessor(cosmos.database, orchestrator)
    await processor.start()
    return PipelineComponents(processor=processor)
