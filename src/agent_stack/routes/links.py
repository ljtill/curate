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

    # Build a map of link_id -> pipeline invocation groups for display
    link_run_groups: dict[str, list[list]] = {}
    for link in links:
        runs = await runs_repo.get_by_trigger(link.id)
        link_run_groups[link.id] = _group_runs_by_invocation(runs)

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

    edition = await editions_repo.get(edition_id, edition_id)
    if not edition or edition.status == EditionStatus.PUBLISHED:
        return RedirectResponse("/links/", status_code=303)

    link = await links_repo.get(link_id, edition_id)
    if not link:
        return RedirectResponse(f"/links/?edition_id={edition_id}", status_code=303)

    await links_repo.soft_delete(link, edition_id)

    # Regenerate edition content if this link was already drafted into it
    if link_id in edition.link_ids:
        edition.link_ids.remove(link_id)
        edition.content = {}
        await editions_repo.update(edition, edition_id)

        # Reset remaining drafted links to REVIEWED so the change feed
        # re-triggers the Draft agent for each, rebuilding edition content.
        remaining = await links_repo.get_by_status(edition_id, LinkStatus.DRAFTED)
        for remaining_link in remaining:
            remaining_link.status = LinkStatus.REVIEWED
            await links_repo.update(remaining_link, edition_id)

    return RedirectResponse(f"/links/?edition_id={edition_id}", status_code=303)


def _get_editions_repo(cosmos: CosmosClient) -> EditionRepository:
    return EditionRepository(cosmos.database)


def _group_runs_by_invocation(runs: list) -> list[list]:
    """Group a flat list of agent runs into pipeline invocations.

    Each orchestrator run marks the start of a new invocation. Stages that
    follow belong to that group until the next orchestrator run appears.
    """
    if not runs:
        return []

    groups: list[list] = []
    for run in runs:
        if run.stage == "orchestrator" or not groups:
            groups.append([])
        groups[-1].append(run)
    return groups
