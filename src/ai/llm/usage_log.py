"""
Token log for every LLM call, for the Green Algorithms estimate of the tool's own footprint.

One JSON line per call in data/llm_usage_log.jsonl: time, purpose, model, prompt version, tokens,
latency, ok. No plan, group or researcher identifier is written.
The file is local (in .gitignore): report the totals from summary() instead of committing it.
"""
from __future__ import annotations
import json
from datetime import datetime
from pathlib import Path

from .client import LLMResult

DEFAULT_LOG = Path(__file__).resolve().parents[3] / "data" / "llm_usage_log.jsonl"


def log_usage(result: LLMResult, purpose: str, prompt_version: str, path=DEFAULT_LOG) -> None:
    if path is None:
        return
    entry = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "purpose": purpose,
        "model": result.model,
        "prompt_version": prompt_version,
        **{k: result.usage.get(k, 0) for k in ("input_tokens", "output_tokens",
                                               "cache_creation_input_tokens", "cache_read_input_tokens")},
        "latency_s": round(result.latency_s, 3),
        "ok": result.ok,
    }
    with open(path, "a") as f:
        f.write(json.dumps(entry) + "\n")


def summary(path=DEFAULT_LOG) -> dict:
    """Totals over the log: calls, input and output tokens (input for the Green Algorithms estimate)."""
    if not Path(path).exists():
        return {"calls": 0, "input_tokens": 0, "output_tokens": 0}
    rows = [json.loads(l) for l in Path(path).read_text().splitlines() if l.strip()]
    return {"calls": len(rows),
            "input_tokens": sum(r["input_tokens"] for r in rows),
            "output_tokens": sum(r["output_tokens"] for r in rows)}
