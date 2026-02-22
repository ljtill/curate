"""Settings routes — memory management and application configuration."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from agent_stack.auth.middleware import get_user

router = APIRouter(tags=["settings"])

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
    memory_service = request.app.state.memory_service
    templates = request.app.state.templates
    settings = getattr(request.app.state, "settings", None)

    memory_enabled = memory_service.enabled if memory_service else False
    store_name = memory_service.store_name if memory_service else "—"
    memory_disabled_by_config = bool(
        settings and settings.foundry.project_endpoint and not settings.memory.enabled
    )

    project_memories: list = []
    personal_memories: list = []

    if memory_service and memory_enabled:
        project_memories = await memory_service.list_memories("project-editorial")
        user_scope = _get_user_scope(request)
        if user_scope:
            personal_memories = await memory_service.list_memories(user_scope)

    return templates.TemplateResponse(
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
        },
    )


@router.post("/settings/memory/toggle", response_class=HTMLResponse)
async def toggle_memory(
    request: Request,
    enabled: Annotated[str, Form(...)],
) -> HTMLResponse:
    """Toggle memory on/off globally."""
    memory_service = request.app.state.memory_service
    if memory_service:
        memory_service.set_enabled(enabled=enabled == "true")
        logger.info("Memory toggled to %s", enabled)

    templates = request.app.state.templates
    is_enabled = memory_service.enabled if memory_service else False
    return templates.TemplateResponse(
        "partials/memory_toggle.html",
        {"request": request, "memory_enabled": is_enabled},
    )


@router.get("/settings/memory/project", response_class=HTMLResponse)
async def list_project_memories(request: Request) -> HTMLResponse:
    """List project-wide memories (HTMX partial)."""
    memory_service = request.app.state.memory_service
    templates = request.app.state.templates
    memories: list = []
    if memory_service and memory_service.enabled:
        memories = await memory_service.list_memories("project-editorial")
    return templates.TemplateResponse(
        "partials/memory_list.html",
        {"request": request, "memories": memories, "scope": "project"},
    )


@router.delete("/settings/memory/project", response_class=HTMLResponse)
async def clear_project_memories(request: Request) -> HTMLResponse:
    """Clear all project-wide memories."""
    memory_service = request.app.state.memory_service
    if memory_service:
        await memory_service.clear_memories("project-editorial")
        logger.info("Project-wide memories cleared")

    templates = request.app.state.templates
    return templates.TemplateResponse(
        "partials/memory_list.html",
        {"request": request, "memories": [], "scope": "project"},
    )


@router.get("/settings/memory/personal", response_class=HTMLResponse)
async def list_personal_memories(request: Request) -> HTMLResponse:
    """List the current user's personal memories (HTMX partial)."""
    memory_service = request.app.state.memory_service
    templates = request.app.state.templates
    memories: list = []
    user_scope = _get_user_scope(request)
    if memory_service and memory_service.enabled and user_scope:
        memories = await memory_service.list_memories(user_scope)
    return templates.TemplateResponse(
        "partials/memory_list.html",
        {"request": request, "memories": memories, "scope": "personal"},
    )


@router.delete("/settings/memory/personal", response_class=HTMLResponse)
async def clear_personal_memories(request: Request) -> HTMLResponse:
    """Clear the current user's personal memories."""
    memory_service = request.app.state.memory_service
    user_scope = _get_user_scope(request)
    if memory_service and user_scope:
        await memory_service.clear_memories(user_scope)
        logger.info("Personal memories cleared for scope=%s", user_scope)

    templates = request.app.state.templates
    return templates.TemplateResponse(
        "partials/memory_list.html",
        {"request": request, "memories": [], "scope": "personal"},
    )
