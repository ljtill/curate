"""MSAL authorization code flow for Microsoft Entra ID."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

import msal

if TYPE_CHECKING:
    from agent_stack.config import EntraConfig


class MSALAuth:
    """Handles MSAL authorization code flow for single-tenant Entra ID."""

    SCOPE: ClassVar[list[str]] = ["User.Read"]

    def __init__(self, config: EntraConfig) -> None:
        """Initialize the MSAL client with Entra ID configuration."""
        self._config = config
        self._app = msal.ConfidentialClientApplication(
            client_id=config.client_id,
            client_credential=config.client_secret,
            authority=config.authority,
        )

    def get_auth_url(self, state: str | None = None) -> str:
        """Generate the authorization URL for the login redirect."""
        flow = self._app.initiate_auth_code_flow(
            scopes=self.SCOPE,
            redirect_uri=self._config.redirect_uri,
            state=state,
        )
        return flow.get("auth_uri", "")

    def get_auth_flow(self) -> dict[str, Any]:
        """Initiate the auth code flow and return the full flow dict (for session storage)."""
        return self._app.initiate_auth_code_flow(
            scopes=self.SCOPE,
            redirect_uri=self._config.redirect_uri,
        )

    def complete_auth(self, flow: dict[str, Any], auth_response: dict[str, str]) -> dict[str, Any] | None:
        """Complete the auth code flow with the callback response.

        Returns the token result containing access_token and id_token_claims, or None on failure.
        """
        result = self._app.acquire_token_by_auth_code_flow(flow, auth_response)
        if "error" in result:
            return None
        return result
