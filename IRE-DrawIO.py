"""
IRE-DrawIO.py — Generate draw.io diagrams from IRE project data.

Diagrams are saved as .drawio files and can be opened in the Intel
draw.io instance at https://drawio-ai.intel.com/ (requires Intel SSO).

Actions:
    project-status  Kanban board of SharePoint list items (live data)
    architecture    Static architecture diagram of the IRE toolkit
    open            Open the Intel draw.io instance in your default browser

Usage:
    python IRE-DrawIO.py project-status
    python IRE-DrawIO.py project-status --output diagrams/status.drawio --open
    python IRE-DrawIO.py architecture --open
    python IRE-DrawIO.py open
"""
from __future__ import annotations

import argparse
import os
import sys
import webbrowser
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv

from drawio import DiagramBuilder, PRIORITY_ICON, STATUS_STYLE, STYLES
from graph_auth import get_credential
from version import __version__, log_run

load_dotenv()

# ── Config ────────────────────────────────────────────────────────────────────

SITE_ID     = os.environ["SITE_ID"]
LIST_ID     = os.environ["LIST_ID"]
SCOPES      = ["https://graph.microsoft.com/Sites.ReadWrite.All"]
DRAWIO_URL  = "https://drawio-ai.intel.com/"
OUTPUT_DIR  = Path(__file__).resolve().parent / "diagrams"
STATUS_ORDER = ["New", "In progress", "Blocked", "Completed"]


# ── Graph helpers ─────────────────────────────────────────────────────────────

def _get_token() -> str:
    cred = get_credential(SCOPES, cache_name="IRE-drawio-token-cache")
    return cred.get_token().token


def _fetch_list_items(token: str) -> list[dict]:
    url = (
        f"https://graph.microsoft.com/v1.0/sites/{SITE_ID}"
        f"/lists/{LIST_ID}/items?expand=fields&$orderby=fields/Created desc"
    )
    headers = {"Authorization": f"Bearer {token}"}
    items = []
    while url:
        resp = requests.get(url, headers=headers, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        items.extend(data.get("value", []))
        url = data.get("@odata.nextLink")
    return items


# ── Diagram builders ──────────────────────────────────────────────────────────

def build_project_status_diagram(items: list[dict]) -> DiagramBuilder:
    """Kanban board — one column per status, one box per project."""
    d = DiagramBuilder(
        title=f"IRE Project Status — {datetime.now().strftime('%Y-%m-%d')}",
        page_size=DiagramBuilder.PAGE_A3_LANDSCAPE,
    )
    d.add_note(
        f"<b>IRE Project Tracking</b>  ·  {datetime.now().strftime('%Y-%m-%d %H:%M')}  ·  v{__version__}",
        x=40, y=20, width=600, height=24,
    )

    # Group items by status
    columns: dict[str, list[tuple[str, str]]] = {s: [] for s in STATUS_ORDER}
    for item in items:
        f = item.get("fields", {})
        status = f.get("Status", "New")
        if status not in columns:
            columns[status] = []
        priority = f.get("Priority", "Normal")
        icon = PRIORITY_ICON.get(priority, "")
        label = f"{icon} {f.get('Title', '(no title)')}"
        tooltip = (
            f"Priority: {priority}\n"
            f"Segment: {f.get('Segment', '')}\n"
            f"Phase: {f.get('Projectphase', '')}\n"
            f"{f.get('ProjectSummaryDetails', '')}"
        ).strip()
        columns[status].append((label, tooltip))

    d.add_status_board(columns, col_width=220, item_height=65)
    return d


def build_architecture_diagram() -> DiagramBuilder:
    """Static architecture diagram of the IRE PowerAutomate toolkit."""
    d = DiagramBuilder("IRE Toolkit — Architecture")

    d.add_note(
        "<b>IRE PowerAutomate Toolkit — Architecture</b>",
        x=40, y=20, width=500, height=24,
    )

    # ── Row 1: Config & Auth ──────────────────────────────────────────────────
    env   = d.add_shape(".env\n(config)",       x=40,  y=80,  width=120, height=50, style=STYLES["box_config"])
    auth  = d.add_shape("graph_auth.py\nMSAL + DPAPI", x=220, y=80, width=160, height=50, style=STYLES["box_python"])
    ver   = d.add_shape("version.py\nhistory.jsonl",   x=440, y=80, width=160, height=50, style=STYLES["box_python"])

    # ── Row 2: Python scripts ─────────────────────────────────────────────────
    sp_py = d.add_shape("IRE-SharePoint.py",    x=40,  y=200, width=160, height=50, style=STYLES["box_python"])
    on_py = d.add_shape("IRE-OneNote.py",       x=220, y=200, width=160, height=50, style=STYLES["box_python"])
    dio   = d.add_shape("IRE-DrawIO.py",        x=400, y=200, width=160, height=50, style=STYLES["box_python"])
    hi    = d.add_shape("hello.py",             x=580, y=200, width=120, height=50, style=STYLES["box_python"])

    # ── Row 3: PowerShell scripts ─────────────────────────────────────────────
    sp_ps = d.add_shape("IRE-SharePoint.ps1",   x=40,  y=310, width=160, height=50, style=STYLES["box_ps1"])
    on_ps = d.add_shape("IRE-OneNote.ps1",      x=220, y=310, width=160, height=50, style=STYLES["box_ps1"])

    # ── Row 4: Microsoft Graph API ────────────────────────────────────────────
    graph = d.add_shape("Microsoft Graph API\ngraph.microsoft.com", x=200, y=430, width=240, height=55, style=STYLES["box_azure"])

    # ── Row 5: Services ───────────────────────────────────────────────────────
    spl   = d.add_shape("SharePoint\nIRE Project List",   x=40,  y=550, width=150, height=55, style=STYLES["box_azure"])
    one   = d.add_shape("OneNote\nIE Notebook",           x=220, y=550, width=150, height=55, style=STYLES["box_azure"])
    drw   = d.add_shape("draw.io\ndrawio-ai.intel.com",   x=400, y=550, width=150, height=55, style=STYLES["box_config"])

    # ── Edges: config & auth ──────────────────────────────────────────────────
    d.add_edge(env,  auth,  "loads")
    d.add_edge(auth, sp_py, "token")
    d.add_edge(auth, on_py, "token")
    d.add_edge(auth, dio,   "token")
    d.add_edge(auth, hi,    "token")
    d.add_edge(auth, sp_ps, "token")
    d.add_edge(auth, on_ps, "token")
    d.add_edge(ver,  sp_py, "log")
    d.add_edge(ver,  on_py, "log")
    d.add_edge(ver,  dio,   "log")

    # ── Edges: scripts → Graph API ────────────────────────────────────────────
    d.add_edge(sp_py, graph)
    d.add_edge(on_py, graph)
    d.add_edge(sp_ps, graph)
    d.add_edge(on_ps, graph)
    d.add_edge(dio,   graph)

    # ── Edges: Graph API → services ──────────────────────────────────────────
    d.add_edge(graph, spl)
    d.add_edge(graph, one)
    d.add_edge(dio,   drw, "opens")

    return d


# ── Output helpers ────────────────────────────────────────────────────────────

def _save_diagram(builder: DiagramBuilder, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    out = builder.save(path)
    print(f"\n✅ Diagram saved → {out}")
    return out


def _open_drawio(path: Path | None = None) -> None:
    """Open the Intel draw.io instance in the default browser."""
    print(f"\nOpening {DRAWIO_URL} ...")
    print("  1. Sign in with your Intel SSO credentials.")
    if path:
        print(f"  2. Choose File → Import From → Device and select:")
        print(f"     {path}")
    webbrowser.open(DRAWIO_URL)


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    from project_diagram import attach_diagram_to_item, fetch_item

    parser = argparse.ArgumentParser(
        description="Generate draw.io diagrams from IRE project data.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="action", required=True)

    # project-status
    ps_p = sub.add_parser("project-status", help="Kanban board from SharePoint list (live data)")
    ps_p.add_argument("--output", "-o", type=Path,
                      default=OUTPUT_DIR / "project-status.drawio",
                      help="Output .drawio file path")
    ps_p.add_argument("--open", action="store_true", help="Open draw.io in browser after saving")

    # architecture
    ar_p = sub.add_parser("architecture", help="Static architecture diagram of the IRE toolkit")
    ar_p.add_argument("--output", "-o", type=Path,
                      default=OUTPUT_DIR / "architecture.drawio",
                      help="Output .drawio file path")
    ar_p.add_argument("--open", action="store_true", help="Open draw.io in browser after saving")

    # project (single item)
    pr_p = sub.add_parser("project", help="Generate/re-upload diagram for one project item")
    pr_p.add_argument("--item-id", required=True, metavar="ID",
                      help="SharePoint list item ID")
    pr_p.add_argument("--open", action="store_true", help="Open draw.io in browser after upload")

    # open
    sub.add_parser("open", help="Open the Intel draw.io instance in your default browser")

    args = parser.parse_args()

    if args.action == "open":
        _open_drawio()
        return

    out: Path | None = None
    try:
        if args.action == "project-status":
            print("Fetching SharePoint items...")
            token = _get_token()
            items = _fetch_list_items(token)
            print(f"  {len(items)} items fetched.")
            builder = build_project_status_diagram(items)
            out = _save_diagram(builder, args.output)
            log_run("IRE-DrawIO.py", "project-status", f"{len(items)} items → {out.name}")

        elif args.action == "architecture":
            builder = build_architecture_diagram()
            out = _save_diagram(builder, args.output)
            log_run("IRE-DrawIO.py", "architecture", str(out.name))

        elif args.action == "project":
            token = _get_token()
            item  = fetch_item(token, args.item_id)
            sp_url = attach_diagram_to_item(token, item)
            print(f"\n✅ Diagram linked: {sp_url}")
            log_run("IRE-DrawIO.py", "project", f"item={args.item_id}")

        if getattr(args, "open", False):
            _open_drawio(out)

    except Exception as exc:
        log_run("IRE-DrawIO.py", args.action, str(exc)[:120], success=False)
        print(f"\n❌ {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()