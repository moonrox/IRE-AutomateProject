"""
drawio.py — Build and serialize draw.io diagrams as XML.

No external dependencies — stdlib only.

Quick-start:
    from drawio import DiagramBuilder, STYLES

    d = DiagramBuilder("My Diagram")
    a = d.add_shape("Start", x=100, y=100)
    b = d.add_shape("End",   x=300, y=100)
    d.add_edge(a, b, "next step")
    d.save("output.drawio")
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

# ── Style constants ────────────────────────────────────────────────────────────

STYLES: dict[str, str] = {
    "box":          "rounded=1;whiteSpace=wrap;html=1;",
    "box_new":      "rounded=1;whiteSpace=wrap;html=1;fillColor=#dae8fc;strokeColor=#6c8ebf;",
    "box_progress": "rounded=1;whiteSpace=wrap;html=1;fillColor=#fff2cc;strokeColor=#d6b656;",
    "box_blocked":  "rounded=1;whiteSpace=wrap;html=1;fillColor=#f8cecc;strokeColor=#b85450;",
    "box_done":     "rounded=1;whiteSpace=wrap;html=1;fillColor=#d5e8d4;strokeColor=#82b366;",
    "box_azure":    "rounded=1;whiteSpace=wrap;html=1;fillColor=#dae8fc;strokeColor=#6c8ebf;fontStyle=1;",
    "box_python":   "rounded=1;whiteSpace=wrap;html=1;fillColor=#ffe6cc;strokeColor=#d79b00;",
    "box_ps1":      "rounded=1;whiteSpace=wrap;html=1;fillColor=#e1d5e7;strokeColor=#9673a6;",
    "box_config":   "rounded=1;whiteSpace=wrap;html=1;fillColor=#f5f5f5;strokeColor=#666666;fontColor=#333333;",
    "box_service":  "shape=mxgraph.azure.azure_service_bus;html=1;pointerEvents=1;dashed=0;"
                    "fillColor=#0072C6;strokeColor=none;strokeWidth=2;verticalLabelPosition=bottom;"
                    "verticalAlign=top;align=center;outlineConnect=0;",
    "col_header":   "swimlane;startSize=30;fillColor=#f5f5f5;strokeColor=#666666;"
                    "fontColor=#333333;fontStyle=1;fontSize=11;",
    "arrow":        "edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;"
                    "jettySize=auto;exitX=1;exitY=0.5;exitDx=0;exitDy=0;",
    "arrow_simple": "endArrow=block;endFill=1;",
    "note":         "text;html=1;strokeColor=none;fillColor=none;align=left;"
                    "verticalAlign=middle;whiteSpace=wrap;overflow=hidden;",
}

STATUS_STYLE: dict[str, str] = {
    "New":         STYLES["box_new"],
    "In progress": STYLES["box_progress"],
    "Blocked":     STYLES["box_blocked"],
    "Completed":   STYLES["box_done"],
}

PRIORITY_ICON: dict[str, str] = {
    "High":   "🔴",
    "Normal": "🟡",
    "Low":    "🟢",
}


# ── Core builder ───────────────────────────────────────────────────────────────

class DiagramBuilder:
    """Incrementally build a draw.io diagram and serialize it to XML."""

    # Page sizes (in px at 100% zoom, draw.io uses 96 DPI)
    PAGE_A4_LANDSCAPE = (1169, 827)
    PAGE_A3_LANDSCAPE = (1654, 1169)

    def __init__(self, title: str = "Diagram", page_size: tuple[int, int] = PAGE_A3_LANDSCAPE):
        self._title = title
        self._page_w, self._page_h = page_size
        self._cells: list[ET.Element] = []
        self._counter = 2  # IDs 0 and 1 are reserved

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _new_id(self) -> str:
        id_ = str(self._counter)
        self._counter += 1
        return id_

    # ── Public API ────────────────────────────────────────────────────────────

    def add_shape(
        self,
        value: str,
        x: int,
        y: int,
        width: int = 160,
        height: int = 60,
        style: str = "",
        tooltip: str = "",
        parent: str = "1",
    ) -> str:
        """Add a vertex (box, shape) and return its cell ID."""
        id_ = self._new_id()
        attrs: dict[str, str] = {
            "id": id_,
            "value": value,
            "style": style or STYLES["box"],
            "vertex": "1",
            "parent": parent,
        }
        if tooltip:
            attrs["tooltip"] = tooltip
        cell = ET.Element("mxCell", attrs)
        ET.SubElement(cell, "mxGeometry", {
            "x": str(x), "y": str(y),
            "width": str(width), "height": str(height),
            "as": "geometry",
        })
        self._cells.append(cell)
        return id_

    def add_edge(
        self,
        source: str,
        target: str,
        value: str = "",
        style: str = "",
        parent: str = "1",
    ) -> str:
        """Add a directed edge between two cell IDs and return its cell ID."""
        id_ = self._new_id()
        cell = ET.Element("mxCell", {
            "id": id_,
            "value": value,
            "style": style or STYLES["arrow_simple"],
            "edge": "1",
            "source": source,
            "target": target,
            "parent": parent,
        })
        ET.SubElement(cell, "mxGeometry", {"relative": "1", "as": "geometry"})
        self._cells.append(cell)
        return id_

    def add_project_card(
        self,
        item_id: str,
        fields: dict,
        created_dt: str = "",
        modified_dt: str = "",
        x: int = 40,
        y: int = 60,
        width: int = 600,
    ) -> None:
        """Render a single-project status card onto the diagram."""
        title    = fields.get("Title", "(no title)")
        status   = fields.get("Status", "New")
        priority = fields.get("Priority", "Normal")
        segment  = fields.get("Segment", "")
        phase    = fields.get("Projectphase", "")
        notes    = fields.get("ProjectSummaryDetails", "")
        mgr_rev  = "✓ Manager Reviewed" if fields.get("ManagerReview") else "Pending Review"

        # Title bar — coloured by status
        self.add_shape(
            f"<b>{title}</b>",
            x, y, width, 70,
            style=STATUS_STYLE.get(status, STYLES["box"]),
        )

        # Info row — four equal boxes
        box_w = width // 4
        for i, (label, val) in enumerate([
            ("Status",   status),
            ("Priority", f"{PRIORITY_ICON.get(priority, '')} {priority}"),
            ("Segment",  segment or "—"),
            ("Phase",    phase or "—"),
        ]):
            self.add_shape(
                f"<b>{label}</b><br>{val}",
                x + i * box_w, y + 80, box_w, 55,
                style=STYLES["box_config"],
            )

        # Notes
        note_h = max(60, min(160, len(notes) // 2 + 40)) if notes else 60
        self.add_shape(
            notes or "(no notes)",
            x, y + 145, width, note_h,
            style=STYLES["note"],
        )

        # Footer
        footer_y = y + 155 + note_h
        self.add_shape(
            f"{mgr_rev}   ·   Item ID: {item_id}",
            x, footer_y, width // 2, 35,
            style=STYLES["box_config"],
        )
        self.add_shape(
            f"Created: {created_dt[:10] if created_dt else '—'}   "
            f"Updated: {modified_dt[:10] if modified_dt else '—'}",
            x + width // 2, footer_y, width // 2, 35,
            style=STYLES["box_config"],
        )

    def add_note(self, value: str, x: int, y: int, width: int = 200, height: int = 30) -> str:
        """Add a plain text label (no border)."""
        return self.add_shape(value, x, y, width, height, style=STYLES["note"])

    def add_column_header(self, label: str, x: int, y: int, width: int, height: int = 30) -> str:
        """Add a labelled column header (swimlane-style)."""
        return self.add_shape(label, x, y, width, height, style=STYLES["col_header"])

    # ── High-level layouts ────────────────────────────────────────────────────

    def add_status_board(
        self,
        columns: dict[str, list[tuple[str, str]]],  # status → [(label, tooltip)]
        start_x: int = 40,
        start_y: int = 60,
        col_width: int = 200,
        col_gap: int = 20,
        item_height: int = 60,
        item_gap: int = 10,
    ) -> None:
        """Lay out a Kanban-style status board.

        ``columns`` maps status name → list of (label, tooltip) tuples.
        """
        for col_i, (status, items) in enumerate(columns.items()):
            x = start_x + col_i * (col_width + col_gap)
            self.add_column_header(status, x, start_y, col_width)
            for row_i, (label, tooltip) in enumerate(items):
                item_y = start_y + 40 + row_i * (item_height + item_gap)
                self.add_shape(
                    label, x + 5, item_y,
                    width=col_width - 10, height=item_height,
                    style=STATUS_STYLE.get(status, STYLES["box"]),
                    tooltip=tooltip,
                )

    # ── Serialization ─────────────────────────────────────────────────────────

    def to_xml(self) -> str:
        """Return the diagram as a draw.io XML string."""
        model = ET.Element("mxGraphModel", {
            "dx": "1422", "dy": "762",
            "grid": "1", "gridSize": "10",
            "guides": "1", "tooltips": "1",
            "connect": "1", "arrows": "1",
            "fold": "1", "page": "1",
            "pageScale": "1",
            "pageWidth": str(self._page_w),
            "pageHeight": str(self._page_h),
            "math": "0", "shadow": "0",
        })
        root_el = ET.SubElement(model, "root")
        ET.SubElement(root_el, "mxCell", {"id": "0"})
        ET.SubElement(root_el, "mxCell", {"id": "1", "parent": "0"})
        for cell in self._cells:
            root_el.append(cell)

        ET.indent(model, space="  ")
        return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(model, encoding="unicode")

    def save(self, path: str | Path) -> Path:
        """Write the diagram XML to a .drawio file and return the path."""
        out = Path(path)
        out.write_text(self.to_xml(), encoding="utf-8")
        return out
