"""Profile route — displays the authenticated user's identity."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from curate_web.auth.middleware import require_auth

router = APIRouter(tags=["profile"])


@router.get("/profile", response_class=HTMLResponse)
@require_auth
async def profile(request: Request) -> HTMLResponse:
    """Render the user profile page."""
    user = request.session.get("user", {})
    templates = request.app.state.templates
    return templates.TemplateResponse(
        "profile.html",
        {"request": request, "user": user},
    )
