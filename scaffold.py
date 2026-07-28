"""
scaffold.py — Bootstrap a new project from the IRE framework template.

All template files live in the templates/ directory alongside this script.
Placeholders in template files:
    {{PROJECT_NAME}}  — e.g. "MyNewTool"
    {{PROJECT_SLUG}}  — lowercase-hyphenated, e.g. "my-new-tool"
    {{DESCRIPTION}}   — short description string
    {{DATE}}          — ISO date of scaffold run, e.g. "2026-05-30"

Usage:
    python scaffold.py MyNewTool "Fetches data from the XYZ API"
    python scaffold.py MyNewTool "Fetches data from the XYZ API" --no-venv
    python scaffold.py MyNewTool "Fetches data from the XYZ API" --output C:\\Projects
    python scaffold.py MyNewTool "desc" --path C:\\Projects\\custom-folder  # exact target path
    python scaffold.py MyNewTool "desc" --force                 # scaffold into existing dir
    python scaffold.py MyNewTool "desc" --template C:\\my-tmpl  # custom templates directory

    # Skip optional feature prompts and use defaults:
    python scaffold.py MyNewTool "desc" --yes

    # Explicitly control optional features:
    python scaffold.py MyNewTool "desc" --enable knowledge-identity
    python scaffold.py MyNewTool "desc" --disable knowledge-identity

    # Also install + activate code-review-graph (token-reduction MCP tooling):
    python scaffold.py MyNewTool "desc" --install-crg
    python scaffold.py MyNewTool "desc" --yes --no-install-crg  # non-interactive, skip CRG install

    # Sync an existing project to the current template (adds missing files):
    python scaffold.py --sync C:\\scripts\\ai_scripts\\IRE-Observability
    python scaffold.py --sync C:\\scripts\\ai_scripts\\IRE-Observability --force  # also overwrite changed files
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import date
from pathlib import Path

DEFAULT_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
# Alias kept for backwards compatibility with test_scaffold.py
TEMPLATES_DIR = DEFAULT_TEMPLATES_DIR

# ── Optional features ─────────────────────────────────────────────────────────
# Each entry maps a feature key to the template subdirectory it controls and a
# human-readable prompt.  When a feature is disabled its template files are
# skipped entirely; when enabled, ire-knowledge-schema.yaml gets enabled: true.

OPTIONAL_FEATURES: dict[str, dict] = {
    "knowledge-identity": {
        "label": "Knowledge Identity Layer",
        "description": (
            "AI-readable front matter for docs, author writing profiles, "
            "and team taxonomy — enables AI tools to read, draft, and index "
            "documentation in the author's voice"
        ),
        "template_prefix": "docs",   # skip templates/docs/ when disabled
        "default": True,
    },
    "fable5-agent-mode": {
        "label": "Fable 5 / Mythos 5 Agent Mode",
        "description": (
            "Scaffolds long-running agentic infrastructure for Claude Fable 5 / Mythos 5: "
            "agent_memory/ store (lessons across runs), send_to_user_tool.py (verbatim "
            "mid-task messages), and fable5-system-prompts.md (composable prompt blocks). "
            "Enable if this project will run autonomous or overnight agents."
        ),
        "template_prefix": "agent_memory",  # skip templates/agent_memory/ when disabled
        "default": False,
    },
}

try:
    from project_registry import ProjectRegistry as _Registry, make_slug as _make_slug
    _HAS_REGISTRY = True
except (ImportError, ModuleNotFoundError):
    def _make_slug(name: str) -> str:  # type: ignore[misc]
        return name.lower().replace(" ", "-").replace("_", "-")
    _HAS_REGISTRY = False


# ── Optional feature selection ────────────────────────────────────────────────

def _prompt_features(
    yes: bool,
    enable: list[str],
    disable: list[str],
) -> dict[str, bool]:
    """Return {feature_key: enabled} for every optional feature.

    Resolution order (highest to lowest priority):
      1. Explicit --enable / --disable CLI flags
      2. --yes flag → accept all defaults without prompting
      3. Interactive TTY prompt
      4. Feature default (used when stdin is not a TTY, e.g. in CI)
    """
    import sys

    explicit_on = set(enable or [])
    explicit_off = set(disable or [])
    selections: dict[str, bool] = {}

    if not yes and sys.stdin.isatty():
        print("\nOptional Features — press Enter to accept the default [shown in brackets]:\n")

    for key, meta in OPTIONAL_FEATURES.items():
        if key in explicit_on:
            selections[key] = True
        elif key in explicit_off:
            selections[key] = False
        elif yes or not sys.stdin.isatty():
            selections[key] = meta["default"]
        else:
            default_str = "Y/n" if meta["default"] else "y/N"
            prompt = f"  [{default_str}] {meta['label']}\n        {meta['description']}\n  > "
            raw = input(prompt).strip().lower()
            if raw == "":
                selections[key] = meta["default"]
            else:
                selections[key] = raw in ("y", "yes")
            print()

    return selections


def _prompt_install_crg(yes: bool, install: bool, no_install: bool) -> bool:
    """Decide whether to actively install + activate code-review-graph (CRG).

    CRG is *always available* in every scaffolded project (declared in the
    ``dev`` dependency group, with docs, .gitignore rules, and the optional
    PR-review workflow). This prompt is the separate question of whether to also
    *install and activate* it now — which has side effects: it pip-installs CRG
    into the new .venv, registers a local MCP server for GitHub Copilot CLI, and
    builds the initial code graph.

    Resolution order (highest to lowest priority):
      1. Explicit --install-crg / --no-install-crg CLI flags
      2. --yes flag → default to NOT installing (side-effecting, opt-in)
      3. Interactive TTY prompt (default No)
      4. Non-TTY (e.g. CI) → NOT installed
    """
    import sys

    if install:
        return True
    if no_install:
        return False
    if yes or not sys.stdin.isatty():
        return False

    print(
        "\ncode-review-graph (CRG) — optional token-reduction tooling for AI assistants."
    )
    print(
        "  The template always *includes* CRG (dev dependency + docs + PR workflow)."
    )
    print(
        "  Installing now also: pip installs CRG into .venv, registers a local MCP"
    )
    print(
        "  server for GitHub Copilot CLI, and builds the initial code graph.\n"
    )
    raw = input("  [y/N] Install and activate CRG now?\n  > ").strip().lower()
    print()
    return raw in ("y", "yes")


def _install_crg(target: Path, platform: str = "copilot-cli") -> None:
    """Install + activate code-review-graph in a freshly scaffolded project.

    Best-effort: any failure is reported but never aborts the scaffold run. Uses
    the project's own .venv so the pinned version from pyproject's dev group is
    what gets installed. Skips generated skills/hooks to protect the template's
    own ``.github/skills/`` directory.
    """
    scripts = target / ".venv" / ("Scripts" if sys.platform == "win32" else "bin")
    py = scripts / ("python.exe" if sys.platform == "win32" else "python")
    crg = scripts / ("code-review-graph.exe" if sys.platform == "win32" else "code-review-graph")

    if not py.exists():
        print("  [warn] CRG install skipped: no .venv python (was --no-venv used?)")
        return

    print("\n  Installing code-review-graph (CRG) ...")
    steps = [
        ("pip install dev extras (CRG)", [str(py), "-m", "pip", "install", ".[dev]"]),
        (
            f"register MCP server ({platform})",
            [str(crg), "install", "--platform", platform, "--no-skills", "--no-hooks", "-y"],
        ),
        ("build code graph", [str(crg), "build"]),
    ]
    for label, cmd in steps:
        try:
            subprocess.run(cmd, cwd=str(target), check=True)
            print(f"  [ok] CRG: {label}")
        except (subprocess.CalledProcessError, OSError) as exc:  # noqa: PERF203
            print(f"  [warn] CRG {label} failed: {exc}")
            print("         Finish manually — see docs/knowledge/crg-token-reduction.md")
            return
    print("  [ok] CRG installed. Restart your AI tool to load the MCP server.")


def _disabled_prefixes(feature_selections: dict[str, bool]) -> set[str]:
    """Return the set of template path prefixes that should be skipped."""
    skipped: set[str] = set()
    for key, enabled in feature_selections.items():
        if not enabled:
            prefix = OPTIONAL_FEATURES[key].get("template_prefix", "")
            if prefix:
                skipped.add(prefix)
    return skipped


# ── Template rendering ────────────────────────────────────────────────────────

def _render(text: str, variables: dict[str, str]) -> str:
    """Replace every {{KEY}} occurrence with the matching value."""
    for key, value in variables.items():
        text = text.replace(f"{{{{{key}}}}}", value)
    return text


def _build_vars(name: str, description: str) -> dict[str, str]:
    _validate_scaffold_inputs(name, description)
    return {
        "PROJECT_NAME": name,
        "PROJECT_SLUG": _make_slug(name),
        "DESCRIPTION": description,
        "DATE": date.today().isoformat(),
    }


def _validate_scaffold_inputs(name: str, description: str) -> None:
    """Reject inputs containing template placeholder syntax.

    A name or description containing ``{{...}}`` would be re-processed
    by _render and could bleed into unintended template positions
    (e.g. the description value appearing wherever the name was expected).
    """
    for field, value in (("name", name), ("description", description)):
        if "{{" in value or "}}" in value:
            raise ValueError(
                f"Invalid scaffold {field} {value!r}: "
                "must not contain '{{' or '}}' (template placeholder syntax)."
            )


# ── Scaffold runner ───────────────────────────────────────────────────────────

def scaffold(
    name: str,
    description: str,
    target: Path,
    create_venv: bool = True,
    force: bool = False,
    templates_dir: Path | None = None,
    registry_path: Path | None = None,
    feature_selections: dict[str, bool] | None = None,
    install_crg: bool = False,
) -> None:
    """Generate a new project from the templates directory.

    Args:
        name:               Project display name.
        description:        One-line description written into README / pyproject.
        target:             Absolute path of the new project folder.
        create_venv:        Whether to create a .venv after rendering.
        force:              Allow scaffolding into an already-existing directory.
                            Existing files are overwritten; extra files are kept.
        templates_dir:      Path to the templates folder. Defaults to the
                            ``templates/`` directory next to scaffold.py.
        registry_path:      Override the projects.json path for registration.
                            Pass a tmp_path in tests to avoid polluting the real
                            registry. None (default) uses the env var / LOCALAPPDATA
                            default.
        feature_selections: Mapping of feature key → enabled (True/False).
                            None means all features use their defaults.
        install_crg:        When True, also install + activate code-review-graph
                            in the new .venv after scaffolding (pip install, MCP
                            register, graph build). Requires create_venv=True.
    """
    resolved_templates = templates_dir or DEFAULT_TEMPLATES_DIR
    if not resolved_templates.is_dir():
        raise FileNotFoundError(
            f"Templates directory not found: {resolved_templates}\n"
            "Pass --template <path> or run scaffold.py from its project root."
        )

    if target.exists() and not force:
        raise FileExistsError(
            f"Target directory already exists: {target}\n"
            "Use --force to scaffold into an existing directory."
        )

    selections = feature_selections or {k: v["default"] for k, v in OPTIONAL_FEATURES.items()}
    skip_prefixes = _disabled_prefixes(selections)

    variables = _build_vars(name, description)
    target.mkdir(parents=True, exist_ok=True)
    mode = "(force)" if target.exists() and force else ""
    print(f"\nScaffolding '{name}' -> {target}  {mode}\n")

    # Print active/skipped features
    for key, meta in OPTIONAL_FEATURES.items():
        status = "[enabled]" if selections.get(key, meta["default"]) else "[skipped]"
        print(f"  {status} {meta['label']}")
    print()

    # Cache / VCS artifacts (dirs) and runtime baggage (files) that may pollute
    # the templates tree but must never be copied into a new project (they also
    # contain non-UTF-8 binaries). ``history.jsonl`` is a gitignored runtime log
    # written by version.py — it must be regenerated per-project, never shipped.
    ignore_names = {
        ".git", ".venv", "__pycache__", ".ruff_cache", ".pytest_cache", ".mypy_cache",
        "history.jsonl",
    }

    for src in sorted(resolved_templates.rglob("*")):
        if src.is_dir():
            continue
        rel = src.relative_to(resolved_templates)
        # Skip disabled feature directories
        rel_parts = rel.parts
        if any(rel_parts[0] == prefix for prefix in skip_prefixes):
            print(f"  [skip]  {rel}  (feature disabled)")
            continue
        # Skip cache / VCS artifacts and runtime baggage anywhere in the path
        if any(part in ignore_names for part in rel_parts):
            print(f"  [skip]  {rel}  (cache artifact)")
            continue
        dst = target / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        try:
            raw = src.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            # Non-text/binary template file — copy bytes verbatim, no rendering.
            dst.write_bytes(src.read_bytes())
            print(f"  [ok]    {rel}  (binary copy)")
            continue
        dst.write_text(_render(raw, variables), encoding="utf-8")
        print(f"  [ok]    {rel}")

    # Verify no placeholders slipped through
    unreplaced = []
    for f in target.rglob("*"):
        if f.is_file() and "{{" in f.read_text(encoding="utf-8", errors="ignore"):
            unreplaced.append(f.relative_to(target))
    if unreplaced:
        print("\nWARNING: Unreplaced placeholders found in:")
        for p in unreplaced:
            print(f"     {p}")

    if create_venv:
        venv_path = target / ".venv"
        print(f"\n  Creating .venv with {sys.executable} ...")
        subprocess.run(
            [sys.executable, "-m", "venv", str(venv_path)],
            check=True,
        )
        print("  [ok] .venv created")

        pip = venv_path / "Scripts" / "pip.exe"
        if not pip.exists():
            pip = venv_path / "bin" / "pip"  # Linux/macOS fallback

        for req in ("requirements.txt", "requirements-dev.txt"):
            req_path = target / req
            if req_path.exists():
                print(f"\n  Installing {req} ...")
                subprocess.run(
                    [str(pip), "install", "-r", str(req_path)],
                    check=True,
                )
                print(f"  [ok] {req} installed")

    if install_crg:
        _install_crg(target)

    _register_project(name, description, target, registry_path=registry_path)
    _print_next_steps(name, target, create_venv)


def _register_project(name: str, description: str, target: Path, registry_path: Path | None = None) -> None:
    """Register the new project in the central projects.json registry.

    This is best-effort: registry failures never abort a scaffold run.
    """
    if not _HAS_REGISTRY:
        return
    try:
        _Registry(registry_path=registry_path).register(name, description, project_path=str(target))
        print("  [ok] Registered in projects.json")
    except Exception as exc:  # noqa: BLE001
        print(f"  [warn] Could not register in projects.json: {exc}")


def _print_next_steps(name: str, target: Path, has_venv: bool) -> None:
    activate = r".venv\Scripts\activate"
    msg = (
        f"\n{'='*50}\n"
        f"  Project '{name}' is ready at:\n"
        f"      {target}\n"
        f"\n"
        f"  Next steps:\n"
        f"    cd {target}\n"
        f"    {activate}\n"
        f"    copy .env.example .env    # fill in your values\n"
        f"    python hello.py           # verify environment\n"
        f"    python assess_skills.py   # first skills scan\n"
        f"    pytest\n"
        f"\n"
        f"  Optional — code-review-graph (token reduction for AI assistants):\n"
        f"    See docs/knowledge/crg-token-reduction.md to install/activate later,\n"
        f"    or re-run scaffold with --install-crg. Restart your AI tool after install.\n"
        f"{'='*50}\n"
    )
    sys.stdout.buffer.write(msg.encode("utf-8", errors="replace"))
    sys.stdout.buffer.flush()



# ── Sync runner ───────────────────────────────────────────────────────────────

def _infer_project_meta(target: Path) -> tuple[str, str]:
    """Read name and description from an existing project's pyproject.toml.

    Returns (name, description) strings. Falls back to folder name / empty string.
    """
    pyproject = target / "pyproject.toml"
    name = target.name
    description = ""
    if pyproject.exists():
        import re
        text = pyproject.read_text(encoding="utf-8")
        m_name = re.search(r'^name\s*=\s*"([^"]+)"', text, re.MULTILINE)
        m_desc = re.search(r'^description\s*=\s*"([^"]+)"', text, re.MULTILINE)
        if m_name:
            name = m_name.group(1)
        if m_desc:
            description = m_desc.group(1)
    return name, description


def sync(
    target: Path,
    force: bool = False,
    templates_dir: Path | None = None,
    dry_run: bool = False,
) -> None:
    """Bring an existing project up to date with the current template.

    For each file in the templates directory:
      - MISSING  → render and copy it into the target (always).
      - CHANGED  → report the diff; overwrite only when ``force=True``.
      - SAME     → skip silently.

    Args:
        target:        Absolute path to the existing project directory.
        force:         Overwrite files that exist but differ from the template.
        templates_dir: Path to the templates folder (defaults to templates/ next to scaffold.py).
        dry_run:       Print what would change without writing any files.
    """
    resolved_templates = templates_dir or DEFAULT_TEMPLATES_DIR
    if not resolved_templates.is_dir():
        raise FileNotFoundError(f"Templates directory not found: {resolved_templates}")
    if not target.is_dir():
        raise FileNotFoundError(f"Target project directory not found: {target}")

    name, description = _infer_project_meta(target)
    variables = _build_vars(name, description)

    prefix = "[dry-run] " if dry_run else ""
    print(f"\n{prefix}Syncing template -> {target}")
    print(f"  Project name : {name}")
    print(f"  Description  : {description or '(none)'}\n")

    added, updated, skipped, differs = [], [], [], []

    # Cache / VCS artifacts (dirs) and runtime baggage (files) that pollute the
    # templates tree but must never be synced into a project (they also contain
    # non-UTF-8 binaries). ``history.jsonl`` is a gitignored per-project runtime log.
    ignore_names = {
        ".git", ".venv", "__pycache__", ".ruff_cache", ".pytest_cache", ".mypy_cache",
        "history.jsonl",
    }

    for src in sorted(resolved_templates.rglob("*")):
        if src.is_dir():
            continue
        rel = src.relative_to(resolved_templates)
        # Skip cache / VCS artifacts and runtime baggage anywhere in the path
        if any(part in ignore_names for part in rel.parts):
            continue
        dst = target / rel
        try:
            rendered = _render(src.read_text(encoding="utf-8"), variables)
        except UnicodeDecodeError:
            # Non-text/binary template file — copy bytes verbatim, no rendering.
            if not dst.exists() or dst.read_bytes() != src.read_bytes():
                added.append(rel) if not dst.exists() else differs.append(rel)
                if not dry_run and (force or not dst.exists()):
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    dst.write_bytes(src.read_bytes())
            continue

        if not dst.exists():
            added.append(rel)
            if not dry_run:
                dst.parent.mkdir(parents=True, exist_ok=True)
                dst.write_text(rendered, encoding="utf-8")
            print(f"  {prefix}[added]   {rel}")
        else:
            existing = dst.read_text(encoding="utf-8")
            if existing == rendered:
                skipped.append(rel)
            else:
                differs.append(rel)
                if force:
                    updated.append(rel)
                    if not dry_run:
                        dst.write_text(rendered, encoding="utf-8")
                    print(f"  {prefix}[updated] {rel}")
                else:
                    print(f"  [differs] {rel}  (use --force to overwrite)")

    print(f"""
{'='*54}
  Sync complete for '{name}'

  Added   : {len(added)}   file(s)
  Updated : {len(updated)}   file(s)  {"(--force was set)" if force else ""}
  Differs : {len(differs) - len(updated)}   file(s)  (skipped — add --force to overwrite)
  Same    : {len(skipped)}   file(s)
{'='*54}
""")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Bootstrap a new project from the IRE framework template."
    )

    # ── Sync mode ─────────────────────────────────────────────────────────────
    parser.add_argument(
        "--sync",
        metavar="PATH",
        type=Path,
        default=None,
        help="Sync an existing project directory to the current template (adds missing files)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="(--sync only) Preview changes without writing any files",
    )

    # ── New project mode ───────────────────────────────────────────────────────
    parser.add_argument("name", nargs="?", help="Project name, e.g. MyNewTool")
    parser.add_argument("description", nargs="?", help="Short description of the project")
    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=None,
        help="Parent directory for the new project (default: current directory)",
    )
    parser.add_argument(
        "--path", "-p",
        type=Path,
        default=None,
        metavar="DIR",
        help="Exact target directory for the new project (overrides --output + name)",
    )
    parser.add_argument(
        "--template", "-t",
        type=Path,
        default=None,
        metavar="DIR",
        help="Custom templates directory (default: templates/ next to scaffold.py)",
    )
    parser.add_argument(
        "--force", "-f",
        action="store_true",
        help="Scaffold into an existing directory, overwriting generated files",
    )
    parser.add_argument(
        "--no-venv",
        action="store_true",
        help="Skip .venv creation",
    )
    parser.add_argument(
        "--yes", "-y",
        action="store_true",
        help="Accept all optional feature defaults without prompting",
    )
    parser.add_argument(
        "--enable",
        nargs="+",
        metavar="FEATURE",
        default=[],
        help=f"Enable optional features explicitly. Choices: {list(OPTIONAL_FEATURES)}",
    )
    parser.add_argument(
        "--disable",
        nargs="+",
        metavar="FEATURE",
        default=[],
        help=f"Disable optional features explicitly. Choices: {list(OPTIONAL_FEATURES)}",
    )
    parser.add_argument(
        "--install-crg",
        action="store_true",
        help="Also install + activate code-review-graph (pip install, register MCP, build graph)",
    )
    parser.add_argument(
        "--no-install-crg",
        action="store_true",
        help="Skip the code-review-graph install prompt (leave it available but not installed)",
    )
    args = parser.parse_args()

    if args.sync:
        sync(
            target=args.sync.resolve(),
            force=args.force,
            templates_dir=args.template,
            dry_run=args.dry_run,
        )
    else:
        if not args.name or not args.description:
            parser.error("name and description are required when not using --sync")
        if args.path and args.output is not None:
            parser.error("--path and --output are mutually exclusive")
        if args.install_crg and args.no_install_crg:
            parser.error("--install-crg and --no-install-crg are mutually exclusive")
        output_dir = args.output if args.output is not None else Path.cwd()
        target = args.path.resolve() if args.path else output_dir / args.name
        feature_selections = _prompt_features(
            yes=args.yes,
            enable=args.enable,
            disable=args.disable,
        )
        install_crg = _prompt_install_crg(
            yes=args.yes,
            install=args.install_crg,
            no_install=args.no_install_crg,
        )
        scaffold(
            name=args.name,
            description=args.description,
            target=target,
            create_venv=not args.no_venv,
            force=args.force,
            templates_dir=args.template,
            feature_selections=feature_selections,
            install_crg=install_crg,
        )


if __name__ == "__main__":
    main()
