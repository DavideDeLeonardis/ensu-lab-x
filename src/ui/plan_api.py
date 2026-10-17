"""The experiment-plan side of the UI server (used by src/ui/serve.py). It computes no kg itself:
every number comes from the SuggestionSet, i.e. from src/lab/plan_calculator.py.

    GET  /plan                 the page (src/ui/plan.html)
    GET  /api/labs             labs + all their equipment (for the shared team profile, both pages)
    GET  /profile.js           the shared team profile script
    GET  /api/plan/catalog     labs + their equipment, items, equivalences, requirement tags, demo plan, LLM status
    POST /api/plan/suggest     {"plan", "basis", "use_llm", "provider"} → {"suggestion_set", "errors"[, "ai"]}  (400 if invalid)
                               "ai" (when the AI ran): what the rules alone would suggest, and what the AI left out
                               and why; for the UI only, not part of the SuggestionSet
    POST /api/plan/feedback    [FeedbackEvent] → {"saved": [...]}  (data/feedback_log.json; opt-in in the page)

No group or researcher data is ever sent to the page or stored: a team's choice of lab and equipment
stays in its own browser (localStorage).
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.lab import plan_calculator as calc  # noqa: E402
from src.ai.plan_engine import build_plan_suggestion_set, notes_exclusions  # noqa: E402
from src.contract import validate  # noqa: E402
from src.contract.feedback import append_event, load_events, muted_pairs  # noqa: E402

PAGE = Path(__file__).with_name("plan.html")
PROFILE_JS = Path(__file__).with_name("profile.js")
PLAN_A1 = ROOT / "data" / "plan_A1.json"
LABS = ROOT / "data" / "labs.json"
PLAN_MODES = {"hourly", "shelf", "day", "continuous"}   # equipment that can be a plan line (CONTRACT.md §1b)


def offered(e):
    """The UI offers only devices a team books and uses for a while: always-on lab infrastructure (freezers,
    heat block, water bath: bookable = False) is not part of an experiment, so it is not listed."""
    return e["bookable"] == "True"


def llm_status():
    """{"ollama": bool, "claude": bool}: which LLM providers can be used right now."""
    from src.ai.llm.providers import available
    return available()


def labs():
    """Labs a team can choose, each with all its equipment (grouped by room in the pages).

    `plan_line` says whether the device can be a plan line (priced per hour); an autoclave (per cycle) is
    bookings only. Used by both pages through the shared team profile (src/ui/profile.js)."""
    rooms = {r["id"]: r["name"] for r in json.loads((ROOT / "data/lab_data.json").read_text())["rooms"]}
    out = []
    for lab in json.loads(LABS.read_text()):
        equipment = [{"item_id": eid, "name": calc.EQUIPMENT[eid]["name"], "room": calc.EQUIPMENT[eid]["room"],
                      "plan_line": calc.EQUIPMENT[eid]["mode"] in PLAN_MODES}
                     for eid in lab["equipment"] if eid in calc.EQUIPMENT and offered(calc.EQUIPMENT[eid])]
        out.append({"lab_id": lab["lab_id"], "name": lab["name"], "note": lab.get("note", ""),
                    "rooms": {r: rooms.get(r, r) for r in lab["rooms"]}, "equipment": equipment})
    return out


def catalog():
    """Everything the page needs to edit a plan. No group or researcher data."""
    schema = json.loads((ROOT / "contract/schemas/experiment_plan.schema.json").read_text())
    tags = schema["properties"]["lines"]["items"]["properties"]["requirements"]["items"]["enum"]
    items = [{"item_id": c["item_id"], "name": c["name"], "unit": c["unit"], "kind": c["kind"],
              "confidence": c["confidence"], "source": c["source"]} for c in calc.CONSUMABLES.values()]
    items += [{"item_id": e["id"], "name": e["name"], "unit": "h", "kind": "equipment",
               "confidence": e["confidence"], "source": e["source"]}
              for e in calc.EQUIPMENT.values() if e["mode"] in PLAN_MODES and offered(e)]
    return {"labs": labs(), "items": items, "equivalences": list(calc.EQUIVALENCES.values()),
            "requirements": tags, "plan": json.loads(PLAN_A1.read_text()), "llm": llm_status()}


def quality(plan, basis=None):
    """How much of the estimate rests on measured, derived (published studies) or estimated factors, and the line
    that makes the range widest: the page's answer to "how accurate is this?" (not part of the SuggestionSet)."""
    est = calc.estimate_plan(plan, basis)
    total = est["kg"]["typ"] or 1.0
    conf = lambda i: (calc.CONSUMABLES.get(i) or calc.EQUIPMENT.get(i) or {}).get("confidence", "estimate")  # noqa: E731
    share = {}
    for ln in est["lines"]:
        share[conf(ln["item_id"])] = share.get(conf(ln["item_id"]), 0.0) + ln["kg"]["typ"]
    widest = max(est["lines"], key=lambda ln: ln["kg"]["high"] - ln["kg"]["low"])
    width = (est["kg"]["high"] - est["kg"]["low"]) or 1.0
    return {"share_pct": {k: round(100 * v / total, 1) for k, v in share.items()},
            "widest": {"line_id": widest["line_id"], "item_id": widest["item_id"], "confidence": conf(widest["item_id"]),
                       "share_of_range_pct": round(100 * (widest["kg"]["high"] - widest["kg"]["low"]) / width, 1)}}


def suggest(body):
    """{"plan", "basis", "use_llm", "provider", "note_exclusions"} → (status, response)."""
    plan = body.get("plan") or {}
    errors = validate.check_plan(plan)
    if errors:
        return 400, {"error": "invalid plan", "errors": errors}
    llm = None
    if body.get("use_llm"):
        from src.ai.llm.providers import get_llm
        provider = body.get("provider") if body.get("provider") in ("ollama", "claude") else None
        llm = get_llm(provider)
    basis, muted, trace = body.get("basis") or None, muted_pairs(), {}
    # rules-only runs keep out what the AI found ruled out by the notes, while the quote is still in the notes
    kept = [] if llm is not None else notes_exclusions(plan, body.get("note_exclusions"))
    sset = build_plan_suggestion_set(plan, llm=llm, basis=basis, muted_pairs=muted, trace=trace,
                                     excluded_eqs={k["equivalence_id"] for k in kept})
    out = {"suggestion_set": sset, "errors": validate.check_suggestion_set(sset, plan=plan),
           "quality": quality(plan, basis), "note_exclusions": kept}
    if llm is not None:   # the same plan with the rules only: the page shows what the AI changed
        rules = build_plan_suggestion_set(plan, basis=basis, muted_pairs=muted, usage_log=None)
        pick = lambda ss: [{"line_id": s["line_ids"][0], "equivalence_id": s["change"]["equivalence_id"]}  # noqa: E731
                           for s in ss["suggestions"]]
        out["ai"] = {"rules_choice": pick(rules), "left_out": trace.get("left_out", []),
                     "kept_without_quote": trace.get("kept_without_quote", []),
                     "omitted": trace.get("omitted", []),
                     "invalid_ids": trace.get("invalid_ids", 0)}
    return 200, out


def save_feedback(events):
    """Append FeedbackEvents (validated by append_event), numbering event_id after the log."""
    n = len(load_events())
    saved = []
    for i, ev in enumerate(events, start=1):
        ev = {**ev, "event_id": f"FB-{n + i:04d}"}
        append_event(ev)
        saved.append(ev)
    return saved
