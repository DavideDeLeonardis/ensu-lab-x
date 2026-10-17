"""
Contract tests for experiment plans (CONTRACT.md §1b, §3b): the validator catches each kind of
violation in a plan output, and fails closed while the catalogue or the plan calculator is missing.

Uses a tiny FIXTURE catalogue (ids starting with FIX-, numbers made up for the test) patched into the
validator, so these tests don't depend on the real data files.

    python3 -m unittest tests/test_plan_contract.py -v
"""
import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.contract import validate  # noqa: E402
from src.contract.validate import check_suggestion_set, check_plan, check_feedback  # noqa: E402
from src.contract.feedback import muted_pairs  # noqa: E402

CONSUMABLES = {
    "FIX-TIP": {"item_id": "FIX-TIP", "unit": "piece"},
    "FIX-TIP-REFILL": {"item_id": "FIX-TIP-REFILL", "unit": "piece"},
    "FIX-SERUM": {"item_id": "FIX-SERUM", "unit": "L"},
}
EQUIVALENCES = {
    "EQ-901": {"equivalence_id": "EQ-901", "item_id": "FIX-TIP", "alternative_id": "FIX-TIP-REFILL",
               "type": "substitute", "ratio": "1", "incompatible_with": "rnase_free",
               "requires_validation": "False", "needs_other_party": "False"},
    "EQ-902": {"equivalence_id": "EQ-902", "item_id": "FIX-SERUM", "alternative_id": "FIX-TIP",
               "type": "substitute", "ratio": "1", "incompatible_with": "",
               "requires_validation": "True", "needs_other_party": "False"},
}
SAVING = {"saving_kg": {"low": 1.2, "typ": 1.5, "high": 2.1}, "saving_pct": 40.0}

PLAN = {
    "plan_id": "PLAN-TEST-0001",
    "lines": [
        {"line_id": "L1", "item_id": "FIX-TIP", "quantity": 960, "unit": "piece", "requirements": ["sterile"]},
        {"line_id": "L2", "item_id": "FIX-SERUM", "quantity": 0.5, "unit": "L",
         "locked": True, "lock_reason": "Validated protocol requires this serum"},
        {"line_id": "L3", "item_id": "BSC-1", "quantity": 15, "unit": "h"},
    ],
}

OUTPUT = {
    "request_id": "PLAN-TEST-0001",
    "line_ids": ["L1", "L2", "L3"],
    "generator": {"proposer": "llm", "phraser": "template", "model": "claude-haiku-5-5",
                  "prompt_version": "proposer-v1"},
    "estimate": {"kwh": 6.0, "kg": {"low": 5.0, "typ": 7.0, "high": 10.0},
                 "hotspots": [{"item_id": "FIX-SERUM", "kg_typ": 4.0, "share_pct": 57.1, "locked": True}],
                 "locked_kg": 4.0},
    "suggestions": [{
        "id": "S1", "type": "substitute", "line_ids": ["L1"],
        "headline": "Use refill racks for your tips",
        "change": {"line_id": "L1", "equivalence_id": "EQ-901", "alternative_id": "FIX-TIP-REFILL",
                   "new_quantity": 960},
        "saving_kg": dict(SAVING["saving_kg"]), "saving_pct": 40.0,
        "why": "Refills avoid a new box for every rack: about 1.5 kg CO₂e less (40%).",
        "tradeoff": "You refill racks by hand.",
        "confidence": "low", "requires_validation": False, "needs_other_party": False,
    }],
    "suppressed": [{"line_id": "L2", "reason": "hard_constraint", "detail": "Validated protocol requires this serum"}],
}


def output_with(**changes):
    """Copy of the fixture output with suggestion S1 edited."""
    doc = copy.deepcopy(OUTPUT)
    doc["suggestions"][0].update(changes)
    return doc


class PlanFixture(unittest.TestCase):
    """Patches the fixture catalogue and a fake plan calculator into the validator."""

    def setUp(self):
        for target, value in (("_plan_data", (CONSUMABLES, EQUIVALENCES)), ("_plan_saving", SAVING)):
            p = patch.object(validate, target, return_value=value)
            p.start()
            self.addCleanup(p.stop)

    def errors(self, doc, plan=PLAN):
        return check_suggestion_set(doc, plan=plan)

    def assertCaught(self, doc, text, plan=PLAN):
        errs = self.errors(doc, plan)
        self.assertTrue([e for e in errs if text in e], f"expected an error mentioning {text!r}, got {errs}")


class TestPlanOutput(PlanFixture):
    def test_fixture_output_is_valid(self):
        self.assertEqual(self.errors(OUTPUT), [])

    def test_plan_is_required(self):
        self.assertCaught(OUTPUT, "pass the ExperimentPlan", plan=None)

    def test_rule1_locked_line(self):
        doc = output_with(line_ids=["L2"], change={**OUTPUT["suggestions"][0]["change"], "line_id": "L2"})
        self.assertCaught(doc, "locked")

    def test_rule1_locked_line_must_be_suppressed(self):
        doc = copy.deepcopy(OUTPUT)
        doc["suppressed"] = []
        self.assertCaught(doc, "locked line L2 missing")

    def test_rule2_invented_equivalence(self):
        doc = output_with(change={**OUTPUT["suggestions"][0]["change"], "equivalence_id": "EQ-999"})
        self.assertCaught(doc, "not in data/equivalences.csv")

    def test_rule2_equivalence_for_another_item(self):
        doc = output_with(change={**OUTPUT["suggestions"][0]["change"], "equivalence_id": "EQ-902",
                                  "alternative_id": "FIX-TIP"})
        self.assertCaught(doc, "is for FIX-SERUM")

    def test_rule2_requirement_clash(self):
        plan = copy.deepcopy(PLAN)
        plan["lines"][0]["requirements"] = ["rnase_free"]
        self.assertCaught(OUTPUT, "incompatible", plan=plan)

    def test_rule2_quantity_not_from_ratio(self):
        doc = output_with(change={**OUTPUT["suggestions"][0]["change"], "new_quantity": 500})
        self.assertCaught(doc, "quantity × ratio")

    def test_rule4_max_three(self):
        doc = copy.deepcopy(OUTPUT)
        doc["suggestions"] = [dict(doc["suggestions"][0], id=f"S{i}") for i in range(1, 5)]
        self.assertCaught(doc, "schema")

    def test_rule5_invented_number(self):
        doc = output_with(saving_kg={"low": 3.0, "typ": 4.0, "high": 5.0},
                          why="Refills avoid a new box for every rack.")
        self.assertCaught(doc, "does not match calculator")

    def test_rule7_name_in_text_and_in_plan_id(self):
        self.assertCaught(output_with(why="B2 already uses refills."), "names a researcher")
        plan = dict(PLAN, plan_id="PLAN-A1-0001")
        self.assertCaught(dict(OUTPUT, request_id="PLAN-A1-0001"), "names a researcher", plan=plan)

    def test_rule11_invented_number_in_text(self):
        self.assertCaught(output_with(why="Refills save about 9.5 kg CO₂e."), "not a calculator value")
        self.assertCaught(output_with(why="Refills save 80% of the impact."), "not a calculator value")

    def test_generator_is_required(self):
        doc = copy.deepcopy(OUTPUT)
        del doc["generator"]
        self.assertCaught(doc, "generator")

    def test_suggestion_with_both_bookings_and_lines(self):
        self.assertCaught(output_with(booking_ids=["BK-098"]), "schema")


class TestFailClosed(unittest.TestCase):
    """Without the catalogue or the plan calculator, a plan output can never pass."""

    def test_without_catalogue(self):
        with patch.object(validate, "_plan_data", return_value=None):
            errs = check_suggestion_set(OUTPUT, plan=PLAN)
        self.assertTrue([e for e in errs if "rules 2 and 5 need" in e])

    def test_without_plan_calculator(self):
        with patch.object(validate, "_plan_data", return_value=(CONSUMABLES, EQUIVALENCES)), \
             patch.object(validate, "_plan_saving", return_value=None):
            errs = check_suggestion_set(OUTPUT, plan=PLAN)
        self.assertTrue([e for e in errs if "cannot re-price" in e])


class TestPlanInput(PlanFixture):
    def test_fixture_plan_is_valid(self):
        self.assertEqual(check_plan(PLAN), [])

    def test_locked_needs_a_reason(self):
        plan = copy.deepcopy(PLAN)
        del plan["lines"][1]["lock_reason"]
        self.assertTrue(check_plan(plan))

    def test_unknown_item_and_wrong_unit(self):
        plan = copy.deepcopy(PLAN)
        plan["lines"][0]["item_id"] = "FIX-NOPE"
        plan["lines"][2]["unit"] = "run"
        errs = check_plan(plan)
        self.assertTrue([e for e in errs if "unknown item" in e])
        self.assertTrue([e for e in errs if "does not match the catalogue" in e])


class TestPlanFeedback(unittest.TestCase):
    EVENT = {"event_id": "FB-0100", "request_id": "PLAN-TEST-0001", "suggestion_id": "S1",
             "suggestion_type": "substitute", "item_id": "FIX-TIP", "action": "reject",
             "reason": "not_equivalent_for_my_protocol", "timestamp": "2026-10-15 10:00"}

    def test_item_feedback_is_valid(self):
        self.assertEqual(check_feedback([self.EVENT]), [])

    def test_needs_exactly_one_of_equipment_and_item(self):
        neither = {k: v for k, v in self.EVENT.items() if k != "item_id"}
        both = dict(self.EVENT, equipment_id="BSC-1")
        self.assertTrue(check_feedback([neither]))
        self.assertTrue(check_feedback([both]))

    def test_muting_works_on_items(self):
        self.assertEqual(muted_pairs([self.EVENT] * 3), {("substitute", "FIX-TIP")})


if __name__ == "__main__":
    unittest.main()
