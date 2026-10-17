"""
footprint.py: local (Ollama) calls are priced with Green Algorithms on the laptop, API calls with data-centre
factors. Synthetic logs in a temporary folder only: no network, data/llm_usage_log.jsonl is never written.

    python3 -m unittest tests/test_footprint.py -v
"""
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import footprint as fp  # noqa: E402


def row(purpose, model, output_tokens, latency_s):
    return {"timestamp": "2026-10-15 16:00:00", "purpose": purpose, "model": model, "prompt_version": "v1",
            "input_tokens": 300, "output_tokens": output_tokens, "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0, "latency_s": latency_s, "ok": True}


LOCAL_RUN = [row("proposer", "qwen2.5:3b", 160, 4.0), row("phraser", "qwen2.5:3b", 70, 2.0),
             row("phraser", "qwen2.5:3b", 70, 2.0), row("booking-proposer", "qwen2.5:3b", 500, 30.0)]


class LocalModelTest(unittest.TestCase):
    def test_model_kind(self):
        self.assertTrue(fp.is_ollama_model("qwen2.5:3b"))
        self.assertFalse(fp.is_ollama_model("claude-haiku-5-5"))
        self.assertFalse(fp.is_ollama_model("fake-llm"))

    def test_green_algorithms_formula(self):
        wh = fp.local_wh(3600)   # one hour at the device power = that many Wh (usage 1, PUE 1)
        for c in fp.CASES:
            self.assertAlmostEqual(wh[c], fp.DEVICE_W[c] * fp.LOCAL_USAGE * fp.LOCAL_PUE)

    def test_per_run_skips_booking_calls(self):
        pr = fp.per_run_from_log(LOCAL_RUN)
        self.assertEqual((pr["runs"], pr["calls"], pr["other_calls"]), (1, 3, 1))
        self.assertEqual(pr["local"], {"models": ["qwen2.5:3b"], "output_tokens": 300, "latency_s": 8.0})
        self.assertEqual(pr["api"]["output_tokens"], 0)

    def test_local_calls_use_no_data_centre_factor(self):
        wh, g = fp.measured_footprint(fp.per_run_from_log(LOCAL_RUN), 262.2)
        for c in fp.CASES:
            self.assertAlmostEqual(wh[c], 8.0 / 3600 * fp.DEVICE_W[c])
            self.assertAlmostEqual(g[c], wh[c] / 1000 * 262.2)
        self.assertEqual(fp.measured_footprint(fp.per_run_from_log(LOCAL_RUN), 0.0)[1]["high"], 0)

    def test_api_calls_keep_per_token_factors(self):
        rows = [row("proposer", "claude-haiku-5-5", 100, 5.0), row("phraser", "claude-haiku-5-5", 100, 5.0)]
        wh, g = fp.measured_footprint(fp.per_run_from_log(rows), 262.2)
        for c in fp.CASES:
            self.assertAlmostEqual(wh[c], 200 * fp.WH_PER_OUTPUT_TOKEN[c])
            self.assertAlmostEqual(g[c], fp.llm_grams({k: 200 for k in fp.CASES})[c])

    def test_cli_prints_local_line_and_leaves_real_log_alone(self):
        with tempfile.TemporaryDirectory() as d:
            log = Path(d) / "log.jsonl"
            log.write_text("".join(json.dumps(r) + "\n" for r in LOCAL_RUN))
            out = io.StringIO()
            with contextlib.redirect_stdout(out), patch("src.ai.plan_engine.log_usage") as log_usage:
                fp.main(["--log", str(log)])
        text = out.getvalue()
        self.assertIn("Local model qwen2.5:3b (Ollama)", text)
        self.assertIn("1 booking calls not counted", text)
        self.assertIn("same tokens, data-centre Wh", text)
        log_usage.assert_not_called()   # no LLM call, nothing appended to data/llm_usage_log.jsonl

    def test_doc_names_the_device_source_and_how_to_measure(self):
        doc = (ROOT / "FOOTPRINT.md").read_text()
        for needle in ("## Local model (Ollama)", "NOTEBOOKCHECK2023", "sudo powermetrics", "--device-w"):
            self.assertIn(needle, doc)


if __name__ == "__main__":
    unittest.main()
