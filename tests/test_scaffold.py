"""Tests for scaffold.py — security-focused validation."""
from __future__ import annotations

import pytest

from scaffold import _validate_scaffold_inputs, _build_vars


class TestValidateScaffoldInputs:
    def test_valid_name_and_description_pass(self) -> None:
        _validate_scaffold_inputs("MyProject", "A simple project")

    def test_name_with_template_syntax_raises(self) -> None:
        with pytest.raises(ValueError, match="template placeholder syntax"):
            _validate_scaffold_inputs("{{DESCRIPTION}}", "some desc")

    def test_description_with_template_syntax_raises(self) -> None:
        with pytest.raises(ValueError, match="template placeholder syntax"):
            _validate_scaffold_inputs("MyProject", "desc {{PROJECT_NAME}}")

    def test_closing_braces_also_rejected(self) -> None:
        with pytest.raises(ValueError, match="template placeholder syntax"):
            _validate_scaffold_inputs("Bad}}Name", "desc")

    def test_build_vars_rejects_injected_name(self) -> None:
        with pytest.raises(ValueError):
            _build_vars("{{DESCRIPTION}}", "injected")

    def test_build_vars_returns_correct_keys_for_valid_input(self) -> None:
        result = _build_vars("MyTool", "Does things")
        assert result["PROJECT_NAME"] == "MyTool"
        assert result["PROJECT_SLUG"] == "mytool"
        assert result["DESCRIPTION"] == "Does things"
        assert "DATE" in result
