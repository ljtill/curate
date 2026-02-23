"""Tests for the profile route."""

from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from curate_web.routes.profile import profile

_UNAUTHORIZED_STATUS = 401


def _make_request(*, user: dict | None = None) -> MagicMock:
    """Create a mock request with app state."""
    request = MagicMock()
    request.app.state.templates = MagicMock()
    if user is not None:
        request.session = {"user": user}
    else:
        request.session = {}
    return request


@pytest.mark.unit
class TestProfilePage:
    """Test the profile page rendering."""

    async def test_renders_with_authenticated_user(self) -> None:
        """Verify profile page renders with user claims."""
        user = {
            "name": "Test User",
            "preferred_username": "test@example.com",
            "oid": "abc-123",
        }
        request = _make_request(user=user)
        await profile(request)
        request.app.state.templates.TemplateResponse.assert_called_once()
        call_args = request.app.state.templates.TemplateResponse.call_args
        assert call_args[0][0] == "profile.html"
        assert call_args[0][1]["user"] == user

    async def test_rejects_unauthenticated_user(self) -> None:
        """Verify profile page returns 401 when not authenticated."""
        request = _make_request()
        with pytest.raises(HTTPException) as exc_info:
            await profile(request)
        assert exc_info.value.status_code == _UNAUTHORIZED_STATUS

    async def test_renders_with_local_dev_user(self) -> None:
        """Verify profile page works with the local dev mock user."""
        user = {
            "name": "Local Developer",
            "preferred_username": "local@localhost",
            "oid": "00000000-0000-0000-0000-000000000000",
        }
        request = _make_request(user=user)
        await profile(request)
        call_args = request.app.state.templates.TemplateResponse.call_args
        assert call_args[0][1]["user"]["oid"] == "00000000-0000-0000-0000-000000000000"
