
from weekly_auto import report_builder as rb
from weekly_auto.collectors import ChangeItem, SourceResult
from weekly_auto.util import work_week_from_label


def _sr(name, items):
    r = SourceResult(name=name, kind="test")
    r.items = items
    return r


def test_group_returns_six_tuple_with_transcripts():
    res = [_sr("repo", [
        ChangeItem("repo", "commit", "feat(ui): x", "2026-07-24", "h1"),
        ChangeItem("repo", "adr", "ADR-001: y", "2026-07-24", "ADR-001"),
        ChangeItem("repo", "email", "[Inbox] hi - a@b", "2026-07-24", ""),
        ChangeItem("repo", "meeting", "Standup", "2026-07-24", ""),
        ChangeItem("repo", "transcript", "Sync - 2 speaker(s)", "2026-07-24", "x.vtt"),
        ChangeItem("repo", "file", "notes.md", "2026-07-24", "notes.md"),
    ])]
    commits, adrs, emails, meetings, transcripts, warnings = rb._group(res)
    assert len(commits["repo"]) == 2   # commit + file both land in commits
    assert len(adrs) == 1
    assert len(emails) == 1
    assert len(meetings) == 1
    assert len(transcripts) == 1
    assert warnings == []


def test_warning_is_collected():
    r = SourceResult(name="bad", kind="test")
    r.warning = "unreachable"
    _, _, _, _, _, warnings = rb._group([r])
    assert warnings == ["bad: unreachable"]


def test_progress_lines_render_transcript_section():
    res = [_sr("m", [
        ChangeItem("m", "transcript", "Weekly Sync - 3 speaker(s), 40 cues", "2026-07-24", "a.vtt"),
    ])]
    lines = rb._progress_lines(res)
    assert any("Meeting transcripts captured" in ln for ln in lines)
    assert any("Weekly Sync" in ln for ln in lines)


def test_summarize_commits_extracts_scopes():
    items = [
        ChangeItem("r", "commit", "feat(ui): a", "", ""),
        ChangeItem("r", "commit", "docs(ops): b", "", ""),
    ]
    s = rb._summarize_commits(items)
    assert "across" in s and "ui" in s and "ops" in s


def test_summarize_commits_falls_back_to_types():
    items = [ChangeItem("r", "commit", "fix: a", "", ""),
             ChangeItem("r", "commit", "chore: b", "", "")]
    s = rb._summarize_commits(items)
    assert "fix" in s and "chore" in s


def test_summary_markdown_strips_subbullets():
    md = "\n".join([
        "## Progress",
        "- Source - 5 change(s):",
        "  - detail one (2026-07-24)",
        "  - detail two (2026-07-24)",
        "- Another summary line",
    ])
    out = rb.summary_markdown(md)
    assert "detail one" not in out
    assert "Another summary line" in out
    assert "Source - 5 change(s):" in out


def test_build_markdown_has_standard_sections():
    wk = work_week_from_label("WW30-2026")
    res = [_sr("repo", [ChangeItem("repo", "commit", "feat: x", "2026-07-16", "h")])]
    md = rb.build_markdown(wk, "Tester", res, {"blockers": [], "next_week": []})
    assert "## Progress" in md
    assert "## Blockers / Risks" in md
    assert "## Next Week" in md
    assert "None." in md and "TBD." in md


def test_read_notes_parses_sections(tmp_path):
    p = tmp_path / "notes.md"
    p.write_text("[Blockers]\n- b1\n\n[Next Week]\n- n1\n- n2\n", encoding="utf-8")
    notes = rb.read_notes(p)
    assert notes["blockers"] == ["b1"]
    assert notes["next_week"] == ["n1", "n2"]
