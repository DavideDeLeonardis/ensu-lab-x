"""
Check an AI output (SuggestionSet), an ExperimentPlan or feedback events against the contract:
the JSON schemas plus every rule in CONTRACT.md §3 and §3b that code can check.

    pip install jsonschema
    python3 src/contract/validate.py contract/examples/A1_suggestion_set.json
    python3 src/contract/validate.py contract/examples/feedback_events.json
    python3 src/contract/validate.py <plan.json>                          # an ExperimentPlan
    python3 src/contract/validate.py <suggestion_set.json> --plan <plan.json>   # output for a plan

Library use (from the repo root):
    from src.contract.validate import check_suggestion_set, check_plan, check_feedback
    errors = check_suggestion_set(doc)               # booking request output; [] means valid
    errors = check_suggestion_set(doc, plan=plan)    # experiment plan output

Plan outputs are checked fail-closed: if the catalogue (data/consumables.csv,
data/equivalences.csv) or the plan calculator is missing, the rules that need them report an error.
"""
import csv
import json
import re
import sys
from datetime import datetime
from functools import lru_cache
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

# Rule 11: numbers written next to "kg" or "%" in the text
KG_IN_TEXT = re.compile(r"(\d+(?:\.\d+)?)\s*kg\b")
PCT_IN_TEXT = re.compile(r"(\d+(?:\.\d+)?)\s*%")


@lru_cache(maxsize=1)
def _plan_data():
    """(consumables by item_id, equivalences by equivalence_id), or None while the files don't exist."""
    cons, eqs = DATA / "consumables.csv", DATA / "equivalences.csv"
    if not (cons.exists() and eqs.exists()):
        return None
    with open(cons) as f:
        consumables = {r["item_id"]: r for r in csv.DictReader(f)}
    with open(eqs) as f:
        equivalences = {r["equivalence_id"]: r for r in csv.DictReader(f)}
    return consumables, equivalences


def _plan_saving(plan, line_id, equivalence_id, basis=None):
    """Rule 5 for plans: the plan calculator's saving result, or None if it can't price this pair."""
    try:
        from src.lab.plan_calculator import plan_saving
    except (ImportError, OSError):   # calculator or its data files missing
        return None
    try:
        return plan_saving(plan, line_id, equivalence_id, basis)
    except ValueError:               # pair not allowed: already reported by rule 2
        return None


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

    # Rule 11: a "%" in the text may also be an autoclave load ("a 45% load")
    loads = [BOOKINGS.get(x, {}).get("load_pct") for x in
             s.get("booking_ids", []) + [change.get("merge_into_booking_id")]]
    return errs + _check_text_and_threshold(s, extra_pct=[float(x) for x in loads if x])


def _names_in(text):
    """Rule 7: group names and researcher IDs found in `text`."""
    found = [f"names a group ('{n}')" for n in GROUP_NAMES if n.lower() in text.lower()]
    m = RESEARCHER_RE.search(text)
    if m:
        found.append(f"names a researcher ('{m.group(0)}')")
    return found


def _written_matches(written, values):
    """True if `written` (e.g. '1.9') is one of `values` rounded to the precision written."""
    decimals = len(written.split(".")[1]) if "." in written else 0
    return any(abs(float(v) - float(written)) <= 0.5 * 10 ** -decimals + 1e-9 for v in values)


def _check_text_and_threshold(s, extra_kg=(), extra_pct=()):
    """Rules 6, 7, 8 and 11: shared by booking and plan suggestions."""
    errs = []
    sid = s.get("id", "?")
    # Rule 6
    if not str(s.get("tradeoff", "")).strip():
        errs.append(f"{sid}: tradeoff is empty")
    # Rule 7: no group names or researcher IDs in the text
    text = " ".join(str(s.get(k, "")) for k in ("headline", "why", "tradeoff"))
    errs += [f"{sid}: text {e}" for e in _names_in(text)]
    # Rule 11: numbers in the text come from the calculator (or from the data, e.g. a load or a quantity)
    kg_values = list(s.get("saving_kg", {}).values()) + list(extra_kg)
    pct_values = [s["saving_pct"]] * ("saving_pct" in s) + list(extra_pct)
    for written in KG_IN_TEXT.findall(text):
        if not _written_matches(written, kg_values):
            errs.append(f"{sid}: text says '{written} kg', which is not a calculator value (rule 11)")
    for written in PCT_IN_TEXT.findall(text):
        if not _written_matches(written, pct_values):
            errs.append(f"{sid}: text says '{written}%', which is not a calculator value (rule 11)")
    # Rule 8
    if s.get("saving_kg", {}).get("typ", 0) < MIN_SAVING_KG:
        errs.append(f"{sid}: saves {s['saving_kg']['typ']} kg, below the {MIN_SAVING_KG} kg threshold")
    return errs


def _check_plan_suggestion(s, plan, basis=None):
    """Rules 1, 2, 5, 6 for one suggestion on an experiment plan (`basis`: the electricity basis of the output)."""
    errs = []
    lines = {ln["line_id"]: ln for ln in plan.get("lines", [])}
    sid = s.get("id", "?")
    change = s.get("change", {})
    line_ids = s.get("line_ids", [])
    if len(line_ids) != 1:
        return [f"{sid}: a plan suggestion changes exactly one line"]
    lid = line_ids[0]
    line = lines.get(lid)
    if line is None:
        return [f"{sid}: line {lid} is not part of this plan"]
    if change.get("line_id") != lid:
        errs.append(f"{sid}: change.line_id {change.get('line_id')} does not match line_ids {lid}")
    # Rule 1
    if line.get("locked"):
        return errs + [f"{sid}: touches {lid}, which is locked ({line.get('lock_reason', '')})"]

    data = _plan_data()
    if data is None:
        return errs + [f"{sid}: rules 2 and 5 need data/consumables.csv and data/equivalences.csv"]
    consumables, equivalences = data

    # Rule 2: only a curated equivalence for this item, compatible with the line's requirements
    eq = equivalences.get(change.get("equivalence_id", ""))
    if eq is None:
        return errs + [f"{sid}: {change.get('equivalence_id')} is not in data/equivalences.csv (rule 2)"]
    if eq["item_id"] != line["item_id"]:
        errs.append(f"{sid}: {eq['equivalence_id']} is for {eq['item_id']}, not for {line['item_id']} (rule 2)")
    if change.get("alternative_id") != eq["alternative_id"]:
        errs.append(f"{sid}: alternative {change.get('alternative_id')} does not match {eq['equivalence_id']} (rule 2)")
    if s.get("type") != eq["type"]:
        errs.append(f"{sid}: type {s.get('type')} does not match {eq['equivalence_id']} ({eq['type']})")
    clash = set(line.get("requirements", [])) & {t for t in eq["incompatible_with"].split(";") if t}
    if clash:
        errs.append(f"{sid}: {eq['equivalence_id']} is incompatible with the line's requirements {sorted(clash)} (rule 2)")
    expected_qty = line["quantity"] * float(eq["ratio"])
    if abs(change.get("new_quantity", -1) - expected_qty) > 1e-6 * max(1.0, expected_qty):
        errs.append(f"{sid}: new_quantity {change.get('new_quantity')} is not quantity × ratio ({expected_qty:g})")
    for flag in ("needs_other_party", "requires_validation"):
        if bool(s.get(flag, False)) != (eq[flag] == "True"):
            errs.append(f"{sid}: {flag} does not match {eq['equivalence_id']}")
    # Rule 6: a change that needs validation says so
    if eq["requires_validation"] == "True" and "validat" not in str(s.get("tradeoff", "")).lower():
        errs.append(f"{sid}: requires validation but the trade-off does not say so (rule 6)")

    # Rule 5: numbers must match the plan calculator
    result = _plan_saving(plan, lid, eq["equivalence_id"], basis)
    if result is None:
        errs.append(f"{sid}: rule 5: the plan calculator cannot re-price this suggestion")
    elif "saving_kg" in s and not _close(s["saving_kg"], result["saving_kg"]):
        errs.append(f"{sid}: saving_kg.typ {s['saving_kg']['typ']} does not match calculator "
                    f"({result['saving_kg']['typ']:.3f})")

    # Rule 11: a kg quantity of the item itself may appear in the text
    in_kg = consumables.get(line["item_id"], {}).get("unit") == "kg"
    return errs + _check_text_and_threshold(
        s, extra_kg=[line["quantity"], change.get("new_quantity", 0)] if in_kg else ())


def _schema_errors(name, doc):
    schema = json.loads((SCHEMAS / name).read_text())
    return [f"schema: {e.message[:200]}" for e in Draft202012Validator(schema).iter_errors(doc)]


def check_plan(plan):
    """An ExperimentPlan: schema, privacy of plan_id, and (once the catalogue exists) known items and units."""
    errors = _schema_errors("experiment_plan.schema.json", plan)
    errors += [f"plan_id {e}" for e in _names_in(str(plan.get("plan_id", "")))]
    ids = [ln.get("line_id") for ln in plan.get("lines", [])]
    if len(ids) != len(set(ids)):
        errors.append("plan: line_ids must be unique")
    data = _plan_data()
    if data is not None:
        consumables, _ = data
        for ln in plan.get("lines", []):
            item, unit = ln.get("item_id"), ln.get("unit")
            expected = consumables.get(item, {}).get("unit") or ("h" if item in EQUIPMENT else None)
            if expected is None:
                errors.append(f"plan: {ln.get('line_id')}: unknown item {item}")
            elif unit != expected:
                errors.append(f"plan: {ln.get('line_id')}: unit {unit} does not match the catalogue ({expected})")
    return errors


def check_suggestion_set(doc, plan=None):
    """Errors for a SuggestionSet ([] = valid). Pass the ExperimentPlan when the output is for a plan."""
    errors = _schema_errors("suggestion_set.schema.json", doc)
    request_ids = set(doc.get("booking_ids", []))
    sugg = doc.get("suggestions", [])
    is_plan = "line_ids" in doc or any("line_ids" in s for s in sugg)

    if is_plan:
        if plan is None:
            return errors + ["plan output: pass the ExperimentPlan to check it (validate.py <output> --plan <plan>)"]
        errors += [f"plan: {e}" for e in check_plan(plan)]
        errors += _check_plan_output(doc, plan)
        for s in sugg:
            basis = doc.get("estimate", {}).get("electricity", {}).get("basis")
            errors += _check_plan_suggestion(s, plan, basis) if "line_ids" in s else \
                [f"{s.get('id', '?')}: a plan output cannot contain booking suggestions"]
    else:
        for s in sugg:
            errors += _check_suggestion(s, request_ids)

    # Savings must be additive for the UI (estimate after Accept): one suggestion per booking / line
    touched = [x for s in sugg for x in s.get("booking_ids", []) + s.get("line_ids", [])]
    if len(touched) != len(set(touched)):
        errors.append("two suggestions change the same booking or line (savings would not add up)")

    # Rule 4: biggest saving first
    typ = [s["saving_kg"]["typ"] for s in sugg if "saving_kg" in s]
    if typ != sorted(typ, reverse=True):
        errors.append("suggestions are not sorted by saving_kg.typ (descending)")

    # Rule 1: every fixed booking in the request is listed as suppressed
    listed = {x.get("booking_id") for x in doc.get("suppressed", [])}
    for bid in request_ids:
        if BOOKINGS.get(bid, {}).get("movable") == "no" and bid not in listed:
            errors.append(f"fixed booking {bid} missing from 'suppressed'")

    # Hotspots: one entry per device (or item), largest first
    hs = doc.get("estimate", {}).get("hotspots", [])
    ids = [h.get("equipment_id") or h.get("item_id") for h in hs]
    if len(ids) != len(set(ids)):
        errors.append("hotspots must be aggregated per equipment_id / item_id (duplicates found)")
    if [h["kg_typ"] for h in hs] != sorted((h["kg_typ"] for h in hs), reverse=True):
        errors.append("hotspots are not sorted by kg_typ (descending)")
    return errors


def _check_plan_output(doc, plan):
    """Plan-level checks: same plan, generator stated, rule 7 on the id, rule 1 for locked lines."""
    errors = []
    if doc.get("request_id") != plan.get("plan_id"):
        errors.append(f"request_id {doc.get('request_id')} is not the plan_id {plan.get('plan_id')}")
    errors += [f"request_id {e}" for e in _names_in(str(doc.get("request_id", "")))]
    plan_lines = [ln["line_id"] for ln in plan.get("lines", [])]
    if sorted(doc.get("line_ids", [])) != sorted(plan_lines):
        errors.append("line_ids do not match the plan's lines")
    if "generator" not in doc:
        errors.append("plan output must say who proposed and phrased the suggestions ('generator')")
    listed = {x.get("line_id") for x in doc.get("suppressed", [])}
    for ln in plan.get("lines", []):
        if ln.get("locked") and ln["line_id"] not in listed:
            errors.append(f"locked line {ln['line_id']} missing from 'suppressed'")
    return errors


def check_feedback(events):
    schema = json.loads((SCHEMAS / "feedback_event.schema.json").read_text())
    return [f"{ev.get('event_id')}: {e.message}" for ev in events
            for e in Draft202012Validator(schema).iter_errors(ev)]


def main():
    args = sys.argv[1:]
    plan = None
    if len(args) == 3 and args[1] == "--plan":
        plan = json.loads(Path(args[2]).read_text())
    elif len(args) != 1:
        sys.exit(__doc__)
    doc = json.loads(Path(args[0]).read_text())
    if isinstance(doc, list):
        errors = check_feedback(doc)
    elif "lines" in doc:
        errors = check_plan(doc)
    else:
        errors = check_suggestion_set(doc, plan=plan)
    if errors:
        print("INVALID")
        for e in errors:
            print(" -", e)
        sys.exit(1)
    print("OK")


if __name__ == "__main__":
    main()
