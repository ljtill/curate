"""Tests for the authentication middleware."""

from unittest.mock import MagicMock

from curate_web.auth.middleware import get_user


def test_get_user_returns_none_without_session() -> None:
    """Verify get user returns none without session."""
    request = MagicMock()
    del request.session
    assert get_user(request) is None


def test_get_user_returns_none_for_empty_session() -> None:
    """Verify get user returns none for empty session."""
    request = MagicMock()
    request.session = {}
    assert get_user(request) is None


def test_get_user_returns_user_from_session() -> None:
    """Verify get user returns user from session."""
    request = MagicMock()
    request.session = {"user": {"name": "Test User"}}
    user = get_user(request)
    assert user == {"name": "Test User"}
