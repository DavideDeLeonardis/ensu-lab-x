"""
Domain models matching data/bookings.csv, data/equipment.csv, and
data/scenario_request.csv as documented in README.md / CONTRACT.md, and as
confirmed against the real src/lab/calculator.py.

These are intentionally plain dataclasses with no calculator logic in them --
all kg/kWh numbers still come from calculator.py via ports.CalculatorPort.

NOTE on equipment.csv: calculator.py reads EQUIPMENT[r["id"]] -- the id
column is literally "id", not "equipment_id". It also reads e["shelves"]
for shelf-mode equipment (total shelf count of the unit), which isn't
listed in README.md's own equipment.csv data dictionary -- worth flagging
to the team, since the doc and the code appear to have drifted.
"""
from __future__ import annotations
import csv
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, Literal

FMT = "%Y-%m-%d %H:%M"  # matches calculator.py's own FMT exactly

MOVABLE_VALUES = {"no", "within day", "\u00b11 day", "within week"}
Confidence = Literal["measured", "derived", "estimate"]


def fmt(dt: datetime) -> str:
    """Format a datetime the way calculator.py expects it (it parses plain
    strings, not datetime objects, via its own FMT)."""
    return dt.strftime(FMT)


@dataclass(frozen=True)
class Booking:
    booking_id: str
    equipment_id: str
    start: datetime
    end: datetime
    movable: str          # one of MOVABLE_VALUES
    constraint: Optional[str] = None   # required when movable == "no"
    load_pct: Optional[float] = None   # autoclave-style loads
    shelves: Optional[int] = None      # incubator shelf share
    # Cached from bookings.csv's own kwh/kg_low/kg_typ/kg_high columns --
    # this is the CURRENT scheduled state as last priced by calculator.py,
    # NOT a substitute for calling calc.estimate()/calc.saving() for any
    # hypothetical change (Rule 5 still applies to those). Useful as a
    # ground-truth "before" figure when the real calculator can't be run
    # (e.g. equipment.csv/grid_intensity.csv aren't available yet).
    cached_kwh: Optional[float] = None
    cached_kg_typ: Optional[float] = None
    cached_kg_low: Optional[float] = None
    cached_kg_high: Optional[float] = None

    def __post_init__(self):
        if self.movable not in MOVABLE_VALUES:
            raise ValueError(f"unknown movable value: {self.movable!r}")
        if self.movable == "no" and not self.constraint:
            raise ValueError(f"{self.booking_id}: movable='no' requires a constraint")

    @staticmethod
    def from_row(row: dict) -> "Booking":
        def _opt_float(key: str) -> Optional[float]:
            v = row.get(key)
            return float(v) if v not in (None, "") else None

        return Booking(
            booking_id=row["booking_id"],
            equipment_id=row["equipment_id"],
            start=datetime.strptime(row["start"], FMT),
            end=datetime.strptime(row["end"], FMT),
            movable=row["movable"],
            constraint=row.get("constraint") or None,
            load_pct=_opt_float("load_pct"),
            shelves=int(row["shelves"]) if row.get("shelves") not in (None, "") else None,
            cached_kwh=_opt_float("kwh"),
            cached_kg_typ=_opt_float("kg_typ"),
            cached_kg_low=_opt_float("kg_low"),
            cached_kg_high=_opt_float("kg_high"),
        )


@dataclass(frozen=True)
class Equipment:
    equipment_id: str
    mode: str                 # hourly | cycle | shelf | day | continuous
    confidence: Confidence
    name: Optional[str] = None        # real column -- see candidates.derive_alternates
    category: Optional[str] = None    # real column, confirmed in equipment.csv
    room: Optional[str] = None        # real column, confirmed in equipment.csv
    bookable: Optional[bool] = None   # real column, confirmed in equipment.csv
    shareable: Optional[bool] = None  # real column -- NOT the substitutability
                                       # signal; see candidates.py docstring


# rule: "lowest confidence of the equipment values involved" (CONTRACT.md)
_CONFIDENCE_RANK = {"estimate": 0, "derived": 1, "measured": 2}
_RANK_TO_LABEL = {0: "low", 1: "medium", 2: "high"}


def lowest_confidence_label(equipment: list[Equipment]) -> str:
    """
    CONTRACT.md: confidence = the LOWEST confidence of the equipment values
    involved: estimate -> low, derived -> medium, measured -> high.

    This is pure data lookup, not something an LLM should decide -- kept here
    so both the AI layer and any future validator use the same one function.
    """
    if not equipment:
        raise ValueError("need at least one piece of equipment")
    worst_rank = min(_CONFIDENCE_RANK[e.confidence] for e in equipment)
    return _RANK_TO_LABEL[worst_rank]


# --- real CSV loaders --------------------------------------------------
# Same path convention as calculator.py itself: this file will live at
# src/ai/domain.py in the real repo, so parents[2] from here is the repo
# root, exactly like calculator.py's parents[2] from src/lab/calculator.py.
DATA = Path(__file__).resolve().parents[2] / "data"


def _csv_bool(v: Optional[str]) -> Optional[bool]:
    if v is None or v == "":
        return None
    return v.strip().lower() in ("true", "1", "yes")


def load_equipment_csv(path: Optional[Path] = None) -> dict[str, Equipment]:
    """Reads id, mode, confidence, category, room, bookable, shareable.
    calculator.py's own internal fields (active_kw, kwh_per_cycle, etc.)
    aren't needed here -- calculator.py owns those."""
    path = path or (DATA / "equipment.csv")
    out = {}
    with open(path) as f:
        for row in csv.DictReader(f):
            out[row["id"]] = Equipment(
                equipment_id=row["id"],
                mode=row["mode"],
                confidence=row["confidence"],
                name=row.get("name") or None,
                category=row.get("category") or None,
                room=row.get("room") or None,
                bookable=_csv_bool(row.get("bookable")),
                shareable=_csv_bool(row.get("shareable")),
            )
    return out
