"""Tests for MSALAuth authorization flow."""

from unittest.mock import MagicMock, patch

from agent_stack.auth.msal_auth import MSALAuth
from agent_stack.config import EntraConfig


@patch("agent_stack.auth.msal_auth.msal.ConfidentialClientApplication")
def test_get_auth_flow_returns_flow_dict(mock_msal_class: MagicMock) -> None:
    """Verify get auth flow returns flow dict."""
    mock_app = MagicMock()
    flow = {"auth_uri": "https://login.example.com/authorize", "state": "abc"}
    mock_app.initiate_auth_code_flow.return_value = flow
    mock_msal_class.return_value = mock_app

    config = EntraConfig.__new__(EntraConfig)
    object.__setattr__(config, "tenant_id", "tenant-1")
    object.__setattr__(config, "client_id", "client-1")
    object.__setattr__(config, "client_secret", "secret")
    object.__setattr__(config, "redirect_uri", "http://localhost/callback")

    auth = MSALAuth(config)
    result = auth.get_auth_flow()

    assert result == flow


@patch("agent_stack.auth.msal_auth.msal.ConfidentialClientApplication")
def test_complete_auth_returns_none_on_error(mock_msal_class: MagicMock) -> None:
    """Verify complete auth returns none on error."""
    mock_app = MagicMock()
    mock_app.acquire_token_by_auth_code_flow.return_value = {"error": "invalid_grant"}
    mock_msal_class.return_value = mock_app

    config = EntraConfig.__new__(EntraConfig)
    object.__setattr__(config, "tenant_id", "tenant-1")
    object.__setattr__(config, "client_id", "client-1")
    object.__setattr__(config, "client_secret", "secret")
    object.__setattr__(config, "redirect_uri", "http://localhost/callback")

    auth = MSALAuth(config)
    result = auth.complete_auth({}, {"code": "abc"})

    assert result is None


@patch("agent_stack.auth.msal_auth.msal.ConfidentialClientApplication")
def test_complete_auth_returns_result_on_success(mock_msal_class: MagicMock) -> None:
    """Verify complete auth returns result on success."""
    mock_app = MagicMock()
    token_result = {"access_token": "tok-123", "id_token_claims": {"name": "User"}}
    mock_app.acquire_token_by_auth_code_flow.return_value = token_result
    mock_msal_class.return_value = mock_app

    config = EntraConfig.__new__(EntraConfig)
    object.__setattr__(config, "tenant_id", "tenant-1")
    object.__setattr__(config, "client_id", "client-1")
    object.__setattr__(config, "client_secret", "secret")
    object.__setattr__(config, "redirect_uri", "http://localhost/callback")

    auth = MSALAuth(config)
    result = auth.complete_auth({}, {"code": "abc"})

    assert result == token_result
