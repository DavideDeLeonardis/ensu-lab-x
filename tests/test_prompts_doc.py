"""PROMPTS.md must contain the prompts exactly as the code sends them (course report, section H)."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.ai.llm import prompts  # noqa: E402


class TestPromptsAreDocumented(unittest.TestCase):
    def test_prompts_md_matches_the_code(self):
        doc = (ROOT / "PROMPTS.md").read_text()
        for text in (prompts.PROPOSER_SYSTEM, prompts.PHRASER_SYSTEM, prompts.PROPOSER_VERSION, prompts.PHRASER_VERSION,
                     prompts.BOOKING_PROPOSER_SYSTEM, prompts.BOOKING_PHRASER_SYSTEM,
                     prompts.BOOKING_PROPOSER_VERSION, prompts.BOOKING_PHRASER_VERSION):
            self.assertIn(text, doc, "PROMPTS.md is out of date: update it and bump the prompt version")


if __name__ == "__main__":
    unittest.main()
