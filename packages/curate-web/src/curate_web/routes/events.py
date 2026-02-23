"""SSE events route — real-time status updates."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, Request

from curate_web.auth.middleware import require_authenticated_user
from curate_web.events import EventManager

if TYPE_CHECKING:
    from sse_starlette.sse import EventSourceResponse

router = APIRouter(tags=["events"], dependencies=[Depends(require_authenticated_user)])


@router.get("/events")
async def events(request: Request) -> EventSourceResponse:
    """SSE endpoint for real-time pipeline status updates."""
    manager = EventManager.get_instance()
    return manager.create_response(request)
