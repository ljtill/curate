"""Links routes — submit and view links."""

from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from agent_stack.database.repositories.agent_runs import AgentRunRepository
from agent_stack.database.repositories.links import LinkRepository
from agent_stack.models.link import Link, LinkStatus

router = APIRouter(prefix="/links", tags=["links"])


@router.get("/", response_class=HTMLResponse)
async def list_links(request: Request):
    """Render the links page with all links for the active edition."""
    templates = request.app.state.templates
    cosmos = request.app.state.cosmos
    editions_repo = _get_editions_repo(cosmos)
    links_repo = LinkRepository(cosmos.database)
    runs_repo = AgentRunRepository(cosmos.database)

    edition = await editions_repo.get_active()
    links = await links_repo.get_by_edition(edition.id) if edition else []

    # Build a map of link_id -> agent runs for display
    link_runs: dict[str, list] = {}
    for link in links:
        link_runs[link.id] = await runs_repo.get_by_trigger(link.id)

    return templates.TemplateResponse(
        "links.html",
        {"request": request, "links": links, "edition": edition, "link_runs": link_runs},
    )


@router.post("/")
async def submit_link(request: Request, url: str = Form(...)):
    """Submit a new link for the active edition."""
    cosmos = request.app.state.cosmos
    editions_repo = _get_editions_repo(cosmos)
    links_repo = LinkRepository(cosmos.database)

    edition = await editions_repo.get_active()
    if not edition:
        return RedirectResponse("/links/", status_code=303)

    link = Link(url=url, edition_id=edition.id)
    await links_repo.create(link)
    return RedirectResponse("/links/", status_code=303)


@router.post("/{link_id}/retry")
async def retry_link(request: Request, link_id: str):
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


def _get_editions_repo(cosmos):
    from agent_stack.database.repositories.editions import EditionRepository

    return EditionRepository(cosmos.database)
