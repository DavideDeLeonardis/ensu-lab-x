"""Build the booking page from src/ui/app_template.html (serve.py calls build_html on every request).

Injects a SuggestionSet (default: contract/examples/A1_suggestion_set_from_ai_layer.json) and a slim lab lookup
(equipment names, the request's bookings, grid curve). Other groups' bookings are reduced to times + load:
no group, researcher or purpose (CONTRACT.md rule 7).
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
UI = ROOT / "src" / "ui"


DEFAULT_SUGGESTIONS = ROOT / "contract/examples/A1_suggestion_set_from_ai_layer.json"


def build_html(suggestions_path=DEFAULT_SUGGESTIONS, placeholders=False):
    """The page as a string, with the SuggestionSet and the lab lookup baked in."""
    sset = json.loads(Path(suggestions_path).read_text())
    lab = json.loads((ROOT / "data/lab_data.json").read_text())
    # Only the two JSON interface files are read (CSV is the lab team's dummy-data source):
    # the SuggestionSet above, and data/lab_data.json for display data (CONTRACT.md §5).
    request = [b for b in lab["bookings"] if b["scenario"]]          # the demo request (A1)
    own = {b["booking_id"] for b in request}
    own_group = next((g["name"] for g in lab["groups"] if g["id"] == request[0]["group"]), "") if request else ""

    # All bookings are embedded (so a SuggestionSet loaded later in the page still resolves),
    # but only the researcher's own carry purpose/constraint.
    bookings = {}
    for b in lab["bookings"]:
        slim = {k: b[k] for k in ("booking_id", "equipment_id", "start", "end", "movable", "load_pct", "shelves")}
        if b["booking_id"] in own:
            slim.update(purpose=b["purpose"], constraint=b["constraint"], shelves=b["shelves"], own=True,
                        kg_typ=b["kg_typ"])
        else:
            slim["own"] = False  # another group's booking: never carries a name
        bookings[b["booking_id"]] = slim

    payload = {
        "placeholders": bool(placeholders),   # demo: explanation panels show "to be filled in"
        "suggestion_set": sset,
        "lab": {
            "epoch": lab["epoch"],
            "grid": lab["grid"],
            "equipment": {e["id"]: {"name": e["name"], "room": e["room"], "mode": e["mode"],
                                     "bookable": e["bookable"], "shelves": e.get("shelves") or None,
                                     "confidence": e["confidence"], "source": e["source"],
                                     "basis": e["basis"]} for e in lab["equipment"]},
            "rooms": {r["id"]: r["name"] for r in lab["rooms"]},
            "sources": lab["sources"],
            "days": lab["days"],
            "request_order": [b["booking_id"] for b in sorted(request, key=lambda b: b["start"])],
            "own_group": own_group,   # the researcher's own group only; never other groups (rule 7)
            "bookings": bookings,
        },
    }
    return (UI / "app_template.html").read_text().replace(
        "/*__DATA__*/null", json.dumps(payload, ensure_ascii=False)), sset
