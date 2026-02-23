"""Links routes — submit and view links."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse

import curate_web.services.links as link_svc
from curate_common.database.repositories.agent_runs import AgentRunRepository
from curate_common.database.repositories.editions import EditionRepository
from curate_common.database.repositories.links import LinkRepository
from curate_web.auth.middleware import require_authenticated_user
from curate_web.services.agent_runs import group_runs_by_invocation

if TYPE_CHECKING:
    from curate_common.database.client import CosmosClient

router = APIRouter(
    prefix="/links",
    tags=["links"],
    dependencies=[Depends(require_authenticated_user)],
)

logger = logging.getLogger(__name__)


@router.get("/", response_class=HTMLResponse)
async def list_links(
    request: Request, edition_id: Annotated[str | None, Query()] = None
) -> HTMLResponse:
    """Render the links page with edition selector and filtered links."""
    started_at = time.monotonic()
    templates = request.app.state.templates
    cosmos = request.app.state.cosmos
    editions_repo = _get_editions_repo(cosmos)
    links_repo = LinkRepository(cosmos.database)
    runs_repo = AgentRunRepository(cosmos.database)

    editions = await editions_repo.list_unpublished()

    edition = None
    if editions:
        if edition_id:
            edition = next((e for e in editions if e.id == edition_id), None)
        if not edition:
            edition = editions[0]

    links = await links_repo.get_by_edition(edition.id) if edition else []

    runs = await runs_repo.get_by_triggers([link.id for link in links])
    runs_by_trigger: dict[str, list] = {}
    for run in runs:
        runs_by_trigger.setdefault(run.trigger_id, []).append(run)

    link_run_groups = {
        link.id: group_runs_by_invocation(runs_by_trigger.get(link.id, []))
        for link in links
    }

    logger.info(
        "Links page loaded — requested_edition=%s selected_edition=%s "
        "editions=%d links=%d run_lookups=%d duration_ms=%.0f",
        edition_id,
        edition.id if edition else None,
        len(editions),
        len(links),
        len(links),
        (time.monotonic() - started_at) * 1000,
    )

    return templates.TemplateResponse(
        "links.html",
        {
            "request": request,
            "links": links,
            "edition": edition,
            "editions": editions,
            "link_run_groups": link_run_groups,
        },
    )


@router.post("/")
async def submit_link(
    request: Request,
    url: Annotated[str, Form(...)],
    edition_id: Annotated[str, Form(...)],
) -> RedirectResponse:
    """Submit a new link for the selected edition."""
    cosmos = request.app.state.cosmos
    editions_repo = _get_editions_repo(cosmos)
    links_repo = LinkRepository(cosmos.database)

    link = await link_svc.submit_link(url, edition_id, links_repo, editions_repo)
    if not link:
        return RedirectResponse("/links/", status_code=303)
    logger.info(
        "Link submitted — link=%s edition=%s url=%s",
        link.id,
        link.edition_id,
        url,
    )
    return RedirectResponse(f"/links/?edition_id={link.edition_id}", status_code=303)


@router.post("/{link_id}/retry")
async def retry_link(request: Request, link_id: str) -> RedirectResponse:
    """Reset a failed link to submitted so it re-enters the pipeline."""
    cosmos = request.app.state.cosmos
    editions_repo = _get_editions_repo(cosmos)
    links_repo = LinkRepository(cosmos.database)

    edition = await editions_repo.get_active()
    if not edition:
        return RedirectResponse("/links/", status_code=303)

    success = await link_svc.retry_link(link_id, edition.id, links_repo)
    if not success:
        return RedirectResponse("/links/", status_code=303)
    logger.info("Link retried — link=%s edition=%s", link_id, edition.id)
    return RedirectResponse("/links/", status_code=303)


@router.post("/{link_id}/delete")
async def delete_link(
    request: Request,
    link_id: str,
    edition_id: Annotated[str, Form(...)],
) -> RedirectResponse:
    """Soft-delete a link and regenerate edition content if it was drafted."""
    cosmos = request.app.state.cosmos
    editions_repo = _get_editions_repo(cosmos)
    links_repo = LinkRepository(cosmos.database)

    result = await link_svc.delete_link(link_id, edition_id, links_repo, editions_repo)
    if result is None:
        return RedirectResponse("/links/", status_code=303)
    logger.info("Link deleted — link=%s edition=%s", link_id, edition_id)
    return RedirectResponse(f"/links/?edition_id={edition_id}", status_code=303)


def _get_editions_repo(cosmos: CosmosClient) -> EditionRepository:
    return EditionRepository(cosmos.database)
