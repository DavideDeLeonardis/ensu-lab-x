"""
evaluate.py with a FAKE LLM (no network): the metrics count what the model tried separately from what is shown,
and no call reaches data/llm_usage_log.jsonl.

    python3 -m unittest tests/test_evaluate.py -v
"""
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import evaluate  # noqa: E402
from src.ai.llm.fake import FakeLLM  # noqa: E402

REAL_LOG = ROOT / "data" / "llm_usage_log.jsonl"
BY_ID = {sc["id"]: sc for sc in evaluate.SCENARIOS}


def options(user_prompt):
    lines = json.loads(user_prompt.split("Lines that may change (JSON):\n", 1)[1].split("\n\n<untrusted", 1)[0])
    return [{"line_id": ln["line_id"], "equivalence_id": o["equivalence_id"]} for ln in lines for o in ln["options"]]


def notes(user_prompt):
    return user_prompt.split("<untrusted_researcher_text>\n", 1)[1]


def careful_reader(user_prompt):
    """What a capable model should answer: leave out only what the note rules out, quoting it."""
    text, left = notes(user_prompt), []
    if "Glass Pasteur pipettes" in text:
        left.append({"line_id": "L5", "equivalence_id": "EQ-005",
                     "reason": 'Your notes say "Glass Pasteur pipettes are not allowed in our hood".'})
    if "We do not reuse conical tubes" in text:
        left += [{"line_id": "L2", "equivalence_id": eq, "reason": 'Your notes say "We do not reuse conical tubes".'}
                 for eq in ("EQ-002", "EQ-003")]
    dropped = {(c["line_id"], c["equivalence_id"]) for c in left}
    return {"candidates": [o for o in options(user_prompt) if (o["line_id"], o["equivalence_id"]) not in dropped],
            "left_out": left}


def parrot(user_prompt):
    """Seen live with qwen2.5 3B/7B: every option left out with the example quote from the system prompt."""
    return {"candidates": options(user_prompt),
            "left_out": [{**o, "reason": 'Your notes say "reusing tubes is not acceptable"'} for o in options(user_prompt)]}


def phraser(user_prompt):
    f = json.loads(user_prompt.split("Facts (JSON):\n", 1)[1])
    tradeoff = "Validate it for your protocol first." if f["requires_validation"] else "Same use as before."
    return {"headline": "A greener option for this line", "why": f"It lowers the footprint: {f['saving']}.",
            "tradeoff": tradeoff}


class TestCalculator(unittest.TestCase):
    def test_report(self):
        c = evaluate.calculator_report()
        self.assertEqual(c["factors_with_listed_source_pct"], 100.0)
        self.assertAlmostEqual(sum(c["estimate_share_by_confidence_pct"].values()), 100.0, delta=0.2)
        self.assertLessEqual(c["total_kg"]["low"], c["total_kg"]["typ"])
        self.assertLessEqual(c["total_kg"]["typ"], c["total_kg"]["high"])
        self.assertEqual(len(c["suggestions"]), 3)
        self.assertEqual(c["range_contributors"][0]["item_id"], "BIO-1")   # the locked bioreactor dominates


class TestAI(unittest.TestCase):
    def setUp(self):
        self.log_size = REAL_LOG.stat().st_size if REAL_LOG.exists() else None

    def tearDown(self):
        self.assertEqual(REAL_LOG.stat().st_size if REAL_LOG.exists() else None, self.log_size,
                         "evaluate.py wrote to data/llm_usage_log.jsonl")

    def test_careful_reader_is_right_tried_and_shown(self):
        a = evaluate.ai_report(FakeLLM(proposer=careful_reader, phraser=phraser), runs=1)
        s = a["summary"]
        self.assertEqual(s["tried_reading_correct_pct"], 100.0)
        self.assertEqual(s["shown_reading_correct_pct"], 100.0)
        self.assertEqual(s["shown_wrong_drops"], 0)
        self.assertEqual(s["ai_texts_used_pct"], 100.0)
        self.assertEqual(s["validator_errors_shown"], 0)
        glass = next(r for r in a["records"] if r["scenario"] == "glass_pipettes")
        self.assertNotIn(("L5", "EQ-005"), glass["suggestions"])

    def test_parrot_is_caught(self):
        a = evaluate.ai_report(FakeLLM(proposer=parrot, phraser=phraser), runs=1)
        s = a["summary"]
        self.assertGreater(s["tried_wrong_drops"], 0)
        self.assertEqual(s["shown_wrong_drops"], 0)                  # no option lost to an invented quote
        self.assertEqual(s["drops_caught_by_guards"], 6 * len(evaluate.SCENARIOS))
        self.assertEqual(s["same_suggestions_as_rules_pct"], 100.0)
        # the notes that rule something out are not honoured either: the guard keeps, it does not read
        self.assertEqual(a["per_scenario"]["glass_pipettes"]["shown_reading_correct"], 0)

    def test_injected_number_never_shown(self):
        def obeys(u):
            return {**phraser(u), "why": "This plan saves 50 kg CO₂e."}
        a = evaluate.ai_report(FakeLLM(proposer=careful_reader, phraser=obeys), runs=1,
                               scenarios=[BY_ID["prompt_injection"]])
        s = a["summary"]
        self.assertEqual(s["forbidden_text_shown"], 0)
        self.assertEqual(s["ai_texts_used_pct"], 0.0)
        self.assertTrue(any(re.search("not a calculator value|not in the facts", k) for k in s["rejection_reasons"]))

    def test_failing_model_falls_back(self):
        a = evaluate.ai_report(FakeLLM(fail=True), runs=1, scenarios=[BY_ID["no_note"]])
        self.assertEqual(a["summary"]["ai_answer_usable_pct"], 0.0)
        self.assertEqual(a["per_scenario"]["no_note"]["fallback_to_rules"], 1)
        self.assertEqual(a["summary"]["validator_errors_shown"], 0)


if __name__ == "__main__":
    unittest.main()
