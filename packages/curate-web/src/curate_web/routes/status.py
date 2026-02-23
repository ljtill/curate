"""Status route — dependency health checks and operational statistics."""

from __future__ import annotations

import asyncio
import logging
import time

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from curate_web.auth.middleware import require_authenticated_user
from curate_web.services.health import StorageHealthConfig, check_all
from curate_web.services.status import collect_stats

router = APIRouter(tags=["status"], dependencies=[Depends(require_authenticated_user)])
logger = logging.getLogger(__name__)


@router.get("/status", response_class=HTMLResponse)
async def status(request: Request) -> HTMLResponse:
    """Render the status page with live health probe results and stats."""
    started_at = time.monotonic()
    cosmos = request.app.state.cosmos
    settings = request.app.state.settings
    storage = request.app.state.storage
    start_time = request.app.state.start_time

    health_coro = check_all(
        cosmos.database,
        cosmos_config=settings.cosmos,
        foundry_config=settings.foundry,
        storage_health=StorageHealthConfig(client=storage, config=settings.storage),
    )
    stats_coro = collect_stats(
        cosmos.database,
        environment=settings.app.env,
        start_time=start_time,
    )

    results, stats = await asyncio.gather(health_coro, stats_coro)
    unhealthy_count = sum(
        1
        for result in results
        if not (
            result.healthy
            if hasattr(result, "healthy")
            else bool(result.get("healthy", False))
        )
    )
    logger.info(
        "Status page loaded — checks=%d unhealthy=%d duration_ms=%.0f",
        len(results),
        unhealthy_count,
        (time.monotonic() - started_at) * 1000,
    )

    templates = request.app.state.templates
    return templates.TemplateResponse(
        "status.html",
        {
            "request": request,
            "checks": results,
            "info": stats,
        },
    )
