"""
The contract's time rules (CONTRACT.md §3, rule 3) as code: the single source of truth,
used by both the AI layer (src/ai/candidates.py) and the validator (src/contract/validate.py).
Pure standard library, no data loading.
"""
from datetime import datetime, timedelta

LAB_OPEN_HOUR, LAB_CLOSE_HOUR = 8, 20  # the tool only proposes Mon–Fri, 08:00–20:00


def movable_window(start: datetime, end: datetime, movable: str):
    """(earliest start, latest end) a moved booking must fit in, or None if `movable == "no"`."""
    if movable == "within day":
        day = start.replace(hour=0, minute=0)
        return day, day + timedelta(days=1)
    if movable == "±1 day":
        return start - timedelta(days=1), end + timedelta(days=1)
    if movable == "within week":
        monday = (start - timedelta(days=start.weekday())).replace(hour=0, minute=0)
        return monday, monday + timedelta(days=7)
    if movable == "no":
        return None
    raise ValueError(f"unknown movable value: {movable!r}")


def in_lab_hours(start: datetime, end: datetime) -> bool:
    """True if the whole slot is on one weekday, inside LAB_OPEN_HOUR–LAB_CLOSE_HOUR."""
    return (start.weekday() < 5 and start.date() == end.date()
            and start.hour >= LAB_OPEN_HOUR
            and (end.hour, end.minute) <= (LAB_CLOSE_HOUR, 0))
