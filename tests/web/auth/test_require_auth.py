"""Tests for the require_auth decorator."""

from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from curate_web.auth.middleware import require_auth, require_authenticated_user

_EXPECTED_UNAUTHORIZED_STATUS = 401


@require_auth
async def protected_view(_request: MagicMock) -> None:
    """Handle protected view."""
    return {"user": "authenticated"}


async def test_require_auth_raises_401_when_no_session() -> None:
    """Verify require auth raises 401 when no session."""
    request = MagicMock()
    del request.session
    with pytest.raises(HTTPException) as exc_info:
        await protected_view(request)
    assert exc_info.value.status_code == _EXPECTED_UNAUTHORIZED_STATUS


async def test_require_auth_raises_401_when_no_user() -> None:
    """Verify require auth raises 401 when no user."""
    request = MagicMock()
    request.session = {}
    with pytest.raises(HTTPException) as exc_info:
        await protected_view(request)
    assert exc_info.value.status_code == _EXPECTED_UNAUTHORIZED_STATUS


async def test_require_auth_passes_when_user_present() -> None:
    """Verify require auth passes when user present."""
    request = MagicMock()
    request.session = {"user": {"name": "Test User"}}
    result = await protected_view(request)
    assert result == {"user": "authenticated"}


def test_require_authenticated_user_returns_user() -> None:
    """Verify dependency helper returns user when authenticated."""
    request = MagicMock()
    user = {"name": "Test User"}
    request.session = {"user": user}
    assert require_authenticated_user(request) == user


def test_require_authenticated_user_raises_when_missing() -> None:
    """Verify dependency helper raises 401 when unauthenticated."""
    request = MagicMock()
    request.session = {}
    with pytest.raises(HTTPException) as exc_info:
        require_authenticated_user(request)
    assert exc_info.value.status_code == _EXPECTED_UNAUTHORIZED_STATUS


def test_require_authenticated_user_bypasses_auth_in_development() -> None:
    """Verify local development bypasses Entra auth."""
    request = MagicMock()
    request.session = {}
    request.app.state.settings.app.is_development = True

    user = require_authenticated_user(request)

    assert user["name"] == "Local Developer"
    assert request.session["user"] == user
