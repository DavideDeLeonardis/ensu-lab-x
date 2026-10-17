"""
Tests for the plan calculator (src/lab/plan_calculator.py) on the real Lab X catalogue, and a hand-built
plan SuggestionSet validated end-to-end against the real data (before the plan engine exists).

    python3 -m unittest tests/test_plan_calculator.py -v
"""
import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.lab.plan_calculator import estimate_plan, estimate_line, plan_saving, electricity_factor  # noqa: E402
from src.contract.validate import check_plan, check_suggestion_set  # noqa: E402

PLAN = json.loads((ROOT / "data/plan_A1.json").read_text())


def line(line_id):
    return next(ln for ln in PLAN["lines"] if ln["line_id"] == line_id)


class TestPricing(unittest.TestCase):
    def test_consumable_is_quantity_times_factor(self):
        e = estimate_line(line("L1"), "location")           # 960 tips × 3.09 g, range ±10%
        self.assertEqual(e["kg"], {"low": 2.67, "typ": 2.966, "high": 3.263})
        self.assertEqual(e["electricity"]["typ"], 0.0)

    def test_equipment_is_hours_times_kw_times_grid(self):
        e = estimate_line(line("L8"), "location")           # BIO-1: 96 h × 0.6 kW × 262.2 g/kWh
        self.assertEqual(e["kwh"], 57.6)
        self.assertEqual(e["kg"]["typ"], 15.103)

    def test_shelf_hour_is_one_shelf(self):
        e = estimate_line({"line_id": "L99", "item_id": "INC-2", "quantity": 312, "unit": "h"}, "location")
        self.assertAlmostEqual(e["kwh"], 312 * 2.06 / 24 / 4, places=3)

    def test_market_basis_zeroes_electricity_only(self):
        loc, mkt = estimate_plan(PLAN, "location"), estimate_plan(PLAN, "market")
        self.assertEqual(mkt["electricity"], {"basis": "market", "g_per_kwh": 0.0, "source": "MC2024"})
        self.assertEqual(mkt["breakdown"]["electricity"]["typ"], 0.0)
        self.assertEqual(mkt["breakdown"]["embodied"], loc["breakdown"]["embodied"])
        self.assertTrue(all(ln["electricity"]["typ"] == 0.0 for ln in mkt["lines"]))
        self.assertLess(mkt["kg"]["typ"], loc["kg"]["typ"])

    def test_basis_from_environment(self):
        with patch.dict(os.environ, {"LABX_ELECTRICITY_BASIS": "market"}):
            self.assertEqual(electricity_factor()["basis"], "market")
        with self.assertRaises(ValueError):
            electricity_factor("nuclear")

    def test_cycle_equipment_is_not_a_plan_line(self):
        with self.assertRaises(ValueError):
            estimate_line({"line_id": "L99", "item_id": "AUT-1", "quantity": 1, "unit": "h"})


class TestSaving(unittest.TestCase):
    def test_saving_is_before_minus_after_and_sorted(self):
        s = plan_saving(PLAN, "L1", "EQ-001", "location")  # 960 × (3.09 − 2.22) g
        self.assertEqual(s["saving_kg"]["typ"], round(s["before"]["kg"]["typ"] - s["after"]["kg"]["typ"], 3))
        self.assertAlmostEqual(s["saving_kg"]["typ"], 0.835, places=3)
        self.assertTrue(s["saving_kg"]["low"] <= s["saving_kg"]["typ"] <= s["saving_kg"]["high"])

    def test_reuse_follows_the_electricity_basis(self):
        loc = plan_saving(PLAN, "L2", "EQ-002", "location")
        mkt = plan_saving(PLAN, "L2", "EQ-002", "market")
        self.assertGreater(loc["after"]["electricity"]["typ"], 0)
        self.assertGreater(mkt["saving_kg"]["typ"], loc["saving_kg"]["typ"])

    def test_pairs_the_curated_list_does_not_allow(self):
        for line_id, eq in (("L8", "EQ-001"),     # locked line
                            ("L1", "EQ-002"),     # equivalence for another item
                            ("L4", "EQ-004"),     # tc_treated clashes with glass dishes
                            ("L1", "EQ-999")):    # not in the list
            with self.subTest(line=line_id, eq=eq), self.assertRaises(ValueError):
                plan_saving(PLAN, line_id, eq)


def hand_built_output(basis="location"):
    """A plan SuggestionSet built by hand from the calculator: what the plan engine must produce."""
    est = estimate_plan(PLAN, basis)
    s = plan_saving(PLAN, "L5", "EQ-005", basis)
    per_item = {}
    for ln in est["lines"]:
        d = per_item.setdefault(ln["item_id"], {"kg": 0.0, "locked": True})
        d["kg"] += ln["kg"]["typ"]
        d["locked"] = d["locked"] and ln["locked"]
    hotspots = sorted(({"item_id": i, "kg_typ": round(d["kg"], 2),
                        "share_pct": round(100 * d["kg"] / est["kg"]["typ"], 1), "locked": d["locked"]}
                       for i, d in per_item.items()), key=lambda h: h["kg_typ"], reverse=True)[:4]
    return {
        "request_id": PLAN["plan_id"],
        "line_ids": [ln["line_id"] for ln in PLAN["lines"]],
        "generator": {"proposer": "rules", "phraser": "template", "model": None, "prompt_version": None},
        "estimate": {"kwh": est["kwh"], "kg": est["kg"], "breakdown": est["breakdown"],
                     "electricity": est["electricity"], "hotspots": hotspots,
                     "locked_kg": round(sum(ln["kg"]["typ"] for ln in est["lines"] if ln["locked"]), 2)},
        "suggestions": [{
            "id": "S1", "type": "substitute", "line_ids": ["L5"],
            "headline": "Reuse glass Pasteur pipettes",
            "change": {"line_id": "L5", "equivalence_id": "EQ-005", "alternative_id": s["alternative_id"],
                       "new_quantity": s["new_quantity"]},
            "saving_kg": s["saving_kg"], "saving_pct": s["saving_pct"],
            "why": f"Washing and reusing glass pipettes avoids new plastic ones: about "
                   f"{s['saving_kg']['typ']:.1f} kg CO₂e less ({s['saving_pct']:.0f}%).",
            "tradeoff": "Glass pipettes are washed and autoclaved between uses and can break.",
            "confidence": "medium", "requires_validation": False, "needs_other_party": False,
        }],
        "suppressed": [
            {"line_id": "L4", "reason": "requirement_conflict", "detail": "tc_treated"},
            {"line_id": "L8", "reason": "hard_constraint", "detail": "Protocol timing fixed; safety interlock"},
        ],
    }


class TestEndToEndWithRealData(unittest.TestCase):
    def test_demo_plan_is_valid(self):
        self.assertEqual(check_plan(PLAN), [])

    def test_hand_built_output_is_valid_for_both_bases(self):
        for basis in ("location", "market"):
            with self.subTest(basis=basis):
                self.assertEqual(check_suggestion_set(hand_built_output(basis), plan=PLAN), [])

    def test_saving_priced_on_the_wrong_basis_is_caught(self):
        doc = hand_built_output("location")
        doc["estimate"]["electricity"]["basis"] = "market"
        self.assertTrue([e for e in check_suggestion_set(doc, plan=PLAN) if "does not match calculator" in e])

    def test_clashing_equivalence_is_caught(self):
        doc = hand_built_output()
        doc["suggestions"][0]["line_ids"] = ["L4"]
        doc["suggestions"][0]["change"] = {"line_id": "L4", "equivalence_id": "EQ-004",
                                           "alternative_id": "PETRI-6-GLASS-REUSE", "new_quantity": 20}
        self.assertTrue([e for e in check_suggestion_set(doc, plan=PLAN) if "incompatible" in e])


class TestAddedSwaps(unittest.TestCase):
    """EQ-007 (confocal → widefield) and EQ-008/009 (1 L flasks, Farley & Nicolet 2023 S1 Table, case 3)."""
    def plan_with(self, *lines):
        return {**PLAN, "lines": PLAN["lines"] + list(lines)}

    def test_confocal_to_widefield_saves_electricity_only(self):
        plan = self.plan_with({"line_id": "L9", "item_id": "CONF-1", "quantity": 4, "unit": "h"})
        self.assertGreater(plan_saving(plan, "L9", "EQ-007", "location")["saving_kg"]["low"], 0)
        self.assertEqual(plan_saving(plan, "L9", "EQ-007", "market")["saving_kg"]["typ"], 0)

    def test_flask_reuse_matches_the_source(self):
        """The paper's fold change for glass flasks (6.9×) comes back with its own UK electricity factor."""
        from src.lab.plan_calculator import CONSUMABLES
        su, glass = (CONSUMABLES[i] for i in ("FLASK-1L-SU", "FLASK-1L-GLASS-REUSE"))
        per_use_glass = float(glass["kg_per_unit"]) + float(glass["kwh_per_unit"]) * 0.21233
        self.assertAlmostEqual(float(su["kg_per_unit"]) / per_use_glass, 6.894, delta=0.01)
        plan = self.plan_with({"line_id": "L9", "item_id": "FLASK-1L-SU", "quantity": 4, "unit": "piece"})
        for eq in ("EQ-008", "EQ-009"):
            self.assertGreater(plan_saving(plan, "L9", eq, "location")["saving_kg"]["low"], 1.0)

    def test_single_use_required_blocks_flask_reuse(self):
        plan = self.plan_with({"line_id": "L9", "item_id": "FLASK-1L-SU", "quantity": 4, "unit": "piece",
                               "requirements": ["single_use_required"]})
        with self.assertRaises(ValueError):
            plan_saving(plan, "L9", "EQ-008")


if __name__ == "__main__":
    unittest.main()
