"""weekly_auto.graph_client - minimal Microsoft Graph client for the weekly job.

Reuses the SAME proven, already-consented delegated credential that the IRE
project-tracking flow uses: a DPAPI-encrypted refresh token cached by the
PowerShell Graph scripts at %APPDATA%\\IRE-graph_refresh.bin, refreshed for the
Sites.ReadWrite.All + Mail.Send scopes.

This deliberately avoids the OneNote path (Notes.ReadWrite.All) which is blocked
on IT admin consent. Both scopes used here are already consented for the app, so
the scheduled job runs unattended with no device-code prompt.
"""
from __future__ import annotations

import base64
import ctypes
import ctypes.wintypes as wintypes
import os
from pathlib import Path

import requests

_TOKEN_URL = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
_GRAPH = "https://graph.microsoft.com/v1.0"
_SCOPES = (
    "https://graph.microsoft.com/Sites.ReadWrite.All "
    "https://graph.microsoft.com/Mail.Send offline_access"
)
_REFRESH_CACHE = "IRE-graph_refresh.bin"
_DOCX_CT = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


class _DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _dpapi_unprotect(blob: bytes) -> bytes:
    """Decrypt a CurrentUser DPAPI blob (matches PowerShell Protect-Token)."""
    src = _DATA_BLOB(
        len(blob),
        ctypes.cast(ctypes.create_string_buffer(blob, len(blob)), ctypes.POINTER(ctypes.c_char)),
    )
    out = _DATA_BLOB()
    if not ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(src), None, None, None, None, 0, ctypes.byref(out)
    ):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(out.pbData)


class GraphAuthError(RuntimeError):
    """Raised when the cached credential is missing or expired (needs re-auth)."""


class GraphClient:
    def __init__(self, tenant_id: str, client_id: str, site_id: str) -> None:
        self._tenant = tenant_id
        self._client = client_id
        self._site = site_id
        self._token: str | None = None

    # ── auth ────────────────────────────────────────────────────────────────
    def _load_refresh_token(self) -> str:
        cache = Path(os.environ.get("APPDATA", str(Path.home()))) / _REFRESH_CACHE
        if not cache.exists():
            raise GraphAuthError(
                f"No cached Graph credential at {cache}. Run IRE-SharePoint.ps1 "
                "-Action GetToken once (interactive) to seed it."
            )
        return _dpapi_unprotect(base64.b64decode(cache.read_text())).decode()

    def token(self) -> str:
        if self._token:
            return self._token
        refresh = self._load_refresh_token()
        resp = requests.post(
            _TOKEN_URL.format(tenant=self._tenant),
            data={
                "client_id": self._client,
                "grant_type": "refresh_token",
                "refresh_token": refresh,
                "scope": _SCOPES,
            },
            timeout=30,
        )
        data = resp.json()
        if "access_token" not in data:
            raise GraphAuthError(
                f"Token refresh failed ({data.get('error')}): "
                f"{data.get('error_description', 'unknown')[:180]}"
            )
        self._token = data["access_token"]
        return self._token

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.token()}"}

    # ── actions ─────────────────────────────────────────────────────────────
    def upload_to_library(self, folder: str, name: str, file_path: str | Path) -> str:
        """PUT a file into the site's default drive under `folder`. Returns webUrl."""
        data = Path(file_path).read_bytes()
        uri = f"{_GRAPH}/sites/{self._site}/drive/root:/{folder}/{name}:/content"
        resp = requests.put(
            uri, headers={**self._headers(), "Content-Type": _DOCX_CT}, data=data, timeout=120
        )
        if resp.status_code not in (200, 201):
            raise RuntimeError(f"Upload failed HTTP {resp.status_code}: {resp.text[:300]}")
        return resp.json().get("webUrl", "")

    def send_mail(
        self,
        to: list[str],
        subject: str,
        html_body: str,
        attachment_path: str | Path | None = None,
    ) -> None:
        """Send an email as the signed-in user, optionally with a file attachment."""
        message: dict = {
            "subject": subject,
            "body": {"contentType": "HTML", "content": html_body},
            "toRecipients": [{"emailAddress": {"address": addr}} for addr in to],
        }
        if attachment_path:
            p = Path(attachment_path)
            b64 = base64.b64encode(p.read_bytes()).decode()
            message["attachments"] = [
                {
                    "@odata.type": "#microsoft.graph.fileAttachment",
                    "name": p.name,
                    "contentType": _DOCX_CT,
                    "contentBytes": b64,
                }
            ]
        resp = requests.post(
            f"{_GRAPH}/me/sendMail",
            headers={**self._headers(), "Content-Type": "application/json"},
            json={"message": message, "saveToSentItems": True},
            timeout=60,
        )
        if resp.status_code not in (200, 202):
            raise RuntimeError(f"sendMail failed HTTP {resp.status_code}: {resp.text[:300]}")
