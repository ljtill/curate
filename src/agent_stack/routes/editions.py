"""Editions routes — list, create, view detail, publish."""

from __future__ import annotations

import asyncio
import logging
from typing import Annotated

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from agent_stack.database.repositories.agent_runs import AgentRunRepository
from agent_stack.database.repositories.editions import EditionRepository
from agent_stack.database.repositories.links import LinkRepository
from agent_stack.services import editions as edition_svc

router = APIRouter(prefix="/editions", tags=["editions"])

logger = logging.getLogger(__name__)


@router.get("/", response_class=HTMLResponse)
async def list_editions(request: Request) -> HTMLResponse:
    """Render the editions list page."""
    templates = request.app.state.templates
    cosmos = request.app.state.cosmos
    repo = EditionRepository(cosmos.database)
    editions = await edition_svc.list_editions(repo)
    return templates.TemplateResponse(
        "editions.html",
        {"request": request, "editions": editions},
    )


@router.post("/")
async def create_edition(request: Request) -> RedirectResponse:
    """Create a new edition with an auto-generated issue number and title."""
    cosmos = request.app.state.cosmos
    repo = EditionRepository(cosmos.database)
    await edition_svc.create_edition(repo)
    logger.info("Edition created")
    return RedirectResponse("/editions/", status_code=303)


@router.get("/{edition_id}", response_class=HTMLResponse)
async def edition_detail(request: Request, edition_id: str) -> HTMLResponse:
    """Render the edition detail page."""
    templates = request.app.state.templates
    cosmos = request.app.state.cosmos
    editions_repo = EditionRepository(cosmos.database)
    links_repo = LinkRepository(cosmos.database)
    runs_repo = AgentRunRepository(cosmos.database)

    detail = await edition_svc.get_edition_detail(
        edition_id, editions_repo, links_repo, runs_repo
    )

    return templates.TemplateResponse(
        "edition_detail.html",
        {"request": request, "editing": False, **detail},
    )


@router.get("/{edition_id}/preview", response_class=HTMLResponse)
async def preview_edition(request: Request, edition_id: str) -> HTMLResponse:
    """Render the newsletter preview using the public template."""
    templates = request.app.state.templates
    cosmos = request.app.state.cosmos
    repo = EditionRepository(cosmos.database)
    edition = await edition_svc.get_edition(edition_id, repo)
    return templates.TemplateResponse(
        "newsletter/edition.html",
        {"request": request, "edition": edition},
    )


@router.post("/{edition_id}/publish")
async def publish_edition(request: Request, edition_id: str) -> RedirectResponse:
    """Trigger the publish pipeline for an edition via the orchestrator agent."""
    logger.info("Publish requested — edition=%s", edition_id)
    processor = request.app.state.processor
    if processor is None:
        logger.warning(
            "Publish skipped — pipeline unavailable because FOUNDRY_PROJECT_ENDPOINT "
            "is not configured (edition=%s)",
            edition_id,
        )
        return RedirectResponse(f"/editions/{edition_id}", status_code=303)

    orchestrator = processor.orchestrator
    task = asyncio.create_task(edition_svc.publish_edition(edition_id, orchestrator))
    if not hasattr(request.app.state, "background_tasks"):
        request.app.state.background_tasks = []
    request.app.state.background_tasks.append(task)
    return RedirectResponse(f"/editions/{edition_id}", status_code=303)


@router.post("/{edition_id}/delete")
async def delete_edition(request: Request, edition_id: str) -> RedirectResponse:
    """Soft-delete an edition and redirect to the editions list."""
    cosmos = request.app.state.cosmos
    repo = EditionRepository(cosmos.database)
    await edition_svc.delete_edition(edition_id, repo)
    logger.info("Edition deleted — edition=%s", edition_id)
    return RedirectResponse("/editions/", status_code=303)


@router.get("/{edition_id}/title/edit", response_class=HTMLResponse)
async def edit_title_form(request: Request, edition_id: str) -> HTMLResponse:
    """Return the inline title edit form partial."""
    templates = request.app.state.templates
    cosmos = request.app.state.cosmos
    repo = EditionRepository(cosmos.database)
    edition = await edition_svc.get_edition(edition_id, repo)
    return templates.TemplateResponse(
        "partials/edition_title.html",
        {"request": request, "edition": edition, "editing": True},
    )


@router.get("/{edition_id}/title/cancel", response_class=HTMLResponse)
async def cancel_title_edit(request: Request, edition_id: str) -> HTMLResponse:
    """Return the display-mode title partial (cancel editing)."""
    templates = request.app.state.templates
    cosmos = request.app.state.cosmos
    repo = EditionRepository(cosmos.database)
    edition = await edition_svc.get_edition(edition_id, repo)
    return templates.TemplateResponse(
        "partials/edition_title.html",
        {"request": request, "edition": edition, "editing": False},
    )


@router.post("/{edition_id}/title", response_class=HTMLResponse)
async def update_title(
    request: Request, edition_id: str, title: Annotated[str, Form()] = ""
) -> HTMLResponse:
    """Update the edition title and return the display partial."""
    templates = request.app.state.templates
    cosmos = request.app.state.cosmos
    repo = EditionRepository(cosmos.database)
    edition = await edition_svc.update_title(edition_id, title, repo)
    logger.info("Edition title updated — edition=%s", edition_id)
    return templates.TemplateResponse(
        "partials/edition_title.html",
        {"request": request, "edition": edition, "editing": False},
    )
