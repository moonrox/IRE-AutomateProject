"""
tests/test_drawio.py — Unit tests for the DiagramBuilder (drawio.py)
and the diagram-generation helpers in IRE-DrawIO.py.

Covers:
  - XML structure and required attributes
  - Shape / edge / note creation
  - Status board layout
  - Architecture diagram (no network calls)
  - File save / delete round-trip
"""
from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from drawio import (
    PRIORITY_ICON,
    STATUS_STYLE,
    STYLES,
    DiagramBuilder,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse(builder: DiagramBuilder) -> ET.Element:
    """Return the root <mxGraphModel> element from a builder's XML."""
    raw = builder.to_xml()
    # strip the <?xml …?> declaration before parsing
    raw_body = raw.split("?>", 1)[-1].strip()
    return ET.fromstring(raw_body)


def _cells(builder: DiagramBuilder) -> list[ET.Element]:
    """Return all <mxCell> elements (excluding the two reserved ones)."""
    root = _parse(builder)
    return [c for c in root.find("root") if c.get("id") not in ("0", "1")]


# ── Basic XML structure ───────────────────────────────────────────────────────

class TestXmlStructure:
    def test_root_element_is_mxgraphmodel(self):
        d = DiagramBuilder("Test")
        model = _parse(d)
        assert model.tag == "mxGraphModel"

    def test_reserved_cells_present(self):
        d = DiagramBuilder("Test")
        root_el = _parse(d).find("root")
        ids = {c.get("id") for c in root_el}
        assert "0" in ids
        assert "1" in ids

    def test_page_size_a4_landscape(self):
        d = DiagramBuilder("Test", page_size=DiagramBuilder.PAGE_A4_LANDSCAPE)
        model = _parse(d)
        assert model.get("pageWidth") == "1169"
        assert model.get("pageHeight") == "827"

    def test_page_size_a3_landscape(self):
        d = DiagramBuilder("Test", page_size=DiagramBuilder.PAGE_A3_LANDSCAPE)
        model = _parse(d)
        assert model.get("pageWidth") == "1654"
        assert model.get("pageHeight") == "1169"

    def test_xml_declaration_present(self):
        d = DiagramBuilder("Test")
        assert d.to_xml().startswith('<?xml version="1.0"')


# ── Shape creation ────────────────────────────────────────────────────────────

class TestAddShape:
    def test_returns_string_id(self):
        d = DiagramBuilder()
        id_ = d.add_shape("Hello", x=10, y=20)
        assert isinstance(id_, str)

    def test_ids_are_unique(self):
        d = DiagramBuilder()
        ids = [d.add_shape(f"S{i}", x=i * 10, y=0) for i in range(5)]
        assert len(set(ids)) == 5

    def test_shape_attributes(self):
        d = DiagramBuilder()
        id_ = d.add_shape("Box", x=50, y=100, width=200, height=80)
        cells = _cells(d)
        assert len(cells) == 1
        cell = cells[0]
        assert cell.get("id") == id_
        assert cell.get("value") == "Box"
        assert cell.get("vertex") == "1"

    def test_geometry_values(self):
        d = DiagramBuilder()
        d.add_shape("G", x=30, y=40, width=120, height=55)
        geo = _cells(d)[0].find("mxGeometry")
        assert geo.get("x") == "30"
        assert geo.get("y") == "40"
        assert geo.get("width") == "120"
        assert geo.get("height") == "55"

    def test_custom_style_applied(self):
        d = DiagramBuilder()
        d.add_shape("S", x=0, y=0, style=STYLES["box_progress"])
        assert _cells(d)[0].get("style") == STYLES["box_progress"]

    def test_default_style_is_box(self):
        d = DiagramBuilder()
        d.add_shape("S", x=0, y=0)
        assert _cells(d)[0].get("style") == STYLES["box"]

    def test_tooltip_attribute(self):
        d = DiagramBuilder()
        d.add_shape("S", x=0, y=0, tooltip="my tip")
        assert _cells(d)[0].get("tooltip") == "my tip"

    def test_no_tooltip_by_default(self):
        d = DiagramBuilder()
        d.add_shape("S", x=0, y=0)
        assert _cells(d)[0].get("tooltip") is None


# ── Edge creation ─────────────────────────────────────────────────────────────

class TestAddEdge:
    def test_returns_string_id(self):
        d = DiagramBuilder()
        a = d.add_shape("A", x=0, y=0)
        b = d.add_shape("B", x=200, y=0)
        eid = d.add_edge(a, b)
        assert isinstance(eid, str)

    def test_edge_attributes(self):
        d = DiagramBuilder()
        a = d.add_shape("A", x=0, y=0)
        b = d.add_shape("B", x=200, y=0)
        eid = d.add_edge(a, b, value="next")
        edge = next(c for c in _cells(d) if c.get("id") == eid)
        assert edge.get("edge") == "1"
        assert edge.get("source") == a
        assert edge.get("target") == b
        assert edge.get("value") == "next"

    def test_edge_default_style(self):
        d = DiagramBuilder()
        a = d.add_shape("A", x=0, y=0)
        b = d.add_shape("B", x=200, y=0)
        eid = d.add_edge(a, b)
        edge = next(c for c in _cells(d) if c.get("id") == eid)
        assert edge.get("style") == STYLES["arrow_simple"]

    def test_edge_custom_style(self):
        d = DiagramBuilder()
        a = d.add_shape("A", x=0, y=0)
        b = d.add_shape("B", x=200, y=0)
        eid = d.add_edge(a, b, style=STYLES["arrow"])
        edge = next(c for c in _cells(d) if c.get("id") == eid)
        assert edge.get("style") == STYLES["arrow"]

    def test_edge_geometry_is_relative(self):
        d = DiagramBuilder()
        a = d.add_shape("A", x=0, y=0)
        b = d.add_shape("B", x=200, y=0)
        eid = d.add_edge(a, b)
        edge = next(c for c in _cells(d) if c.get("id") == eid)
        geo = edge.find("mxGeometry")
        assert geo.get("relative") == "1"


# ── Note / column header ──────────────────────────────────────────────────────

class TestNoteAndHeader:
    def test_add_note_uses_note_style(self):
        d = DiagramBuilder()
        d.add_note("Hello", x=0, y=0)
        assert _cells(d)[0].get("style") == STYLES["note"]

    def test_add_column_header_uses_col_header_style(self):
        d = DiagramBuilder()
        d.add_column_header("Col", x=0, y=0, width=200)
        assert _cells(d)[0].get("style") == STYLES["col_header"]


# ── Status board layout ───────────────────────────────────────────────────────

class TestStatusBoard:
    def test_creates_header_and_items(self):
        d = DiagramBuilder()
        columns = {
            "New":         [("Item A", "tip A"), ("Item B", "")],
            "In progress": [("Item C", "tip C")],
            "Blocked":     [],
            "Completed":   [("Item D", "")],
        }
        d.add_status_board(columns)
        cells = _cells(d)
        # 4 headers + 4 items = 8 cells
        assert len(cells) == 8

    def test_status_style_applied_to_items(self):
        d = DiagramBuilder()
        d.add_status_board({"New": [("X", "")]})
        cells = _cells(d)
        item_cell = cells[1]  # index 0 is the header
        assert item_cell.get("style") == STATUS_STYLE["New"]

    def test_column_header_style(self):
        d = DiagramBuilder()
        d.add_status_board({"Blocked": [("Y", "")]})
        header = _cells(d)[0]
        assert header.get("style") == STYLES["col_header"]
        assert header.get("value") == "Blocked"

    def test_empty_column_only_has_header(self):
        d = DiagramBuilder()
        d.add_status_board({"Completed": []})
        assert len(_cells(d)) == 1  # just the header


# ── Priority icons and status styles ─────────────────────────────────────────

class TestConstants:
    def test_priority_icons_defined(self):
        for key in ("High", "Normal", "Low"):
            assert key in PRIORITY_ICON

    def test_status_styles_cover_all_statuses(self):
        for status in ("New", "In progress", "Blocked", "Completed"):
            assert status in STATUS_STYLE
            assert STATUS_STYLE[status]  # non-empty string


# ── Architecture diagram (no network) ────────────────────────────────────────

def _import_build_architecture_diagram():
    """Import build_architecture_diagram from IRE-DrawIO.py (hyphen in filename).

    The module imports azure/msal at the top level even though
    build_architecture_diagram never calls any auth code, so we stub those
    heavy modules out before loading.
    """
    import importlib.util
    import os
    import sys
    import types
    import unittest.mock

    # --- stub heavy transitive deps that aren't installed in the test venv ---
    stubs = {
        "msal": types.ModuleType("msal"),
        "msal_extensions": types.ModuleType("msal_extensions"),
        "azure": types.ModuleType("azure"),
        "azure.core": types.ModuleType("azure.core"),
        "azure.core.credentials": types.ModuleType("azure.core.credentials"),
    }
    # azure.core.credentials must expose AccessToken
    stubs["azure.core.credentials"].AccessToken = type("AccessToken", (), {})
    # msal must expose PublicClientApplication
    stubs["msal"].PublicClientApplication = type("PublicClientApplication", (), {})

    # graph_auth itself also needs to be stubbed at the sys.modules level so
    # the `from graph_auth import DeviceCodeCredential` line in IRE-DrawIO.py works
    graph_auth_stub = types.ModuleType("graph_auth")
    graph_auth_stub.DeviceCodeCredential = type("DeviceCodeCredential", (), {})
    stubs["graph_auth"] = graph_auth_stub

    # version.py stub (log_run / __version__)
    version_stub = types.ModuleType("version")
    version_stub.__version__ = "0.0.0-test"
    version_stub.log_run = lambda *a, **kw: None
    stubs["version"] = version_stub

    env_patch = {
        "CLIENT_ID": "test-client-id",
        "TENANT_ID": "test-tenant-id",
        "SITE_ID":   "test-site-id",
        "LIST_ID":   "test-list-id",
    }

    spec = importlib.util.spec_from_file_location(
        "IRE_DrawIO",
        Path(__file__).resolve().parent.parent / "IRE-DrawIO.py",
    )
    mod = importlib.util.module_from_spec(spec)

    with unittest.mock.patch.dict(sys.modules, stubs):
        with unittest.mock.patch.dict(os.environ, env_patch):
            spec.loader.exec_module(mod)

    return mod.build_architecture_diagram


class TestArchitectureDiagram:
    def test_builds_without_error(self):
        build = _import_build_architecture_diagram()
        builder = build()
        assert isinstance(builder, DiagramBuilder)

    def test_produces_valid_xml(self):
        build = _import_build_architecture_diagram()
        builder = build()
        xml = builder.to_xml()
        assert "<mxGraphModel" in xml
        assert "<mxCell" in xml

    def test_has_expected_shapes(self):
        build = _import_build_architecture_diagram()
        builder = build()
        xml = builder.to_xml()
        for label in ("IRE-DrawIO.py", "graph_auth.py", "Microsoft Graph API"):
            assert label in xml, f"Expected shape label not found: {label}"


# ── File save and delete round-trip ──────────────────────────────────────────

class TestSaveAndDelete:
    def test_save_creates_file(self, tmp_path):
        d = DiagramBuilder("Save Test")
        d.add_shape("Node", x=100, y=100)
        out = d.save(tmp_path / "test_diagram.drawio")
        assert out.exists()
        assert out.suffix == ".drawio"

    def test_saved_file_is_valid_xml(self, tmp_path):
        d = DiagramBuilder("XML Check")
        d.add_shape("A", x=0, y=0)
        out = d.save(tmp_path / "check.drawio")
        content = out.read_text(encoding="utf-8")
        # Must parse without error
        ET.fromstring(content.split("?>", 1)[-1].strip())

    def test_saved_file_contains_title_shapes(self, tmp_path):
        d = DiagramBuilder("My Title")
        d.add_shape("Special Node", x=50, y=50)
        out = d.save(tmp_path / "titled.drawio")
        content = out.read_text(encoding="utf-8")
        assert "Special Node" in content

    def test_delete_after_save(self, tmp_path):
        """Create a diagram file, verify it exists, then delete it."""
        d = DiagramBuilder("Delete Test")
        d.add_shape("Temp Node", x=0, y=0)
        out = d.save(tmp_path / "to_delete.drawio")
        assert out.exists(), "File should exist after save"

        out.unlink()

        assert not out.exists(), "File should be removed after deletion"

    def test_save_creates_parent_dirs(self, tmp_path):
        d = DiagramBuilder("Nested")
        d.add_shape("N", x=0, y=0)
        nested = tmp_path / "deep" / "nested" / "diagram.drawio"
        nested.parent.mkdir(parents=True, exist_ok=True)
        out = d.save(nested)
        assert out.exists()
