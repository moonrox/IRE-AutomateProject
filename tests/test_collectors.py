from weekly_auto.collectors import _parse_vtt, _safe_name, _vtt_summary

SAMPLE_VTT = """WEBVTT

00:00:01.000 --> 00:00:04.500
<v John Monroe>Welcome everyone to the sync.</v>

00:00:05.000 --> 00:00:09.250
<v Jane Doe>Thanks John, quick update on the dashboard.</v>

00:00:10.000 --> 00:00:12.800
<v John Monroe>Great, go ahead.</v>
"""


def test_parse_vtt_extracts_speakers_and_cues():
    p = _parse_vtt(SAMPLE_VTT)
    assert p["speakers"] == ["John Monroe", "Jane Doe"]
    assert p["cues"] == 3
    assert p["duration"] == "00:00:12"
    assert p["first_line"].startswith("Welcome everyone")


def test_parse_vtt_empty():
    p = _parse_vtt("WEBVTT\n")
    assert p["cues"] == 0
    assert p["speakers"] == []


def test_vtt_summary_mentions_speakers_and_cues():
    s = _vtt_summary(SAMPLE_VTT)
    assert "2 speaker(s)" in s
    assert "3 cues" in s


def test_vtt_summary_no_cues():
    s = _vtt_summary("WEBVTT\n")
    assert "no spoken cues" in s


def test_safe_name_sanitizes():
    assert _safe_name("Weekly Sync: Q3/2026 <plan>") == "Weekly_Sync_Q3_2026_plan"
    assert _safe_name("///") == "meeting"
    assert len(_safe_name("x" * 200)) <= 80
