from weekly_auto.graph_client import _DOCX_CT, _content_type


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
