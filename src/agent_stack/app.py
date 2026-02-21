"""FastAPI application factory with lifespan events."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from agent_stack.agents.llm import create_chat_client
from agent_stack.config import load_settings
from agent_stack.database.client import CosmosClient
from agent_stack.database.repositories.agent_runs import AgentRunRepository
from agent_stack.database.repositories.editions import EditionRepository
from agent_stack.database.repositories.feedback import FeedbackRepository
from agent_stack.database.repositories.links import LinkRepository
from agent_stack.pipeline.change_feed import ChangeFeedProcessor
from agent_stack.pipeline.orchestrator import PipelineOrchestrator
from agent_stack.routes.agent_runs import router as agent_runs_router
from agent_stack.routes.agents import router as agents_router
from agent_stack.routes.auth import router as auth_router
from agent_stack.routes.dashboard import router as dashboard_router
from agent_stack.routes.editions import router as editions_router
from agent_stack.routes.events import router as events_router
from agent_stack.routes.feedback import router as feedback_router
from agent_stack.routes.links import router as links_router
from agent_stack.routes.status import router as status_router
from agent_stack.storage.blob import BlobStorageClient
from agent_stack.storage.renderer import StaticSiteRenderer

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent / "templates"
STATIC_DIR = Path(__file__).resolve().parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle — initialize DB, start change feed."""
    settings = load_settings()

    if settings.monitor.connection_string:
        from azure.monitor.opentelemetry import configure_azure_monitor

        configure_azure_monitor(connection_string=settings.monitor.connection_string)
        logger.info("Azure Monitor OpenTelemetry configured")

    cosmos = CosmosClient(settings.cosmos)
    await cosmos.initialize()
    app.state.cosmos = cosmos
    app.state.settings = settings
    app.state.templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

    # Start the agent pipeline
    chat_client = create_chat_client(settings.openai)
    editions_repo = EditionRepository(cosmos.database)

    render_fn = None
    upload_fn = None
    storage: BlobStorageClient | None = None

    if settings.storage.connection_string:
        try:
            storage = BlobStorageClient(settings.storage)
            await storage.initialize()
            app.state.storage = storage

            renderer = StaticSiteRenderer(editions_repo, storage)
            render_fn = renderer.render_edition
            upload_fn = storage.upload_html
            logger.info("Blob storage configured")
        except Exception:
            logger.warning("Failed to connect to blob storage — publish uploads disabled", exc_info=True)
            if storage:
                await storage.close()
            storage = None
    else:
        logger.warning("AZURE_STORAGE_CONNECTION_STRING not set — publish uploads disabled")

    orchestrator = PipelineOrchestrator(
        client=chat_client,
        links_repo=LinkRepository(cosmos.database),
        editions_repo=editions_repo,
        feedback_repo=FeedbackRepository(cosmos.database),
        agent_runs_repo=AgentRunRepository(cosmos.database),
        render_fn=render_fn,
        upload_fn=upload_fn,
    )
    processor = ChangeFeedProcessor(cosmos.database, orchestrator)
    await processor.start()
    app.state.processor = processor
    logger.info("Application started")

    yield

    await processor.stop()
    if storage:
        await storage.close()
    await cosmos.close()
    logger.info("Application shutdown")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="The Agent Stack — Editorial Dashboard",
        lifespan=lifespan,
    )

    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    app.include_router(auth_router)
    app.include_router(dashboard_router)
    app.include_router(links_router)
    app.include_router(editions_router)
    app.include_router(feedback_router)
    app.include_router(events_router)
    app.include_router(agent_runs_router)
    app.include_router(agents_router)
    app.include_router(status_router)

    return app


def main() -> None:
    """Entry point for running the application."""
    log_dir = Path(__file__).resolve().parent.parent.parent / "logs"
    log_dir.mkdir(exist_ok=True)

    file_handler = logging.FileHandler(log_dir / "server.log", mode="w")
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))

    logging.basicConfig(level=logging.INFO, handlers=[logging.StreamHandler(), file_handler])
    logging.getLogger("azure").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    # The Cosmos SDK logs a noisy INFO message on the root logger every change
    # feed poll ("'feed_range' empty. Using full range by default.").  Suppress it.
    class _FeedRangeFilter(logging.Filter):
        def filter(self, record: logging.LogRecord) -> bool:
            return "'feed_range' empty" not in record.getMessage()

    logging.getLogger().addFilter(_FeedRangeFilter())

    app = create_app()
    uvicorn.run(app, host="0.0.0.0", port=8000, log_config=None)


if __name__ == "__main__":
    main()
