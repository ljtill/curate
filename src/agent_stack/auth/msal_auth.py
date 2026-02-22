"""MSAL authorization code flow for Microsoft Entra ID."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, ClassVar

import msal

if TYPE_CHECKING:
    from agent_stack.config import EntraConfig

logger = logging.getLogger(__name__)


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

    def get_auth_flow(self) -> dict[str, Any]:
        """Initiate the auth code flow.

        Returns the full flow dict (for session storage).
        """
        logger.info("Auth flow started")
        return self._app.initiate_auth_code_flow(
            scopes=self.SCOPE,
            redirect_uri=self._config.redirect_uri,
        )

    def complete_auth(
        self, flow: dict[str, Any], auth_response: dict[str, str]
    ) -> dict[str, Any] | None:
        """Complete the auth code flow with the callback response.

        Returns the token result containing access_token and
        id_token_claims, or None on failure.
        """
        result = self._app.acquire_token_by_auth_code_flow(flow, auth_response)
        if "error" in result:
            logger.warning("Auth flow failed — error=%s", result.get("error"))
            return None
        logger.info("Auth flow completed")
        return result
