"""Settings routes — memory management and application configuration."""

from __future__ import annotations

import logging
import time
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse

from curate_web.auth.middleware import get_user, require_authenticated_user
from curate_web.dependencies import get_agent_run_repository
from curate_web.runtime import get_runtime
from curate_web.services.health import StorageHealthConfig, check_all
from curate_web.services.status import AppInfo, TokenUsage, _format_uptime

router = APIRouter(
    tags=["settings"], dependencies=[Depends(require_authenticated_user)]
)

logger = logging.getLogger(__name__)


def _get_user_scope(request: Request) -> str | None:
    """Derive a per-user memory scope from the Microsoft Entra ID claims."""
    user = get_user(request)
    if not user:
        return None
    oid = user.get("oid", "")
    return f"user-{oid}" if oid else None


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request) -> HTMLResponse:
    """Render the settings page with memory status and management controls."""
    runtime = get_runtime(request)
    memory_service = runtime.memory_service
    settings = runtime.settings

    memory_enabled = memory_service.enabled if memory_service else False
    store_name = memory_service.store_name if memory_service else "—"
    memory_disabled_by_config = bool(
        settings.foundry.project_endpoint and not settings.memory.enabled
    )

    project_memories: list = []
    personal_memories: list = []

    if memory_service and memory_enabled:
        project_memories = await memory_service.list_memories("project-editorial")
        user_scope = _get_user_scope(request)
        if user_scope:
            personal_memories = await memory_service.list_memories(user_scope)

    # Token usage, health checks, and app info
    import platform  # noqa: PLC0415
    import sys  # noqa: PLC0415

    from curate_common import __version__  # noqa: PLC0415

    runs_repo = get_agent_run_repository(runtime)
    token_totals = await runs_repo.aggregate_token_usage()
    token_usage = TokenUsage(
        input_tokens=token_totals["input_tokens"],
        output_tokens=token_totals["output_tokens"],
        total_tokens=token_totals["total_tokens"],
    )

    started_at = time.monotonic()
    health_checks = await check_all(
        runtime.cosmos.database,
        cosmos_config=settings.cosmos,
        foundry_config=settings.foundry,
        storage_health=StorageHealthConfig(
            client=runtime.storage,
            config=settings.storage,
        ),
        servicebus_config=settings.servicebus,
        monitor_config=settings.monitor,
    )
    logger.debug(
        "Settings health checks duration_ms=%.0f",
        (time.monotonic() - started_at) * 1000,
    )

    app_info = AppInfo(
        version=__version__,
        environment=settings.app.env,
        python_version=f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        platform=platform.machine(),
        uptime=_format_uptime(runtime.start_time),
    )

    return runtime.templates.TemplateResponse(
        "settings.html",
        {
            "request": request,
            "memory_enabled": memory_enabled,
            "memory_configured": memory_service is not None,
            "memory_disabled_by_config": memory_disabled_by_config,
            "store_name": store_name,
            "project_memories": project_memories,
            "personal_memories": personal_memories,
            "project_memory_count": len(project_memories),
            "personal_memory_count": len(personal_memories),
            "checks": health_checks,
            "app_info": app_info,
            "token_usage": token_usage,
        },
    )


@router.post("/settings/memory/toggle", response_class=HTMLResponse)
async def toggle_memory(
    request: Request,
    enabled: Annotated[str, Form(...)],
) -> HTMLResponse:
    """Toggle memory on/off globally."""
    runtime = get_runtime(request)
    memory_service = runtime.memory_service
    if memory_service:
        memory_service.set_enabled(enabled=enabled == "true")
        logger.info("Memory toggled to %s", enabled)

    is_enabled = memory_service.enabled if memory_service else False
    return runtime.templates.TemplateResponse(
        "partials/memory_toggle.html",
        {"request": request, "memory_enabled": is_enabled},
    )


@router.get("/settings/memory/project", response_class=HTMLResponse)
async def list_project_memories(request: Request) -> HTMLResponse:
    """List project-wide memories (HTMX partial)."""
    runtime = get_runtime(request)
    memory_service = runtime.memory_service
    memories: list = []
    if memory_service and memory_service.enabled:
        memories = await memory_service.list_memories("project-editorial")
    return runtime.templates.TemplateResponse(
        "partials/memory_list.html",
        {"request": request, "memories": memories, "scope": "project"},
    )


@router.delete("/settings/memory/project", response_class=HTMLResponse)
async def clear_project_memories(request: Request) -> HTMLResponse:
    """Clear all project-wide memories."""
    runtime = get_runtime(request)
    memory_service = runtime.memory_service
    if memory_service:
        await memory_service.clear_memories("project-editorial")
        logger.info("Project-wide memories cleared")

    return runtime.templates.TemplateResponse(
        "partials/memory_list.html",
        {"request": request, "memories": [], "scope": "project"},
    )


@router.get("/settings/memory/personal", response_class=HTMLResponse)
async def list_personal_memories(request: Request) -> HTMLResponse:
    """List the current user's personal memories (HTMX partial)."""
    runtime = get_runtime(request)
    memory_service = runtime.memory_service
    memories: list = []
    user_scope = _get_user_scope(request)
    if memory_service and memory_service.enabled and user_scope:
        memories = await memory_service.list_memories(user_scope)
    return runtime.templates.TemplateResponse(
        "partials/memory_list.html",
        {"request": request, "memories": memories, "scope": "personal"},
    )


@router.delete("/settings/memory/personal", response_class=HTMLResponse)
async def clear_personal_memories(request: Request) -> HTMLResponse:
    """Clear the current user's personal memories."""
    runtime = get_runtime(request)
    memory_service = runtime.memory_service
    user_scope = _get_user_scope(request)
    if memory_service and user_scope:
        await memory_service.clear_memories(user_scope)
        logger.info("Personal memories cleared for scope=%s", user_scope)

    return runtime.templates.TemplateResponse(
        "partials/memory_list.html",
        {"request": request, "memories": [], "scope": "personal"},
    )
