"""weekly_auto.collectors - gather change items from all registered sources.

Each collector returns a list of ChangeItem. Collectors degrade gracefully:
an unreachable UNC path or a non-git folder produces a warning item rather than
crashing the whole run.
"""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .util import WorkWeek

_CODE_EXTS = {
    ".py", ".ps1", ".sh", ".js", ".ts", ".json", ".yaml", ".yml", ".toml",
    ".cfg", ".ini", ".md", ".sql", ".html", ".css", ".tf", ".bicep",
}
_SKIP_DIRS = {".venv", ".git", "__pycache__", ".pytest_cache", "node_modules",
              ".mypy_cache", ".ruff_cache", "dist", "build", ".tracker",
              ".code-review-graph"}
_ADR_RE = re.compile(r"ADR[-_ ]?(\d{2,4})", re.IGNORECASE)


@dataclass
class ChangeItem:
    source: str          # human name of the source
    category: str        # 'commit' | 'adr' | 'file' | 'warning'
    title: str
    date: str = ""       # ISO date
    ref: str = ""        # commit hash / file path / adr id


@dataclass
class SourceResult:
    name: str
    kind: str
    items: list[ChangeItem] = field(default_factory=list)
    warning: str = ""


# ── git helpers ──────────────────────────────────────────────────────────────

def _git(repo: Path, *args: str) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), "--no-pager", *args],
            capture_output=True, text=True, timeout=120,
        )
        return proc.returncode, (proc.stdout or "") + (proc.stderr or "")
    except (OSError, subprocess.SubprocessError) as exc:
        return 1, str(exc)


def _is_git_repo(path: Path) -> bool:
    return (path / ".git").exists()


def collect_git_repo(name: str, path: str, ww: WorkWeek, all_branches: bool = False) -> SourceResult:
    res = SourceResult(name=name, kind="git_repo")
    repo = Path(path)
    if not repo.exists():
        res.warning = f"path not reachable: {path}"
        return res
    if not _is_git_repo(repo):
        res.warning = f"not a git repo: {path}"
        return res
    args = ["log", f"--since={ww.since_iso}", f"--until={ww.until_iso}",
            "--pretty=format:%h%x1f%ad%x1f%an%x1f%s", "--date=short"]
    if all_branches:
        args.insert(1, "--all")
    code, out = _git(repo, *args)
    if code != 0:
        res.warning = f"git log failed: {out.strip()[:160]}"
        return res
    for line in out.splitlines():
        if "\x1f" not in line:
            continue
        h, d, author, subject = (line.split("\x1f") + ["", "", "", ""])[:4]
        res.items.append(ChangeItem(name, "commit", subject, d, h))
    return res


def collect_git_scan(name: str, root: str, ww: WorkWeek, max_depth: int = 1,
                     exclude: list[str] | None = None) -> list[SourceResult]:
    """Discover git repos under `root` and collect commits from each."""
    exclude = {e.lower() for e in (exclude or [])}
    root_path = Path(root)
    results: list[SourceResult] = []
    if not root_path.exists():
        r = SourceResult(name=name, kind="git_scan")
        r.warning = f"root not reachable: {root}"
        return [r]
    try:
        children = [d for d in root_path.iterdir() if d.is_dir()]
    except OSError as exc:
        r = SourceResult(name=name, kind="git_scan")
        r.warning = f"cannot list {root}: {exc}"
        return [r]
    for child in sorted(children):
        if child.name.lower() in exclude or child.name in _SKIP_DIRS:
            continue
        if _is_git_repo(child):
            results.append(collect_git_repo(child.name, str(child), ww, all_branches=False))
    if not results:
        r = SourceResult(name=name, kind="git_scan")
        r.warning = f"no git repos found under {root}"
        results.append(r)
    return results


def collect_adr(name: str, path: str, ww: WorkWeek, all_branches: bool = False) -> SourceResult:
    """Detect ADR files ADDED to the repo within the WW window."""
    res = SourceResult(name=name, kind="adr")
    repo = Path(path)
    if not repo.exists() or not _is_git_repo(repo):
        res.warning = f"ADR source unavailable: {path}"
        return res
    args = ["log", f"--since={ww.since_iso}", f"--until={ww.until_iso}",
            "--diff-filter=A", "--name-only",
            "--pretty=format:%x1e%ad", "--date=short"]
    if all_branches:
        args.insert(1, "--all")
    code, out = _git(repo, *args)
    if code != 0:
        res.warning = f"git log failed: {out.strip()[:160]}"
        return res
    seen: set[str] = set()
    cur_date = ""
    for line in out.splitlines():
        if line.startswith("\x1e"):
            cur_date = line[1:].strip()
            continue
        f = line.strip()
        if not f:
            continue
        m = _ADR_RE.search(Path(f).name)
        if not m:
            continue
        adr_id = f"ADR-{int(m.group(1)):03d}"
        if adr_id in seen:
            continue
        seen.add(adr_id)
        title = _read_adr_title(repo / f) or Path(f).stem
        res.items.append(ChangeItem(name, "adr", f"{adr_id}: {title}", cur_date, adr_id))
    return res


def _read_adr_title(fp: Path) -> str:
    try:
        if not fp.exists():
            return ""
        for line in fp.read_text(encoding="utf-8", errors="ignore").splitlines():
            s = line.strip().lstrip("#").strip()
            if s:
                return re.sub(r"^ADR[-_ ]?\d+[:\-\s]*", "", s, flags=re.IGNORECASE)[:120]
    except OSError:
        return ""
    return ""


def collect_fs_mtime(name: str, path: str, ww: WorkWeek) -> SourceResult:
    """List code/config files modified within the WW window (non-git fallback)."""
    res = SourceResult(name=name, kind="fs_mtime")
    root = Path(path)
    if not root.exists():
        res.warning = f"path not reachable: {path}"
        return res
    start = datetime.combine(ww.start, datetime.min.time()).timestamp()
    end = datetime.combine(ww.end, datetime.max.time()).timestamp()
    for fp in root.rglob("*"):
        if not fp.is_file() or fp.suffix.lower() not in _CODE_EXTS:
            continue
        if any(part in _SKIP_DIRS for part in fp.parts):
            continue
        try:
            mtime = fp.stat().st_mtime
        except OSError:
            continue
        if start <= mtime <= end:
            rel = fp.relative_to(root)
            res.items.append(
                ChangeItem(name, "file", str(rel),
                           datetime.fromtimestamp(mtime).strftime("%Y-%m-%d"),
                           str(rel))
            )
    return res


def collect_email(name: str, graph, folders: list[str], ww: WorkWeek,
                  keywords: list[str] | None = None,
                  exclude: list[str] | None = None,
                  max_items: int = 25) -> SourceResult:
    """Scan Outlook mail folders (via Graph Mail.Read) for the WW window.

    `graph` is a GraphClient exposing read_messages(). Produces ChangeItem
    (category='email'). Optional `keywords` filter subject/preview
    case-insensitively; `exclude` drops noise (marketing, personal) by matching
    subject/preview/sender case-insensitively. Degrades gracefully: an auth/scope
    gap or API error yields a warning rather than crashing the run.
    """
    from .graph_client import GraphAuthError  # local import: avoids hard dep

    res = SourceResult(name=name, kind="email")
    since = f"{ww.since_iso}T00:00:00Z"
    until = f"{ww.end.isoformat()}T23:59:59Z"
    kws = [k.lower() for k in (keywords or [])]
    excl = [e.lower() for e in (exclude or [])]
    seen: set[str] = set()
    try:
        for folder in folders or ["Inbox"]:
            for m in graph.read_messages(folder, since, until, top=max_items * 2):
                subject = m.get("subject", "")
                blob = f"{subject}\n{m.get('preview', '')}\n{m.get('from', '')}".lower()
                if kws and not any(k in blob for k in kws):
                    continue
                if excl and any(e in blob for e in excl):
                    continue
                key = f"{subject}|{m.get('from', '')}|{m.get('received', '')}"
                if key in seen:
                    continue
                seen.add(key)
                who = m.get("from") or (m.get("to") or [""])[0]
                label = folder.strip()
                title = f"[{label}] {subject} - {who}" if who else f"[{label}] {subject}"
                res.items.append(
                    ChangeItem(name, "email", title, m.get("received", ""), m.get("web_link", ""))
                )
                if len(res.items) >= max_items:
                    return res
    except GraphAuthError as exc:
        res.warning = f"email scan skipped (auth/scope): {str(exc)[:160]}"
    except Exception as exc:  # noqa: BLE001 - never break the run
        res.warning = f"email scan error: {str(exc)[:160]}"
    return res


def collect_calendar(name: str, ww: WorkWeek, lookahead_days: int = 7,
                     meetings_only: bool = True, keywords: list[str] | None = None,
                     exclude: list[str] | None = None,
                     max_items: int = 30) -> SourceResult:
    """Read meeting contents from the LOCAL Outlook client via COM (pywin32).

    This is the non-Graph path: it talks to the user's running Outlook MAPI
    profile / cached mailbox, so it needs NO Graph Calendars.Read permission and
    no Azure app registration. Covers the WW window plus `lookahead_days` of
    upcoming meetings. Produces ChangeItem(category='meeting').

    Degrades gracefully: missing pywin32, no Outlook, or a COM/Object-Model-Guard
    error yields a warning rather than crashing the run.
    """
    from datetime import datetime, timedelta

    res = SourceResult(name=name, kind="calendar")
    kws = [k.lower() for k in (keywords or [])]
    excl = [e.lower() for e in (exclude or [])]

    try:
        import pythoncom  # type: ignore
        import win32com.client  # type: ignore
    except ImportError:
        res.warning = "calendar scan skipped: pywin32 not installed (pip install pywin32)"
        return res

    try:
        pythoncom.CoInitialize()
    except Exception:  # noqa: BLE001 - already initialized is fine
        pass

    try:
        try:
            outlook = win32com.client.GetActiveObject("Outlook.Application")
        except Exception:  # noqa: BLE001 - not running; launch it
            outlook = win32com.client.Dispatch("Outlook.Application")
        mapi = outlook.GetNamespace("MAPI")
        cal = mapi.GetDefaultFolder(9)  # olFolderCalendar

        items = cal.Items
        # Must enable recurrence expansion BEFORE sorting, or recurring meetings
        # only surface on their series master date.
        items.IncludeRecurrences = True
        items.Sort("[Start]")

        start_dt = datetime.combine(ww.start, datetime.min.time())
        end_dt = datetime.combine(ww.end + timedelta(days=lookahead_days), datetime.max.time())
        fmt = "%m/%d/%Y %I:%M %p"
        flt = f"[Start] >= '{start_dt.strftime(fmt)}' AND [Start] <= '{end_dt.strftime(fmt)}'"
        if meetings_only:
            flt += " AND [MeetingStatus] > 0"
        restricted = items.Restrict(flt)

        seen: set[str] = set()
        for appt in restricted:
            try:
                subject = (appt.Subject or "(no subject)").strip()
            except Exception:  # noqa: BLE001
                subject = "(no subject)"
            try:
                organizer = (appt.Organizer or "").strip()
            except Exception:  # noqa: BLE001
                organizer = ""
            try:
                location = (appt.Location or "").strip()
            except Exception:  # noqa: BLE001
                location = ""
            try:
                body = (appt.Body or "").strip()
            except Exception:  # noqa: BLE001 - Object Model Guard may block
                body = ""
            try:
                start_str = str(appt.Start)[:10]
            except Exception:  # noqa: BLE001
                start_str = ""

            blob = f"{subject}\n{body}\n{organizer}\n{location}".lower()
            if kws and not any(k in blob for k in kws):
                continue
            if excl and any(e in blob for e in excl):
                continue
            key = f"{subject}|{start_str}"
            if key in seen:
                continue
            seen.add(key)

            title = f"{subject} - {organizer}" if organizer else subject
            if location:
                title += f" @ {location}"
            res.items.append(ChangeItem(name, "meeting", title, start_str, ""))
            if len(res.items) >= max_items:
                break
    except Exception as exc:  # noqa: BLE001 - never break the run
        res.warning = f"calendar scan error: {str(exc)[:160]}"
    finally:
        try:
            pythoncom.CoUninitialize()
        except Exception:  # noqa: BLE001
            pass
    return res


def _parse_vtt(vtt: str) -> dict:
    """Parse WebVTT into a deterministic summary (no LLM).

    Returns {speakers, cues, duration, first_line}. Teams VTT cues look like:
        00:00:03.120 --> 00:00:07.450
        <v John Monroe>hello everyone</v>
    """
    speakers: list[str] = []
    lines: list[str] = []
    last_ts = ""
    first_line = ""
    spk_re = re.compile(r"<v\s+([^>]+)>(.*?)</v>", re.IGNORECASE | re.DOTALL)
    ts_re = re.compile(r"(\d{2}:\d{2}:\d{2})\.\d{3}\s*-->\s*(\d{2}:\d{2}:\d{2})")
    for raw in vtt.splitlines():
        line = raw.strip()
        mt = ts_re.search(line)
        if mt:
            last_ts = mt.group(2)
            continue
        for who, text in spk_re.findall(line):
            who = who.strip()
            text = re.sub(r"<[^>]+>", "", text).strip()
            if who and who not in speakers:
                speakers.append(who)
            if text:
                lines.append(text)
                if not first_line:
                    first_line = text
    return {
        "speakers": speakers,
        "cues": len(lines),
        "duration": last_ts,
        "first_line": first_line[:160],
    }


def _vtt_summary(vtt: str) -> str:
    """One-line deterministic summary of a transcript for the weekly report."""
    p = _parse_vtt(vtt)
    if not p["cues"]:
        return "transcript captured (no spoken cues parsed)"
    parts = [f"{len(p['speakers'])} speaker(s)", f"{p['cues']} cues"]
    if p["duration"]:
        parts.append(f"~{p['duration']}")
    tail = f" - opening: \u201c{p['first_line']}\u201d" if p["first_line"] else ""
    return ", ".join(parts) + tail


def _safe_name(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", s).strip("_")[:80] or "meeting"


def collect_transcripts(name: str, graph, ww: WorkWeek, out_dir: str | Path,
                        keywords: list[str] | None = None,
                        exclude: list[str] | None = None,
                        max_items: int = 20) -> SourceResult:
    """Capture Teams meeting transcripts (VTT) for the WW window via Graph.

    Delegated access is ORGANIZER-ONLY and requires the meeting to have been
    transcribed. Saves each `.vtt` under `out_dir` and produces a
    ChangeItem(category='transcript') whose title carries a short deterministic
    summary and whose ref is the saved file path. Degrades gracefully: an
    auth/scope gap or API error yields a warning rather than crashing the run.
    """
    from .graph_client import GraphAuthError  # local import: avoids hard dep

    res = SourceResult(name=name, kind="transcript")
    since = f"{ww.since_iso}T00:00:00Z"
    until = f"{ww.end.isoformat()}T23:59:59Z"
    kws = [k.lower() for k in (keywords or [])]
    excl = [e.lower() for e in (exclude or [])]
    out_path = Path(out_dir)
    try:
        out_path.mkdir(parents=True, exist_ok=True)
        for mtg in graph.fetch_transcripts(since, until, top=max_items * 3):
            subject = mtg.get("subject", "(no subject)")
            blob = subject.lower()
            if kws and not any(k in blob for k in kws):
                continue
            if excl and any(e in blob for e in excl):
                continue
            vtts = mtg.get("transcripts") or []
            if not vtts:
                continue  # organized but not transcribed -> skip silently
            vtt = vtts[0]
            fname = f"{mtg.get('date', '')}-{_safe_name(subject)}.vtt"
            (out_path / fname).write_text(vtt, encoding="utf-8")
            title = f"{subject} - {_vtt_summary(vtt)}"
            res.items.append(
                ChangeItem(name, "transcript", title, mtg.get("date", ""),
                           str(out_path / fname))
            )
            if len(res.items) >= max_items:
                break
    except GraphAuthError as exc:
        res.warning = f"transcript scan skipped (auth/scope): {str(exc)[:160]}"
    except Exception as exc:  # noqa: BLE001 - never break the run
        res.warning = f"transcript scan error: {str(exc)[:160]}"
    return res


def collect_all(sources: list[dict], ww: WorkWeek) -> list[SourceResult]:
    """Run every configured source collector and return a flat result list."""
    results: list[SourceResult] = []
    for src in sources:
        kind = src.get("type")
        name = src.get("name", kind or "source")
        try:
            if kind == "git_repo":
                results.append(collect_git_repo(name, src["path"], ww, src.get("all_branches", False)))
            elif kind == "git_scan":
                results.extend(collect_git_scan(
                    name, src["root"], ww, src.get("max_depth", 1), src.get("exclude")))
            elif kind == "adr":
                results.append(collect_adr(name, src["path"], ww, src.get("all_branches", False)))
            elif kind == "fs_mtime":
                results.append(collect_fs_mtime(name, src["path"], ww))
            else:
                r = SourceResult(name=name, kind=str(kind))
                r.warning = f"unknown source type: {kind}"
                results.append(r)
        except Exception as exc:  # noqa: BLE001 - collector must never break the run
            r = SourceResult(name=name, kind=str(kind))
            r.warning = f"collector error: {exc}"
            results.append(r)
    return results
