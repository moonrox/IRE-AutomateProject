import json

import pytest

import weekly_auto.graph_client as gc
from weekly_auto.graph_client import _DOCX_CT, GraphAuthError, GraphClient, _content_type


def test_content_type_markdown():
    assert _content_type("report.md") == "text/markdown"
    assert _content_type("a.markdown") == "text/markdown"


def test_content_type_docx():
    assert _content_type("weekly.docx") == _DOCX_CT


def test_content_type_common():
    assert _content_type("a.txt") == "text/plain"
    assert _content_type("a.pdf") == "application/pdf"
    assert _content_type("a.html") == "text/html"


def test_content_type_unknown_falls_back():
    assert _content_type("archive.zip") == "application/octet-stream"
    assert _content_type("noext") == "application/octet-stream"


# ── auth_mode / az login ──────────────────────────────────────────────────────

def test_invalid_auth_mode_rejected():
    with pytest.raises(GraphAuthError):
        GraphClient(auth_mode="bogus")


def _fake_proc(returncode=0, stdout="", stderr=""):
    class P:
        pass
    p = P()
    p.returncode = returncode
    p.stdout = stdout
    p.stderr = stderr
    return p


def test_token_from_az_success(monkeypatch):
    monkeypatch.setattr(gc.shutil, "which", lambda name: "C:/az.cmd")
    monkeypatch.setattr(
        gc.subprocess, "run",
        lambda *a, **k: _fake_proc(0, json.dumps({"accessToken": "AZ_TOK"})),
    )
    assert GraphClient(auth_mode="az").token() == "AZ_TOK"


def test_token_from_az_missing_cli(monkeypatch):
    monkeypatch.setattr(gc.shutil, "which", lambda name: None)
    with pytest.raises(GraphAuthError, match="Azure CLI"):
        GraphClient(auth_mode="az").token()


def test_token_from_az_not_logged_in(monkeypatch):
    monkeypatch.setattr(gc.shutil, "which", lambda name: "C:/az.cmd")
    monkeypatch.setattr(
        gc.subprocess, "run",
        lambda *a, **k: _fake_proc(1, "", "Please run 'az login'"),
    )
    with pytest.raises(GraphAuthError, match="az login"):
        GraphClient(auth_mode="az").token()


def test_auto_falls_back_to_az_when_no_cache(monkeypatch, tmp_path):
    # Point the refresh cache at a non-existent file so auto skips it.
    monkeypatch.setattr(GraphClient, "_refresh_cache_path",
                        lambda self: tmp_path / "missing.bin")
    monkeypatch.setattr(gc.shutil, "which", lambda name: "C:/az.cmd")
    monkeypatch.setattr(
        gc.subprocess, "run",
        lambda *a, **k: _fake_proc(0, json.dumps({"accessToken": "AZ_FALLBACK"})),
    )
    assert GraphClient(auth_mode="auto").token() == "AZ_FALLBACK"


def test_refresh_mode_requires_tenant_client(monkeypatch, tmp_path):
    cache = tmp_path / "IRE-graph_refresh.bin"
    cache.write_text("x")
    monkeypatch.setattr(GraphClient, "_refresh_cache_path", lambda self: cache)
    with pytest.raises(GraphAuthError, match="DEV_TENANT_ID"):
        GraphClient(auth_mode="refresh_token").token()

