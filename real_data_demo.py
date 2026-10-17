"""
Runs the full src/ai pipeline against the ACTUAL data/bookings.csv and the
real A1 scenario request within it, using the REAL src/lab/calculator.py --
no approximation anywhere, now that equipment.csv and grid_intensity.csv
both exist for real.

    python3 real_data_demo.py

Must be run from inside the real repo (ensu-lab-x/), with this file at the
repo root, since RealCalculator imports src.lab.calculator, which itself
expects data/equipment.csv, data/bookings.csv and data/grid_intensity.csv
to exist at <repo_root>/data/.
"""
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.ai.domain import Booking, load_equipment_csv
from src.ai.build import build_suggestion_set
from src.ai.calculator_adapter import RealCalculator
from src.contract.feedback import muted_pairs

REPO_ROOT = Path(__file__).resolve().parent
BOOKINGS_CSV = REPO_ROOT / "data" / "bookings.csv"
EQUIPMENT_CSV = REPO_ROOT / "data" / "equipment.csv"

with open(BOOKINGS_CSV, newline="") as f:
    rows = list(csv.DictReader(f))

all_bookings = [Booking.from_row(r) for r in rows]
bookings_by_id = {b.booking_id: b for b in all_bookings}

# The real A1 request: every row bookings.csv itself marks scenario == "True"
request_ids = [r["booking_id"] for r in rows if r["scenario"] == "True"]
request_bookings = [bookings_by_id[bid] for bid in request_ids]

equipment_by_id = load_equipment_csv(EQUIPMENT_CSV)
calc = RealCalculator()

result = build_suggestion_set(
    request_id="REQ-A1-2026-10-12",
    request_bookings=request_bookings,
    all_bookings=all_bookings,
    equipment_by_id=equipment_by_id,
    calc=calc,
    muted_pairs=muted_pairs(),  # rule 9, from data/feedback_log.json
)

print(json.dumps(result, indent=2))
print("\n--- sanity check: estimate.kg.typ should be close to README's ~24.9 kg ---")
print(f"got: {result['estimate']['kg']['typ']}")
