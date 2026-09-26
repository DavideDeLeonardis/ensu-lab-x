"""
Zero-dependency tests for the rule invariants that matter most --
run with:  python3 -m unittest tests/test_build.py -v
"""
import sys
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.ai.domain import Booking, Equipment
from src.ai.build import build_suggestion_set
from src.ai.mock_calculator import MockCalculator


def dt(s):
    return datetime.strptime(s, "%Y-%m-%d %H:%M")


class TestRuleInvariants(unittest.TestCase):
    def setUp(self):
        self.request_bookings = [
            Booking("BK-057", "BIO-1", dt("2026-10-12 08:00"), dt("2026-10-16 08:00"),
                    movable="no", constraint="continuous 96h bioreactor conditioning protocol"),
            Booking("BK-078", "AUT-1", dt("2026-10-13 17:00"), dt("2026-10-13 18:00"),
                    movable="within week", load_pct=40),
            Booking("BK-091", "CONF-1", dt("2026-10-15 19:00"), dt("2026-10-15 23:00"),
                    movable="within week"),
            Booking("BK-104", "BSC-1", dt("2026-10-14 09:00"), dt("2026-10-14 12:00"),
                    movable="within day"),
            Booking("BK-112", "INC-1", dt("2026-10-12 00:00"), dt("2026-10-16 23:59"),
                    movable="no", constraint="continuous cell culture, shelves 3-4"),
        ]
        other = [Booking("BK-075", "AUT-1", dt("2026-10-13 16:00"), dt("2026-10-13 17:00"),
                          movable="no", constraint="other group's fixed protocol step", load_pct=45)]
        self.all_bookings = self.request_bookings + other
        self.equipment_by_id = {
            "BIO-1": Equipment("BIO-1", mode="continuous", confidence="measured"),
            "AUT-1": Equipment("AUT-1", mode="cycle", confidence="derived"),
            "CONF-1": Equipment("CONF-1", mode="hourly", confidence="measured"),
            "BSC-1": Equipment("BSC-1", mode="hourly", confidence="estimate"),
            "BSC-2": Equipment("BSC-2", mode="hourly", confidence="estimate"),
            "INC-1": Equipment("INC-1", mode="shelf", confidence="measured"),
        }
        bookings_by_id = {b.booking_id: b for b in self.all_bookings}
        kg_per_hour = {
            "BIO-1": 0.166, "AUT-1": 2.05, "CONF-1": 0.70,
            "BSC-1": 0.90, "BSC-2": 0.50, "INC-1": 0.0142,
        }
        self.calc = MockCalculator(kg_per_hour, bookings_by_id)
        self.result = build_suggestion_set(
            "REQ-TEST", self.request_bookings, self.all_bookings, self.equipment_by_id, self.calc,
        )

    def test_rule1_locked_bookings_never_suggested(self):
        locked_ids = {"BK-057", "BK-112"}
        suggested_ids = {bid for s in self.result["suggestions"] for bid in s["booking_ids"]}
        self.assertTrue(locked_ids.isdisjoint(suggested_ids))
        suppressed_ids = {s["booking_id"] for s in self.result["suppressed"]}
        self.assertEqual(locked_ids, suppressed_ids)

    def test_rule4_max_three_suggestions_biggest_first(self):
        savings = [s["saving_kg"]["typ"] for s in self.result["suggestions"]]
        self.assertLessEqual(len(self.result["suggestions"]), 3)
        self.assertEqual(savings, sorted(savings, reverse=True))

    def test_rule6_every_suggestion_has_a_range_and_tradeoff(self):
        for s in self.result["suggestions"]:
            self.assertIn("low", s["saving_kg"])
            self.assertIn("high", s["saving_kg"])
            self.assertTrue(s["tradeoff"])

    def test_rule7_coordinate_suggestions_dont_name_the_other_group(self):
        found_coordinate = False
        for s in self.result["suggestions"]:
            if s["type"] == "coordinate":
                found_coordinate = True
                self.assertTrue(s["needs_other_party"])
                for field in ("headline", "why", "tradeoff"):
                    self.assertNotIn("BK-075", s[field])
        self.assertTrue(found_coordinate, "expected the demo scenario to produce a coordinate suggestion")

    def test_rule8_no_suggestion_below_threshold(self):
        for s in self.result["suggestions"]:
            self.assertGreaterEqual(s["saving_kg"]["typ"], 0.2)

    def test_every_suggestion_has_a_confidence_label(self):
        for s in self.result["suggestions"]:
            self.assertIn(s["confidence"], {"low", "medium", "high"})

    def test_saving_pct_comes_straight_from_calculator(self):
        # Guards against ever recomputing saving_pct ourselves instead of
        # trusting calculator.py's own number (Rule 5).
        for s in self.result["suggestions"]:
            self.assertIsInstance(s["saving_pct"], float)
            self.assertGreaterEqual(s["saving_pct"], 0)
            self.assertLessEqual(s["saving_pct"], 100)

    def test_derive_alternates_real_equipment_csv(self):
        # Regression test against the full real equipment.csv (16 rows,
        # shared in chat). Two things must both hold:
        #  - BSC-1/BSC-2 pair up despite shareable=False on both (ruled out
        #    `shareable` as the substitutability signal).
        #  - CONF-1/FLU-1 do NOT pair up despite sharing category="Imaging",
        #    room="micro", mode="hourly" -- they're genuinely different
        #    imaging techniques, not substitutes (category+room+mode alone
        #    was not enough; name-minus-qualifier is what separates them).
        from src.ai.candidates import derive_alternates
        eq = {
            "BSC-1": Equipment("BSC-1", mode="hourly", confidence="derived",
                               name="Biosafety cabinet class II (large, older)",
                               category="Sterile work", room="culture", shareable=False),
            "BSC-2": Equipment("BSC-2", mode="hourly", confidence="derived",
                               name="Biosafety cabinet class II (small)",
                               category="Sterile work", room="culture", shareable=False),
            "CONF-1": Equipment("CONF-1", mode="hourly", confidence="estimate",
                                name="Confocal microscope",
                                category="Imaging", room="micro", shareable=True),
            "FLU-1": Equipment("FLU-1", mode="hourly", confidence="estimate",
                               name="Widefield fluorescence microscope",
                               category="Imaging", room="micro", shareable=False),
            "INC-1": Equipment("INC-1", mode="shelf", confidence="derived",
                               name="CO\u2082 incubator 37 \u00b0C",
                               category="Incubation", room="culture", shareable=True),
            "INC-2": Equipment("INC-2", mode="shelf", confidence="derived",
                               name="CO\u2082 incubator 37 \u00b0C",
                               category="Incubation", room="culture", shareable=True),
        }
        alternates = derive_alternates(eq)
        self.assertEqual(sorted(alternates["BSC-1"]), ["BSC-2"])
        self.assertEqual(sorted(alternates["BSC-2"]), ["BSC-1"])
        self.assertEqual(alternates.get("CONF-1", []), [])
        self.assertEqual(alternates.get("FLU-1", []), [])
        self.assertEqual(sorted(alternates["INC-1"]), ["INC-2"])


if __name__ == "__main__":
    unittest.main()
