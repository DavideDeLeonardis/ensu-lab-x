"""The UI's bridge to the real pipeline. It computes nothing itself: every kg comes from
src/lab/calculator.py via the AI team's build_suggestion_set, and feedback goes through
src/contract/feedback.append_event.

    from src.ui.engine import price_request, save_feedback
    sset, errors = price_request(request_json)   # BookingRequest -> SuggestionSet (+ validator errors)
    saved = save_feedback(events)                 # FeedbackEvents -> data/feedback_log.json
    rows = save_plan(req)                         # confirmed plan -> data/confirmed_bookings.csv

Used by src/ui/serve.py (live prototype) and src/ui/price_request.py (command line).

BookingRequest (proposed for CONTRACT.md §1):
    {"request_id": "REQ-A1-2026-10-12", "group": "A", "researcher": "A1",
     "bookings": [{"booking_id", "equipment_id", "start", "end", "purpose", "movable",
                   "constraint", "load_pct", "shelves"}, ...]}
New bookings (IDs the CSV doesn't know, e.g. BK-901) exist in memory only while pricing;
data/bookings.csv is never changed.
"""
import csv
import sys
import threading
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.lab import calculator  # noqa: E402
from src.ai.domain import Booking, load_equipment_csv  # noqa: E402
from src.ai.build import build_suggestion_set  # noqa: E402
from src.ai.calculator_adapter import RealCalculator  # noqa: E402
from src.contract import validate  # noqa: E402
from src.contract.feedback import append_event, load_events, muted_pairs  # noqa: E402

FIELDS = ("booking_id", "equipment_id", "start", "end", "purpose", "movable", "constraint", "load_pct", "shelves")
# Same columns as data/bookings.csv, so the file can be read the same way
CSV_COLUMNS = ["booking_id", "equipment_id", "group", "researcher", "start", "end", "purpose", "movable",
               "constraint", "load_pct", "shelves", "scenario", "kwh", "kg_low", "kg_typ", "kg_high"]
# The researcher's confirmed plan. Kept apart from data/bookings.csv, which src/lab/generate.py regenerates
# (and which the calculator, validator and AI load as the fixed demo lab).
CONFIRMED = ROOT / "data" / "confirmed_bookings.csv"
MOVABLE = {"no", "within day", "±1 day", "within week"}
CSV_ROWS = list(csv.DictReader(open(ROOT / "data/bookings.csv", newline="")))
EQUIPMENT = load_equipment_csv(ROOT / "data/equipment.csv")
_LOCK = threading.Lock()  # pricing patches module-level tables; one request at a time


@contextmanager
def _with_request_rows(rows):
    """Let the calculator and the validator see the request's rows (edited or new) while pricing."""
    saved = {name: dict(table) for name, table in (("calc", calculator.BOOKINGS), ("val", validate.BOOKINGS))}
    try:
        for r in rows:
            calculator.BOOKINGS[r["booking_id"]] = r
            validate.BOOKINGS[r["booking_id"]] = r
        yield
    finally:
        calculator.BOOKINGS.clear(); calculator.BOOKINGS.update(saved["calc"])
        validate.BOOKINGS.clear(); validate.BOOKINGS.update(saved["val"])


def price_request(req, llm=None):
    """BookingRequest dict -> (SuggestionSet dict, list of validator errors).

    `llm` (optional): an LLM client that picks among the allowed options and writes the text (src/ai/booking_ai.py).
    The booking purposes go to it scrubbed, as untrusted text; group and researcher ids never do."""
    group, researcher = req.get("group", "A"), req.get("researcher", "A1")
    req_ids = {b["booking_id"] for b in req["bookings"]}
    # the researcher's original rows are replaced by the request (they may have been edited or removed)
    original_own = {r["booking_id"] for r in CSV_ROWS if r["researcher"] == researcher and r["scenario"] == "True"}
    others = [r for r in CSV_ROWS if r["booking_id"] not in original_own | req_ids]

    rows = []
    for b in req["bookings"]:
        row = {k: ("" if b.get(k) is None else str(b.get(k))) for k in FIELDS}
        row.update(group=group, researcher=researcher, scenario="True")
        rows.append(row)

    with _LOCK, _with_request_rows(rows):
        request_bookings = [Booking.from_row(r) for r in rows]
        sset = build_suggestion_set(
            request_id=req["request_id"],
            request_bookings=request_bookings,
            all_bookings=[Booking.from_row(r) for r in others] + request_bookings,
            equipment_by_id=EQUIPMENT,
            calc=RealCalculator(),
            muted_pairs=muted_pairs(),  # rule 9, from data/feedback_log.json
            llm=llm,
            free_text="; ".join(r["purpose"] for r in rows if r["purpose"]),
        )
        errors = validate.check_suggestion_set(sset)
    return sset, errors


def save_feedback(events):
    """Append FeedbackEvents to data/feedback_log.json, renumbering event_id to follow the log."""
    n = len(load_events())
    saved = []
    for i, ev in enumerate(events, start=1):
        ev = {**ev, "event_id": f"FB-{n + i:04d}"}
        append_event(ev)  # validates against the schema first
        saved.append(ev)
    return saved


def load_plan():
    """The last confirmed plan (list of dicts), or None if nothing was confirmed yet."""
    if not CONFIRMED.exists():
        return None
    with open(CONFIRMED, newline="") as f:
        rows = list(csv.DictReader(f))
    return rows or None


def save_plan(req):
    """Write the confirmed plan to data/confirmed_bookings.csv (replaces the previous one).
    Every row is checked and priced with calculator.estimate(), like the kwh/kg columns of bookings.csv."""
    from datetime import datetime
    group, researcher = req.get("group", "A"), req.get("researcher", "A1")
    rows, seen = [], set()
    for b in req["bookings"]:
        row = {k: ("" if b.get(k) is None else str(b.get(k))) for k in FIELDS}
        bid, eq = row["booking_id"], row["equipment_id"]
        if not bid or bid in seen:
            raise ValueError(f"missing or duplicate booking_id {bid!r}")
        if eq not in calculator.EQUIPMENT:
            raise ValueError(f"{bid}: unknown equipment {eq!r}")
        if row["movable"] not in MOVABLE:
            raise ValueError(f"{bid}: invalid movable {row['movable']!r}")
        start, end = (datetime.strptime(row[k], "%Y-%m-%d %H:%M") for k in ("start", "end"))
        if end <= start:
            raise ValueError(f"{bid}: end must be after start")
        est = calculator.estimate(eq, row["start"], row["end"], shelves=int(row["shelves"] or 1))
        row.update(group=group, researcher=researcher, scenario="True", kwh=est["kwh"],
                   kg_low=est["kg"]["low"], kg_typ=est["kg"]["typ"], kg_high=est["kg"]["high"])
        rows.append(row)
        seen.add(bid)
    rows.sort(key=lambda r: r["start"])
    tmp = CONFIRMED.with_suffix(".tmp")
    with open(tmp, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        w.writeheader()
        w.writerows(rows)
    tmp.replace(CONFIRMED)  # atomic: never leaves a half-written file
    return rows


def reset_demo():
    """Back to the fixed demo: forget the confirmed plan and empty the feedback log."""
    if CONFIRMED.exists():
        CONFIRMED.unlink()
    from src.contract.feedback import LOG
    LOG.write_text("[]\n")
