"""weekly_mcp.py - MCP server for the IRE automated weekly status report.

Exposes the weekly_auto pipeline as Model Context Protocol tools over **stdio**
transport, so it runs locally in the caller's own Windows session: Outlook COM
(calendar), the caller's cached Graph token (email + transcripts), and the
caller's git credentials all resolve to *that* user. Nothing runs on a shared
server - IREDEV01 only hosts documentation and the registry entry.

Tools
-----
- list_sources()                          : show configured/enabled sources
- preview_weekly(ww?)                      : dry-run; return the Markdown report
- generate_weekly(ww?)                     : build + write the .md deliverable
- publish_weekly(ww?, upload?, email?)     : build + SharePoint upload + email
- fetch_transcripts(ww?)                   : capture organized+transcribed VTT
- set_notes(blockers?, next_week?)         : update weekly_notes.md sections

Run:
    python weekly_mcp.py            # stdio (for an MCP client / mcp.json)
"""
from __future__ import annotations

import os
from pathlib import Path

from fastmcp import FastMCP

import run_weekly as rw
from weekly_auto import collectors, report_builder
from weekly_auto.graph_client import GraphAuthError, GraphClient
from weekly_auto.util import work_week, work_week_from_label

THIS_DIR = Path(__file__).resolve().parent
mcp = FastMCP("ire-automate-weekly")


def _resolve_ww(ww: str | None):
    return work_week_from_label(ww) if ww else work_week()


def _collect(cfg: dict, ww) -> list:
    results = collectors.collect_all(cfg.get("sources", []), ww)
    results.extend(rw._collect_email_sources(cfg, ww))
    results.extend(rw._collect_calendar_sources(cfg, ww))
    results.extend(rw._collect_transcript_sources(cfg, ww))
    return results


def _build_md(cfg: dict, ww, results: list) -> str:
    notes = report_builder.read_notes(THIS_DIR / cfg.get("notes_file", "weekly_notes.md"))
    author = cfg.get("author", "Your Name")
    return report_builder.build_markdown(ww, author, results, notes)


@mcp.tool()
def list_sources() -> dict:
    """List every configured source and whether it is enabled, for the current config."""
    cfg = rw._load_config()
    out = {
        "author": cfg.get("author"),
        "sources": [
            {"type": s.get("type"), "name": s.get("name"),
             "path": s.get("path") or s.get("root")}
            for s in cfg.get("sources", [])
        ],
        "email_source_enabled": bool(cfg.get("email_source", {}).get("enabled")),
        "calendar_source_enabled": bool(cfg.get("calendar_source", {}).get("enabled")),
        "transcript_source_enabled": bool(cfg.get("transcript_source", {}).get("enabled")),
    }
    return out


@mcp.tool()
def preview_weekly(ww: str | None = None) -> dict:
    """Dry-run the weekly for `ww` (e.g. 'WW30'); collect + render Markdown, no upload/email.

    Runs entirely locally under the caller's credentials. Returns the report
    Markdown plus per-source item counts and any coverage warnings.
    """
    cfg = rw._load_config()
    wk = _resolve_ww(ww)
    results = _collect(cfg, wk)
    md = _build_md(cfg, wk, results)
    return {
        "work_week": wk.human,
        "window": f"{wk.since_iso} .. {wk.end.isoformat()}",
        "total_items": sum(len(r.items) for r in results),
        "warnings": [f"{r.name}: {r.warning}" for r in results if r.warning],
        "markdown": md,
    }


@mcp.tool()
def generate_weekly(ww: str | None = None) -> dict:
    """Build the weekly for `ww` and write the .md deliverable to weekly_reports/.

    Does NOT upload or email. Returns the written path and the Markdown.
    """
    cfg = rw._load_config()
    wk = _resolve_ww(ww)
    results = _collect(cfg, wk)
    md = _build_md(cfg, wk, results)
    name = cfg.get("sharepoint_name_template", "{ww}-Weekly.md").format(
        ww=wk.label, year=wk.year)
    reports_dir = THIS_DIR / "weekly_reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    path = reports_dir / name
    path.write_text(md, encoding="utf-8")
    return {"work_week": wk.human, "path": str(path), "markdown": md}


@mcp.tool()
def publish_weekly(ww: str | None = None, upload: bool = True, email: bool = True) -> dict:
    """Build, then SharePoint-upload and/or email the weekly for `ww`.

    Requires DEV_TENANT_ID / DEV_CLIENT_ID / SITE_ID in the environment and a
    valid cached Graph token. Returns the SharePoint URL and delivery status.
    """
    cfg = rw._load_config()
    wk = _resolve_ww(ww)
    results = _collect(cfg, wk)
    md = _build_md(cfg, wk, results)
    name = cfg.get("sharepoint_name_template", "{ww}-Weekly.md").format(
        ww=wk.label, year=wk.year)
    reports_dir = THIS_DIR / "weekly_reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    path = reports_dir / name
    path.write_text(md, encoding="utf-8")

    tenant = os.getenv("DEV_TENANT_ID", "")
    client = os.getenv("DEV_CLIENT_ID", "")
    site = os.getenv("SITE_ID", "")
    if not (tenant and client and site):
        return {"error": "DEV_TENANT_ID / DEV_CLIENT_ID / SITE_ID missing from environment",
                "path": str(path)}
    graph = GraphClient(tenant, client, site)
    status: dict = {"work_week": wk.human, "path": str(path)}

    if upload:
        try:
            folder = cfg.get("sharepoint_folder", "weeklies")
            status["sharepoint_url"] = graph.upload_to_library(folder, name, path)
        except (GraphAuthError, Exception) as exc:  # noqa: BLE001
            status["upload_error"] = str(exc)[:200]

    ecfg = cfg.get("email", {})
    if email and ecfg.get("enabled"):
        try:
            subject = ecfg.get("subject_template", "IRE Weekly Status - {ww}").format(
                ww=wk.label, year=wk.year)
            html = report_builder.markdown_to_html(report_builder.summary_markdown(md))
            url = status.get("sharepoint_url", "")
            banner = (f"<p><b>SharePoint:</b> <a href=\"{url}\">{name}</a> "
                      f"(also attached)</p>") if url else ""
            graph.send_mail(ecfg.get("to", []), subject, banner + html, path)
            status["emailed_to"] = ecfg.get("to", [])
        except (GraphAuthError, Exception) as exc:  # noqa: BLE001
            status["email_error"] = str(exc)[:200]
    return status


@mcp.tool()
def fetch_transcripts(ww: str | None = None) -> dict:
    """Capture Teams meeting transcripts (VTT) you ORGANIZED and had transcribed in `ww`.

    Delegated access is organizer-only and needs OnlineMeetingTranscript.Read.All
    consent. Saves .vtt files under transcripts/ and returns a short summary per
    captured meeting.
    """
    cfg = rw._load_config()
    wk = _resolve_ww(ww)
    tenant = os.getenv("DEV_TENANT_ID", "")
    client = os.getenv("DEV_CLIENT_ID", "")
    site = os.getenv("SITE_ID", "")
    if not (tenant and client):
        return {"error": "DEV_TENANT_ID / DEV_CLIENT_ID missing from environment"}
    graph = GraphClient(tenant, client, site)
    tr_src = cfg.get("transcript_source", {})
    out_dir = THIS_DIR / tr_src.get("out_dir", "transcripts")
    res = collectors.collect_transcripts(
        tr_src.get("name", "Meeting Transcripts"), graph, wk, out_dir,
        keywords=tr_src.get("subject_keywords"),
        exclude=tr_src.get("exclude_keywords"),
        max_items=int(tr_src.get("max_items", 20)),
    )
    return {
        "work_week": wk.human,
        "warning": res.warning or None,
        "captured": [{"summary": it.title, "date": it.date, "file": it.ref}
                     for it in res.items],
    }


@mcp.tool()
def set_notes(blockers: list[str] | None = None, next_week: list[str] | None = None) -> dict:
    """Overwrite the [Blockers] and/or [Next Week] sections of weekly_notes.md.

    Pass a list of bullet strings for either section. Omitted sections are left
    unchanged. The Progress section is always auto-generated from source activity.
    """
    notes_path = THIS_DIR / rw._load_config().get("notes_file", "weekly_notes.md")
    existing = report_builder.read_notes(notes_path)
    blk = blockers if blockers is not None else existing.get("blockers", [])
    nxt = next_week if next_week is not None else existing.get("next_week", [])
    lines = ["# Weekly Status Notes", "",
             "Auto-managed sections consumed by the weekly report.", "",
             "[Blockers]"]
    lines += [f"- {b}" for b in blk] or ["- None."]
    lines += ["", "[Next Week]"]
    lines += [f"- {n}" for n in nxt] or ["- TBD."]
    notes_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"path": str(notes_path), "blockers": blk, "next_week": nxt}


if __name__ == "__main__":
    mcp.run()
