"""Profile route — displays the authenticated user's identity."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from curate_web.auth.middleware import require_auth
from curate_web.runtime import get_runtime

router = APIRouter(tags=["profile"])


@router.get("/profile", response_class=HTMLResponse)
@require_auth
async def profile(request: Request) -> HTMLResponse:
    """Render the user profile page."""
    user = request.session.get("user", {})
    runtime = get_runtime(request)
    return runtime.templates.TemplateResponse(
        "profile.html",
        {"request": request, "user": user},
    )
