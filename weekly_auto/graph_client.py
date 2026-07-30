"""weekly_auto.graph_client - minimal Microsoft Graph client for the weekly job.

Two delegated auth paths, selected by ``auth_mode`` (default ``auto``):

1. ``az`` - acquire a Graph token from the signed-in **Azure CLI** session
   (``az account get-access-token``). This reuses the credentials the user
   already established with ``az login`` and works even when the laptop is
   joined to a *different resource domain* than the ``amr`` login. It needs NO
   custom app registration, NO admin consent, and NO Python MSAL dependency
   (so it is immune to the MSAL version pitfalls of the device-code flow).

2. ``refresh_token`` - reuse the proven, already-consented delegated credential
   that the IRE project-tracking flow uses: a DPAPI-encrypted refresh token
   cached by the PowerShell Graph scripts at %APPDATA%\\IRE-graph_refresh.bin,
   refreshed for Sites.ReadWrite.All + Mail.Send + Mail.Read + Calendars.Read.

``auto`` (the default) uses the cached refresh token when it exists, and
otherwise falls back to the Azure CLI - so an existing seeded machine keeps
working while a brand-new user only needs ``az login``.

This deliberately avoids the OneNote path (Notes.ReadWrite.All) which is blocked
on IT admin consent.

NOTE (refresh_token mode): Mail.Read was added after the original seed. If
reading mail returns an auth/scope error, re-seed the cached refresh token once
(interactive device-code) so consent includes Mail.Read -- see
IRE-SharePoint.ps1 -Action GetToken.
"""
from __future__ import annotations

import base64
import ctypes
import ctypes.wintypes as wintypes
import json
import os
import shutil
import subprocess
from pathlib import Path

import requests

# Resource/audience for Microsoft Graph tokens issued by the Azure CLI.
_GRAPH_RESOURCE = "https://graph.microsoft.com"
# Recognised auth modes.
_AUTH_MODES = ("auto", "az", "refresh_token")

_TOKEN_URL = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
_GRAPH = "https://graph.microsoft.com/v1.0"
_SCOPES = (
    "https://graph.microsoft.com/Sites.ReadWrite.All "
    "https://graph.microsoft.com/Mail.Send "
    "https://graph.microsoft.com/Mail.Read "
    "https://graph.microsoft.com/Calendars.Read "
    "https://graph.microsoft.com/OnlineMeetings.Read "
    "https://graph.microsoft.com/OnlineMeetingTranscript.Read.All offline_access"
)

# Friendly folder name -> Graph well-known mailFolder id.
_WELL_KNOWN_FOLDERS = {
    "inbox": "inbox",
    "sent": "sentitems",
    "sent items": "sentitems",
    "sentitems": "sentitems",
    "drafts": "drafts",
    "archive": "archive",
    "deleted": "deleteditems",
    "deleted items": "deleteditems",
}
_REFRESH_CACHE = "IRE-graph_refresh.bin"
_DOCX_CT = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _content_type(name: str) -> str:
    """Best-effort content type from a file name's extension."""
    ext = Path(name).suffix.lower()
    return {
        ".md": "text/markdown",
        ".markdown": "text/markdown",
        ".docx": _DOCX_CT,
        ".txt": "text/plain",
        ".pdf": "application/pdf",
        ".html": "text/html",
    }.get(ext, "application/octet-stream")


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
    def __init__(self, tenant_id: str = "", client_id: str = "", site_id: str = "",
                 auth_mode: str = "auto") -> None:
        self._tenant = tenant_id
        self._client = client_id
        self._site = site_id
        mode = (auth_mode or "auto").strip().lower()
        if mode not in _AUTH_MODES:
            raise GraphAuthError(
                f"Unknown auth_mode '{auth_mode}'. Use one of: {', '.join(_AUTH_MODES)}."
            )
        self._auth_mode = mode
        self._token: str | None = None

    # ── auth ────────────────────────────────────────────────────────────────
    def _refresh_cache_path(self) -> Path:
        return Path(os.environ.get("APPDATA", str(Path.home()))) / _REFRESH_CACHE

    def _load_refresh_token(self) -> str:
        cache = self._refresh_cache_path()
        if not cache.exists():
            raise GraphAuthError(
                f"No cached Graph credential at {cache}. Run IRE-SharePoint.ps1 "
                "-Action GetToken once (interactive) to seed it, or use az login "
                "(auth_mode 'az')."
            )
        return _dpapi_unprotect(base64.b64decode(cache.read_text())).decode()

    def _token_from_refresh(self) -> str:
        """Acquire a Graph token from the DPAPI-cached delegated refresh token."""
        if not (self._tenant and self._client):
            raise GraphAuthError(
                "refresh_token auth requires DEV_TENANT_ID and DEV_CLIENT_ID "
                "(set them in .env) or switch to auth_mode 'az' (az login)."
            )
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
        return data["access_token"]

    def _token_from_az(self) -> str:
        """Acquire a Graph token from the signed-in Azure CLI (``az login``).

        Reuses the user's existing az session, so it works across resource
        domains with an amr login and needs no app registration or MSAL. Raises
        an actionable GraphAuthError when az is missing or no one is logged in.
        """
        az = shutil.which("az") or shutil.which("az.cmd")
        if not az:
            raise GraphAuthError(
                "Azure CLI ('az') not found on PATH. Install it and run "
                "'az login', then set auth_mode 'az' (or 'auto')."
            )
        cmd = [az, "account", "get-access-token",
               "--resource", _GRAPH_RESOURCE, "--output", "json"]
        if self._tenant:
            cmd += ["--tenant", self._tenant]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
        except (OSError, subprocess.SubprocessError) as exc:
            raise GraphAuthError(f"Failed to invoke az: {exc}") from exc
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "").strip()[:200]
            raise GraphAuthError(
                "az account get-access-token failed - run 'az login' first "
                f"(cross-domain laptops: 'az login --use-device-code'). Detail: {err}"
            )
        try:
            token = json.loads(proc.stdout).get("accessToken", "")
        except (ValueError, TypeError) as exc:
            raise GraphAuthError(f"Could not parse az token output: {exc}") from exc
        if not token:
            raise GraphAuthError("az returned no accessToken - run 'az login' first.")
        return token

    def token(self) -> str:
        if self._token:
            return self._token
        if self._auth_mode == "az":
            self._token = self._token_from_az()
        elif self._auth_mode == "refresh_token":
            self._token = self._token_from_refresh()
        else:  # auto: prefer an existing seeded refresh token, else az login
            if self._refresh_cache_path().exists() and self._tenant and self._client:
                try:
                    self._token = self._token_from_refresh()
                except GraphAuthError:
                    self._token = self._token_from_az()
            else:
                self._token = self._token_from_az()
        return self._token

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.token()}"}

    # ── actions ─────────────────────────────────────────────────────────────
    def upload_to_library(self, folder: str, name: str, file_path: str | Path) -> str:
        """PUT a file into the site's default drive under `folder`. Returns webUrl."""
        data = Path(file_path).read_bytes()
        uri = f"{_GRAPH}/sites/{self._site}/drive/root:/{folder}/{name}:/content"
        resp = requests.put(
            uri, headers={**self._headers(), "Content-Type": _content_type(name)},
            data=data, timeout=120,
        )
        if resp.status_code not in (200, 201):
            raise RuntimeError(f"Upload failed HTTP {resp.status_code}: {resp.text[:300]}")
        return resp.json().get("webUrl", "")

    def delete_from_library(self, folder: str, name: str) -> bool:
        """DELETE a file from the site's default drive under `folder`.

        Returns True if deleted, False if it did not exist (HTTP 404).
        """
        uri = f"{_GRAPH}/sites/{self._site}/drive/root:/{folder}/{name}:/"
        resp = requests.delete(uri, headers=self._headers(), timeout=60)
        if resp.status_code in (200, 204):
            return True
        if resp.status_code == 404:
            return False
        raise RuntimeError(f"Delete failed HTTP {resp.status_code}: {resp.text[:300]}")

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
                    "contentType": _content_type(p.name),
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

    def read_messages(
        self,
        folder: str,
        since_iso: str,
        until_iso: str,
        top: int = 50,
    ) -> list[dict]:
        """Return messages in `folder` received within [since_iso, until_iso].

        `folder` is a friendly name (Inbox, Sent Items, ...) mapped to a Graph
        well-known folder id. `since_iso`/`until_iso` are full UTC datetimes
        (e.g. '2026-07-19T00:00:00Z'). Returns a list of dicts with keys:
        subject, from, to, received, web_link, preview. Read-only (Mail.Read).
        """
        well_known = _WELL_KNOWN_FOLDERS.get(folder.strip().lower())
        base = (
            f"{_GRAPH}/me/mailFolders/{well_known}/messages"
            if well_known
            else f"{_GRAPH}/me/messages"
        )
        params = {
            "$select": "subject,from,toRecipients,receivedDateTime,webLink,bodyPreview",
            "$filter": (
                f"receivedDateTime ge {since_iso} and receivedDateTime le {until_iso}"
            ),
            "$orderby": "receivedDateTime desc",
            "$top": str(max(1, min(top, 100))),
        }
        resp = requests.get(
            base,
            headers={**self._headers(), "Prefer": 'outlook.timezone="UTC"'},
            params=params,
            timeout=60,
        )
        if resp.status_code == 403:
            raise GraphAuthError(
                "Mail.Read not consented for this app/token. Re-seed the cached "
                "credential (IRE-SharePoint.ps1 -Action GetToken) so consent "
                "includes Mail.Read."
            )
        if resp.status_code != 200:
            raise RuntimeError(f"read_messages failed HTTP {resp.status_code}: {resp.text[:300]}")

        out: list[dict] = []
        for m in resp.json().get("value", []):
            frm = (m.get("from") or {}).get("emailAddress", {})
            to_list = [
                (r.get("emailAddress") or {}).get("address", "")
                for r in (m.get("toRecipients") or [])
            ]
            out.append({
                "subject": (m.get("subject") or "(no subject)").strip(),
                "from": frm.get("address", "") or frm.get("name", ""),
                "to": [a for a in to_list if a],
                "received": (m.get("receivedDateTime") or "")[:10],
                "web_link": m.get("webLink", ""),
                "preview": (m.get("bodyPreview") or "").strip(),
            })
        return out

    # ── online-meeting transcripts (delegated: organizer-only) ───────────────
    def organized_online_meetings(self, since_iso: str, until_iso: str,
                                  top: int = 100) -> list[dict]:
        """Return online meetings the signed-in user ORGANIZED in the window.

        Uses /me/calendarView (NOT /me/events $filter, which 400s on start).
        `since_iso`/`until_iso` are full UTC datetimes
        (e.g. '2026-07-19T00:00:00Z'). Returns dicts with keys:
        subject, date (YYYY-MM-DD), join_url. Delegated transcript access is
        organizer-only, so non-organized meetings are dropped here.
        """
        params = {
            "startDateTime": since_iso,
            "endDateTime": until_iso,
            "$select": "subject,isOrganizer,isOnlineMeeting,onlineMeeting,start",
            "$orderby": "start/dateTime",
            "$top": str(max(1, min(top, 200))),
        }
        resp = requests.get(
            f"{_GRAPH}/me/calendarView",
            headers={**self._headers(), "Prefer": 'outlook.timezone="UTC"'},
            params=params,
            timeout=60,
        )
        if resp.status_code == 403:
            raise GraphAuthError(
                "Calendars.Read not consented for this app/token. Re-seed the "
                "cached credential (IRE-SharePoint.ps1 -Action GetToken) so "
                "consent includes Calendars.Read + OnlineMeetingTranscript.Read.All."
            )
        if resp.status_code != 200:
            raise RuntimeError(
                f"calendarView failed HTTP {resp.status_code}: {resp.text[:300]}")
        out: list[dict] = []
        seen: set[str] = set()
        for ev in resp.json().get("value", []):
            if not (ev.get("isOnlineMeeting") and ev.get("isOrganizer")):
                continue
            join_url = ((ev.get("onlineMeeting") or {}).get("joinUrl") or "").strip()
            if not join_url or join_url in seen:
                continue
            seen.add(join_url)
            out.append({
                "subject": (ev.get("subject") or "(no subject)").strip(),
                "date": ((ev.get("start") or {}).get("dateTime") or "")[:10],
                "join_url": join_url,
            })
        return out

    def resolve_online_meeting_id(self, join_url: str) -> str:
        """Resolve a Teams joinUrl to its onlineMeeting id (empty if not found)."""
        params = {"$filter": f"JoinWebUrl eq '{join_url}'"}
        resp = requests.get(
            f"{_GRAPH}/me/onlineMeetings",
            headers=self._headers(), params=params, timeout=60,
        )
        if resp.status_code != 200:
            return ""
        vals = resp.json().get("value", [])
        return vals[0].get("id", "") if vals else ""

    def list_transcripts(self, meeting_id: str) -> list[str]:
        """Return transcript ids for an online meeting (empty if none/not transcribed)."""
        resp = requests.get(
            f"{_GRAPH}/me/onlineMeetings/{meeting_id}/transcripts",
            headers=self._headers(), timeout=60,
        )
        if resp.status_code != 200:
            return []
        return [t.get("id", "") for t in resp.json().get("value", []) if t.get("id")]

    def get_transcript_vtt(self, meeting_id: str, transcript_id: str) -> str:
        """Download a transcript's WebVTT content as text (empty on failure)."""
        resp = requests.get(
            f"{_GRAPH}/me/onlineMeetings/{meeting_id}/transcripts/{transcript_id}/content",
            headers=self._headers(), params={"$format": "text/vtt"}, timeout=120,
        )
        return resp.text if resp.status_code == 200 else ""

    def fetch_transcripts(self, since_iso: str, until_iso: str,
                          top: int = 100) -> list[dict]:
        """High-level: organized+transcribed meetings in the window with their VTT.

        Returns a list of dicts: {subject, date, join_url, meeting_id,
        transcripts: [vtt_text, ...]}. Meetings with no transcript are still
        returned (empty transcripts list) so the caller can report coverage.
        """
        meetings = self.organized_online_meetings(since_iso, until_iso, top=top)
        out: list[dict] = []
        for mtg in meetings:
            mid = self.resolve_online_meeting_id(mtg["join_url"])
            vtts: list[str] = []
            if mid:
                for tid in self.list_transcripts(mid):
                    vtt = self.get_transcript_vtt(mid, tid)
                    if vtt:
                        vtts.append(vtt)
            out.append({**mtg, "meeting_id": mid, "transcripts": vtts})
        return out
