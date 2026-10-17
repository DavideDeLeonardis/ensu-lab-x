"""
Footprint paradox: CO2e of the tool's own LLM use vs the CO2e its suggestions can save. Method: FOOTPRINT.md.

    python3 footprint.py                        # estimate for data/plan_A1.json (no API call, no key)
    python3 footprint.py --runs-per-year 500    # yearly lab usage (an estimate: change it)
    python3 footprint.py --log [PATH]           # use measured tokens (default data/llm_usage_log.jsonl)
    python3 footprint.py --log --model qwen2.5:3b   # only the calls of one model
    python3 footprint.py --log --device-w 22    # local model: use your own power reading (sudo powermetrics)

Every coefficient below is sourced (keys in FOOTPRINT.md) or marked ESTIMATE. The calculator prices the
savings; this script only multiplies tokens (API model) or measured runtime (local model) by published energy
and carbon factors.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from src.ai.plan_engine import build_plan_suggestion_set, preview_prompts  # noqa: E402
from src.ai.llm.usage_log import DEFAULT_LOG  # noqa: E402
from src.contract.feedback import muted_pairs  # noqa: E402
from src.lab.plan_calculator import electricity_factor  # noqa: E402

CASES = ("low", "typ", "high")

# Wh per output token, data-centre overhead (PUE) included. Per-request energy / output tokens of the
# 1k-input / 1k-output prompt in Jegham et al. (2025), Table 4; typ also matches Epoch AI (0.3 Wh / 500 tokens).
WH_PER_OUTPUT_TOKEN = {
    "low": 0.172 / 1000,    # LLaMA-3.1-8B (JEGHAM2025)
    "typ": 0.6 / 1000,      # GPT-4.1 nano 0.575 Wh (JEGHAM2025); GPT-4o 0.3 Wh / 500 tokens (EPOCH2025)
    "high": 4.464 / 1000,   # Claude 3.5 Haiku (JEGHAM2025): the closest model family we found
}

# g CO2e per kWh of the data centre's electricity (the region Anthropic serves from is not disclosed).
G_PER_KWH = {
    "low": 0.03 / 0.24 * 1000,  # 125: Google's median Gemini prompt, 0.03 g / 0.24 Wh, market-based (ELSWORTH2025)
    "typ": 287.0,               # AWS, as used for Claude by JEGHAM2025
    "high": 475.0,              # world average used by Green Algorithms (LANNELONGUE2021, from IEA 2019)
}

# Output tokens per plan run (thinking included). ESTIMATE until the log has measured values.
#   low:  the bare JSON answers, from the schemas and the character limits in PROMPTS.md
#         (proposer ~40 tokens for 3 picks, phraser ~120 tokens for 80 + 200 + 160 characters plus keys)
#   typ:  ESTIMATE, about 2.5x the bare JSON for adaptive thinking at effort "low"
#   high: the hard cap, max_tokens 2048 (proposer) + 1024 per phraser (src/ai/plan_engine.py)
PROPOSER_JSON_TOKENS, PHRASER_JSON_TOKENS = 40, 120
PROPOSER_MAX_TOKENS, PHRASER_MAX_TOKENS = 2048, 1024
THINKING_FACTOR_TYP = 2.5

# Green Algorithms cross-check on logged latency (Eq. 1 of LANNELONGUE2021, parameters of JEGHAM2025):
# one request = latency x node power x share of the node x PUE. Latency includes network and queueing, so
# this overestimates.
NODE_KW = 10.2                                        # NVIDIA DGX H100/H200 node (JEGHAM2025)
NODE_SHARE = {"low": 0.055, "typ": 0.065, "high": 0.075}   # node utilisation per request (JEGHAM2025)
PUE = 1.14                                            # AWS (JEGHAM2025)

# Local model (Ollama on the demo laptop): the Green Algorithms formula with known hardware,
# Wh = latency x device power x usage x PUE, priced with the Dutch grid of data/electricity_factors.csv.
# Device powers are wall-socket measurements of the same configuration (NOTEBOOKCHECK2023). Which of them an
# Ollama call resembles is an ESTIMATE: generation runs on the GPU (Metal), so typ is a GPU-bound load.
DEVICE = 'MacBook Pro 14" (2023), M2 Pro 10-core CPU / 16-core GPU, 16 GB'
DEVICE_W = {
    "low": 24.5,    # GPU power alone, Cinebench R23 + 3DMark stress (NOTEBOOKCHECK2023): no display, memory, rest
    "typ": 46.6,    # whole laptop at the wall, Witcher 3 ultra, GPU-bound (NOTEBOOKCHECK2023)
    "high": 71.4,   # whole laptop at the wall, maximum, Prime95 + FurMark (NOTEBOOKCHECK2023)
}
LOCAL_USAGE = 1.0   # ESTIMATE: the device counts as fully busy for the whole call (latency includes model loading)
LOCAL_PUE = 1.0     # no data centre; adapter losses are already in the wall measurement

PLAN_PURPOSES = ("proposer", "phraser")   # booking-* calls belong to the booking tool, not to a plan run


def is_ollama_model(model: str) -> bool:
    """Ollama names are "name:tag" (e.g. qwen2.5:3b); Claude ids have no colon. Unknown names count as API."""
    return ":" in model and not model.startswith("claude")


def output_tokens_per_run(n_phrasers: int) -> dict:
    bare = PROPOSER_JSON_TOKENS + n_phrasers * PHRASER_JSON_TOKENS
    return {"low": bare, "typ": round(bare * THINKING_FACTOR_TYP),
            "high": PROPOSER_MAX_TOKENS + n_phrasers * PHRASER_MAX_TOKENS}


def llm_grams(tokens: dict) -> dict:
    """g CO2e per run: output tokens x Wh/token x g/kWh (low with low, high with high)."""
    return {c: tokens[c] * WH_PER_OUTPUT_TOKEN[c] / 1000 * G_PER_KWH[c] for c in CASES}


def local_wh(latency_s: float, device_w: dict = DEVICE_W) -> dict:
    """Wh of a local run: Green Algorithms E = t x P x u x PUE (LANNELONGUE2021), per case."""
    return {c: latency_s / 3600 * device_w[c] * LOCAL_USAGE * LOCAL_PUE for c in CASES}


def read_log(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


def per_run_from_log(rows: list[dict]) -> dict:
    """Mean output tokens and latency per plan run (one proposer call = one run), split local / API."""
    plan_rows = [r for r in rows if r["purpose"] in PLAN_PURPOSES]
    runs = sum(r["purpose"] == "proposer" for r in plan_rows)
    out = {"runs": runs, "calls": len(plan_rows), "other_calls": len(rows) - len(plan_rows)}
    for kind, local in (("local", True), ("api", False)):
        part = [r for r in plan_rows if is_ollama_model(r["model"]) == local]
        out[kind] = {"models": sorted({r["model"] for r in part}),
                     "output_tokens": sum(r["output_tokens"] for r in part) / runs if runs else 0.0,
                     "latency_s": sum(r["latency_s"] for r in part) / runs if runs else 0.0}
    return out


def measured_footprint(per_run: dict, local_g_per_kwh: float, device_w: dict = DEVICE_W) -> tuple[dict, dict]:
    """(Wh, g CO2e) per run: API calls priced per token with data-centre factors, local calls with GA."""
    api_tokens = per_run["api"]["output_tokens"]
    loc = local_wh(per_run["local"]["latency_s"], device_w)
    wh = {c: api_tokens * WH_PER_OUTPUT_TOKEN[c] + loc[c] for c in CASES}
    g = {c: api_tokens * WH_PER_OUTPUT_TOKEN[c] / 1000 * G_PER_KWH[c] + loc[c] / 1000 * local_g_per_kwh
         for c in CASES}
    return wh, g


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", default=str(ROOT / "data" / "plan_A1.json"))
    ap.add_argument("--basis", choices=["location", "market"])
    ap.add_argument("--runs-per-year", type=int, default=500, help="ESTIMATE: plan runs per year in the lab")
    ap.add_argument("--log", nargs="?", const=str(DEFAULT_LOG), help="use measured output tokens from the usage log")
    ap.add_argument("--model", help="with --log: only the calls of this model (e.g. qwen2.5:3b)")
    ap.add_argument("--device-w", type=float,
                    help="local model: your own measured device power in W (all cases), e.g. from powermetrics")
    args = ap.parse_args(argv)

    plan = json.loads(Path(args.plan).read_text())
    requests = preview_prompts(plan, basis=args.basis, muted_pairs=muted_pairs())
    n_phrasers = sum(r["purpose"] == "phraser" for r in requests)
    sset = build_plan_suggestion_set(plan, llm=None, basis=args.basis, muted_pairs=muted_pairs())
    saved = {c: sum(s["saving_kg"][c] for s in sset["suggestions"]) for c in CASES}
    n_sugg = len(sset["suggestions"])

    source = "estimate (no measured tokens)"
    tokens = output_tokens_per_run(n_phrasers)
    wh = {c: tokens[c] * WH_PER_OUTPUT_TOKEN[c] for c in CASES}
    g = llm_grams(tokens)
    ga = per_run = None
    device_w = {c: args.device_w for c in CASES} if args.device_w else DEVICE_W
    grid = electricity_factor(args.basis)
    if args.log:
        log = Path(args.log)
        per_run = per_run_from_log([r for r in read_log(log) if args.model in (None, r["model"])])
        if per_run["runs"]:
            tokens = {c: per_run["local"]["output_tokens"] + per_run["api"]["output_tokens"] for c in CASES}
            source = (f"measured: {per_run['calls']} plan calls, {per_run['runs']} runs in {log.name}"
                      + (f" ({per_run['other_calls']} booking calls not counted)" if per_run["other_calls"] else ""))
            wh, g = measured_footprint(per_run, float(grid["g_per_kwh"]), device_w)
            if per_run["api"]["latency_s"]:
                ga = {c: per_run["api"]["latency_s"] / 3600 * NODE_KW * 1000 * NODE_SHARE[c] * PUE for c in CASES}
        else:
            print(f"--- {log.name} has no runs yet: falling back to the estimate", file=sys.stderr)
            per_run = None
    local = per_run and per_run["local"]["models"]

    print(f"Plan {Path(args.plan).name}: {len(requests)} requests "
          f"(~{sum(r['est_input_tokens'] for r in requests)} input tokens), output tokens per run: {source}")
    if local:
        print(f"Local model {', '.join(local)} (Ollama) on {DEVICE}: Green Algorithms, measured latency x device W "
              f"x usage {LOCAL_USAGE} x PUE {LOCAL_PUE}, {float(grid['g_per_kwh']):g} g/kWh "
              f"({grid['basis']}, {grid['source']})" + (" [device W: your measurement]" if args.device_w else ""))
    print(f"{'':28}{'low':>12}{'typ':>12}{'high':>12}")
    print(f"{'output tokens / run':28}" + "".join(f"{tokens[c]:>12,.0f}" for c in CASES))
    if local:
        print(f"{'local latency s / run':28}" + "".join(f"{per_run['local']['latency_s']:>12.2f}" for c in CASES))
        print(f"{'local device W':28}" + "".join(f"{device_w[c]:>12.1f}" for c in CASES))
    print(f"{'LLM Wh / run':28}" + "".join(f"{wh[c]:>12.3f}" for c in CASES))
    print(f"{'LLM g CO2e / run':28}" + "".join(f"{g[c]:>12.3f}" for c in CASES))
    if local:
        same = {c: tokens[c] * WH_PER_OUTPUT_TOKEN[c] for c in CASES}
        print(f"{'same tokens, data-centre Wh':28}" + "".join(f"{same[c]:>12.3f}" for c in CASES)
              + "   (JEGHAM2025 per-token factors, for comparison)")
    if ga:
        print(f"{'GA check Wh / run (latency)':28}" + "".join(f"{ga[c]:>12.3f}" for c in CASES))
    print(f"{'offered saving kg / run':28}" + "".join(f"{saved[c]:>12.2f}" for c in CASES)
          + f"   ({n_sugg} suggestions, basis {sset['estimate']['electricity']['basis']})")
    print(f"{'LLM g CO2e / year':28}" + "".join(f"{g[c] * args.runs_per_year:>12.1f}" for c in CASES)
          + f"   ({args.runs_per_year} runs, ESTIMATE)")

    # Break-even, pessimistic pairing: highest LLM footprint against the low bound of the average saving per suggestion.
    if n_sugg and g["high"] > 0:
        per_sugg_low_g = saved["low"] / n_sugg * 1000
        year_high_g = g["high"] * args.runs_per_year
        offset = year_high_g / per_sugg_low_g
        offset_txt = f"{offset:.1f}" if offset >= 1 else f"{offset:.2g}"
        print(f"\nWorst case: one accepted suggestion ({per_sugg_low_g / 1000:.2f} kg) offsets the LLM use of "
              f"{per_sugg_low_g / g['high']:,.0f} runs; a year of LLM use ({year_high_g / 1000:.3g} kg) is offset by "
              f"{offset_txt} accepted suggestions.")
        print(f"Typical:    one accepted suggestion offsets {saved['typ'] / n_sugg * 1000 / g['typ']:,.0f} runs.")
    elif n_sugg:
        print(f"\nThe LLM use counts as 0 g CO2e on the {grid['basis']} basis (direct emissions only): "
              "no break-even to compute.")


if __name__ == "__main__":
    main()
