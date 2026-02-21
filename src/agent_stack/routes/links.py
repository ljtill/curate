"""Links routes — submit and view links."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from agent_stack.database.repositories.agent_runs import AgentRunRepository
from agent_stack.database.repositories.editions import EditionRepository
from agent_stack.database.repositories.links import LinkRepository
from agent_stack.models.edition import EditionStatus
from agent_stack.models.link import Link, LinkStatus

if TYPE_CHECKING:
    from agent_stack.database.client import CosmosClient

router = APIRouter(prefix="/links", tags=["links"])


@router.get("/", response_class=HTMLResponse)
async def list_links(
    request: Request, edition_id: Annotated[str | None, Query()] = None
) -> HTMLResponse:
    """Render the links page with edition selector and filtered links."""
    templates = request.app.state.templates
    cosmos = request.app.state.cosmos
    editions_repo = _get_editions_repo(cosmos)
    links_repo = LinkRepository(cosmos.database)
    runs_repo = AgentRunRepository(cosmos.database)

    editions = await editions_repo.list_unpublished()

    # Resolve selected edition: use query param if valid, else default to first
    edition = None
    if editions:
        if edition_id:
            edition = next((e for e in editions if e.id == edition_id), None)
        if not edition:
            edition = editions[0]

    links = await links_repo.get_by_edition(edition.id) if edition else []

    # Build a map of link_id -> agent runs for display
    link_runs: dict[str, list] = {}
    for link in links:
        link_runs[link.id] = await runs_repo.get_by_trigger(link.id)

    return templates.TemplateResponse(
        "links.html",
        {
            "request": request,
            "links": links,
            "edition": edition,
            "editions": editions,
            "link_runs": link_runs,
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

    edition = await editions_repo.get(edition_id, edition_id)
    if not edition or edition.status == EditionStatus.PUBLISHED:
        return RedirectResponse("/links/", status_code=303)

    link = Link(url=url, edition_id=edition.id)
    await links_repo.create(link)
    return RedirectResponse(f"/links/?edition_id={edition.id}", status_code=303)


@router.post("/{link_id}/retry")
async def retry_link(request: Request, link_id: str) -> RedirectResponse:
    """Reset a failed link to submitted so it re-enters the pipeline."""
    cosmos = request.app.state.cosmos
    editions_repo = _get_editions_repo(cosmos)
    links_repo = LinkRepository(cosmos.database)

    edition = await editions_repo.get_active()
    if not edition:
        return RedirectResponse("/links/", status_code=303)

    link = await links_repo.get(link_id, edition.id)
    if not link or link.status != LinkStatus.FAILED:
        return RedirectResponse("/links/", status_code=303)

    link.status = LinkStatus.SUBMITTED
    link.title = None
    link.content = None
    await links_repo.update(link, edition.id)
    return RedirectResponse("/links/", status_code=303)


def _get_editions_repo(cosmos: CosmosClient) -> EditionRepository:
    return EditionRepository(cosmos.database)
