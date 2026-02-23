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

import uvicorn
from azure.core.exceptions import HttpResponseError, ServiceRequestError
from azure.monitor.opentelemetry import configure_azure_monitor
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware import Middleware
from starlette.middleware.sessions import SessionMiddleware

from curate_common.config import Settings, load_settings
from curate_common.database.repositories.editions import EditionRepository
from curate_common.health import check_emulators
from curate_common.logging import configure_logging
from curate_web.routes.agent_runs import router as agent_runs_router
from curate_web.routes.auth import router as auth_router
from curate_web.routes.dashboard import router as dashboard_router
from curate_web.routes.editions import router as editions_router
from curate_web.routes.events import router as events_router
from curate_web.routes.feedback import router as feedback_router
from curate_web.routes.links import router as store_router
from curate_web.routes.settings import router as settings_router
from curate_web.routes.status import router as status_router
from curate_web.startup import (
    init_database,
    init_memory,
    init_storage,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Awaitable, Callable

logger = logging.getLogger(__name__)


def _find_dir(name: str) -> Path:
    """Locate a directory by walking up from this file to the workspace root."""
    current = Path(__file__).resolve().parent
    for _ in range(10):
        candidate = current / name
        if candidate.is_dir():
            return candidate
        current = current.parent
    return Path.cwd() / name


TEMPLATES_DIR = _find_dir("templates")
STATIC_DIR = Path(__file__).resolve().parent / "static"
_ERROR_503_PATH = TEMPLATES_DIR / "errors" / "503.html"
_DEFAULT_HOST = "0.0.0.0"  # noqa: S104
_REQUEST_ID_HEADER = "x-request-id"


def _configure_logging(settings: Settings) -> None:
    """Configure logging with console and file output."""
    configure_logging(settings.app.log_level, log_file="web.log")


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


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage application lifecycle — initialize DB and storage."""
    settings = load_settings()

    if settings.monitor.connection_string:
        configure_azure_monitor(connection_string=settings.monitor.connection_string)
        logger.info("Azure Monitor OpenTelemetry configured")

    try:
        cosmos = await init_database(settings)
    except ConnectionError as exc:
        logger.error(str(exc))  # noqa: TRY400
        raise SystemExit(1) from None
    app.state.cosmos = cosmos
    app.state.settings = settings
    app.state.templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

    editions_repo = EditionRepository(cosmos.database)

    storage_components = await init_storage(settings, editions_repo)
    app.state.storage = storage_components.client

    memory_components = await init_memory(settings)
    app.state.memory_service = memory_components.service

    app.state.start_time = datetime.now(UTC)
    logger.info("Web running")

    yield

    logger.info("Web shutting down")
    await storage_components.client.close()
    await cosmos.close()
    logger.info("Web shutdown complete")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = load_settings()
    _configure_logging(settings)
    session_secret = settings.app.secret_key.strip()
    if not session_secret:
        if settings.app.is_development:
            session_secret = uuid.uuid4().hex
        else:
            msg = "APP_SECRET_KEY must be set in non-development environments"
            raise RuntimeError(msg)
    middleware = [
        Middleware(
            SessionMiddleware,  # ty: ignore[invalid-argument-type]
            secret_key=session_secret,
            same_site="lax",
            https_only=not settings.app.is_development,
        )
    ]
    app = FastAPI(
        title="Curate — Editorial Dashboard",
        lifespan=lifespan,
        middleware=middleware,
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

    @app.exception_handler(ServiceRequestError)
    async def _service_unreachable_handler(
        _request: Request, _exc: ServiceRequestError
    ) -> HTMLResponse:
        logger.warning("Backend service unreachable — is Docker running?")
        content = (
            _ERROR_503_PATH.read_text()
            if _ERROR_503_PATH.exists()
            else ("<h1>Service Unavailable</h1><p>Unable to reach the database.</p>")
        )
        return HTMLResponse(content=content, status_code=503)

    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    app.include_router(auth_router)
    app.include_router(dashboard_router)
    app.include_router(store_router)
    app.include_router(editions_router)
    app.include_router(feedback_router)
    app.include_router(events_router)
    app.include_router(agent_runs_router)
    app.include_router(status_router)
    app.include_router(settings_router)

    return app


def main() -> None:
    """Entry point for running the application."""
    settings = load_settings()
    _configure_logging(settings)

    logger.info("Web starting")

    if settings.app.is_development and not asyncio.run(check_emulators(settings)):
        return

    if settings.app.is_development:
        uvicorn.run(
            "curate_web.app:create_app",
            factory=True,
            host=_DEFAULT_HOST,
            port=8000,
            reload=True,
            reload_dirs=["packages"],
            log_config=None,
        )
    else:
        app = create_app()
        uvicorn.run(app, host=_DEFAULT_HOST, port=8000, log_config=None)


if __name__ == "__main__":
    main()
