"""
Contract tests: the gold examples pass, the validator catches each kind of violation,
and the real AI engine's output respects the contract end-to-end.

    python3 -m unittest tests/test_contract.py -v
"""
import copy
import csv
import json
import sys
import unittest
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.contract.validate import check_suggestion_set, check_feedback, movable_window, BOOKINGS
from src.contract.feedback import muted_pairs

GOLD = json.loads((ROOT / "contract/examples/A1_suggestion_set.json").read_text())
FEEDBACK = json.loads((ROOT / "contract/examples/feedback_events.json").read_text())


def gold_with(**changes):
    """Copy of the gold set with the confocal suggestion (S2) edited."""
    doc = copy.deepcopy(GOLD)
    s2 = next(s for s in doc["suggestions"] if s["id"] == "S2")
    for k, v in changes.items():
        s2[k] = v
    return doc


def errors_mentioning(doc, text):
    return [e for e in check_suggestion_set(doc) if text in e]


class TestGoldExamples(unittest.TestCase):
    def test_gold_suggestion_set_is_valid(self):
        self.assertEqual(check_suggestion_set(GOLD), [])

    def test_gold_feedback_is_valid(self):
        self.assertEqual(check_feedback(FEEDBACK), [])


class TestValidatorCatchesViolations(unittest.TestCase):
    def test_rule1_fixed_booking(self):
        doc = gold_with(booking_ids=["BK-057"])
        self.assertTrue(errors_mentioning(doc, "fixed"))

    def test_rule3_outside_lab_hours(self):
        doc = gold_with(change={"new_start": "2026-10-16 17:00", "new_end": "2026-10-16 21:00"})
        self.assertTrue(errors_mentioning(doc, "lab hours"))

    def test_rule3_weekend(self):
        doc = gold_with(change={"new_start": "2026-10-17 12:00", "new_end": "2026-10-17 16:00"})
        self.assertTrue(errors_mentioning(doc, "lab hours"))

    def test_rule3_outside_movable_window(self):
        doc = gold_with(change={"new_start": "2026-10-19 12:00", "new_end": "2026-10-19 16:00"})
        self.assertTrue(errors_mentioning(doc, "window"))

    def test_rule5_invented_number(self):
        doc = gold_with(saving_kg={"low": 2.0, "typ": 3.0, "high": 4.0})
        self.assertTrue(errors_mentioning(doc, "does not match calculator"))

    def test_rule7_names_a_group_or_researcher(self):
        self.assertTrue(errors_mentioning(gold_with(why="Group Cartilage & disc images right before you."), "names a group"))
        self.assertTrue(errors_mentioning(gold_with(why="B2 images right before you."), "names a researcher"))

    def test_rule8_below_threshold(self):
        doc = copy.deepcopy(GOLD)
        doc["suggestions"].append({**doc["suggestions"][1], "id": "S3",
                                   "saving_kg": {"low": 0.05, "typ": 0.1, "high": 0.15}})
        self.assertTrue([e for e in check_suggestion_set(doc) if "threshold" in e])

    def test_one_suggestion_per_booking(self):
        doc = copy.deepcopy(GOLD)
        doc["suggestions"][1]["booking_ids"] = ["BK-078"]
        self.assertTrue([e for e in check_suggestion_set(doc) if "same booking" in e])

    def test_hotspots_must_be_per_equipment(self):
        doc = copy.deepcopy(GOLD)
        doc["estimate"]["hotspots"][3] = dict(doc["estimate"]["hotspots"][2])
        self.assertTrue([e for e in check_suggestion_set(doc) if "aggregated" in e])


class TestContractDefinitions(unittest.TestCase):
    def test_within_week_is_the_calendar_week(self):
        lo, hi = movable_window(BOOKINGS["BK-098"])  # Thu 15 Oct 19:00
        self.assertEqual((lo, hi), (datetime(2026, 10, 12, 0, 0), datetime(2026, 10, 19, 0, 0)))

    def test_muting_after_three_rejects(self):
        ev = {"suggestion_type": "coordinate", "equipment_id": "AUT-1", "action": "reject"}
        self.assertEqual(muted_pairs([ev] * 2), set())
        self.assertEqual(muted_pairs([ev] * 3), {("coordinate", "AUT-1")})


class TestEngineRespectsContract(unittest.TestCase):
    """Runs the real AI engine (src/ai) on the demo request and validates what it returns."""

    def test_engine_texts_are_concrete(self):
        """The phraser states the real trade-off, not a generic one."""
        out = {s["type"]: s for s in self._engine_output()["suggestions"]}
        self.assertIn("17 hours later", out["reschedule"]["tradeoff"])
        self.assertIn("16:00", out["coordinate"]["tradeoff"])
        self.assertIn("another group", out["coordinate"]["tradeoff"])

    def _engine_output(self):
        from src.ai.domain import Booking, load_equipment_csv
        from src.ai.build import build_suggestion_set
        from src.ai.calculator_adapter import RealCalculator

        with open(ROOT / "data/bookings.csv") as f:
            rows = list(csv.DictReader(f))
        all_bookings = [Booking.from_row(r) for r in rows]
        request = [b for b, r in zip(all_bookings, rows) if r["scenario"] == "True"]
        return build_suggestion_set("REQ-A1-2026-10-12", request, all_bookings,
                                    load_equipment_csv(), RealCalculator(), muted_pairs=muted_pairs())

    def test_engine_output_is_valid(self):
        self.assertEqual(check_suggestion_set(self._engine_output()), [])

if __name__ == "__main__":
    unittest.main()
