"""Editions routes — list, create, view detail, publish."""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse

import curate_web.services.editions as edition_svc
import curate_web.services.revisions as revision_svc
from curate_common.database.repositories.agent_runs import AgentRunRepository
from curate_common.database.repositories.editions import EditionRepository
from curate_common.database.repositories.feedback import FeedbackRepository
from curate_common.database.repositories.links import LinkRepository
from curate_common.database.repositories.revisions import RevisionRepository
from curate_web.auth.middleware import require_authenticated_user
from curate_web.runtime import get_runtime

router = APIRouter(
    prefix="/editions",
    tags=["editions"],
    dependencies=[Depends(require_authenticated_user)],
)

logger = logging.getLogger(__name__)


@router.get("/", response_class=HTMLResponse)
async def list_editions(_request: Request) -> RedirectResponse:
    """Redirect editions list to dashboard."""
    return RedirectResponse("/", status_code=303)


@router.post("/")
async def create_edition(request: Request) -> RedirectResponse:
    """Create a new edition with an auto-generated issue number and title."""
    runtime = get_runtime(request)
    repo = EditionRepository(runtime.cosmos.database)
    await edition_svc.create_edition(repo)
    logger.info("Edition created")
    return RedirectResponse("/editions/", status_code=303)


@router.get("/{edition_id}", response_class=HTMLResponse)
async def edition_detail(request: Request, edition_id: str) -> HTMLResponse:
    """Render the edition workspace page."""
    runtime = get_runtime(request)
    editions_repo = EditionRepository(runtime.cosmos.database)
    links_repo = LinkRepository(runtime.cosmos.database)
    runs_repo = AgentRunRepository(runtime.cosmos.database)
    feedback_repo = FeedbackRepository(runtime.cosmos.database)
    revisions_repo = RevisionRepository(runtime.cosmos.database)

    data = await edition_svc.get_workspace_data(
        edition_id, editions_repo, links_repo, runs_repo, feedback_repo, revisions_repo
    )

    return runtime.templates.TemplateResponse(
        "workspace.html",
        {"request": request, **data},
    )


@router.get("/{edition_id}/preview", response_class=HTMLResponse)
async def preview_edition(request: Request, edition_id: str) -> HTMLResponse:
    """Render the newsletter preview using the public template."""
    runtime = get_runtime(request)
    repo = EditionRepository(runtime.cosmos.database)
    edition = await edition_svc.get_edition(edition_id, repo)
    return runtime.templates.TemplateResponse(
        "newsletter/edition.html",
        {"request": request, "edition": edition},
    )


@router.post("/{edition_id}/publish")
async def publish_edition(request: Request, edition_id: str) -> RedirectResponse:
    """Request publish for an edition via Service Bus."""
    logger.info("Publish requested — edition=%s", edition_id)
    event_publisher = get_runtime(request).event_publisher
    if event_publisher is None:
        logger.warning(
            "Publish skipped — event publisher unavailable (edition=%s)",
            edition_id,
        )
        return RedirectResponse(f"/editions/{edition_id}", status_code=303)

    task = asyncio.create_task(edition_svc.publish_edition(edition_id, event_publisher))
    if not hasattr(request.app.state, "background_tasks"):
        request.app.state.background_tasks = []
    request.app.state.background_tasks.append(task)
    return RedirectResponse(f"/editions/{edition_id}", status_code=303)


@router.post("/{edition_id}/delete")
async def delete_edition(request: Request, edition_id: str) -> RedirectResponse:
    """Soft-delete an edition and redirect to the editions list."""
    runtime = get_runtime(request)
    repo = EditionRepository(runtime.cosmos.database)
    await edition_svc.delete_edition(edition_id, repo)
    logger.info("Edition deleted — edition=%s", edition_id)
    return RedirectResponse("/editions/", status_code=303)


@router.post("/{edition_id}/revert/{revision_id}")
async def revert_edition(
    request: Request, edition_id: str, revision_id: str
) -> RedirectResponse:
    """Revert edition content to a previous revision (Git-style)."""
    runtime = get_runtime(request)
    editions_repo = EditionRepository(runtime.cosmos.database)
    revisions_repo = RevisionRepository(runtime.cosmos.database)
    await revision_svc.revert_to_revision(
        revision_id, edition_id, editions_repo, revisions_repo
    )
    logger.info("Edition reverted — edition=%s revision=%s", edition_id, revision_id)
    return RedirectResponse(f"/editions/{edition_id}", status_code=303)
