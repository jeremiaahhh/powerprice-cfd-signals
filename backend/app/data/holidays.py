"""
German holiday and calendar utilities.

Provides functions to detect German public holidays (all federal states'
nationwide holidays), weekends, and heuristic bridge days.

Relies on the `holidays` library (pip install holidays).
"""

from __future__ import annotations

import functools
from datetime import date, datetime, timezone, timedelta
from typing import Optional

import holidays

from app.core.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# German public holiday coverage
# ---------------------------------------------------------------------------

# Nationwide German holidays — these apply in every federal state.
# The `holidays` library supports per-state (subdiv) calendars; we combine
# across all 16 states to capture any day that is a public holiday in
# *at least one* state, since electricity demand is influenced by the most
# populated states.
_ALL_STATES = [
    "BB", "BE", "BW", "BY", "HB", "HE", "HH",
    "MV", "NI", "NW", "RP", "SH", "SL", "SN", "ST", "TH",
]

# Only these holidays are truly nationwide (common to all 16 states):
_NATIONWIDE_HOLIDAY_NAMES = {
    "Neujahr",                       # New Year's Day
    "Karfreitag",                    # Good Friday
    "Ostermontag",                   # Easter Monday
    "Tag der Arbeit",                # Labour Day (1 May)
    "Christi Himmelfahrt",           # Ascension Day
    "Pfingstmontag",                 # Whit Monday
    "Tag der Deutschen Einheit",     # German Unity Day (3 Oct)
    "1. Weihnachtstag",              # Christmas Day (25 Dec)
    "2. Weihnachtstag",              # Boxing Day (26 Dec)
}


# ---------------------------------------------------------------------------
# Year-level cache
# ---------------------------------------------------------------------------

@functools.lru_cache(maxsize=8)
def _get_holiday_calendar(year: int) -> dict[date, str]:
    """
    Build (and cache) a merged holiday calendar for Germany for *year*.

    The calendar maps ``date`` objects to the holiday name string.
    Where the same date exists in multiple state calendars, the first
    non-empty name is kept.
    """
    merged: dict[date, str] = {}

    for state in _ALL_STATES:
        try:
            cal = holidays.Germany(state=state, years=year)
            for dt, name in cal.items():
                if dt not in merged:
                    merged[dt] = name
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Could not build holiday calendar for state %s, year %d: %s",
                state, year, exc
            )

    logger.debug(
        "Holiday calendar for %d: %d unique holiday dates across all states",
        year, len(merged)
    )
    return merged


def _to_date(dt: datetime) -> date:
    """Convert a datetime (aware or naive) to a date in UTC-local-date sense."""
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc)
    return dt.date()


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def is_german_holiday(dt: datetime) -> bool:
    """
    Return True if *dt* falls on a German public holiday in any federal state.

    Parameters
    ----------
    dt:
        The datetime to check.  Timezone-aware datetimes are converted to
        UTC before extracting the date.
    """
    d = _to_date(dt)
    calendar = _get_holiday_calendar(d.year)
    return d in calendar


def get_holiday_name(dt: datetime) -> Optional[str]:
    """
    Return the German name of the public holiday on *dt*, or None if it is
    not a holiday.

    If the date appears in multiple state calendars with different names,
    the first name encountered is returned.

    Parameters
    ----------
    dt:
        The datetime to check.
    """
    d = _to_date(dt)
    calendar = _get_holiday_calendar(d.year)
    return calendar.get(d)


def is_weekend(dt: datetime) -> bool:
    """
    Return True if *dt* falls on a Saturday (weekday==5) or Sunday (weekday==6).

    Parameters
    ----------
    dt:
        The datetime to check.
    """
    d = _to_date(dt)
    return d.weekday() >= 5  # 5 = Saturday, 6 = Sunday


def is_non_working_day(dt: datetime) -> bool:
    """
    Return True if *dt* is a weekend day or a German public holiday.

    Convenience wrapper combining :func:`is_weekend` and
    :func:`is_german_holiday`.
    """
    return is_weekend(dt) or is_german_holiday(dt)


def is_bridge_day(dt: datetime) -> bool:
    """
    Heuristic detection of German "Brückentage" (bridge days).

    A bridge day is a weekday that falls between a public holiday and a
    weekend, making it attractive for employees to take as annual leave and
    thereby reducing electricity demand.

    Heuristic rules:
    1. The day itself must be a weekday (Mon–Fri) and NOT a public holiday.
    2. At least one of the immediately adjacent days (previous or next
       calendar day) must be a public holiday.
    3. The other adjacent day must be a weekend OR another public holiday.

    This catches the most common patterns, e.g.:
    - Friday between Thursday holiday and Saturday
    - Monday between Sunday and Tuesday holiday (rare but possible)

    Parameters
    ----------
    dt:
        The datetime to check.

    Returns
    -------
    bool
        True if the day is identified as a bridge day by the heuristic.
    """
    d = _to_date(dt)

    # Must be a regular weekday that is not itself a holiday
    if d.weekday() >= 5 or is_german_holiday(dt):
        return False

    prev_day = d - timedelta(days=1)
    next_day = d + timedelta(days=1)

    prev_dt = datetime(prev_day.year, prev_day.month, prev_day.day, tzinfo=timezone.utc)
    next_dt = datetime(next_day.year, next_day.month, next_day.day, tzinfo=timezone.utc)

    prev_is_non_working = is_non_working_day(prev_dt)
    next_is_non_working = is_non_working_day(next_dt)

    # At least one adjacent day is a holiday specifically (not just weekend)
    prev_is_holiday = is_german_holiday(prev_dt)
    next_is_holiday = is_german_holiday(next_dt)

    if not (prev_is_holiday or next_is_holiday):
        return False  # No adjacent holiday — not a bridge day

    # Both neighbours are non-working days (holiday + weekend or holiday + holiday)
    return prev_is_non_working and next_is_non_working


def day_type(dt: datetime) -> str:
    """
    Classify *dt* into a calendar day-type string relevant for price modelling.

    Returns one of:
    - ``"holiday"``      — German public holiday
    - ``"bridge_day"``   — heuristic bridge day (high absenteeism)
    - ``"weekend"``      — Saturday or Sunday (not a holiday)
    - ``"weekday"``      — ordinary Mon–Fri working day

    Parameters
    ----------
    dt:
        The datetime to classify.
    """
    if is_german_holiday(dt):
        return "holiday"
    if is_bridge_day(dt):
        return "bridge_day"
    if is_weekend(dt):
        return "weekend"
    return "weekday"


def get_calendar_features(dt: datetime) -> dict:
    """
    Return a dictionary of calendar feature flags for use in ML feature
    engineering.

    Keys
    ----
    is_holiday : bool
    is_weekend : bool
    is_bridge_day : bool
    is_non_working : bool
    day_of_week : int          — 0=Monday … 6=Sunday
    hour_of_day : int          — 0–23 (UTC hour)
    month : int                — 1–12
    day_type : str             — "holiday" | "bridge_day" | "weekend" | "weekday"
    holiday_name : str | None  — e.g. "Ostermontag"
    """
    d = _to_date(dt)
    return {
        "is_holiday": is_german_holiday(dt),
        "is_weekend": is_weekend(dt),
        "is_bridge_day": is_bridge_day(dt),
        "is_non_working": is_non_working_day(dt),
        "day_of_week": d.weekday(),
        "hour_of_day": dt.hour if dt.tzinfo else dt.replace(tzinfo=timezone.utc).hour,
        "month": d.month,
        "day_type": day_type(dt),
        "holiday_name": get_holiday_name(dt),
    }
