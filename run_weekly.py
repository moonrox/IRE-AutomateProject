"""run_weekly.py - orchestrate the automated IRE weekly status report.

Steps:
  1. Load the source registry (weekly_sources.json).
  2. Collect changes from every source for the target work week.
  3. Build Markdown + Word report in the standard Progress/Blockers/Next-Week form.
  4. Upload the .docx to the IRE SharePoint 'weeklies' library.
  5. Email a copy (with attachment) to the configured recipient(s).

Designed to run unattended from a Scheduled Task (Wed 17:00). Auth reuses the
already-consented Sites.ReadWrite.All + Mail.Send delegated token cached by the
IRE Graph PowerShell scripts (no OneNote / admin-consent dependency).

Usage:
    python run_weekly.py                 # current work week, upload + email
    python run_weekly.py --ww WW30       # specific work week
    python run_weekly.py --no-upload     # build only
    python run_weekly.py --no-email      # skip email
    python run_weekly.py --dry-run       # build locally, no SharePoint/email
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(THIS_DIR))

try:
    from dotenv import load_dotenv
    load_dotenv(THIS_DIR / ".env", override=False)
except ImportError:
    pass

from weekly_auto import collectors, report_builder  # noqa: E402
from weekly_auto.graph_client import GraphAuthError, GraphClient  # noqa: E402
from weekly_auto.util import work_week, work_week_from_label  # noqa: E402

REPORTS_DIR = THIS_DIR / "weekly_reports"
CONFIG_PATH = THIS_DIR / "weekly_sources.json"


def _load_config() -> dict:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def _collect_email_sources(cfg: dict, ww) -> list:
    """Scan Outlook mail (Graph Mail.Read) if email_source is enabled.

    Runs during collection so mail highlights appear even on --dry-run. Never
    raises: missing creds or scope gaps become a source-coverage warning.
    """
    email_src = cfg.get("email_source", {})
    if not email_src.get("enabled"):
        return []

    name = email_src.get("name", "Outlook Email")
    tenant = os.getenv("DEV_TENANT_ID", "")
    client = os.getenv("DEV_CLIENT_ID", "")
    site = os.getenv("SITE_ID", "")
    if not (tenant and client):
        r = collectors.SourceResult(name=name, kind="email")
        r.warning = "email scan skipped: DEV_TENANT_ID / DEV_CLIENT_ID missing from .env"
        return [r]

    graph = GraphClient(tenant, client, site)
    print(f"[weekly] Scanning Outlook mail: folders={email_src.get('folders', ['Inbox'])}")
    return [collectors.collect_email(
        name,
        graph,
        email_src.get("folders", ["Inbox"]),
        ww,
        keywords=email_src.get("subject_keywords"),
        max_items=int(email_src.get("max_items", 25)),
    )]


def main() -> int:
    ap = argparse.ArgumentParser(description="Automated IRE weekly status report")
    ap.add_argument("--ww", help="Target work week, e.g. WW30 or WW30-2026")
    ap.add_argument("--no-upload", action="store_true", help="Do not upload to SharePoint")
    ap.add_argument("--no-email", action="store_true", help="Do not send the email")
    ap.add_argument("--dry-run", action="store_true", help="Build only; no SharePoint/email")
    args = ap.parse_args()

    cfg = _load_config()
    ww = work_week_from_label(args.ww) if args.ww else work_week()
    author = cfg.get("author", "John Monroe")
    author_title = cfg.get("author_title", "Infrastructure Reliability Engineering")

    print(f"[weekly] Building {ww.human}")
    print(f"[weekly] Window: {ww.since_iso} .. {ww.end.isoformat()}")

    results = collectors.collect_all(cfg.get("sources", []), ww)
    results.extend(_collect_email_sources(cfg, ww))
    total_items = sum(len(r.items) for r in results)
    warned = [r for r in results if r.warning]
    print(f"[weekly] Collected {total_items} change item(s) from {len(results)} source(s); "
          f"{len(warned)} source warning(s).")

    notes = report_builder.read_notes(THIS_DIR / cfg.get("notes_file", "weekly_notes.md"))

    md = report_builder.build_markdown(ww, author, results, notes)
    md_path = REPORTS_DIR / f"{ww.label}-{ww.year}.md"
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    md_path.write_text(md, encoding="utf-8")
    print(f"[weekly] Wrote {md_path}")

    docx_name = cfg.get("sharepoint_name_template", "{ww}-Weekly.docx").format(
        ww=ww.label, year=ww.year)
    docx_path = REPORTS_DIR / docx_name
    report_builder.build_docx(ww, author, author_title, results, notes, docx_path)
    print(f"[weekly] Wrote {docx_path}")

    if args.dry_run:
        print("[weekly] Dry run - skipping SharePoint upload and email.")
        return 0

    tenant = os.getenv("DEV_TENANT_ID", "")
    client = os.getenv("DEV_CLIENT_ID", "")
    site = os.getenv("SITE_ID", "")
    if not (tenant and client and site):
        print("[weekly] ERROR: DEV_TENANT_ID / DEV_CLIENT_ID / SITE_ID missing from .env")
        return 2

    graph = GraphClient(tenant, client, site)

    upload_ok = False
    sharepoint_url = ""
    if not args.no_upload:
        try:
            folder = cfg.get("sharepoint_folder", "weeklies")
            url = graph.upload_to_library(folder, docx_name, docx_path)
            print(f"[weekly] Uploaded to SharePoint: {url}")
            sharepoint_url = url
            upload_ok = True
        except GraphAuthError as exc:
            print(f"[weekly] AUTH ERROR (re-auth needed): {exc}")
        except Exception as exc:  # noqa: BLE001
            print(f"[weekly] Upload failed: {exc}")

    email_cfg = cfg.get("email", {})
    if not args.no_email and email_cfg.get("enabled"):
        try:
            subject = email_cfg.get("subject_template", "IRE Weekly Status - {ww}").format(
                ww=ww.label, year=ww.year)
            html = report_builder.markdown_to_html(md)
            if sharepoint_url:
                banner = (f"<p><b>SharePoint:</b> "
                          f"<a href=\"{sharepoint_url}\">{docx_name}</a> "
                          f"(also attached)</p>")
            elif not args.no_upload:
                banner = ("<p style='color:#a00'><b>Note:</b> SharePoint upload did not "
                          "complete this run; see attached/inline report.</p>")
            else:
                banner = ""
            graph.send_mail(email_cfg.get("to", []), subject, banner + html, docx_path)
            print(f"[weekly] Emailed report to {', '.join(email_cfg.get('to', []))}")
        except GraphAuthError as exc:
            print(f"[weekly] AUTH ERROR (re-auth needed): {exc}")
        except Exception as exc:  # noqa: BLE001
            print(f"[weekly] Email failed: {exc}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
