"""FastAPI application factory with lifespan events."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlparse

import httpx
import uvicorn
from azure.core.exceptions import HttpResponseError
from azure.monitor.opentelemetry import configure_azure_monitor
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from agent_stack.agents.llm import create_chat_client
from agent_stack.agents.memory import FoundryMemoryProvider
from agent_stack.config import Settings, load_settings
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
from agent_stack.routes.settings import router as settings_router
from agent_stack.routes.status import router as status_router
from agent_stack.services.memory import MemoryService
from agent_stack.storage.blob import BlobStorageClient
from agent_stack.storage.renderer import StaticSiteRenderer

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Awaitable, Callable

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent / "templates"
STATIC_DIR = Path(__file__).resolve().parent / "static"
_DEFAULT_HOST = "0.0.0.0"  # noqa: S104
_REQUEST_ID_HEADER = "x-request-id"
_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


class _FeedRangeFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return "'feed_range' empty" not in record.getMessage()


def _configure_logging(settings: Settings, *, include_file_handler: bool) -> None:
    """Configure logging for both factory and CLI startup modes."""
    log_level = getattr(logging, settings.app.log_level.upper(), logging.INFO)
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    if not root_logger.handlers:
        stream_handler = logging.StreamHandler()
        stream_handler.setLevel(log_level)
        stream_handler.setFormatter(logging.Formatter(_LOG_FORMAT))
        root_logger.addHandler(stream_handler)

    if include_file_handler:
        log_dir = Path(__file__).resolve().parent.parent.parent / "logs"
        log_dir.mkdir(exist_ok=True)
        log_path = (log_dir / "server.log").resolve()
        has_file_handler = False
        for handler in root_logger.handlers:
            if not isinstance(handler, logging.FileHandler):
                continue
            if Path(handler.baseFilename).resolve() == log_path:
                has_file_handler = True
                break
        if not has_file_handler:
            file_handler = logging.FileHandler(log_path, mode="w")
            file_handler.setLevel(log_level)
            file_handler.setFormatter(logging.Formatter(_LOG_FORMAT))
            root_logger.addHandler(file_handler)

    logging.getLogger("azure").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("sse_starlette").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)
    logging.getLogger("agent_framework").setLevel(logging.WARNING)
    logging.getLogger("python_multipart").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)

    if not any(
        isinstance(filter_, _FeedRangeFilter) for filter_ in root_logger.filters
    ):
        root_logger.addFilter(_FeedRangeFilter())


def _install_request_diagnostics_middleware(app: FastAPI, settings: Settings) -> None:
    """Install middleware that logs request timings and slow responses."""
    app.state.inflight_requests = 0
    slow_request_ms = settings.app.slow_request_ms

    @app.middleware("http")
    async def _request_diagnostics(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = request.headers.get(_REQUEST_ID_HEADER) or uuid.uuid4().hex[:12]
        request.state.request_id = request_id
        app.state.inflight_requests += 1
        inflight_at_start = app.state.inflight_requests
        started_at = time.monotonic()
        response: Response | None = None

        try:
            response = await call_next(request)
            response.headers.setdefault(_REQUEST_ID_HEADER, request_id)
            return response
        finally:
            elapsed_ms = (time.monotonic() - started_at) * 1000
            app.state.inflight_requests = max(app.state.inflight_requests - 1, 0)
            status_code = response.status_code if response else 500
            message = (
                "Request handled — request_id=%s method=%s path=%s status=%d "
                "duration_ms=%.0f inflight_start=%d inflight_now=%d"
            )
            args = (
                request_id,
                request.method,
                request.url.path,
                status_code,
                elapsed_ms,
                inflight_at_start,
                app.state.inflight_requests,
            )
            if request.url.path != "/events" and elapsed_ms >= slow_request_ms:
                logger.warning(message, *args)
            else:
                logger.debug(message, *args)


async def _check_emulators(settings: Settings) -> bool:
    """Verify local emulators are reachable. Return False if any are down."""
    failures: list[str] = []
    async with httpx.AsyncClient(timeout=3) as client:
        cosmos_url = settings.cosmos.endpoint
        if not cosmos_url:
            failures.append(
                "AZURE_COSMOS_ENDPOINT is not set — add it to .env (see .env.example)"
            )
        elif not cosmos_url.startswith("https://"):
            try:
                await client.get(f"{cosmos_url.rstrip('/')}/")
            except httpx.ConnectError:
                parsed = urlparse(cosmos_url)
                failures.append(f"Cosmos DB emulator is not running at {parsed.netloc}")

        storage_url = settings.storage.account_url
        if not storage_url:
            failures.append(
                "AZURE_STORAGE_ACCOUNT_URL is not set — add it to .env "
                "(see .env.example)"
            )
        elif not storage_url.startswith("https://"):
            try:
                parsed = urlparse(storage_url)
                await client.get(f"{parsed.scheme}://{parsed.netloc}/")
            except httpx.ConnectError:
                parsed = urlparse(storage_url)
                failures.append(
                    f"Azurite storage emulator is not running at {parsed.netloc}"
                )

    if failures:
        for failure in failures:
            logger.error(failure)
        logger.error("Start the emulators with: docker compose up -d")
        return False
    return True


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:  # noqa: PLR0915
    """Manage application lifecycle — initialize DB, start change feed."""
    settings = load_settings()

    if settings.monitor.connection_string:
        configure_azure_monitor(connection_string=settings.monitor.connection_string)
        logger.info("Azure Monitor OpenTelemetry configured")

    cosmos = CosmosClient(settings.cosmos)
    await cosmos.initialize()
    app.state.cosmos = cosmos
    app.state.settings = settings
    app.state.templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

    chat_client = None
    if settings.foundry.project_endpoint:
        chat_client = create_chat_client(settings.foundry)
    else:
        logger.warning(
            "FOUNDRY_PROJECT_ENDPOINT is not set — agent pipeline will be unavailable"
        )
    editions_repo = EditionRepository(cosmos.database)

    storage = BlobStorageClient(settings.storage)
    await storage.initialize()
    app.state.storage = storage

    renderer = StaticSiteRenderer(editions_repo, storage)
    render_fn = renderer.render_edition
    upload_fn = storage.upload_html
    logger.info("Blob storage configured")

    # Initialize Foundry Memory (optional — gracefully disabled when unconfigured)
    context_providers: list | None = None
    memory_service: MemoryService | None = None
    if settings.foundry.project_endpoint and settings.memory.enabled:
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
        except Exception:  # noqa: BLE001
            logger.warning(
                "Foundry Memory initialization failed, continuing without memory",
                exc_info=True,
            )
    app.state.memory_service = memory_service

    processor = None
    if chat_client:
        orchestrator = PipelineOrchestrator(
            client=chat_client,
            links_repo=LinkRepository(cosmos.database),
            editions_repo=editions_repo,
            feedback_repo=FeedbackRepository(cosmos.database),
            agent_runs_repo=AgentRunRepository(cosmos.database),
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

    app.state.processor = processor
    app.state.start_time = datetime.now(UTC)
    logger.info("Application started")

    yield

    if processor:
        await processor.stop()
    await storage.close()
    await cosmos.close()
    logger.info("Application shutdown")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = load_settings()
    _configure_logging(settings, include_file_handler=False)
    app = FastAPI(
        title="The Agent Stack — Editorial Dashboard",
        lifespan=lifespan,
    )
    _install_request_diagnostics_middleware(app, settings)

    @app.exception_handler(HttpResponseError)
    async def _azure_error_handler(
        _request: Request, exc: HttpResponseError
    ) -> HTMLResponse:
        logger.exception("Azure service error: %s", exc.message)
        return HTMLResponse(
            content=f"<h1>Service Error</h1><p>{exc.message}</p>",
            status_code=502,
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
    app.include_router(settings_router)

    return app


def main() -> None:
    """Entry point for running the application."""
    settings = load_settings()
    _configure_logging(settings, include_file_handler=True)

    if settings.app.is_development and not asyncio.run(_check_emulators(settings)):
        return

    app = create_app()
    uvicorn.run(app, host=_DEFAULT_HOST, port=8000, log_config=None)


if __name__ == "__main__":
    main()
