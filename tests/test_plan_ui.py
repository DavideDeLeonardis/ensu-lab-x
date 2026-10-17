"""
The plan side of the merged UI (src/ui/plan_api.py, served by src/ui/serve.py), without touching the real logs.

    python3 -m unittest tests/test_plan_ui.py -v
"""
import copy
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.ui import plan_api  # noqa: E402
from src.contract.validate import GROUP_NAMES, RESEARCHER_RE  # noqa: E402

PLAN = json.loads((ROOT / "data/plan_A1.json").read_text())


class TestPlanServer(unittest.TestCase):
    def test_catalog_has_no_group_or_researcher_data(self):
        text = json.dumps(plan_api.catalog(), ensure_ascii=False)
        self.assertFalse(any(name in text for name in GROUP_NAMES))
        self.assertIsNone(RESEARCHER_RE.search(text))

    def test_catalog_reports_llm_providers(self):
        with patch("src.ai.llm.providers.available", return_value={"ollama": True, "claude": False}):
            self.assertEqual(plan_api.catalog()["llm"], {"ollama": True, "claude": False})

    def test_catalog_offers_only_plan_items(self):
        ids = {i["item_id"] for i in plan_api.catalog()["items"]}
        self.assertIn("TIP-10-F-RACK", ids)
        self.assertNotIn("AUT-1", ids)          # cycle equipment cannot be a plan line

    def test_suggest_returns_a_valid_suggestion_set(self):
        with patch("src.ai.llm.providers.available", return_value={"ollama": False, "claude": False}):
            status, res = plan_api.suggest({"plan": PLAN, "basis": "market", "use_llm": True})
        self.assertEqual(status, 200)
        self.assertEqual(res["errors"], [])
        self.assertEqual(res["suggestion_set"]["generator"]["proposer"], "rules")   # no key: no LLM
        self.assertEqual(res["suggestion_set"]["estimate"]["electricity"]["basis"], "market")

    def test_ai_answer_comes_with_the_rules_choice(self):
        from src.ai.llm.fake import FakeLLM
        llm = FakeLLM(proposer={"candidates": [{"line_id": "L1", "equivalence_id": "EQ-001"}],
                                "left_out": [{"line_id": "L5", "equivalence_id": "EQ-005", "reason": "Glass is fragile here."}]})
        with patch("src.ai.llm.providers.get_llm", return_value=llm), \
             patch("src.ai.plan_engine.log_usage"):        # keep fake calls out of data/llm_usage_log.jsonl
            status, res = plan_api.suggest({"plan": PLAN, "use_llm": True})
        self.assertEqual(status, 200)
        self.assertEqual(res["errors"], [])
        self.assertEqual(len(res["ai"]["rules_choice"]), 3)            # the rules alone would suggest 3
        self.assertEqual(res["ai"]["left_out"], [])                       # no quote from the notes: not dropped
        self.assertEqual(res["ai"]["kept_without_quote"], [{"line_id": "L5", "equivalence_id": "EQ-005"}])
        self.assertIn("EQ-005", [s["change"]["equivalence_id"] for s in res["suggestion_set"]["suggestions"]])

    def test_note_exclusions_survive_a_rules_recalculation(self):
        """Seen live: the AI left out the glass pipettes (notes); after "Apply" the rules brought them back."""
        note = "Glass Pasteur pipettes are not allowed in our hood because broken glass is a safety risk."
        veto = [{"equivalence_id": "EQ-005", "reason": f'Your notes say "{note}"'}]
        eqs = lambda res: [s["change"]["equivalence_id"] for s in res["suggestion_set"]["suggestions"]]  # noqa: E731
        status, res = plan_api.suggest({"plan": dict(PLAN, notes=note), "note_exclusions": veto})
        self.assertEqual(status, 200)
        self.assertNotIn("EQ-005", eqs(res))
        self.assertEqual([k["equivalence_id"] for k in res["note_exclusions"]], ["EQ-005"])
        self.assertEqual(res["errors"], [])
        # the quote is gone from the notes (or never was): the exclusion lapses, the rules offer it again
        for notes in ("Cells are sensitive to serum lot changes.", "Glass is fine."):
            status, res = plan_api.suggest({"plan": dict(PLAN, notes=notes), "note_exclusions": veto})
            self.assertIn("EQ-005", eqs(res))
            self.assertEqual(res["note_exclusions"], [])

    def test_invalid_plan_is_rejected(self):
        bad = copy.deepcopy(PLAN)
        bad["lines"][0]["unit"] = "kg"
        status, res = plan_api.suggest({"plan": bad})
        self.assertEqual(status, 400)
        self.assertTrue(res["errors"])

    def test_feedback_is_validated_and_numbered(self):
        event = {"event_id": "FB-0000", "request_id": "REQ-1a2b3c4d", "suggestion_id": "S1",
                 "suggestion_type": "substitute", "item_id": "PASTEUR-SU", "action": "accept",
                 "timestamp": "2026-10-15 00:00"}
        with patch.object(plan_api, "load_events", return_value=[{}] * 7), \
             patch.object(plan_api, "append_event") as append:
            saved = plan_api.save_feedback([event])
        self.assertEqual(saved[0]["event_id"], "FB-0008")
        append.assert_called_once()


class TestLabs(unittest.TestCase):
    def test_labs_list_all_equipment_with_plan_flag(self):
        labs = plan_api.labs()
        self.assertTrue(labs)
        plan_items = {i["item_id"] for i in plan_api.catalog()["items"] if i["kind"] == "equipment"}
        for lab in labs:
            by_id = {e["item_id"]: e for e in lab["equipment"]}
            self.assertTrue(all(e["room"] in lab["rooms"] for e in lab["equipment"]))
            # a device can be a plan line exactly when the plan catalogue offers it
            self.assertEqual({i for i, e in by_id.items() if e["plan_line"]}, plan_items & set(by_id))
            self.assertFalse(by_id["AUT-1"]["plan_line"])   # autoclave: priced per cycle, bookings only


class TestMergedServer(unittest.TestCase):
    """serve.py serves the start page, both assistants and both APIs (real HTTP on a free local port)."""

    @classmethod
    def setUpClass(cls):
        import threading
        from http.server import ThreadingHTTPServer
        from src.ui import serve
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), serve.Handler)
        cls.base = f"http://127.0.0.1:{cls.srv.server_address[1]}"
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def get(self, path):
        import urllib.request
        with urllib.request.urlopen(self.base + path, timeout=10) as r:
            return r.status, r.read().decode()

    def test_pages(self):
        for path, marker in (("/", "Plan an experiment"), ("/plan", "Experiment plan assistant"),
                             ("/bookings", "booking assistant"), ("/profile.js", "LabProfile"),
                             ("/api/labs", "LABX")):
            with self.subTest(path):
                status, body = self.get(path)
                self.assertEqual(status, 200)
                self.assertIn(marker, body)

    def test_both_assistants_share_the_team_profile(self):
        for path in ("/plan", "/bookings"):
            with self.subTest(path):
                self.assertIn('<script src="profile.js"></script>', self.get(path)[1])

    def test_pages_are_linked(self):
        """Plan: estimate on its own + an Ask-the-AI button + booked hours; bookings: the plan's machine hours."""
        plan_page, booking_page = self.get("/plan")[1], self.get("/bookings")[1]
        self.assertIn('id="askAi"', plan_page)
        self.assertNotIn('id="go"', plan_page)
        self.assertIn('api("/api/plan")', plan_page)          # booked hours come from the confirmed bookings
        self.assertIn("labx.plan.draft", booking_page)          # the booking page reads the plan kept in the browser
        self.assertIn("data-bookplan", booking_page)
        for page in (plan_page, booking_page):
            self.assertIn("summary(", page)                     # same "Team & lab" text on both pages

    def test_plan_suggest_over_http(self):
        import urllib.request
        req = urllib.request.Request(self.base + "/api/plan/suggest", method="POST",
                                     data=json.dumps({"plan": PLAN, "use_llm": False}).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            res = json.loads(r.read())
        self.assertEqual(res["errors"], [])
        self.assertEqual(res["suggestion_set"]["request_id"], PLAN["plan_id"])

    def test_booking_api_still_works(self):
        status, body = self.get("/api/health")
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(body)["ok"])


if __name__ == "__main__":
    unittest.main()
