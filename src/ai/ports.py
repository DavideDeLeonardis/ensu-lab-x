"""
Ports: the EXACT interface of the real src/lab/calculator.py, confirmed
against its actual source (shared in chat). Two functions, both plain dicts
in/out -- no classes to match, which makes this simpler than the earlier
guessed version.

    estimate(equipment_id, start, end, shelves=1, warmup=True) -> {
        "kwh": float,
        "kg": {"low": float, "typ": float, "high": float},
        "avg_grid_g_per_kwh": float | None,
    }

    saving(booking_id, new_start=None, new_end=None, new_equipment=None,
           cancel=False, warmup=True) -> {
        "booking_id": str,
        "before": <estimate() shape>,
        "after": <estimate() shape>,
        "saving_kwh": float,
        "saving_kg": {"low": float, "typ": float, "high": float},
        "saving_pct": float,
    }

One function, `saving()`, covers all three of our candidate types just by
which arguments are passed -- there is no separate "merge" function:

    reschedule -> saving(booking_id, new_start=..., new_end=...)
    share      -> saving(booking_id, new_equipment=alt_id)
                  # new_start/new_end default to the booking's own -- same
                  # time, different unit.
    coordinate -> saving(booking_id, cancel=True)
                  # the booking being merged away is treated as fully
                  # cancelled (after = 0); its own footprint IS the saving,
                  # because its samples now ride along in another cycle
                  # that was going to run anyway.

`start`/`end` are strings in "%Y-%m-%d %H:%M", matching calculator.py's own
FMT -- not datetime objects. See domain.py's `fmt()` helper.
"""
from __future__ import annotations
from typing import Protocol, TypedDict, Optional


class KgRange(TypedDict):
    low: float
    typ: float
    high: float


class Estimate(TypedDict):
    kwh: float
    kg: KgRange
    avg_grid_g_per_kwh: Optional[float]


class SavingResult(TypedDict):
    booking_id: str
    before: Estimate
    after: Estimate
    saving_kwh: float
    saving_kg: KgRange
    saving_pct: float


class CalculatorPort(Protocol):
    def estimate(
        self, equipment_id: str, start: str, end: str, shelves: int = 1, warmup: bool = True
    ) -> Estimate: ...

    def saving(
        self,
        booking_id: str,
        new_start: Optional[str] = None,
        new_end: Optional[str] = None,
        new_equipment: Optional[str] = None,
        cancel: bool = False,
        warmup: bool = True,
    ) -> SavingResult: ...
