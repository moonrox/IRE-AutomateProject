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
    start: date   # Thursday (inclusive) - reporting window opens
    end: date     # Wednesday (inclusive) - report due date

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
            f"WW{self.ww} - Reporting window "
            f"{self.start.strftime('%a %b %d')} - "
            f"{self.end.strftime('%a %b %d, %Y')}"
        )


def _report_window(ww: int, year: int) -> tuple[date, date]:
    """Thu-AM -> Wed-PM reporting window for an Intel work week.

    The report is due on Wednesday, so the window covers the trailing 7 days:
    the Wednesday that falls inside the WW's Sun-Sat span, back to the prior
    Thursday. Consecutive work weeks tile without overlap
    (e.g. WW30 = Thu Jul 16 -> Wed Jul 22, WW31 = Thu Jul 23 -> Wed Jul 29).
    """
    ww_sunday = _jan1_sunday(year) + timedelta(weeks=ww - 1)
    wednesday = ww_sunday + timedelta(days=3)   # Sun + 3 = Wed
    thursday = wednesday - timedelta(days=6)     # prior Thursday
    return thursday, wednesday


def work_week(d: date | None = None) -> WorkWeek:
    """Return the WorkWeek (number, year, Thu-Wed reporting window) for `d`."""
    d = d or date.today()
    ww, year = intel_ww(d), d.year
    start, end = _report_window(ww, year)
    return WorkWeek(ww=ww, year=year, start=start, end=end)


def work_week_from_label(label: str, ref: date | None = None) -> WorkWeek:
    """Build a WorkWeek (Thu-Wed reporting window) from 'WW30' or 'WW30-2026'."""
    ref = ref or date.today()
    label = label.upper().replace("WW", "")
    if "-" in label:
        ww_str, year_str = label.split("-", 1)
        ww, year = int(ww_str), int(year_str)
    else:
        ww, year = int(label), ref.year
    start, end = _report_window(ww, year)
    return WorkWeek(ww=ww, year=year, start=start, end=end)


def _sunday_of(d: date) -> date:
    """Return the Sunday that starts the calendar week containing `d`."""
    return d - timedelta(days=(d.weekday() + 1) % 7)


def now_stamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")
