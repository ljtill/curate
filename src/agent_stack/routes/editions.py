"""Editions routes — list, create, view detail, publish."""

from __future__ import annotations

import asyncio
from typing import Annotated

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from agent_stack.database.repositories.agent_runs import AgentRunRepository
from agent_stack.database.repositories.editions import EditionRepository
from agent_stack.database.repositories.links import LinkRepository
from agent_stack.models.edition import Edition

router = APIRouter(prefix="/editions", tags=["editions"])


@router.get("/", response_class=HTMLResponse)
async def list_editions(request: Request) -> HTMLResponse:
    """Render the editions list page."""
    templates = request.app.state.templates
    cosmos = request.app.state.cosmos
    repo = EditionRepository(cosmos.database)
    editions = await repo.list_all()
    return templates.TemplateResponse(
        "editions.html",
        {"request": request, "editions": editions},
    )


@router.post("/")
async def create_edition(
    request: Request, title: Annotated[str, Form()] = ""
) -> RedirectResponse:
    """Create a new edition."""
    cosmos = request.app.state.cosmos
    repo = EditionRepository(cosmos.database)
    edition = Edition(content={"title": title.strip(), "sections": []})
    await repo.create(edition)
    return RedirectResponse("/editions/", status_code=303)


@router.get("/{edition_id}", response_class=HTMLResponse)
async def edition_detail(request: Request, edition_id: str) -> HTMLResponse:
    """Render the edition detail page."""
    templates = request.app.state.templates
    cosmos = request.app.state.cosmos
    editions_repo = EditionRepository(cosmos.database)
    links_repo = LinkRepository(cosmos.database)
    runs_repo = AgentRunRepository(cosmos.database)

    edition = await editions_repo.get(edition_id, edition_id)
    links = await links_repo.get_by_edition(edition_id) if edition else []

    # Gather all agent runs for this edition's links and feedback
    trigger_ids = [link.id for link in links]
    agent_runs = await runs_repo.get_by_triggers(trigger_ids) if trigger_ids else []
    links_by_id = {link.id: link for link in links}

    return templates.TemplateResponse(
        "edition_detail.html",
        {
            "request": request,
            "edition": edition,
            "links": links,
            "editing": False,
            "agent_runs": agent_runs,
            "links_by_id": links_by_id,
        },
    )


@router.get("/{edition_id}/preview", response_class=HTMLResponse)
async def preview_edition(request: Request, edition_id: str) -> HTMLResponse:
    """Render the newsletter preview using the public template."""
    templates = request.app.state.templates
    cosmos = request.app.state.cosmos
    repo = EditionRepository(cosmos.database)
    edition = await repo.get(edition_id, edition_id)
    return templates.TemplateResponse(
        "newsletter/edition.html",
        {"request": request, "edition": edition},
    )


@router.post("/{edition_id}/publish")
async def publish_edition(request: Request, edition_id: str) -> RedirectResponse:
    """Trigger the publish pipeline for an edition via the orchestrator agent."""
    orchestrator = request.app.state.processor.orchestrator
    task = asyncio.create_task(orchestrator.handle_publish(edition_id))
    request.app.state.setdefault("_background_tasks", []).append(task)
    return RedirectResponse(f"/editions/{edition_id}", status_code=303)


@router.post("/{edition_id}/delete")
async def delete_edition(request: Request, edition_id: str) -> RedirectResponse:
    """Soft-delete an edition and redirect to the editions list."""
    cosmos = request.app.state.cosmos
    repo = EditionRepository(cosmos.database)
    edition = await repo.get(edition_id, edition_id)
    if edition:
        await repo.soft_delete(edition, edition_id)
    return RedirectResponse("/editions/", status_code=303)


@router.get("/{edition_id}/title/edit", response_class=HTMLResponse)
async def edit_title_form(request: Request, edition_id: str) -> HTMLResponse:
    """Return the inline title edit form partial."""
    templates = request.app.state.templates
    cosmos = request.app.state.cosmos
    repo = EditionRepository(cosmos.database)
    edition = await repo.get(edition_id, edition_id)
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
    edition = await repo.get(edition_id, edition_id)
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
    edition = await repo.get(edition_id, edition_id)
    if edition:
        edition.content["title"] = title.strip()
        await repo.update(edition, edition_id)
    return templates.TemplateResponse(
        "partials/edition_title.html",
        {"request": request, "edition": edition, "editing": False},
    )
