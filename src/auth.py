"""Authentication helper for Microsoft Graph.

This module wraps MSAL's ConfidentialClientApplication to obtain an application (client credentials)
access token suitable for calling the Microsoft Graph API and SharePoint endpoints used elsewhere
in the application.

Design notes:
 - We deliberately use the client credentials (application) flow; interactive delegated flows are
   out of scope for this sample.
 - A minimal abstraction keeps the rest of the code decoupled from MSAL specifics.
 - Token caching (acquire_token_silent) can be introduced later if multiple calls are made; for a
   single-run summarization we keep it simple.
"""

from typing import Dict
import msal

from .config import AppConfig


class GraphAuth:
    """Acquire Azure AD access tokens for Microsoft Graph using client credentials."""

    def __init__(self, cfg: AppConfig):
        self.cfg = cfg
        # Authority = login host + tenant id (could be a tenant GUID or domain)
        self.authority = f"{cfg.graph.authority_host}/{cfg.tenant_id}"
        # Build a confidential client (uses client secret). For production consider managed identities
        # or certificate credentials for improved security posture.
        self.app = msal.ConfidentialClientApplication(
            client_id=cfg.client_id,
            client_credential=self.cfg.client_secret,
            authority=self.authority,
        )

    def get_token(self) -> str:
        """Return a bearer token string for Microsoft Graph.

        Raises:
            RuntimeError: if token acquisition fails.
        """
        # We directly call acquire_token_for_client (no account context). If you add caching, pass a
        # token cache to the ConfidentialClientApplication or call acquire_token_silent first.
        result: Dict = self.app.acquire_token_for_client(scopes=self.cfg.graph.scope)
        if "access_token" not in result:
            raise RuntimeError(
                f"Failed to acquire token: {result.get('error')}: {result.get('error_description')}"
            )
        return result["access_token"]
