"""FastAPI application factory with lifespan events."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from agent_stack.config import load_settings
from agent_stack.database.client import CosmosClient
from agent_stack.routes.auth import router as auth_router
from agent_stack.routes.dashboard import router as dashboard_router
from agent_stack.routes.editions import router as editions_router
from agent_stack.routes.events import router as events_router
from agent_stack.routes.feedback import router as feedback_router
from agent_stack.routes.links import router as links_router

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
    logger.info("Application started")

    yield

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

    return app


def main() -> None:
    """Entry point for running the application."""
    logging.basicConfig(level=logging.INFO)
    app = create_app()
    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
