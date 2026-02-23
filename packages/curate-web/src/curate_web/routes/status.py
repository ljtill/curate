"""Status route — dependency health checks and operational statistics."""

from __future__ import annotations

import asyncio
import logging
import time

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from curate_web.auth.middleware import require_authenticated_user
from curate_web.runtime import get_runtime
from curate_web.services.health import StorageHealthConfig, check_all
from curate_web.services.status import collect_stats

router = APIRouter(tags=["status"], dependencies=[Depends(require_authenticated_user)])
logger = logging.getLogger(__name__)


@router.get("/status", response_class=HTMLResponse)
async def status(request: Request) -> HTMLResponse:
    """Render the status page with live health probe results and stats."""
    started_at = time.monotonic()
    runtime = get_runtime(request)

    health_coro = check_all(
        runtime.cosmos.database,
        cosmos_config=runtime.settings.cosmos,
        foundry_config=runtime.settings.foundry,
        storage_health=StorageHealthConfig(
            client=runtime.storage,
            config=runtime.settings.storage,
        ),
    )
    stats_coro = collect_stats(
        runtime.cosmos.database,
        environment=runtime.settings.app.env,
        start_time=runtime.start_time,
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

    return runtime.templates.TemplateResponse(
        "status.html",
        {
            "request": request,
            "checks": results,
            "info": stats,
        },
    )
