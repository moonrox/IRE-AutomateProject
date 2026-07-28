"""weekly_auto.util - Intel Work Week helpers and small shared utilities."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import NamedTuple


def _jan1_sunday(year: int) -> date:
    """Return the Sunday on or before Jan 1 of `year` (Intel WW1 start)."""
    jan1 = date(year, 1, 1)
    dow_net = (jan1.weekday() + 1) % 7  # 0=Sun .. 6=Sat
    return jan1 - timedelta(days=dow_net)


def intel_ww(d: date) -> int:
    """Return the Intel work-week number for date `d`."""
    return (d - _jan1_sunday(d.year)).days // 7 + 1


class WorkWeek(NamedTuple):
    ww: int
    year: int
    start: date   # Sunday (inclusive)
    end: date     # Saturday (inclusive)

    @property
    def label(self) -> str:
        return f"WW{self.ww}"

    @property
    def since_iso(self) -> str:
        return self.start.isoformat()

    @property
    def until_iso(self) -> str:
        # git --until is inclusive of the day; use end-of-day next day
        return (self.end + timedelta(days=1)).isoformat()

    @property
    def human(self) -> str:
        return (
            f"WW{self.ww} - Week of "
            f"{self.start.strftime('%b %d')}-{self.end.strftime('%b %d, %Y')}"
        )


def work_week(d: date | None = None) -> WorkWeek:
    """Return the WorkWeek (number, year, Sun-Sat window) containing `d`."""
    d = d or date.today()
    start = _sunday_of(d)
    end = start + timedelta(days=6)
    return WorkWeek(ww=intel_ww(d), year=d.year, start=start, end=end)


def work_week_from_label(label: str, ref: date | None = None) -> WorkWeek:
    """Build a WorkWeek from a 'WW30' or 'WW30-2026' label."""
    ref = ref or date.today()
    label = label.upper().replace("WW", "")
    if "-" in label:
        ww_str, year_str = label.split("-", 1)
        ww, year = int(ww_str), int(year_str)
    else:
        ww, year = int(label), ref.year
    start = _jan1_sunday(year) + timedelta(weeks=ww - 1)
    end = start + timedelta(days=6)
    return WorkWeek(ww=ww, year=year, start=start, end=end)


def _sunday_of(d: date) -> date:
    """Return the Sunday that starts the calendar week containing `d`."""
    return d - timedelta(days=(d.weekday() + 1) % 7)


def now_stamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")
