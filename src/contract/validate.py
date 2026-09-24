"""
Check an AI output (SuggestionSet) or feedback events against the contract,
plus the rules a schema cannot express.

    pip install jsonschema
    python3 src/contract/validate.py contract/examples/A1_suggestion_set.json
    python3 src/contract/validate.py contract/examples/feedback_events.json
"""
import csv
import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
SCHEMAS = ROOT / "contract" / "schemas"
path = Path(sys.argv[1])
doc = json.loads(path.read_text())

bookings = {r["booking_id"]: r for r in csv.DictReader(open(ROOT / "data" / "bookings.csv"))}
errors = []

if isinstance(doc, list):  # feedback events
    schema = json.loads((SCHEMAS / "feedback_event.schema.json").read_text())
    for ev in doc:
        errors += [f"{ev.get('event_id')}: {e.message}" for e in Draft202012Validator(schema).iter_errors(ev)]
else:
    schema = json.loads((SCHEMAS / "suggestion_set.schema.json").read_text())
    errors += [e.message for e in Draft202012Validator(schema).iter_errors(doc)]
    sugg = doc.get("suggestions", [])
    # Rule: never touch a booking with movable = no
    for s in sugg:
        for bid in s.get("booking_ids", []):
            b = bookings.get(bid)
            if b is None:
                errors.append(f"{s['id']}: unknown booking {bid}")
            elif b["movable"] == "no":
                errors.append(f"{s['id']}: touches {bid}, which is fixed ({b['constraint']})")
    # Rule: sorted by saving, descending
    typ = [s["saving_kg"]["typ"] for s in sugg]
    if typ != sorted(typ, reverse=True):
        errors.append("suggestions are not sorted by saving_kg.typ (descending)")
    # Rule: every fixed booking in the request is listed as suppressed
    listed = {x["booking_id"] for x in doc.get("suppressed", [])}
    for bid in doc.get("booking_ids", []):
        if bookings.get(bid, {}).get("movable") == "no" and bid not in listed:
            errors.append(f"fixed booking {bid} missing from 'suppressed'")

if errors:
    print("INVALID")
    for e in errors:
        print(" -", e)
    sys.exit(1)
print("OK")
