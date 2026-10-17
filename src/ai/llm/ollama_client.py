"""
Local LLM client (Ollama) for the plan engine: an alternative provider to the Claude API.

    from src.ai.llm.ollama_client import OllamaClient
    llm = OllamaClient()             # needs `ollama serve` running and `ollama pull qwen2.5:3b`

Why: free, no data leaves the laptop, and the energy use can be measured on our own hardware (Green
Algorithms: runtime × power). Model: Qwen2.5 3B, a small open model. Same contract as AnthropicClient:
JSON constrained by the schema (Ollama structured outputs, `format`), ids as enums, temperature 0.
Standard library only (urllib).
"""
from __future__ import annotations
import json
import os
import time
import urllib.error
import urllib.request

from .client import LLMResult

DEFAULT_MODEL = "qwen2.5:3b"
DEFAULT_HOST = "http://127.0.0.1:11434"


def _post(url: str, payload: dict, timeout: float) -> dict:
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


class OllamaClient:
    def __init__(self, model: str = DEFAULT_MODEL, host: str | None = None, timeout: float = 120.0, post=_post):
        self.model = model
        self.host = (host or os.environ.get("OLLAMA_HOST_URL") or DEFAULT_HOST).rstrip("/")
        self.timeout = timeout
        self._post = post   # injectable for tests (no network)

    def complete_json(self, system: str, user: str, schema: dict, max_tokens: int) -> LLMResult:
        start = time.monotonic()
        try:
            out = self._post(f"{self.host}/api/chat", {
                "model": self.model,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                "format": schema,
                "stream": False,
                "options": {"temperature": 0, "num_predict": max_tokens},
            }, self.timeout)
        except Exception as e:  # connection refused, timeout, HTTP error, bad JSON from the server: fall back
            return LLMResult(None, self.model, latency_s=time.monotonic() - start,
                             error=f"{type(e).__name__}: {str(e)[:120]}")
        latency = time.monotonic() - start
        usage = {"input_tokens": int(out.get("prompt_eval_count") or 0),
                 "output_tokens": int(out.get("eval_count") or 0),
                 "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}
        if out.get("done_reason") not in (None, "stop"):   # e.g. "length": the JSON may be cut off
            return LLMResult(None, self.model, usage, latency, error=f"done_reason={out.get('done_reason')}")
        try:
            data = json.loads((out.get("message") or {}).get("content") or "")
        except json.JSONDecodeError:
            data = None
        if not isinstance(data, dict):
            return LLMResult(None, self.model, usage, latency, error="no JSON object in the answer")
        return LLMResult(data, self.model, usage, latency)


def is_available(model: str = DEFAULT_MODEL, host: str | None = None) -> bool:
    """True if an Ollama server answers and has `model` pulled (quick check, 1 s timeout)."""
    host = (host or os.environ.get("OLLAMA_HOST_URL") or DEFAULT_HOST).rstrip("/")
    try:
        with urllib.request.urlopen(f"{host}/api/tags", timeout=1) as resp:
            names = {m.get("name") for m in json.loads(resp.read()).get("models", [])}
    except (urllib.error.URLError, OSError, ValueError):
        return False
    return model in names
