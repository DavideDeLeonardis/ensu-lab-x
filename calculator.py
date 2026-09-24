"""
Deterministic CO2 calculator for Lab X.

This is the ONLY place kWh and kg CO2e numbers come from. The AI layer proposes
changes; this module prices them. Reads data/equipment.csv and data/grid_intensity.csv.

Library use:
    from calculator import estimate, saving
    estimate("CONF-1", "2026-10-16 12:00", "2026-10-16 16:00", warmup=False)
    saving("BK-098", new_start="2026-10-16 12:00", new_end="2026-10-16 16:00", warmup=False)
    saving("BK-078", cancel=True)           # e.g. cycle merged into another group's cycle

CLI:
    python3 calculator.py estimate CONF-1 "2026-10-16 12:00" "2026-10-16 16:00" --no-warmup
    python3 calculator.py saving BK-098 "2026-10-16 12:00" "2026-10-16 16:00" --no-warmup
    python3 calculator.py saving BK-078 --cancel
"""

import argparse
import csv
import json
from datetime import datetime
from pathlib import Path

DATA = Path(__file__).parent / "data"
FMT = "%Y-%m-%d %H:%M"
STEP = 0.25  # hours


def _num(v):
    return float(v) if v not in ("", None) else 0.0


EQUIPMENT = {}
with open(DATA / "equipment.csv") as f:
    for r in csv.DictReader(f):
        EQUIPMENT[r["id"]] = r

GRID = []
with open(DATA / "grid_intensity.csv") as f:
    rows = list(csv.DictReader(f))
EPOCH = datetime.strptime(rows[0]["timestamp"], FMT)
GRID = [float(r["gco2_per_kwh"]) for r in rows]

BOOKINGS = {}
with open(DATA / "bookings.csv") as f:
    for r in csv.DictReader(f):
        BOOKINGS[r["booking_id"]] = r


def _h(ts):
    return (datetime.strptime(ts, FMT) - EPOCH).total_seconds() / 3600


def _grid(h):
    return GRID[max(0, min(len(GRID) - 1, int(h)))]


def estimate(equipment_id, start, end, shelves=1, warmup=True):
    """kWh and kg CO2e (low/typ/high) for using `equipment_id` from `start` to `end`."""
    e = EQUIPMENT[equipment_id]
    s, t = _h(start), _h(end)
    t = min(t, len(GRID))  # data window ends 18 Oct 24:00
    mode = e["mode"]
    chunks = []
    if mode == "cycle":
        n = max(1, round((t - s) / STEP))
        chunks = [(s + i * STEP, _num(e["kwh_per_cycle"]) / n) for i in range(n)]
    else:
        if mode == "hourly":
            kw = _num(e["active_kw"])
            s0 = s - (_num(e["warmup_min"]) / 60 if warmup else 0)
        elif mode == "shelf":
            kw = _num(e["kwh_per_day"]) / 24 / _num(e["shelves"]) * shelves
            s0 = s
        else:  # day / continuous
            kw = _num(e["kwh_per_day"]) / 24
            s0 = s
        h = s0
        while h < t - 1e-9:
            chunks.append((h, kw * STEP))
            h += STEP
    kwh = sum(k for _, k in chunks)
    kg = sum(k * _grid(h) / 1000 for h, k in chunks)
    return {
        "kwh": round(kwh, 3),
        "kg": {"low": round(kg * _num(e["low"]), 3), "typ": round(kg, 3), "high": round(kg * _num(e["high"]), 3)},
        "avg_grid_g_per_kwh": round(kg / kwh * 1000, 1) if kwh else None,
    }


def saving(booking_id, new_start=None, new_end=None, new_equipment=None, cancel=False, warmup=True):
    """kg CO2e saved by changing (or cancelling/merging) an existing booking. Positive = saving."""
    b = BOOKINGS[booking_id]
    shelves = int(b["shelves"]) if b["shelves"] else 1
    before = estimate(b["equipment_id"], b["start"], b["end"], shelves)
    if cancel:
        after = {"kwh": 0.0, "kg": {"low": 0.0, "typ": 0.0, "high": 0.0}}
    else:
        after = estimate(new_equipment or b["equipment_id"], new_start or b["start"], new_end or b["end"],
                         shelves, warmup=warmup)
    return {
        "booking_id": booking_id,
        "before": before,
        "after": after,
        "saving_kwh": round(before["kwh"] - after["kwh"], 3),
        "saving_kg": {k: round(before["kg"][k] - after["kg"][k], 3) for k in ("low", "typ", "high")},
        "saving_pct": round((1 - after["kg"]["typ"] / before["kg"]["typ"]) * 100, 1) if before["kg"]["typ"] else 0,
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Lab X CO2 calculator")
    sub = ap.add_subparsers(dest="cmd", required=True)
    pe = sub.add_parser("estimate")
    pe.add_argument("equipment_id")
    pe.add_argument("start")
    pe.add_argument("end")
    pe.add_argument("--shelves", type=int, default=1)
    pe.add_argument("--no-warmup", action="store_true")
    ps = sub.add_parser("saving")
    ps.add_argument("booking_id")
    ps.add_argument("new_start", nargs="?")
    ps.add_argument("new_end", nargs="?")
    ps.add_argument("--equipment")
    ps.add_argument("--cancel", action="store_true")
    ps.add_argument("--no-warmup", action="store_true")
    a = ap.parse_args()
    if a.cmd == "estimate":
        out = estimate(a.equipment_id, a.start, a.end, a.shelves, warmup=not a.no_warmup)
    else:
        out = saving(a.booking_id, a.new_start, a.new_end, a.equipment, a.cancel, warmup=not a.no_warmup)
    print(json.dumps(out, indent=2))
