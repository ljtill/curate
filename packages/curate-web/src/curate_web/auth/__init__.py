"""Authentication module — Microsoft Entra ID via MSAL."""

from curate_web.auth.middleware import require_auth, require_authenticated_user
from curate_web.auth.msal_auth import MSALAuth

__all__ = ["MSALAuth", "require_auth", "require_authenticated_user"]
