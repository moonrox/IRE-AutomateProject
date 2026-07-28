"""
version.py — Version tracking and execution history for IRE PowerAutomate scripts.

Usage (CLI):
    python version.py               # show version + last 10 history entries
    python version.py --history 20  # show last N entries
    python version.py --changelog   # show full changelog
    python version.py --log "script" "action" "details"  # append a log entry
"""
from __future__ import annotations

import argparse
import json
import os
import socket
from datetime import datetime
from pathlib import Path

# ── Version ──────────────────────────────────────────────────────────────────

__version__ = "1.0.0"

# ── Changelog ────────────────────────────────────────────────────────────────

CHANGELOG: list[dict] = [
    {
        "version": "1.0.0",
        "date": "2026-05-30",
        "changes": [
            "Initial Python port of IRE-SharePoint.ps1 and IRE-OneNote.ps1",
            "Added graph_auth.py — MSAL DeviceCodeCredential with DPAPI-backed cache",
            "Added .env configuration; hardcoded values removed from all scripts",
            "Added .gitignore covering secrets, token caches, and history log",
            "Added version.py — centralised version tracking and execution history",
        ],
    },
]

# ── History log ──────────────────────────────────────────────────────────────

_ROOT = Path(__file__).resolve().parent
HISTORY_FILE = _ROOT / "history.jsonl"


def log_run(
    script: str,
    action: str,
    details: str = "",
    success: bool = True,
) -> None:
    """Append one JSON line to history.jsonl.

    Keep ``details`` short and free of tokens, passwords, or full content bodies.
    """
    entry = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "version": __version__,
        "script": script,
        "action": action,
        "details": details,
        "success": success,
        "user": os.environ.get("USERNAME") or os.environ.get("USER", "unknown"),
        "host": socket.gethostname(),
    }
    # Append is atomic enough for single-user scenarios; each line is self-contained JSON.
    with open(HISTORY_FILE, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")


def show_history(n: int = 10) -> None:
    if not HISTORY_FILE.exists():
        print("No history yet.")
        return
    lines = HISTORY_FILE.read_text(encoding="utf-8").splitlines()
    recent = lines[-n:]
    print(f"\n{'─'*60}")
    print(f"  Execution History  (last {len(recent)} of {len(lines)} entries)")
    print(f"{'─'*60}")
    for line in recent:
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        status = "✅" if e.get("success") else "❌"
        ts = e.get("timestamp", "")[:19]
        print(f"  {status}  {ts}   {e.get('script','?')}:{e.get('action','?')}")
        if e.get("details"):
            print(f"       {e['details']}")
    print()


def show_changelog() -> None:
    print(f"\n{'─'*60}")
    print("  IRE PowerAutomate — Changelog")
    print(f"{'─'*60}")
    for entry in reversed(CHANGELOG):
        print(f"\n  v{entry['version']}  ({entry['date']})")
        for change in entry["changes"]:
            print(f"    • {change}")
    print()


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="IRE script version and history viewer")
    parser.add_argument("--history", type=int, metavar="N", default=10,
                        help="Show last N history entries (default: 10)")
    parser.add_argument("--changelog", action="store_true",
                        help="Show full changelog")
    parser.add_argument("--log", nargs=3, metavar=("SCRIPT", "ACTION", "DETAILS"),
                        help="Append a history entry (used by scripts)")
    args = parser.parse_args()

    if args.log:
        log_run(script=args.log[0], action=args.log[1], details=args.log[2])
        return

    print(f"\n  IRE PowerAutomate Scripts  v{__version__}")

    if args.changelog:
        show_changelog()
    else:
        show_history(args.history)


if __name__ == "__main__":
    main()
