"""SSE events route — real-time status updates."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Request

from agent_stack.events import EventManager

if TYPE_CHECKING:
    from sse_starlette.sse import EventSourceResponse

router = APIRouter(tags=["events"])


@router.get("/events")
async def events(request: Request) -> EventSourceResponse:
    """SSE endpoint for real-time pipeline status updates."""
    manager = EventManager.get_instance()
    return manager.create_response(request)
