"""Store routes — global link library, submit, associate, delete."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

import curate_web.services.links as link_svc
from curate_common.database.repositories.editions import EditionRepository
from curate_common.database.repositories.links import LinkRepository
from curate_web.auth.middleware import require_authenticated_user
from curate_web.runtime import get_runtime

if TYPE_CHECKING:
    from curate_common.database.client import CosmosClient

router = APIRouter(
    prefix="/store",
    tags=["store"],
    dependencies=[Depends(require_authenticated_user)],
)

logger = logging.getLogger(__name__)


@router.get("/", response_class=HTMLResponse)
async def list_store(request: Request) -> HTMLResponse:
    """Render the global links store page."""
    started_at = time.monotonic()
    runtime = get_runtime(request)
    links_repo = LinkRepository(runtime.cosmos.database)

    links = await links_repo.list_all()

    logger.info(
        "Store page loaded — links=%d duration_ms=%.0f",
        len(links),
        (time.monotonic() - started_at) * 1000,
    )

    return runtime.templates.TemplateResponse(
        "store.html",
        {
            "request": request,
            "links": links,
        },
    )


@router.post("/")
async def submit_link(
    request: Request,
    url: Annotated[str, Form(...)],
) -> RedirectResponse:
    """Submit a new link to the global store."""
    runtime = get_runtime(request)
    links_repo = LinkRepository(runtime.cosmos.database)

    link = await link_svc.submit_link(url, links_repo)
    logger.info("Link submitted to store — link=%s url=%s", link.id, url)
    return RedirectResponse("/store/", status_code=303)


@router.post("/{link_id}/associate")
async def associate_link(
    request: Request,
    link_id: str,
    edition_id: Annotated[str, Form(...)],
    next: Annotated[str | None, Form()] = None,  # noqa: A002
) -> RedirectResponse:
    """Associate a store link with an edition."""
    runtime = get_runtime(request)
    links_repo = LinkRepository(runtime.cosmos.database)
    editions_repo = _get_editions_repo(runtime.cosmos)

    link = await link_svc.associate_link(link_id, edition_id, links_repo, editions_repo)
    if link:
        logger.info("Link associated — link=%s edition=%s", link_id, edition_id)
    redirect_url = next or "/store/"
    return RedirectResponse(redirect_url, status_code=303)


@router.post("/{link_id}/disassociate")
async def disassociate_link(
    request: Request,
    link_id: str,
    next: Annotated[str | None, Form()] = None,  # noqa: A002
) -> RedirectResponse:
    """Remove a link's association with its edition."""
    runtime = get_runtime(request)
    links_repo = LinkRepository(runtime.cosmos.database)
    editions_repo = _get_editions_repo(runtime.cosmos)

    link = await link_svc.disassociate_link(link_id, links_repo, editions_repo)
    if link:
        logger.info("Link disassociated — link=%s", link_id)
    redirect_url = next or "/store/"
    return RedirectResponse(redirect_url, status_code=303)


@router.post("/{link_id}/retry")
async def retry_link(request: Request, link_id: str) -> RedirectResponse:
    """Reset a failed link to submitted so it re-enters the pipeline."""
    runtime = get_runtime(request)
    links_repo = LinkRepository(runtime.cosmos.database)

    success = await link_svc.retry_link(link_id, links_repo)
    if success:
        logger.info("Link retried — link=%s", link_id)
    return RedirectResponse("/store/", status_code=303)


@router.post("/{link_id}/delete")
async def delete_link(
    request: Request,
    link_id: str,
) -> RedirectResponse:
    """Soft-delete a link from the store."""
    runtime = get_runtime(request)
    links_repo = LinkRepository(runtime.cosmos.database)
    editions_repo = _get_editions_repo(runtime.cosmos)

    await link_svc.delete_link(link_id, links_repo, editions_repo)
    logger.info("Link deleted — link=%s", link_id)
    return RedirectResponse("/store/", status_code=303)


def _get_editions_repo(cosmos: CosmosClient) -> EditionRepository:
    return EditionRepository(cosmos.database)
