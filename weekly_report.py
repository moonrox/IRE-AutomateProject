"""
weekly_report.py — Auto-generate a WW status report for IRE projects.

Reads from:
  - project_registry.py  (central project list + metadata)
  - ProjectTracker SQLite DB (events + notes logged this WW)
  - File system mtimes (code changes in each project folder)

Outputs:
  - Console summary
  - Markdown file → weekly_reports/WW{n}-{year}.md
  - Optionally posts HTML to OneNote via IRE-OneNote.ps1 -Action AppendToPage

Usage:
  python weekly_report.py                    # current WW
  python weekly_report.py --ww WW24          # specific WW (current year)
  python weekly_report.py --ww WW24-2026     # explicit year
  python weekly_report.py --prev             # last completed WW
  python weekly_report.py --post             # generate + post to OneNote
  python weekly_report.py --ww WW23 --post   # previous WW + post
  python weekly_report.py --out report.md    # custom output path
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

# ── Path setup ────────────────────────────────────────────────────────────────

THIS_DIR = Path(__file__).resolve().parent
AI_SCRIPTS_DIR = THIS_DIR.parent

# Load .env so graph_auth picks up DEV_CLIENT_ID / GRAPH_ENV etc.
try:
    from dotenv import load_dotenv
    load_dotenv(THIS_DIR / ".env", override=False)
except ImportError:
    pass

# Allow importing project_registry from this folder
sys.path.insert(0, str(THIS_DIR))
from project_registry import ProjectRegistry  # noqa: E402

# Allow importing tracker from python_template (optional)
_TRACKER_TEMPLATE_DIR = AI_SCRIPTS_DIR / "python_template"
_TRACKER_DB_PATH = Path(
    os.getenv("TRACKER_DB_PATH") or str(_TRACKER_TEMPLATE_DIR / ".tracker" / "projects.db")
)
try:
    sys.path.insert(0, str(_TRACKER_TEMPLATE_DIR))
    from src.tracker import ProjectTracker  # noqa: E402
    _HAS_TRACKER = True
except (ImportError, ModuleNotFoundError):
    _HAS_TRACKER = False

ONENOTE_SCRIPT = THIS_DIR / "IRE-OneNote.ps1"
REPORTS_DIR = THIS_DIR / "weekly_reports"

# File extensions considered "code/config" for the change scan
_CODE_EXTENSIONS = {
    ".py", ".ps1", ".sh", ".js", ".ts", ".json", ".yaml", ".yml",
    ".toml", ".cfg", ".ini", ".md", ".sql", ".html", ".css",
    ".tf", ".bicep", ".dockerfile", ".env.example",
}
_SKIP_DIRS = {".venv", ".git", "__pycache__", ".pytest_cache", "node_modules",
              ".mypy_cache", "dist", "build", ".tracker"}

# ── Intel Work Week helpers ───────────────────────────────────────────────────

def _jan1_sunday(year: int) -> date:
    """Return the Sunday on or before Jan 1 of `year` (WW1 start)."""
    jan1 = date(year, 1, 1)
    # Python weekday(): Mon=0..Sun=6.  .NET DayOfWeek: Sun=0..Sat=6.
    # To match PS formula: AddDays(-DayOfWeek)  →  subtract (weekday+1)%7 days
    dow_net = (jan1.weekday() + 1) % 7   # 0=Sun, 1=Mon, …, 6=Sat
    return jan1 - timedelta(days=dow_net)


def intel_ww(d: date) -> int:
    """Return the Intel work-week number for date `d`."""
    return (d - _jan1_sunday(d.year)).days // 7 + 1


def ww_range(year: int, ww: int) -> tuple[date, date]:
    """Return (sunday, saturday) for the given Intel WW."""
    start = _jan1_sunday(year) + timedelta(weeks=ww - 1)
    return start, start + timedelta(days=6)


def parse_ww_arg(ww_str: str) -> tuple[int, int]:
    """Parse 'WW24' or 'WW24-2026' → (year, week_num)."""
    today = date.today()
    ww_str = ww_str.strip().upper()
    if "-" in ww_str:
        ww_part, year_part = ww_str.split("-", 1)
        week_num = int(ww_part.lstrip("WW"))
        year = int(year_part)
    else:
        week_num = int(ww_str.lstrip("WW"))
        year = today.year
    return year, week_num


def section_name(d: date) -> str:
    """Return the OneNote section name for a date, e.g. 'June 2026'."""
    return d.strftime("%B %Y")


# ── File-change scanner ───────────────────────────────────────────────────────

def scan_changes(project_path: str, start: date, end: date) -> list[dict]:
    """Return files under project_path modified in [start, end] (inclusive).

    Each entry: {path: str, modified: str (ISO date), extension: str}
    Skips virtualenvs, caches, and binary files.
    """
    root = Path(project_path)
    if not root.exists():
        return []

    changes: list[dict] = []
    start_ts = datetime(start.year, start.month, start.day, tzinfo=timezone.utc).timestamp()
    # end is inclusive through end-of-day
    end_ts = datetime(end.year, end.month, end.day, 23, 59, 59, tzinfo=timezone.utc).timestamp()

    for f in root.rglob("*"):
        if not f.is_file():
            continue
        # Skip excluded directories anywhere in the path
        if any(skip in f.parts for skip in _SKIP_DIRS):
            continue
        if f.suffix.lower() not in _CODE_EXTENSIONS and f.name not in {
            "Dockerfile", "Makefile", ".env.example"
        }:
            continue
        try:
            mtime = f.stat().st_mtime
        except OSError:
            continue
        if start_ts <= mtime <= end_ts:
            changes.append({
                "path": str(f.relative_to(root)),
                "modified": datetime.fromtimestamp(mtime, tz=timezone.utc).strftime("%Y-%m-%d"),
                "extension": f.suffix.lower(),
            })

    changes.sort(key=lambda x: (x["modified"], x["path"]))
    return changes


# ── Tracker reader ────────────────────────────────────────────────────────────

def _tracker_events_for_project(project_name: str, start: date, end: date) -> list[dict]:
    """Read events + notes from the tracker DB for a project within the WW."""
    if not _HAS_TRACKER or not _TRACKER_DB_PATH.exists():
        return []

    try:
        tracker = ProjectTracker(db_path=_TRACKER_DB_PATH, registry_path=None)
        all_events = tracker.history(project_name)
        all_notes  = tracker.get_notes(project_name)
    except Exception:
        return []

    combined: list[dict] = []
    start_iso = start.isoformat()
    end_iso   = (end + timedelta(days=1)).isoformat()  # exclusive upper bound

    for e in all_events:
        ts = e.get("occurred_at", "")
        if start_iso <= ts[:10] < end_iso:
            combined.append({"kind": "event", **e})

    for n in all_notes:
        ts = n.get("created_at", "")
        if start_iso <= ts[:10] < end_iso:
            combined.append({
                "kind": "note",
                "event_type": "note",
                "detail": {"body": n["body"]},
                "occurred_at": n["created_at"],
            })

    combined.sort(key=lambda x: x.get("occurred_at", ""))
    return combined


# ── Report builder ────────────────────────────────────────────────────────────

def _fmt_event(e: dict) -> str:
    """Format a single tracker event into a one-line human string."""
    et = e.get("event_type", "")
    detail = e.get("detail", {})
    if et == "created":
        desc = detail.get("description", "")
        return f"Project created{f' — {desc}' if desc else ''}"
    if et == "feature_added":
        feat = detail.get("feature", "")
        desc = detail.get("description", "")
        return f"Feature added: {feat}{f' — {desc}' if desc else ''}"
    if et == "description_updated":
        return f"Description updated: \"{detail.get('after', '')}\""
    if et == "completed":
        return "Project marked complete"
    if et == "note":
        return f"Note: {detail.get('body', '')}"
    return f"{et}: {json.dumps(detail)}"


def build_report(
    year: int,
    ww: int,
    registry: ProjectRegistry,
    author: str = "",
) -> dict:
    """Gather all data for the report. Returns a structured dict."""
    if not author:
        author = _DEFAULT_AUTHOR
    start, end = ww_range(year, ww)
    projects = registry.list_all()

    sections: list[dict] = []
    all_changes: list[dict] = []

    for p in projects:
        proj_path = p.get("project_path", "")
        changes   = scan_changes(proj_path, start, end) if proj_path else []
        events    = _tracker_events_for_project(p["name"], start, end)

        if not changes and not events:
            continue  # Skip projects with no activity this WW

        all_changes.extend(
            {"project": p["name"], **c} for c in changes
        )
        sections.append({
            "name":    p["name"],
            "status":  p.get("status", "active"),
            "desc":    p.get("description", ""),
            "changes": changes,
            "events":  events,
        })

    return {
        "ww":       f"WW{ww}",
        "year":     year,
        "start":    start,
        "end":      end,
        "author":   author,
        "sections": sections,
        "all_changes": all_changes,
    }


# ── Markdown renderer ─────────────────────────────────────────────────────────

def render_markdown(report: dict) -> str:
    ww    = report["ww"]
    start = report["start"]
    end   = report["end"]
    lines: list[str] = []

    lines += [
        f"# {ww} — Week of {start.strftime('%b %d')}–{end.strftime('%b %d, %Y')}",
        f"{report['author']}",
        "=" * 65,
        "",
    ]

    if not report["sections"]:
        lines.append("*No tracked project activity this week.*")
        return "\n".join(lines)

    # Summary table
    lines += ["## Projects Active This Week", ""]
    lines += ["| Project | Status | Activity |", "|---|---|---|"]
    for s in report["sections"]:
        activity_parts = []
        if s["events"]:
            activity_parts.append(f"{len(s['events'])} tracker event(s)")
        if s["changes"]:
            activity_parts.append(f"{len(s['changes'])} file change(s)")
        lines.append(
            f"| {s['name']} | {s['status']} | {', '.join(activity_parts)} |"
        )
    lines.append("")

    # Per-project detail
    lines.append("## Activity by Project")
    lines.append("")
    for s in report["sections"]:
        lines.append(f"### {s['name']}")
        if s["desc"]:
            lines.append(f"*{s['desc']}*")
        lines.append("")

        if s["events"]:
            lines.append("**Tracker Activity**")
            for e in s["events"]:
                ts = e.get("occurred_at", "")[:10]
                lines.append(f"- `{ts}` {_fmt_event(e)}")
            lines.append("")

        if s["changes"]:
            lines.append("**Files Changed**")
            for c in s["changes"]:
                lines.append(f"- `{c['modified']}` {c['path']}")
            lines.append("")

    return "\n".join(lines)


# ── HTML renderer (for OneNote) ───────────────────────────────────────────────

def render_html(report: dict) -> str:
    ww    = report["ww"]
    start = report["start"]
    end   = report["end"]

    parts: list[str] = [
        f"<h2>{ww} — Week of {start.strftime('%b %d')}–{end.strftime('%b %d, %Y')}</h2>",
        f"<p><em>{report['author']}</em></p>",
        "<hr/>",
    ]

    if not report["sections"]:
        parts.append("<p><em>No tracked project activity this week.</em></p>")
        return "".join(parts)

    parts.append("<h3>Projects Active This Week</h3>")
    parts.append("<table><tr><th>Project</th><th>Status</th><th>Activity</th></tr>")
    for s in report["sections"]:
        activity_parts = []
        if s["events"]:
            activity_parts.append(f"{len(s['events'])} tracker event(s)")
        if s["changes"]:
            activity_parts.append(f"{len(s['changes'])} file change(s)")
        parts.append(
            f"<tr><td>{s['name']}</td><td>{s['status']}</td>"
            f"<td>{', '.join(activity_parts)}</td></tr>"
        )
    parts.append("</table>")

    parts.append("<h3>Activity by Project</h3>")
    for s in report["sections"]:
        parts.append(f"<h4>{s['name']}</h4>")
        if s["desc"]:
            parts.append(f"<p><em>{s['desc']}</em></p>")

        if s["events"]:
            parts.append("<p><strong>Tracker Activity</strong></p><ul>")
            for e in s["events"]:
                ts = e.get("occurred_at", "")[:10]
                parts.append(f"<li><code>{ts}</code> {_fmt_event(e)}</li>")
            parts.append("</ul>")

        if s["changes"]:
            parts.append("<p><strong>Files Changed</strong></p><ul>")
            for c in s["changes"]:
                parts.append(f"<li><code>{c['modified']}</code> {c['path']}</li>")
            parts.append("</ul>")

    return "".join(parts)


# ── Email sender ──────────────────────────────────────────────────────────────

_MAIL_SCOPES = ["https://graph.microsoft.com/Mail.Send"]
_MAIL_DEFAULT_TO = os.getenv("REPORT_MAIL_TO", "")
_DEFAULT_AUTHOR  = os.getenv(
    "REPORT_AUTHOR", "Your Name | Your Team"
)


def send_mail(html: str, ww_label: str, start: date, end: date, to: str = _MAIL_DEFAULT_TO) -> None:
    """Send the weekly report as an HTML email via Microsoft Graph."""
    try:
        from graph_auth import get_credential  # noqa: E402
    except ImportError:
        print("  ⚠  graph_auth.py not found — cannot send email.", file=sys.stderr)
        return

    import urllib.request

    subject = (
        f"{ww_label} IRE Weekly Status Report"
        f" — {start.strftime('%b %d')}–{end.strftime('%b %d, %Y')}"
    )

    payload = json.dumps({
        "message": {
            "subject": subject,
            "body": {"contentType": "HTML", "content": html},
            "toRecipients": [{"emailAddress": {"address": to}}],
        },
        "saveToSentItems": True,
    }).encode("utf-8")

    print(f"\n  Sending email to {to} ...")
    try:
        cred = get_credential(_MAIL_SCOPES, cache_name="IRE-mail-token-cache")
        token = cred.get_token(*_MAIL_SCOPES).token
        req = urllib.request.Request(
            "https://graph.microsoft.com/v1.0/me/sendMail",
            data=payload,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req) as resp:
            if resp.status == 202:
                print(f"  ✔  Email sent to {to}")
            else:
                print(f"  ⚠  Unexpected response: {resp.status}", file=sys.stderr)
    except Exception as exc:  # noqa: BLE001
        print(f"  ⚠  Email failed: {exc}", file=sys.stderr)


# ── OneNote poster ────────────────────────────────────────────────────────────

def post_to_onenote(html: str, ww_label: str, section: str) -> None:
    """Call IRE-OneNote.ps1 to append the HTML to the current WW page."""
    if not ONENOTE_SCRIPT.exists():
        print(f"  ⚠  IRE-OneNote.ps1 not found at {ONENOTE_SCRIPT}", file=sys.stderr)
        return

    # Escape double-quotes in HTML for PowerShell string passing
    escaped = html.replace('"', '`"')
    cmd = [
        "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
        "-File", str(ONENOTE_SCRIPT),
        "-Action", "AppendToPage",
        "-WorkWeek", ww_label,
        "-SectionName", section,
        "-Content", escaped,
    ]
    print(f"\n  Posting to OneNote: {section} > {ww_label} ...")
    result = subprocess.run(cmd, capture_output=False, text=True)
    if result.returncode != 0:
        print(f"  ⚠  IRE-OneNote.ps1 exited with code {result.returncode}", file=sys.stderr)
    else:
        print(f"  ✔  Posted to OneNote successfully")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    today = date.today()
    current_ww = intel_ww(today)

    parser = argparse.ArgumentParser(
        description="Generate an IRE weekly status report."
    )
    ww_group = parser.add_mutually_exclusive_group()
    ww_group.add_argument(
        "--ww", metavar="WW24",
        help="Work week to report on, e.g. WW24 or WW24-2026 (default: current WW)",
    )
    ww_group.add_argument(
        "--prev", action="store_true",
        help="Report on the last completed work week (WW before current)",
    )
    parser.add_argument(
        "--post", action="store_true",
        help="Post the report to OneNote via IRE-OneNote.ps1",
    )
    parser.add_argument(
        "--mail", action="store_true",
        help="Email the report via Microsoft Graph (Mail.Send)",
    )
    parser.add_argument(
        "--mail-to", metavar="ADDRESS", default=_MAIL_DEFAULT_TO,
        help=f"Recipient address for --mail (default: REPORT_MAIL_TO from .env)",
    )
    parser.add_argument(
        "--out", metavar="PATH", default=None,
        help="Override the output markdown path",
    )
    parser.add_argument(
        "--author", default=_DEFAULT_AUTHOR,
        help="Author line shown in the report header",
    )
    parser.add_argument(
        "--registry", type=Path, default=None,
        help="Override the projects.json registry path",
    )
    args = parser.parse_args()

    # Resolve year + WW
    if args.prev:
        ww_num  = current_ww - 1 if current_ww > 1 else 52
        ww_year = today.year if current_ww > 1 else today.year - 1
    elif args.ww:
        ww_year, ww_num = parse_ww_arg(args.ww)
    else:
        ww_year, ww_num = today.year, current_ww

    ww_label    = f"WW{ww_num}"
    start, end  = ww_range(ww_year, ww_num)
    sect_name   = section_name(start)

    print(f"\n  IRE Weekly Status Report Generator")
    print(f"  ──────────────────────────────────────────")
    print(f"  Report  : {ww_label} ({start} – {end})")
    print(f"  Section : {sect_name}")
    print(f"  Today   : {today}  (current: WW{current_ww})")
    if _HAS_TRACKER:
        print(f"  Tracker : {_TRACKER_DB_PATH}")
    else:
        print(f"  Tracker : not available (python_template not found)")
    print()

    registry = ProjectRegistry(registry_path=args.registry)
    report   = build_report(ww_year, ww_num, registry, author=args.author)

    md   = render_markdown(report)
    html = render_html(report)

    # Save markdown
    REPORTS_DIR.mkdir(exist_ok=True)
    out_path = Path(args.out) if args.out else REPORTS_DIR / f"{ww_label}-{ww_year}.md"
    out_path.write_text(md, encoding="utf-8")
    print(f"  ✔  Markdown saved : {out_path}")

    # Print preview
    print()
    print("─" * 65)
    print(md)
    print("─" * 65)

    if args.post:
        post_to_onenote(html, ww_label, sect_name)
    else:
        print(f"\n  Tip: add --post to push this directly to OneNote ({sect_name} > {ww_label})")

    if args.mail:
        if not args.mail_to:
            print("  ⚠  --mail requires a recipient. Set REPORT_MAIL_TO in .env or pass --mail-to.", file=sys.stderr)
        else:
            send_mail(html, ww_label, start, end, to=args.mail_to)
    elif not args.post:
        print(f"  Tip: add --mail to email this report (set REPORT_MAIL_TO in .env)")


if __name__ == "__main__":
    main()
