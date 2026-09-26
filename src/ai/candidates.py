"""
Deterministic candidate generation.

Nothing in this file calls an LLM. Given a booking and the rest of the
lab's schedule, it proposes *where it might be worth checking* -- candidate
reschedule times, candidate alternate equipment, candidate merge targets.
Whether a candidate is actually worth suggesting (i.e. whether it saves
enough CO2e) is decided later, in ranking.py, using calculator.py numbers.

This file never touches a `movable == "no"` booking -- that's enforced at
the type level: callers only pass bookings that are already known movable.

NOTE: equipment "alternates" for share candidates now use derive_alternates()
below, based on equipment.csv's real category/room/shareable columns.
FALLBACK_EQUIPMENT_ALTERNATES is only used while equipment.csv has no data
rows to derive anything from (true as of this writing).
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import timedelta, datetime
from typing import Optional

from .domain import Booking, Equipment

# Fallback only -- used when no Equipment data is available at all (e.g.
# equipment.csv has no data rows yet, as of this writing). Once real
# equipment.csv rows exist, `derive_alternates()` below replaces this
# entirely using the real category/room/shareable columns.
FALLBACK_EQUIPMENT_ALTERNATES: dict[str, list[str]] = {
    "BSC-1": ["BSC-2"],
    "BSC-2": ["BSC-1"],
}


import re

_TRAILING_PAREN = re.compile(r"\s*\([^)]*\)\s*$")


def _normalized_name(name: str) -> str:
    """Strips a trailing parenthetical qualifier, e.g. "Biosafety cabinet
    class II (large, older)" -> "Biosafety cabinet class II". Two units are
    genuinely the same *kind* of thing if this matches; category+room+mode
    alone is NOT enough (see derive_alternates' docstring)."""
    return _TRAILING_PAREN.sub("", name).strip().lower()


def derive_alternates(equipment_by_id: dict[str, Equipment]) -> dict[str, list[str]]:
    """
    Two units are alternates if they are the same underlying KIND of
    equipment (name matches once a trailing size/age/model qualifier in
    parentheses is stripped) AND share category + room + mode.

    Category+room+mode alone is NOT enough: the real equipment.csv has
    CONF-1 (Confocal microscope) and FLU-1 (Widefield fluorescence
    microscope) sharing category="Imaging", room="micro", mode="hourly" --
    but they are genuinely different imaging techniques, not substitutes
    for the same experiment (swapping one for the other would break Rule 2,
    "never change the experiment itself"). Name-stripped-of-qualifier
    correctly separates them (different base names) while still pairing
    BSC-1/"...class II (large, older)" with BSC-2/"...class II (small)"
    (same base name, different size) and all three INC-* incubators
    (identical name).

    NOT gated on `shareable` either -- see the note in an earlier revision
    of this function (kept in version control / chat): shareable=False on
    BOTH BSC-1 and BSC-2 rules out using that flag for this purpose.
    """
    alternates: dict[str, list[str]] = {}
    by_group: dict[tuple, list[str]] = {}
    for eq in equipment_by_id.values():
        if not eq.name or not eq.category or not eq.room or not eq.mode:
            continue
        key = (_normalized_name(eq.name), eq.category, eq.room, eq.mode)
        by_group.setdefault(key, []).append(eq.equipment_id)
    for ids in by_group.values():
        for eid in ids:
            alternates[eid] = [other for other in ids if other != eid]
    return alternates

# Equipment ids that use load_pct-based cycles (autoclave-style) and can
# therefore be merged with another partial-load booking.
MERGEABLE_MODE_EQUIPMENT_HINT = ("AUT",)  # crude prefix match; replace with a
                                          # real `mode == "cycle"` check once
                                          # equipment.csv is loaded properly.


def _movable_window(booking: Booking) -> tuple[datetime, datetime]:
    """Earliest/latest start time this booking may be moved to, per its
    `movable` value. Duration is preserved by the caller."""
    if booking.movable == "within day":
        day_start = booking.start.replace(hour=0, minute=0)
        day_end = booking.start.replace(hour=23, minute=59)
        return day_start, day_end
    if booking.movable == "\u00b11 day":
        return booking.start - timedelta(days=1), booking.start + timedelta(days=1)
    if booking.movable == "within week":
        return booking.start - timedelta(days=booking.start.weekday()), \
               booking.start + timedelta(days=6 - booking.start.weekday())
    raise ValueError(f"generate candidates called on a non-movable booking: {booking.booking_id}")


def _overlaps(a_start, a_end, b_start, b_end) -> bool:
    return a_start < b_end and b_start < a_end


@dataclass(frozen=True)
class RescheduleCandidate:
    booking_id: str
    new_start: datetime
    new_end: datetime


@dataclass(frozen=True)
class ShareCandidate:
    booking_id: str
    new_equipment_id: str


@dataclass(frozen=True)
class CoordinateCandidate:
    booking_id: str
    merge_into_booking_id: str


def generate_reschedule_candidates(
    booking: Booking, all_bookings: list[Booking], step_minutes: int = 60
) -> list[RescheduleCandidate]:
    """Every hour-aligned slot within the movable window where the same
    equipment isn't already booked by someone else."""
    if booking.movable == "no":
        return []
    duration = booking.end - booking.start
    window_start, window_end = _movable_window(booking)

    others = [
        b for b in all_bookings
        if b.equipment_id == booking.equipment_id and b.booking_id != booking.booking_id
    ]

    candidates: list[RescheduleCandidate] = []
    t = window_start
    while t + duration <= window_end:
        if t != booking.start:
            conflict = any(_overlaps(t, t + duration, b.start, b.end) for b in others)
            if not conflict:
                candidates.append(RescheduleCandidate(booking.booking_id, t, t + duration))
        t += timedelta(minutes=step_minutes)
    return candidates


def generate_share_candidates(
    booking: Booking, all_bookings: list[Booking],
    alternates: Optional[dict[str, list[str]]] = None,
) -> list[ShareCandidate]:
    """Alternate equipment that is free during this booking's current time
    window. `alternates` should come from derive_alternates(equipment_by_id)
    once equipment.csv has real rows; falls back to a hand-written map
    otherwise so the pipeline still runs meanwhile."""
    if booking.movable == "no":
        return []
    alternates = alternates if alternates is not None else FALLBACK_EQUIPMENT_ALTERNATES
    candidates_for = alternates.get(booking.equipment_id, [])
    out = []
    for alt_id in candidates_for:
        clashes = [
            b for b in all_bookings
            if b.equipment_id == alt_id
            and _overlaps(booking.start, booking.end, b.start, b.end)
        ]
        if not clashes:
            out.append(ShareCandidate(booking.booking_id, alt_id))
    return out


def generate_coordinate_candidates(
    booking: Booking, all_bookings: list[Booking]
) -> list[CoordinateCandidate]:
    """Other bookings on the same load-based equipment whose load_pct could
    be combined with this one's (<=100% together), within a loose +/-1 day
    window so the merge is still practically useful to the researcher."""
    if booking.movable == "no" or booking.load_pct is None:
        return []
    if not booking.equipment_id.startswith(MERGEABLE_MODE_EQUIPMENT_HINT):
        return []

    window_start = booking.start - timedelta(days=1)
    window_end = booking.start + timedelta(days=1)

    out = []
    for other in all_bookings:
        if other.booking_id == booking.booking_id or other.equipment_id != booking.equipment_id:
            continue
        if other.load_pct is None:
            continue
        if not (window_start <= other.start <= window_end):
            continue
        if booking.load_pct + other.load_pct <= 100:
            out.append(CoordinateCandidate(booking.booking_id, other.booking_id))
    return out
