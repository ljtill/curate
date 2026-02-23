"""Tests for authentication routes — login, callback, logout."""

from unittest.mock import MagicMock, patch

from curate_web.routes.auth import callback, login, logout
from tests.web.routes.runtime_helpers import make_runtime

_EXPECTED_REDIRECT_STATUS = 307


class TestAuthRoutes:
    """Test the Auth Routes."""

    async def test_login_redirects_to_entra(self) -> None:
        """Verify login redirects to entra."""
        request = MagicMock()
        request.app.state.settings.entra = MagicMock()
        request.app.state.runtime = make_runtime(settings=request.app.state.settings)
        request.session = {}

        with patch("curate_web.routes.auth.MSALAuth") as mock_auth_cls:
            mock_auth_cls.return_value.get_auth_flow.return_value = {
                "auth_uri": "https://login.microsoftonline.com/auth"
            }

            response = await login(request)

            assert response.status_code == _EXPECTED_REDIRECT_STATUS
            assert "auth_flow" in request.session

    async def test_callback_success_sets_session(self) -> None:
        """Verify callback success sets session."""
        request = MagicMock()
        request.app.state.settings.entra = MagicMock()
        request.app.state.runtime = make_runtime(settings=request.app.state.settings)
        request.session = {"auth_flow": {"state": "test"}}
        request.query_params = {"code": "auth-code"}

        with patch("curate_web.routes.auth.MSALAuth") as mock_auth_cls:
            mock_auth_cls.return_value.complete_auth.return_value = {
                "id_token_claims": {
                    "name": "Test User",
                    "preferred_username": "test@example.com",
                }
            }

            response = await callback(request)

            assert response.status_code == _EXPECTED_REDIRECT_STATUS
            assert response.headers["location"] == "/"
            assert "user" in request.session

    async def test_callback_failure_redirects_to_login(self) -> None:
        """Verify callback failure redirects to login."""
        request = MagicMock()
        request.app.state.settings.entra = MagicMock()
        request.app.state.runtime = make_runtime(settings=request.app.state.settings)
        request.session = {"auth_flow": {}}
        request.query_params = {}

        with patch("curate_web.routes.auth.MSALAuth") as mock_auth_cls:
            mock_auth_cls.return_value.complete_auth.return_value = None

            response = await callback(request)

            assert response.status_code == _EXPECTED_REDIRECT_STATUS
            assert response.headers["location"] == "/auth/login"

    async def test_logout_clears_session(self) -> None:
        """Verify logout clears session."""
        session = {"user": {"name": "Test"}}
        request = MagicMock()
        request.session = session

        response = await logout(request)

        assert response.status_code == _EXPECTED_REDIRECT_STATUS
        assert response.headers["location"] == "/auth/login"
        assert len(session) == 0
