"""
project_registry.py — Central JSON registry for all IRE framework projects.

Tracks the lifecycle of every project: creation via scaffold, feature additions,
and completion. Data is stored in projects.json.

Default location: %LOCALAPPDATA%\\IRE-AutomateProject\\projects.json
Override:         set the IRE_PROJECTS_JSON environment variable

Usage (CLI):
    python project_registry.py list
    python project_registry.py register "MyProject" "A short description"
    python project_registry.py add-feature "MyProject" "feature-name" "Description"
    python project_registry.py complete "MyProject"
    python project_registry.py show "MyProject"

Usage (API):
    from project_registry import ProjectRegistry
    reg = ProjectRegistry()
    reg.register("MyProject", "Description", project_path=r"C:\\scripts\\ai_scripts\\MyProject")
    reg.add_feature("MyProject", "auth", "JWT authentication")
    reg.complete("MyProject")
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

REGISTRY_ENV_VAR = "IRE_PROJECTS_JSON"


def _default_registry_path() -> Path:
    """Return the default path for projects.json.

    Reads IRE_PROJECTS_JSON env var first; falls back to
    %LOCALAPPDATA%\\IRE-AutomateProject\\projects.json (Windows) or
    ~/.local/share/IRE-AutomateProject/projects.json (other platforms).
    """
    env = os.environ.get(REGISTRY_ENV_VAR, "").strip()
    if env:
        return Path(env).resolve()
    local_app_data = os.environ.get("LOCALAPPDATA") or str(Path.home() / ".local" / "share")
    return Path(local_app_data) / "IRE-AutomateProject" / "projects.json"


def make_slug(name: str) -> str:
    """Convert a project name to a lowercase hyphenated slug."""
    return name.lower().replace(" ", "-").replace("_", "-")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ProjectAlreadyExistsError(Exception):
    pass


class ProjectNotFoundError(Exception):
    pass


class ProjectAlreadyCompleteError(Exception):
    pass


class ProjectRegistry:
    """JSON-backed central registry for IRE project lifecycle tracking."""

    def __init__(self, registry_path: Optional[Path] = None) -> None:
        self.path = Path(registry_path) if registry_path else _default_registry_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _read(self) -> dict:
        if not self.path.exists():
            return {"projects": []}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {"projects": []}

    def _write(self, data: dict) -> None:
        """Atomic write: write to .tmp then replace to avoid partial writes."""
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        os.replace(tmp, self.path)

    def _find(self, data: dict, name: str) -> tuple[int, Optional[dict]]:
        for i, p in enumerate(data.get("projects", [])):
            if p["name"] == name:
                return i, p
        return -1, None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register(
        self, name: str, description: str = "", project_path: str = ""
    ) -> dict:
        """Register a new project and record its start time.

        Raises ProjectAlreadyExistsError if the name is already registered.
        """
        data = self._read()
        _, existing = self._find(data, name)
        if existing:
            raise ProjectAlreadyExistsError(f"Project '{name}' is already registered.")

        entry: dict = {
            "name": name,
            "slug": make_slug(name),
            "description": description,
            "project_path": str(project_path) if project_path else "",
            "status": "active",
            "started_at": _now_iso(),
            "completed_at": None,
            "features": [],
        }
        data.setdefault("projects", []).append(entry)
        self._write(data)
        return entry

    def add_feature(
        self, name: str, feature_name: str, description: str = ""
    ) -> dict:
        """Log a new feature added to a project.

        Raises ProjectNotFoundError or ProjectAlreadyCompleteError as appropriate.
        """
        data = self._read()
        idx, project = self._find(data, name)
        if not project:
            raise ProjectNotFoundError(f"Project '{name}' not found.")
        if project["status"] == "complete":
            raise ProjectAlreadyCompleteError(f"Project '{name}' is already complete.")

        project.setdefault("features", []).append(
            {"name": feature_name, "description": description, "added_at": _now_iso()}
        )
        data["projects"][idx] = project
        self._write(data)
        return project

    def complete(self, name: str) -> dict:
        """Mark a project as complete and record the completion timestamp."""
        data = self._read()
        idx, project = self._find(data, name)
        if not project:
            raise ProjectNotFoundError(f"Project '{name}' not found.")
        if project["status"] == "complete":
            raise ProjectAlreadyCompleteError(f"Project '{name}' is already complete.")

        project["status"] = "complete"
        project["completed_at"] = _now_iso()
        data["projects"][idx] = project
        self._write(data)
        return project

    def get(self, name: str) -> Optional[dict]:
        """Return the project entry by name, or None if not found."""
        _, project = self._find(self._read(), name)
        return project

    def list_all(self) -> list[dict]:
        """Return all registered projects."""
        return self._read().get("projects", [])

    def sync_project(self, name: str, updates: dict) -> None:
        """Merge tracker-managed fields into an existing registry entry.

        Preserves registry-only fields (slug, project_path).
        Silently skips if the project is not found in the registry.
        Used by ProjectTracker to push state changes into projects.json.
        """
        data = self._read()
        idx, project = self._find(data, name)
        if project is None:
            # Project not yet in registry — create a minimal entry so tracker
            # updates are captured even for projects not created via scaffold.
            slug = make_slug(name)
            project = {
                "name": name,
                "slug": slug,
                "description": updates.get("description", ""),
                "project_path": "",
                "status": updates.get("status", "active"),
                "started_at": updates.get("started_at", _now_iso()),
                "completed_at": updates.get("completed_at"),
                "features": updates.get("features", []),
            }
            data.setdefault("projects", []).append(project)
        else:
            for key in ("status", "started_at", "completed_at", "features", "description"):
                if key in updates:
                    project[key] = updates[key]
            data["projects"][idx] = project

        self._write(data)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _cmd_list(reg: ProjectRegistry, _args) -> None:
    projects = reg.list_all()
    if not projects:
        print("No projects registered yet.")
        return
    width = 58
    print(f"\n{'─' * width}")
    print(f"  {'Name':<28}  {'Status':<10}  Started")
    print(f"{'─' * width}")
    for p in projects:
        started = (p.get("started_at") or "")[:10]
        print(f"  {p['name']:<28}  {p['status']:<10}  {started}")
    print(f"{'─' * width}\n")


def _cmd_show(reg: ProjectRegistry, args) -> None:
    project = reg.get(args.name)
    if not project:
        print(f"Project '{args.name}' not found.")
        return
    print(json.dumps(project, indent=2))


def _cmd_register(reg: ProjectRegistry, args) -> None:
    project = reg.register(args.name, args.description, args.path)
    print(f"✔  Registered '{project['name']}' (started {project['started_at'][:10]})")


def _cmd_add_feature(reg: ProjectRegistry, args) -> None:
    reg.add_feature(args.name, args.feature, args.description)
    print(f"✔  Feature '{args.feature}' added to '{args.name}'")


def _cmd_complete(reg: ProjectRegistry, args) -> None:
    project = reg.complete(args.name)
    print(f"✔  '{project['name']}' marked complete ({project['completed_at'][:10]})")


def main() -> None:
    parser = argparse.ArgumentParser(description="IRE project lifecycle registry")
    parser.add_argument(
        "--registry",
        type=Path,
        default=None,
        help=(
            f"Path to projects.json "
            f"(default: ${REGISTRY_ENV_VAR} or %%LOCALAPPDATA%%/IRE-AutomateProject/projects.json)"
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="List all projects")

    p_show = sub.add_parser("show", help="Show full project details")
    p_show.add_argument("name")

    p_reg = sub.add_parser("register", help="Register a new project")
    p_reg.add_argument("name")
    p_reg.add_argument("description", nargs="?", default="")
    p_reg.add_argument("--path", default="", help="Absolute path to the project directory")

    p_feat = sub.add_parser("add-feature", help="Log a feature addition to a project")
    p_feat.add_argument("name")
    p_feat.add_argument("feature")
    p_feat.add_argument("description", nargs="?", default="")

    p_comp = sub.add_parser("complete", help="Mark a project as complete")
    p_comp.add_argument("name")

    args = parser.parse_args()
    reg = ProjectRegistry(registry_path=args.registry)

    dispatch = {
        "list": _cmd_list,
        "show": _cmd_show,
        "register": _cmd_register,
        "add-feature": _cmd_add_feature,
        "complete": _cmd_complete,
    }
    dispatch[args.command](reg, args)


if __name__ == "__main__":
    main()
