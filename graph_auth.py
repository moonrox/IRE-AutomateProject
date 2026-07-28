"""
graph_auth.py — Shared MSAL authentication for IRE Graph scripts.

Supports two environments controlled by GRAPH_ENV in .env:

  GRAPH_ENV=dev  (default)
      Uses DeviceCodeCredential — MSAL public client with device-code browser
      prompt (Intel SSO). Token cache persisted to %APPDATA% via DPAPI.
      Reads DEV_CLIENT_ID / DEV_TENANT_ID from .env.

  GRAPH_ENV=prod
      Uses ClientSecretCredential — MSAL confidential client, app-only flow.
      No browser prompt; requires PROD_CLIENT_ID, PROD_TENANT_ID, and
      PROD_CLIENT_SECRET in .env.  The PROD app registration must have
      Graph *application* permission Sites.Read.All with admin consent granted.

Call ``get_credential(scopes)`` to get the right credential for the active env.
"""
from __future__ import annotations

import os
import time
from pathlib import Path

import msal
import msal_extensions
from azure.core.credentials import AccessToken

_CACHE_DIR = Path(os.environ.get("APPDATA", Path.home()))

# DEV fallback defaults (public app, Intel tenant)
# DEV fallback defaults — read from .env; no hardcoded values so this file
# is safe to publish. See .env.example for required keys.
_DEV_CLIENT_ID_DEFAULT = os.getenv("DEV_CLIENT_ID", "")
_DEV_TENANT_ID_DEFAULT = os.getenv("DEV_TENANT_ID", "")


def _build_cache(cache_name: str) -> msal_extensions.PersistedTokenCache:
    """Return a DPAPI-encrypted (Windows) persistent token cache."""
    cache_path = str(_CACHE_DIR / f"{cache_name}.bin")
    try:
        persistence = msal_extensions.build_encrypted_persistence(cache_path)
    except msal_extensions.PersistenceNotFound:
        persistence = msal_extensions.FilePersistence(cache_path)
    return msal_extensions.PersistedTokenCache(persistence)


class DeviceCodeCredential:
    """MSAL public-client credential with DPAPI-encrypted persistent token cache.

    Used for DEV: interactive device-code flow (Intel SSO).
    Implements the azure-core ``TokenCredential`` protocol.
    """

    def __init__(
        self,
        client_id: str,
        tenant_id: str,
        scopes: list[str],
        cache_name: str = "IRE-py-token-cache",
    ) -> None:
        self._scopes = scopes
        self._app = msal.PublicClientApplication(
            client_id,
            authority=f"https://login.microsoftonline.com/{tenant_id}",
            token_cache=_build_cache(cache_name),
        )

    def get_token(self, *_scopes: str, **kwargs) -> AccessToken:
        """Acquire a token silently if cached, otherwise start device-code flow."""
        accounts = self._app.get_accounts()
        result = (
            self._app.acquire_token_silent(self._scopes, account=accounts[0])
            if accounts
            else None
        )
        if not result:
            flow = self._app.initiate_device_flow(scopes=self._scopes)
            print(f"\n{'═'*45}")
            print(f"  Go to : {flow['verification_uri']}")
            print(f"  Code  : {flow['user_code']}")
            print(f"{'═'*45}\n")
            result = self._app.acquire_token_by_device_flow(flow)

        if "access_token" not in result:
            raise RuntimeError(result.get("error_description", "Authentication failed"))

        expires_on = int(time.time()) + result.get("expires_in", 3600)
        return AccessToken(result["access_token"], expires_on)


class ClientSecretCredential:
    """MSAL confidential-client credential using a client secret.

    Used for PROD: app-only flow, no browser prompt required.
    Always acquires tokens with the ``/.default`` scope (required for
    application permissions in client-credentials flow).
    Implements the azure-core ``TokenCredential`` protocol.
    """

    # App-only (client-credentials) flow must use .default — not delegated scopes.
    _APP_SCOPES = ["https://graph.microsoft.com/.default"]

    def __init__(self, client_id: str, tenant_id: str, client_secret: str) -> None:
        self._app = msal.ConfidentialClientApplication(
            client_id,
            authority=f"https://login.microsoftonline.com/{tenant_id}",
            client_credential=client_secret,
        )

    def get_token(self, *_scopes: str, **kwargs) -> AccessToken:
        """Acquire an app-only token using client credentials."""
        result = self._app.acquire_token_for_client(scopes=self._APP_SCOPES)
        if "access_token" not in result:
            raise RuntimeError(result.get("error_description", "Authentication failed"))
        expires_on = int(time.time()) + result.get("expires_in", 3600)
        return AccessToken(result["access_token"], expires_on)


def get_credential(
    scopes: list[str],
    cache_name: str = "IRE-py-token-cache",
) -> DeviceCodeCredential | ClientSecretCredential:
    """Return the right credential for the active GRAPH_ENV (dev or prod).

    Args:
        scopes: Delegated scopes for DEV device-code flow (ignored in PROD).
        cache_name: Token cache file name for DEV (ignored in PROD).

    Raises:
        ValueError: If GRAPH_ENV is set to an unrecognised value.
        RuntimeError: If required PROD_* env vars are missing.
    """
    env = os.getenv("GRAPH_ENV", "dev").lower()
    if env not in ("dev", "prod"):
        raise ValueError(
            f"GRAPH_ENV must be 'dev' or 'prod', got {os.getenv('GRAPH_ENV')!r}. "
            "Check your .env file."
        )

    if env == "prod":
        missing = [v for v in ("PROD_CLIENT_ID", "PROD_TENANT_ID", "PROD_CLIENT_SECRET")
                   if not os.getenv(v)]
        if missing:
            raise RuntimeError(
                f"GRAPH_ENV=prod requires these .env variables to be set: "
                f"{', '.join(missing)}"
            )
        return ClientSecretCredential(
            os.environ["PROD_CLIENT_ID"],
            os.environ["PROD_TENANT_ID"],
            os.environ["PROD_CLIENT_SECRET"],
        )

    # dev — device code flow
    client_id = os.getenv("DEV_CLIENT_ID", _DEV_CLIENT_ID_DEFAULT)
    tenant_id = os.getenv("DEV_TENANT_ID", _DEV_TENANT_ID_DEFAULT)
    if not client_id or not tenant_id:
        raise RuntimeError(
            "DEV_CLIENT_ID and DEV_TENANT_ID must be set in your .env file. "
            "See .env.example for guidance."
        )
    return DeviceCodeCredential(
        client_id,
        tenant_id,
        scopes,
        cache_name=cache_name,
    )