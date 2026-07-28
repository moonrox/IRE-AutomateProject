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
