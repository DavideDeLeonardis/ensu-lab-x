"""
Runs the whole src/ai pipeline on a small synthetic set of bookings shaped
like the README's A1 demo case (bioreactor locked, confocal reschedulable,
autoclave coordinate-able, BSC shareable, incubator shelves locked), using
MockCalculator so this runs with zero external dependencies and without the
real repo files.

    python3 demo_run.py

Once you have the real calculator.py, equipment.csv and scenario_request.csv,
replace the synthetic data below with a real CSV loader and swap
MockCalculator for a real adapter -- nothing in src/ai/*.py besides this
script and mock_calculator.py needs to change.
"""
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.ai.domain import Booking, Equipment
from src.ai.build import build_suggestion_set
from src.ai.mock_calculator import MockCalculator


def dt(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%d %H:%M")


# --- synthetic bookings, loosely shaped like the A1 demo case in README.md ---
request_bookings = [
    Booking("BK-057", "BIO-1", dt("2026-10-12 08:00"), dt("2026-10-16 08:00"),
            movable="no", constraint="continuous 96h bioreactor conditioning protocol"),
    Booking("BK-078", "AUT-1", dt("2026-10-13 17:00"), dt("2026-10-13 18:00"),
            movable="within week", load_pct=40),
    Booking("BK-091", "CONF-1", dt("2026-10-15 19:00"), dt("2026-10-15 23:00"),
            movable="within week"),
    Booking("BK-104", "BSC-1", dt("2026-10-14 09:00"), dt("2026-10-14 12:00"),
            movable="within day"),
    Booking("BK-112", "INC-1", dt("2026-10-12 00:00"), dt("2026-10-16 23:59"),
            movable="no", constraint="continuous cell culture, shelves 3-4"),
]

# another group's booking, present so a coordinate candidate exists
other_group_bookings = [
    Booking("BK-075", "AUT-1", dt("2026-10-13 16:00"), dt("2026-10-13 17:00"),
            movable="no", constraint="other group's fixed protocol step", load_pct=45),
]

all_bookings = request_bookings + other_group_bookings

equipment_by_id = {
    "BIO-1": Equipment("BIO-1", mode="continuous", confidence="measured"),
    "AUT-1": Equipment("AUT-1", mode="cycle", confidence="derived"),
    "CONF-1": Equipment("CONF-1", mode="hourly", confidence="measured"),
    "BSC-1": Equipment("BSC-1", mode="hourly", confidence="estimate"),
    "BSC-2": Equipment("BSC-2", mode="hourly", confidence="estimate"),
    "INC-1": Equipment("INC-1", mode="shelf", confidence="measured"),
}

bookings_by_id = {b.booking_id: b for b in all_bookings}

# Rough kg/hour so the demo produces plausible-looking numbers; not real data.
kg_per_hour = {
    "BIO-1": 0.166,   # ~15.94 kg over 96h
    "AUT-1": 2.05,    # 1h booking -> ~2.05 kg
    "CONF-1": 0.70,   # 4h booking, evening/overnight mix
    "BSC-1": 0.90,    # 3h booking, daytime
    "BSC-2": 0.50,    # more efficient unit -> a real share benefit to find
    "INC-1": 0.0142,  # ~1.70 kg over ~120h
}

calc = MockCalculator(kg_per_hour, bookings_by_id)

result = build_suggestion_set(
    request_id="REQ-A1-2026-10-12-DEMO",
    request_bookings=request_bookings,
    all_bookings=all_bookings,
    equipment_by_id=equipment_by_id,
    calc=calc,
)

print(json.dumps(result, indent=2))
