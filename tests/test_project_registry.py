"""Tests for project_registry.py"""
import json
import sys
from pathlib import Path

import pytest

# Allow importing project_registry from the project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from project_registry import (
    ProjectRegistry,
    ProjectAlreadyExistsError,
    ProjectNotFoundError,
    ProjectAlreadyCompleteError,
    make_slug,
)


@pytest.fixture
def reg(tmp_path: Path) -> ProjectRegistry:
    return ProjectRegistry(registry_path=tmp_path / "projects.json")


# ---------------------------------------------------------------------------
# make_slug
# ---------------------------------------------------------------------------

class TestMakeSlug:
    def test_lowercases(self):
        assert make_slug("MyProject") == "myproject"

    def test_replaces_spaces(self):
        assert make_slug("My Project") == "my-project"

    def test_replaces_underscores(self):
        assert make_slug("my_project") == "my-project"

    def test_mixed(self):
        assert make_slug("IRE Automate_Tool") == "ire-automate-tool"


# ---------------------------------------------------------------------------
# register()
# ---------------------------------------------------------------------------

class TestRegister:
    def test_creates_entry(self, reg):
        entry = reg.register("alpha")
        assert entry["name"] == "alpha"
        assert entry["status"] == "active"

    def test_slug_is_set(self, reg):
        entry = reg.register("My Project")
        assert entry["slug"] == "my-project"

    def test_stores_description(self, reg):
        entry = reg.register("alpha", "A test project")
        assert entry["description"] == "A test project"

    def test_stores_project_path(self, reg):
        entry = reg.register("alpha", project_path=r"C:\projects\alpha")
        assert entry["project_path"] == r"C:\projects\alpha"

    def test_started_at_is_set(self, reg):
        entry = reg.register("alpha")
        assert entry["started_at"] is not None

    def test_completed_at_is_none(self, reg):
        entry = reg.register("alpha")
        assert entry["completed_at"] is None

    def test_starts_with_no_features(self, reg):
        entry = reg.register("alpha")
        assert entry["features"] == []

    def test_raises_on_duplicate(self, reg):
        reg.register("alpha")
        with pytest.raises(ProjectAlreadyExistsError):
            reg.register("alpha")

    def test_persists_to_json(self, reg, tmp_path):
        reg.register("alpha", "desc")
        data = json.loads((tmp_path / "projects.json").read_text())
        assert data["projects"][0]["name"] == "alpha"

    def test_atomic_write_creates_no_tmp_file(self, reg, tmp_path):
        reg.register("alpha")
        assert not (tmp_path / "projects.tmp").exists()


# ---------------------------------------------------------------------------
# add_feature()
# ---------------------------------------------------------------------------

class TestAddFeature:
    def test_feature_appears_in_project(self, reg):
        reg.register("alpha")
        project = reg.add_feature("alpha", "login", "User login")
        assert len(project["features"]) == 1
        assert project["features"][0]["name"] == "login"

    def test_feature_has_added_at(self, reg):
        reg.register("alpha")
        project = reg.add_feature("alpha", "login")
        assert project["features"][0]["added_at"] is not None

    def test_multiple_features_preserved(self, reg):
        reg.register("alpha")
        reg.add_feature("alpha", "login")
        project = reg.add_feature("alpha", "logout")
        names = [f["name"] for f in project["features"]]
        assert names == ["login", "logout"]

    def test_raises_for_unknown_project(self, reg):
        with pytest.raises(ProjectNotFoundError):
            reg.add_feature("ghost", "feature")

    def test_raises_if_complete(self, reg):
        reg.register("alpha")
        reg.complete("alpha")
        with pytest.raises(ProjectAlreadyCompleteError):
            reg.add_feature("alpha", "late-feat")


# ---------------------------------------------------------------------------
# complete()
# ---------------------------------------------------------------------------

class TestComplete:
    def test_status_becomes_complete(self, reg):
        reg.register("alpha")
        project = reg.complete("alpha")
        assert project["status"] == "complete"

    def test_completed_at_is_set(self, reg):
        reg.register("alpha")
        project = reg.complete("alpha")
        assert project["completed_at"] is not None

    def test_raises_for_unknown_project(self, reg):
        with pytest.raises(ProjectNotFoundError):
            reg.complete("ghost")

    def test_raises_if_already_complete(self, reg):
        reg.register("alpha")
        reg.complete("alpha")
        with pytest.raises(ProjectAlreadyCompleteError):
            reg.complete("alpha")


# ---------------------------------------------------------------------------
# get() / list_all()
# ---------------------------------------------------------------------------

class TestGetAndList:
    def test_get_returns_none_for_unknown(self, reg):
        assert reg.get("ghost") is None

    def test_get_returns_full_entry(self, reg):
        reg.register("alpha", "desc")
        entry = reg.get("alpha")
        assert entry["name"] == "alpha"
        assert entry["description"] == "desc"
        assert "slug" in entry
        assert "project_path" in entry

    def test_list_empty(self, reg):
        assert reg.list_all() == []

    def test_list_returns_all(self, reg):
        reg.register("alpha")
        reg.register("beta")
        names = [p["name"] for p in reg.list_all()]
        assert "alpha" in names
        assert "beta" in names


# ---------------------------------------------------------------------------
# sync_project() — used by ProjectTracker
# ---------------------------------------------------------------------------

class TestSyncProject:
    def test_updates_existing_entry(self, reg):
        reg.register("alpha", "original desc")
        reg.sync_project("alpha", {"status": "complete", "completed_at": "2026-01-01T00:00:00+00:00"})
        entry = reg.get("alpha")
        assert entry["status"] == "complete"

    def test_preserves_slug_and_path(self, reg, tmp_path):
        reg.register("alpha", project_path=r"C:\projects\alpha")
        reg.sync_project("alpha", {"status": "complete", "completed_at": "2026-01-01T00:00:00+00:00"})
        entry = reg.get("alpha")
        assert entry["slug"] == "alpha"
        assert entry["project_path"] == r"C:\projects\alpha"

    def test_creates_entry_for_unregistered_project(self, reg):
        reg.sync_project("new-project", {"status": "active", "started_at": "2026-01-01T00:00:00+00:00",
                                         "completed_at": None, "features": [], "description": ""})
        assert reg.get("new-project") is not None

    def test_tolerates_malformed_json(self, tmp_path):
        registry_path = tmp_path / "projects.json"
        registry_path.write_text("NOT JSON", encoding="utf-8")
        reg = ProjectRegistry(registry_path=registry_path)
        # Should not raise
        reg.sync_project("alpha", {"status": "active", "started_at": "2026-01-01T00:00:00+00:00",
                                   "completed_at": None, "features": [], "description": ""})
        assert reg.get("alpha") is not None
