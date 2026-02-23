"""Authentication routes — login, callback, logout."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from curate_web.auth.msal_auth import MSALAuth
from curate_web.runtime import get_runtime

router = APIRouter(prefix="/auth", tags=["auth"])

logger = logging.getLogger(__name__)


@router.get("/login")
async def login(request: Request) -> RedirectResponse:
    """Redirect to Microsoft Entra ID login page."""
    settings = get_runtime(request).settings
    auth = MSALAuth(settings.entra)
    flow = auth.get_auth_flow()
    request.session["auth_flow"] = flow
    return RedirectResponse(flow["auth_uri"])


@router.get("/callback")
async def callback(request: Request) -> RedirectResponse:
    """Handle the OAuth callback from Entra ID."""
    settings = get_runtime(request).settings
    auth = MSALAuth(settings.entra)
    flow = request.session.pop("auth_flow", {})
    result = auth.complete_auth(flow, dict(request.query_params))
    if result:
        request.session["user"] = result.get("id_token_claims", {})
        logger.info("User logged in")
        return RedirectResponse("/")
    logger.warning("Auth callback failed")
    return RedirectResponse("/auth/login")


@router.get("/logout")
async def logout(request: Request) -> RedirectResponse:
    """Clear the session and redirect to the login page."""
    request.session.clear()
    logger.info("User logged out")
    return RedirectResponse("/auth/login")
