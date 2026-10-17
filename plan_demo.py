"""
Runs the plan engine on the demo experiment plan (data/plan_A1.json) and prints the SuggestionSet.

    python3 plan_demo.py                    # rules + templates, no network
    python3 plan_demo.py --llm              # an LLM proposes and phrases: local Ollama if running, else Claude
    python3 plan_demo.py --llm ollama       # local Qwen2.5 3B (needs `ollama serve` + `ollama pull qwen2.5:3b`)
    python3 plan_demo.py --llm claude       # Claude Haiku 5.5 (team key or ANTHROPIC_API_KEY)
    python3 plan_demo.py --basis market     # electricity factor of the green contract
    python3 plan_demo.py --save             # also write contract/examples/A1_plan_suggestion_set.json
    python3 plan_demo.py --show-prompts     # dry run: the exact prompts an LLM run would send (no key needed)

With --llm, the tokens of every call are appended to data/llm_usage_log.jsonl.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from src.ai.plan_engine import build_plan_suggestion_set, preview_prompts  # noqa: E402
from src.contract.feedback import muted_pairs  # noqa: E402
from src.contract.validate import check_suggestion_set  # noqa: E402
from src.ai.llm.usage_log import summary  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--plan", default=str(ROOT / "data" / "plan_A1.json"))
ap.add_argument("--llm", nargs="?", const="auto", choices=["auto", "ollama", "claude"],
                help="let an LLM propose and phrase (default provider: the first available)")
ap.add_argument("--basis", choices=["location", "market"])
ap.add_argument("--save", action="store_true", help="write contract/examples/A1_plan_suggestion_set.json")
ap.add_argument("--show-prompts", action="store_true", help="print the prompts an LLM run would send, then stop")
args = ap.parse_args()

plan = json.loads(Path(args.plan).read_text())
if args.show_prompts:
    requests = preview_prompts(plan, basis=args.basis, muted_pairs=muted_pairs())
    for r in requests:
        print(f"===== {r['purpose']} ({r['prompt_version']}), ~{r['est_input_tokens']} input tokens (estimate)")
        print("--- system\n" + r["system"] + "\n--- user\n" + r["user"] + "\n")
    total = sum(r["est_input_tokens"] for r in requests)
    print(f"--- {len(requests)} requests, ~{total} input tokens in total (characters / 4: an estimate, not a "
          f"measurement; output and thinking tokens come on top)")
    sys.exit(0)
llm = None
if args.llm:
    from src.ai.llm.providers import available, get_llm
    llm = get_llm(None if args.llm == "auto" else args.llm)
    if llm is None:
        print(f"--- no LLM available ({available()}): running with rules + templates", file=sys.stderr)
    else:
        print(f"--- LLM: {llm.model}", file=sys.stderr)

sset = build_plan_suggestion_set(plan, llm=llm, basis=args.basis, muted_pairs=muted_pairs())
print(json.dumps(sset, indent=2, ensure_ascii=False))

errors = check_suggestion_set(sset, plan=plan)
print(f"\n--- validator: {'OK' if not errors else errors} | generator: {sset['generator']}")
if args.llm:
    print(f"--- token log so far: {summary()}")
if args.save:
    out = ROOT / "contract" / "examples" / "A1_plan_suggestion_set.json"
    out.write_text(json.dumps(sset, indent=2, ensure_ascii=False) + "\n")
    print(f"--- saved {out.relative_to(ROOT)}")
