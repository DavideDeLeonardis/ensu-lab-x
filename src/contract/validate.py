"""
Check an AI output (SuggestionSet) or feedback events against the contract:
the JSON schemas plus every rule in CONTRACT.md §3 that code can check.

    pip install jsonschema
    python3 src/contract/validate.py contract/examples/A1_suggestion_set.json
    python3 src/contract/validate.py contract/examples/feedback_events.json

Library use (from the repo root):
    from src.contract.validate import check_suggestion_set, check_feedback
    errors = check_suggestion_set(doc)   # [] means valid
"""
import csv
import json
import re
import sys
from datetime import datetime
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from src.lab import calculator  # noqa: E402  (rule 5: re-price every suggestion)
from src.contract.rules import LAB_OPEN_HOUR, LAB_CLOSE_HOUR, in_lab_hours  # noqa: E402
from src.contract import rules  # noqa: E402

SCHEMAS = ROOT / "contract" / "schemas"
DATA = ROOT / "data"
FMT = "%Y-%m-%d %H:%M"

MIN_SAVING_KG = 0.2      # rule 8
NUMERIC_TOLERANCE = 0.01  # rule 5: kg may be rounded to 2 decimals

BOOKINGS = {r["booking_id"]: r for r in csv.DictReader(open(DATA / "bookings.csv"))}
EQUIPMENT = {r["id"]: r for r in csv.DictReader(open(DATA / "equipment.csv"))}
_lab = json.loads((DATA / "lab_data.json").read_text())
GROUP_NAMES = [g["name"] for g in _lab["groups"]]
RESEARCHER_RE = re.compile(r"\b(" + "|".join(r for g in _lab["groups"] for r in g["researchers"]) + r")\b")


def _t(s):
    return datetime.strptime(s, FMT)


def movable_window(booking):
    """rules.movable_window for a bookings.csv row."""
    return rules.movable_window(_t(booking["start"]), _t(booking["end"]), booking["movable"])


def _close(a, b):
    return all(abs(a[k] - b[k]) <= NUMERIC_TOLERANCE for k in ("low", "typ", "high"))


def _check_suggestion(s, request_ids):
    errs = []
    sid = s.get("id", "?")
    change = s.get("change", {})
    for bid in s.get("booking_ids", []):
        b = BOOKINGS.get(bid)
        if b is None:
            errs.append(f"{sid}: unknown booking {bid}")
            continue
        if bid not in request_ids:
            errs.append(f"{sid}: {bid} is not part of this request")
        # Rule 1
        if b["movable"] == "no":
            errs.append(f"{sid}: touches {bid}, which is fixed ({b['constraint']})")
            continue

        # Rule 3: new times inside the movable window and inside lab hours
        if "new_start" in change or "new_end" in change:
            ns = _t(change.get("new_start", b["start"]))
            ne = _t(change.get("new_end", b["end"]))
            lo, hi = movable_window(b)
            if ns < lo or ne > hi:
                errs.append(f"{sid}: new slot {ns:%a %d %b %H:%M}–{ne:%H:%M} is outside {bid}'s "
                            f"'{b['movable']}' window ({lo:%a %d %b %H:%M} → {hi:%a %d %b %H:%M})")
            if not in_lab_hours(ns, ne):
                errs.append(f"{sid}: new slot {ns:%a %d %b %H:%M}–{ne:%H:%M} is outside lab hours "
                            f"(Mon–Fri {LAB_OPEN_HOUR:02d}:00–{LAB_CLOSE_HOUR:02d}:00)")
            if ne - ns != _t(b["end"]) - _t(b["start"]):
                errs.append(f"{sid}: rescheduling changes the duration of {bid} (rule 2)")

        # Rule 2 for share: same kind of device
        if "new_equipment_id" in change:
            alt = EQUIPMENT.get(change["new_equipment_id"])
            cur = EQUIPMENT[b["equipment_id"]]
            if alt is None:
                errs.append(f"{sid}: unknown equipment {change['new_equipment_id']}")
            elif (alt["category"], alt["mode"]) != (cur["category"], cur["mode"]):
                errs.append(f"{sid}: {alt['id']} is not the same kind of device as {cur['id']} (rule 2)")

        # Rule 3 for coordinate: merge target on the same cycle device, inside the window, load fits
        if "merge_into_booking_id" in change:
            t = BOOKINGS.get(change["merge_into_booking_id"])
            if t is None:
                errs.append(f"{sid}: unknown merge target {change['merge_into_booking_id']}")
            else:
                lo, hi = movable_window(b)
                if t["equipment_id"] != b["equipment_id"] or EQUIPMENT[b["equipment_id"]]["mode"] != "cycle":
                    errs.append(f"{sid}: can only merge into a cycle on the same device")
                if not (lo <= _t(t["start"]) and _t(t["end"]) <= hi):
                    errs.append(f"{sid}: merge target {t['booking_id']} is outside {bid}'s '{b['movable']}' window")
                if t["load_pct"] and b["load_pct"] and float(t["load_pct"]) + float(b["load_pct"]) > 100:
                    errs.append(f"{sid}: combined load {t['load_pct']}% + {b['load_pct']}% exceeds 100%")
                # Rule 7: another group's booking must be flagged
                if t["group"] != b["group"] and not s.get("needs_other_party"):
                    errs.append(f"{sid}: merges into another group's booking but needs_other_party is false")

        # Rule 5: numbers must match the calculator
        if len(s.get("booking_ids", [])) == 1 and "saving_kg" in s:
            if "merge_into_booking_id" in change:
                options = [calculator.saving(bid, cancel=True)]
            else:
                kw = dict(new_start=change.get("new_start"), new_end=change.get("new_end"),
                          new_equipment=change.get("new_equipment_id"))
                options = [calculator.saving(bid, warmup=w, **kw) for w in (True, False)]
            if not any(_close(s["saving_kg"], o["saving_kg"]) for o in options):
                exp = " or ".join(f"{o['saving_kg']['typ']:.3f}" for o in options)
                errs.append(f"{sid}: saving_kg.typ {s['saving_kg']['typ']} does not match calculator ({exp})")

    # Rule 6
    if not str(s.get("tradeoff", "")).strip():
        errs.append(f"{sid}: tradeoff is empty")
    # Rule 7: no group names or researcher IDs in the text
    text = " ".join(str(s.get(k, "")) for k in ("headline", "why", "tradeoff"))
    for name in GROUP_NAMES:
        if name.lower() in text.lower():
            errs.append(f"{sid}: text names a group ('{name}')")
    m = RESEARCHER_RE.search(text)
    if m:
        errs.append(f"{sid}: text names a researcher ('{m.group(0)}')")
    # Rule 8
    if s.get("saving_kg", {}).get("typ", 0) < MIN_SAVING_KG:
        errs.append(f"{sid}: saves {s['saving_kg']['typ']} kg, below the {MIN_SAVING_KG} kg threshold")
    return errs


def check_suggestion_set(doc):
    schema = json.loads((SCHEMAS / "suggestion_set.schema.json").read_text())
    errors = [f"schema: {e.message[:200]}" for e in Draft202012Validator(schema).iter_errors(doc)]
    request_ids = set(doc.get("booking_ids", []))
    sugg = doc.get("suggestions", [])

    for s in sugg:
        errors += _check_suggestion(s, request_ids)

    # Savings must be additive for the UI (estimate after Accept): one suggestion per booking
    touched = [bid for s in sugg for bid in s.get("booking_ids", [])]
    if len(touched) != len(set(touched)):
        errors.append("two suggestions change the same booking (savings would not add up)")

    # Rule 4: biggest saving first
    typ = [s["saving_kg"]["typ"] for s in sugg if "saving_kg" in s]
    if typ != sorted(typ, reverse=True):
        errors.append("suggestions are not sorted by saving_kg.typ (descending)")

    # Rule 1: every fixed booking in the request is listed as suppressed
    listed = {x["booking_id"] for x in doc.get("suppressed", [])}
    for bid in request_ids:
        if BOOKINGS.get(bid, {}).get("movable") == "no" and bid not in listed:
            errors.append(f"fixed booking {bid} missing from 'suppressed'")

    # Hotspots: one entry per device, largest first
    hs = doc.get("estimate", {}).get("hotspots", [])
    ids = [h["equipment_id"] for h in hs]
    if len(ids) != len(set(ids)):
        errors.append("hotspots must be aggregated per equipment_id (duplicates found)")
    if [h["kg_typ"] for h in hs] != sorted((h["kg_typ"] for h in hs), reverse=True):
        errors.append("hotspots are not sorted by kg_typ (descending)")
    return errors


def check_feedback(events):
    schema = json.loads((SCHEMAS / "feedback_event.schema.json").read_text())
    return [f"{ev.get('event_id')}: {e.message}" for ev in events
            for e in Draft202012Validator(schema).iter_errors(ev)]


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    doc = json.loads(Path(sys.argv[1]).read_text())
    errors = check_feedback(doc) if isinstance(doc, list) else check_suggestion_set(doc)
    if errors:
        print("INVALID")
        for e in errors:
            print(" -", e)
        sys.exit(1)
    print("OK")


if __name__ == "__main__":
    main()
