"""
Deterministic CO2 calculator for experiment plans (CONTRACT.md §1b).

This is the ONLY place kg CO2e numbers for plans come from. Each line is priced as
quantity × emission factor: the non-electric part (`kg_per_unit`) plus electricity
(`kwh_per_unit`, or the device's kW for equipment lines) × the electricity factor.
Reads data/consumables.csv, data/equivalences.csv, data/electricity_factors.csv, data/equipment.csv.

The electricity factor's basis is `location` (NL grid average, default) or `market` (green contract);
set it with LABX_ELECTRICITY_BASIS or the `basis` argument.

Library use (from the repo root):
    from src.lab.plan_calculator import estimate_plan, plan_saving
    plan = json.load(open("data/plan_A1.json"))
    estimate_plan(plan)                         # totals, breakdown, one entry per line
    plan_saving(plan, "L1", "EQ-001")           # saving if line L1 follows equivalence EQ-001

CLI (from the repo root):
    python3 src/lab/plan_calculator.py estimate data/plan_A1.json [--basis market]
    python3 src/lab/plan_calculator.py saving data/plan_A1.json L1 EQ-001 [--basis market]
"""

import argparse
import csv
import json
import os
from pathlib import Path

DATA = Path(__file__).resolve().parents[2] / "data"
BOUNDS = ("low", "typ", "high")


def _rows(name, key):
    with open(DATA / name) as f:
        return {r[key]: r for r in csv.DictReader(f)}


def _num(v):
    return float(v) if v not in ("", None) else 0.0


CONSUMABLES = _rows("consumables.csv", "item_id")
EQUIVALENCES = _rows("equivalences.csv", "equivalence_id")
ELECTRICITY = _rows("electricity_factors.csv", "basis")
EQUIPMENT = _rows("equipment.csv", "id")


def electricity_factor(basis=None):
    """The electricity_factors.csv row for `basis` (default: LABX_ELECTRICITY_BASIS, else 'location')."""
    basis = basis or os.environ.get("LABX_ELECTRICITY_BASIS", "location")
    if basis not in ELECTRICITY:
        raise ValueError(f"unknown electricity basis {basis!r} (expected one of {sorted(ELECTRICITY)})")
    return ELECTRICITY[basis]


def _equipment_kw(e):
    """Average kW of one unit-hour of equipment, by mode (a shelf-mode hour is one shelf)."""
    mode = e["mode"]
    if mode == "hourly":
        return _num(e["active_kw"])
    if mode == "shelf":
        return _num(e["kwh_per_day"]) / 24 / _num(e["shelves"])
    if mode in ("day", "continuous"):
        return _num(e["kwh_per_day"]) / 24
    raise ValueError(f"{e['id']}: mode {mode!r} cannot be a plan line (priced per cycle, not per hour)")


def _price(item_id, quantity, g_per_kwh):
    """Unrounded kWh and kg CO2e ranges (embodied, electricity) for `quantity` of `item_id`."""
    if item_id in CONSUMABLES:
        c = CONSUMABLES[item_id]
        embodied = quantity * _num(c["kg_per_unit"])
        kwh = quantity * _num(c["kwh_per_unit"])
    elif item_id in EQUIPMENT:
        c = EQUIPMENT[item_id]
        embodied = 0.0
        kwh = quantity * _equipment_kw(c)
    else:
        raise ValueError(f"unknown item {item_id!r}")
    electricity = kwh * g_per_kwh / 1000
    mult = {"low": _num(c["low"]), "typ": 1.0, "high": _num(c["high"])}
    return kwh, {k: embodied * mult[k] for k in BOUNDS}, {k: electricity * mult[k] for k in BOUNDS}


def _rounded(kwh, embodied, electricity, **extra):
    return {
        **extra,
        "kwh": round(kwh, 3),
        "embodied": {k: round(embodied[k], 3) for k in BOUNDS},
        "electricity": {k: round(electricity[k], 3) for k in BOUNDS},
        "kg": {k: round(embodied[k] + electricity[k], 3) for k in BOUNDS},
    }


def estimate_line(line, basis=None):
    """kWh and kg CO2e (low/typ/high, split into embodied and electricity) for one plan line."""
    g = _num(electricity_factor(basis)["g_per_kwh"])
    kwh, emb, ele = _price(line["item_id"], line["quantity"], g)
    return _rounded(kwh, emb, ele, line_id=line["line_id"], item_id=line["item_id"],
                    locked=bool(line.get("locked")))


def estimate_plan(plan, basis=None):
    """Totals for the whole plan, the electricity factor used, and one estimate per line.

    Top-level keys mirror SuggestionSet.estimate: `kwh`, `kg`, `breakdown` {embodied, electricity},
    `electricity` (the factor: basis, g_per_kwh, source); plus `lines`."""
    factor = electricity_factor(basis)
    g = _num(factor["g_per_kwh"])
    lines, kwh, emb, ele = [], 0.0, dict.fromkeys(BOUNDS, 0.0), dict.fromkeys(BOUNDS, 0.0)
    for ln in plan["lines"]:
        k, e, el = _price(ln["item_id"], ln["quantity"], g)
        kwh += k
        for b in BOUNDS:
            emb[b] += e[b]
            ele[b] += el[b]
        lines.append(_rounded(k, e, el, line_id=ln["line_id"], item_id=ln["item_id"], locked=bool(ln.get("locked"))))
    total = _rounded(kwh, emb, ele)
    return {
        "kwh": total["kwh"],
        "kg": total["kg"],
        "breakdown": {"embodied": total["embodied"], "electricity": total["electricity"]},
        "electricity": {"basis": factor["basis"], "g_per_kwh": g, "source": factor["source"]},
        "lines": lines,
    }


def plan_saving(plan, line_id, equivalence_id, basis=None):
    """kg CO2e saved if line `line_id` follows the curated equivalence. Positive = saving.

    Each bound is before − after; the three values are then sorted so low ≤ typ ≤ high
    (CONTRACT.md §2, saving range for plans). Raises ValueError for a pair the curated list
    does not allow for this line (wrong item, clashing requirement, locked line)."""
    line = next((ln for ln in plan["lines"] if ln["line_id"] == line_id), None)
    if line is None:
        raise ValueError(f"line {line_id!r} is not in the plan")
    if line.get("locked"):
        raise ValueError(f"line {line_id} is locked ({line.get('lock_reason', '')})")
    eq = EQUIVALENCES.get(equivalence_id)
    if eq is None:
        raise ValueError(f"{equivalence_id!r} is not in data/equivalences.csv")
    if eq["item_id"] != line["item_id"]:
        raise ValueError(f"{equivalence_id} is for {eq['item_id']}, not for {line['item_id']}")
    clash = set(line.get("requirements", [])) & {t for t in eq["incompatible_with"].split(";") if t}
    if clash:
        raise ValueError(f"{equivalence_id} is incompatible with the line's requirements {sorted(clash)}")

    new_quantity = line["quantity"] * _num(eq["ratio"])
    g = _num(electricity_factor(basis)["g_per_kwh"])
    before = _rounded(*_price(line["item_id"], line["quantity"], g))
    after = _rounded(*_price(eq["alternative_id"], new_quantity, g))
    diffs = sorted(round(before["kg"][k] - after["kg"][k], 3) for k in BOUNDS)
    return {
        "line_id": line_id,
        "equivalence_id": equivalence_id,
        "alternative_id": eq["alternative_id"],
        "new_quantity": new_quantity,
        "before": before,
        "after": after,
        "saving_kwh": round(before["kwh"] - after["kwh"], 3),
        "saving_kg": dict(zip(BOUNDS, diffs)),
        "saving_pct": round((1 - after["kg"]["typ"] / before["kg"]["typ"]) * 100, 1) if before["kg"]["typ"] else 0,
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Lab X plan CO2 calculator")
    sub = ap.add_subparsers(dest="cmd", required=True)
    pe = sub.add_parser("estimate")
    pe.add_argument("plan")
    ps = sub.add_parser("saving")
    ps.add_argument("plan")
    ps.add_argument("line_id")
    ps.add_argument("equivalence_id")
    for p in (pe, ps):
        p.add_argument("--basis", choices=sorted(ELECTRICITY))
    a = ap.parse_args()
    plan = json.loads(Path(a.plan).read_text())
    out = estimate_plan(plan, a.basis) if a.cmd == "estimate" else plan_saving(plan, a.line_id, a.equivalence_id, a.basis)
    print(json.dumps(out, indent=2, ensure_ascii=False))
