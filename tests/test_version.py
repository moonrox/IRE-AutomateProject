"""Tests for version.py — version constants, changelog structure, and history logging."""
import json
import tomllib
from pathlib import Path

import version


def test_version_is_semver():
    parts = version.__version__.split(".")
    assert len(parts) == 3
    assert all(p.isdigit() for p in parts)


def test_changelog_has_entries():
    assert len(version.CHANGELOG) >= 1


def test_changelog_entries_have_required_keys():
    for entry in version.CHANGELOG:
        assert "version" in entry
        assert "date" in entry
        assert "changes" in entry
        assert isinstance(entry["changes"], list)
        assert len(entry["changes"]) >= 1


def test_changelog_version_matches_module():
    versions_in_log = [e["version"] for e in version.CHANGELOG]
    assert version.__version__ in versions_in_log


def test_log_run_writes_valid_json(tmp_path, monkeypatch):
    log_file = tmp_path / "history.jsonl"
    monkeypatch.setattr(version, "HISTORY_FILE", log_file)

    version.log_run("test_script", "test_action", "some details")

    lines = log_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["script"] == "test_script"
    assert entry["action"] == "test_action"
    assert entry["details"] == "some details"
    assert entry["success"] is True
    assert entry["version"] == version.__version__


def test_log_run_records_failure(tmp_path, monkeypatch):
    log_file = tmp_path / "history.jsonl"
    monkeypatch.setattr(version, "HISTORY_FILE", log_file)

    version.log_run("test_script", "test_action", success=False)

    entry = json.loads(log_file.read_text().strip())
    assert entry["success"] is False


def test_log_run_appends_multiple_entries(tmp_path, monkeypatch):
    log_file = tmp_path / "history.jsonl"
    monkeypatch.setattr(version, "HISTORY_FILE", log_file)

    version.log_run("s1", "a1")
    version.log_run("s2", "a2")

    lines = log_file.read_text().strip().splitlines()
    assert len(lines) == 2


def test_pyproject_version_matches_module():
    pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
    if pyproject.exists():
        with open(pyproject, "rb") as f:
            data = tomllib.load(f)
        assert data["project"]["version"] == version.__version__
