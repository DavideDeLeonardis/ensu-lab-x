"""
Feedback log (CONTRACT.md §4): the UI appends FeedbackEvents to data/feedback_log.json,
the AI layer reads it to apply rule 9 (muting).

    from src.contract.feedback import append_event, muted_pairs
    append_event({...})                 # UI, after Accept / Reject / Modify / Flag
    muted = muted_pairs()               # AI, before ranking -> {("coordinate", "AUT-1"), ...}

The log is lab-level: events carry no researcher or group ID (Phase 1, §3.1).
"""
import json
from collections import Counter
from pathlib import Path

LOG = Path(__file__).resolve().parents[2] / "data" / "feedback_log.json"
MUTE_AFTER_REJECTS = 3  # rule 9


def load_events(path=LOG):
    return json.loads(Path(path).read_text()) if Path(path).exists() else []


def append_event(event, path=LOG):
    from src.contract.validate import check_feedback
    errors = check_feedback([event])
    if errors:
        raise ValueError("; ".join(errors))
    events = load_events(path)
    events.append(event)
    Path(path).write_text(json.dumps(events, indent=2) + "\n")


def muted_pairs(events=None, threshold=MUTE_AFTER_REJECTS):
    """(suggestion_type, equipment_id) pairs rejected at least `threshold` times."""
    events = load_events() if events is None else events
    rejects = Counter((e["suggestion_type"], e["equipment_id"]) for e in events if e["action"] == "reject")
    return {pair for pair, n in rejects.items() if n >= threshold}
