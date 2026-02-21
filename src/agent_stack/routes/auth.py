"""Authentication routes — login, callback, logout."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from agent_stack.auth.msal_auth import MSALAuth

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/login")
async def login(request: Request) -> RedirectResponse:
    """Redirect to Microsoft Entra ID login page."""
    settings = request.app.state.settings
    auth = MSALAuth(settings.entra)
    flow = auth.get_auth_flow()
    request.session["auth_flow"] = flow
    return RedirectResponse(flow["auth_uri"])


@router.get("/callback")
async def callback(request: Request) -> RedirectResponse:
    """Handle the OAuth callback from Entra ID."""
    settings = request.app.state.settings
    auth = MSALAuth(settings.entra)
    flow = request.session.pop("auth_flow", {})
    result = auth.complete_auth(flow, dict(request.query_params))
    if result:
        request.session["user"] = result.get("id_token_claims", {})
        return RedirectResponse("/")
    return RedirectResponse("/auth/login")


@router.get("/logout")
async def logout(request: Request) -> RedirectResponse:
    """Clear the session and redirect to the login page."""
    request.session.clear()
    return RedirectResponse("/auth/login")
