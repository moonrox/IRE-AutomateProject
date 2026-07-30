from datetime import date, timedelta

from weekly_auto.util import (
    WorkWeek,
    intel_ww,
    work_week,
    work_week_from_label,
)


def test_reporting_window_is_thu_to_wed():
    wk = work_week_from_label("WW30", ref=date(2026, 7, 20))
    assert wk.start.weekday() == 3   # Thursday
    assert wk.end.weekday() == 2     # Wednesday
    assert (wk.end - wk.start).days == 6


def test_known_ww30_ww31_windows_2026():
    ww30 = work_week_from_label("WW30-2026")
    ww31 = work_week_from_label("WW31-2026")
    assert (ww30.start, ww30.end) == (date(2026, 7, 16), date(2026, 7, 22))
    assert (ww31.start, ww31.end) == (date(2026, 7, 23), date(2026, 7, 29))


def test_consecutive_weeks_tile_without_overlap():
    ww30 = work_week_from_label("WW30-2026")
    ww31 = work_week_from_label("WW31-2026")
    assert ww31.start == ww30.end + timedelta(days=1)


def test_until_iso_is_day_after_end():
    wk = work_week_from_label("WW30-2026")
    assert wk.until_iso == (wk.end + timedelta(days=1)).isoformat()
    assert wk.since_iso == wk.start.isoformat()


def test_label_and_human_strings():
    wk = work_week_from_label("WW32-2026")
    assert wk.label == "WW32"
    assert "Reporting window" in wk.human


def test_work_week_defaults_to_today():
    wk = work_week()
    assert isinstance(wk, WorkWeek)
    assert wk.start.weekday() == 3 and wk.end.weekday() == 2


def test_intel_ww_is_positive():
    assert intel_ww(date(2026, 7, 25)) >= 1
