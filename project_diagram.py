"""
project_diagram.py — Per-project draw.io diagram: generate, upload to SharePoint,
link back to the list item, and maintain a local projects.json index.

Typical usage (called by IRE-SharePoint.py after CreateItem):
    from project_diagram import attach_diagram_to_item
    url = attach_diagram_to_item(token, item)   # item = full Graph list item dict

Standalone:
    python project_diagram.py --item-id 42
    python project_diagram.py --setup-column     # one-time column provisioning
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

from drawio import DiagramBuilder
from version import __version__, log_run

# ── Config ────────────────────────────────────────────────────────────────────

SITE_ID = os.environ.get("SITE_ID", "")
LIST_ID = os.environ.get("LIST_ID", "")

_ROOT        = Path(__file__).resolve().parent
PROJECTS_JSON = _ROOT / "projects.json"
DIAGRAMS_DIR  = _ROOT / "diagrams"

_GRAPH = "https://graph.microsoft.com/v1.0"
_DIAGRAM_FOLDER = "Diagrams"          # folder in the site's default drive
_COLUMN_NAME    = "DiagramUrl"        # internal field name on the SharePoint list


# ── Filename sanitization ─────────────────────────────────────────────────────

def _safe_filename(title: str, item_id: str) -> str:
    """Produce a SharePoint-safe filename from a title + item ID."""
    slug = re.sub(r'[/\\:*?"<>|]', "", title)   # strip invalid chars
    slug = slug.strip(". ")[:50]                  # no leading/trailing dot/space, max 50
    slug = re.sub(r"\s+", "-", slug)              # spaces → hyphens
    return f"{slug}-{item_id}.drawio" if slug else f"project-{item_id}.drawio"


# ── SharePoint helpers ────────────────────────────────────────────────────────

def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def ensure_diagrams_folder(token: str) -> None:
    """Create the Diagrams folder in the site drive (no-op if it exists)."""
    url = f"{_GRAPH}/sites/{SITE_ID}/drive/root/children"
    resp = requests.post(
        url,
        headers=_headers(token),
        json={
            "name": _DIAGRAM_FOLDER,
            "folder": {},
            "@microsoft.graph.conflictBehavior": "fail",
        },
        timeout=20,
    )
    if resp.status_code == 409:
        return  # folder already exists — fine
    resp.raise_for_status()


def upload_diagram(token: str, xml: str, filename: str) -> str:
    """Upload diagram XML to SharePoint and return the file's webUrl.

    The Diagrams folder must already exist (call ensure_diagrams_folder first).
    """
    url = (
        f"{_GRAPH}/sites/{SITE_ID}/drive/root:/"
        f"{_DIAGRAM_FOLDER}/{filename}:/content"
    )
    resp = requests.put(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/octet-stream",
        },
        data=xml.encode("utf-8"),
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json().get("webUrl", "")


def ensure_diagram_column(token: str) -> None:
    """Create the DiagramUrl text column on the list if it does not exist.

    Requires Sites.Manage.All — gracefully skips if the caller lacks the scope.
    Run ``python project_diagram.py --setup-column`` with an admin token once.
    """
    # Check existing columns
    cols_url = f"{_GRAPH}/sites/{SITE_ID}/lists/{LIST_ID}/columns"
    resp = requests.get(cols_url, headers=_headers(token), timeout=20)
    if resp.status_code == 403:
        print(
            "  ⚠️  Cannot read list columns (Sites.Manage.All required).\n"
            "     Run `python project_diagram.py --setup-column` with an admin\n"
            "     token once, or add a 'DiagramUrl' text column manually.",
            file=sys.stderr,
        )
        return
    resp.raise_for_status()

    existing = {c["name"] for c in resp.json().get("value", [])}
    if _COLUMN_NAME in existing:
        return  # already provisioned

    # Create the column
    create_resp = requests.post(
        cols_url,
        headers=_headers(token),
        json={
            "name": _COLUMN_NAME,
            "displayName": "Diagram",
            "text": {},
        },
        timeout=20,
    )
    if create_resp.status_code == 403:
        print(
            f"  ⚠️  Cannot create '{_COLUMN_NAME}' column (Sites.Manage.All required).\n"
            "     Diagram URL will be tracked in projects.json only.",
            file=sys.stderr,
        )
        return
    if create_resp.status_code == 409:
        return  # already exists
    create_resp.raise_for_status()
    print(f"  ✔  Created '{_COLUMN_NAME}' column on the list.")


def update_item_diagram_url(token: str, item_id: str, url: str) -> None:
    """PATCH the list item's DiagramUrl field. Silently skips if the column doesn't exist."""
    patch_url = f"{_GRAPH}/sites/{SITE_ID}/lists/{LIST_ID}/items/{item_id}/fields"
    resp = requests.patch(
        patch_url,
        headers=_headers(token),
        json={_COLUMN_NAME: url},
        timeout=20,
    )
    if resp.status_code in (400, 422):
        # Column not present on this list — diagram is still tracked in projects.json
        print(
            f"  ⚠️  List field '{_COLUMN_NAME}' not found — skipping item update.\n"
            "     Run `python project_diagram.py --setup-column` to provision it.",
            file=sys.stderr,
        )
        return
    resp.raise_for_status()


def fetch_item(token: str, item_id: str) -> dict:
    """Fetch a single list item (fields + metadata) by ID."""
    url = f"{_GRAPH}/sites/{SITE_ID}/lists/{LIST_ID}/items/{item_id}?expand=fields"
    resp = requests.get(url, headers=_headers(token), timeout=20)
    resp.raise_for_status()
    return resp.json()


# ── projects.json ─────────────────────────────────────────────────────────────

def load_projects_json() -> dict:
    if PROJECTS_JSON.exists():
        return json.loads(PROJECTS_JSON.read_text(encoding="utf-8"))
    return {"version": __version__, "last_updated": "", "projects": {}}


def save_projects_json(data: dict) -> None:
    data["last_updated"] = datetime.now().isoformat(timespec="seconds")
    PROJECTS_JSON.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _upsert_project_entry(
    item_id: str,
    fields: dict,
    filename: str,
    sharepoint_url: str,
) -> None:
    """Read-modify-write projects.json with the new/updated entry."""
    data = load_projects_json()
    data["projects"][item_id] = {
        "id":                    item_id,
        "title":                 fields.get("Title", ""),
        "status":                fields.get("Status", ""),
        "priority":              fields.get("Priority", ""),
        "diagram_filename":      filename,
        "diagram_sharepoint_url": sharepoint_url,
        "diagram_updated":       datetime.now().isoformat(timespec="seconds"),
    }
    save_projects_json(data)


# ── Diagram builder ───────────────────────────────────────────────────────────

def _build_diagram(item: dict) -> tuple[str, str]:
    """Build a project-card diagram and return (xml_string, safe_filename)."""
    item_id      = str(item.get("id", "0"))
    fields       = item.get("fields", {})
    created_dt   = item.get("createdDateTime", "")
    modified_dt  = item.get("lastModifiedDateTime", "")
    title        = fields.get("Title", "(no title)")

    d = DiagramBuilder(f"{title} — Project Card")
    d.add_note(
        f"<b>{title}</b>  ·  IRE Project Card  ·  v{__version__}",
        x=40, y=20, width=620, height=24,
    )
    d.add_project_card(
        item_id=item_id,
        fields=fields,
        created_dt=created_dt,
        modified_dt=modified_dt,
    )
    return d.to_xml(), _safe_filename(title, item_id)


# ── Main entry point ──────────────────────────────────────────────────────────

def attach_diagram_to_item(token: str, item: dict) -> str:
    """Generate a diagram for a project, upload it, and link it back.

    Returns the SharePoint webUrl of the uploaded diagram.
    Steps (in order so failures are least damaging):
      1. ensure_diagrams_folder  — idempotent, no data at risk
      2. ensure_diagram_column   — idempotent, graceful 403
      3. build + upload diagram  — creates the file in SharePoint
      4. update list item        — links file URL into the list row
      5. update projects.json    — local index
    """
    item_id = str(item.get("id", "0"))
    fields  = item.get("fields", {})
    title   = fields.get("Title", "(no title)")

    print(f"\n  📊 Generating diagram for '{title}' (ID {item_id})...")

    # 1. Ensure folder
    ensure_diagrams_folder(token)

    # 2. Ensure column (best-effort)
    ensure_diagram_column(token)

    # 3. Build + upload
    xml, filename = _build_diagram(item)
    sharepoint_url = upload_diagram(token, xml, filename)
    print(f"  ✔  Uploaded → {sharepoint_url}")

    # Also save locally for reference
    DIAGRAMS_DIR.mkdir(exist_ok=True)
    (DIAGRAMS_DIR / filename).write_text(xml, encoding="utf-8")

    # 4. Link back to list item
    if sharepoint_url:
        update_item_diagram_url(token, item_id, sharepoint_url)

    # 5. projects.json
    _upsert_project_entry(item_id, fields, filename, sharepoint_url)

    log_run("project_diagram.py", "attach", f"item={item_id} file={filename}")
    return sharepoint_url


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    import argparse
    from graph_auth import DeviceCodeCredential

    CLIENT_ID = os.environ["CLIENT_ID"]
    TENANT_ID = os.environ["TENANT_ID"]
    SCOPES    = ["https://graph.microsoft.com/Sites.ReadWrite.All"]

    parser = argparse.ArgumentParser(description="Project diagram tools")
    grp = parser.add_mutually_exclusive_group(required=True)
    grp.add_argument("--item-id", metavar="ID",
                     help="Generate/re-upload diagram for an existing project item ID")
    grp.add_argument("--setup-column", action="store_true",
                     help="Provision the DiagramUrl column on the list (one-time admin step)")
    grp.add_argument("--show", action="store_true",
                     help="Print projects.json index")
    args = parser.parse_args()

    if args.show:
        data = load_projects_json()
        print(json.dumps(data, indent=2))
        return

    cred  = DeviceCodeCredential(CLIENT_ID, TENANT_ID, SCOPES, "IRE-project-diagram")
    token = cred.get_token(*SCOPES).token

    if args.setup_column:
        ensure_diagram_column(token)
        print("Column provisioning complete.")
        return

    item = fetch_item(token, args.item_id)
    url  = attach_diagram_to_item(token, item)
    if url:
        print(f"\n✅ Diagram URL: {url}")


if __name__ == "__main__":
    main()
