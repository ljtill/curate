"""Worker application startup — initialization helpers for the pipeline."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from curate_common.database.client import CosmosClient
from curate_common.database.repositories.agent_runs import AgentRunRepository
from curate_common.database.repositories.feedback import FeedbackRepository
from curate_common.database.repositories.links import LinkRepository
from curate_common.storage.blob import BlobStorageClient
from curate_common.storage.renderer import StaticSiteRenderer
from curate_worker.agents.llm import create_chat_client
from curate_worker.agents.memory import FoundryMemoryProvider
from curate_worker.pipeline.change_feed import ChangeFeedProcessor
from curate_worker.pipeline.orchestrator import PipelineOrchestrator

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from agent_framework import BaseChatClient

    from curate_common.config import Settings
    from curate_common.database.repositories.editions import EditionRepository
    from curate_common.events import EventPublisher

logger = logging.getLogger(__name__)


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
) -> tuple[BlobStorageClient, StaticSiteRenderer]:
    """Initialize blob storage and renderer."""
    storage = BlobStorageClient(settings.storage)
    await storage.initialize()
    renderer = StaticSiteRenderer(editions_repo, storage)
    logger.info("Blob storage configured")
    return storage, renderer


async def init_memory(settings: Settings) -> list | None:
    """Initialize Foundry Memory context providers if configured."""
    if (
        settings.foundry.is_local
        or not settings.foundry.project_endpoint
        or not settings.memory.enabled
    ):
        return None

    try:
        from azure.ai.projects import AIProjectClient  # noqa: PLC0415
        from azure.identity import DefaultAzureCredential  # noqa: PLC0415

        project_client = AIProjectClient(
            endpoint=settings.foundry.project_endpoint,
            credential=DefaultAzureCredential(),
        )
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
        return context_providers  # noqa: TRY300
    except Exception:  # noqa: BLE001
        logger.warning(
            "Foundry Memory initialization failed, continuing without memory",
            exc_info=True,
        )
        return None


async def init_pipeline(
    chat_client: BaseChatClient,
    cosmos: CosmosClient,
    editions_repo: EditionRepository,
    event_publisher: EventPublisher,
    render_fn: Callable[..., Awaitable] | None = None,
    upload_fn: Callable[..., Awaitable] | None = None,
    context_providers: list | None = None,
) -> ChangeFeedProcessor:
    """Create the orchestrator, recover orphaned runs, and start the change feed."""
    orchestrator = PipelineOrchestrator(
        client=chat_client,
        links_repo=LinkRepository(cosmos.database),
        editions_repo=editions_repo,
        feedback_repo=FeedbackRepository(cosmos.database),
        agent_runs_repo=AgentRunRepository(cosmos.database),
        event_publisher=event_publisher,
        render_fn=render_fn,
        upload_fn=upload_fn,
        context_providers=context_providers,
    )

    agent_runs_repo = AgentRunRepository(cosmos.database)
    recovered = await agent_runs_repo.recover_orphaned_runs()
    if recovered:
        logger.info("Recovered %d orphaned agent runs from prior crash", recovered)

    processor = ChangeFeedProcessor(cosmos.database, orchestrator)
    await processor.start()
    return processor
