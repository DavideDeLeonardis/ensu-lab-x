"""
Claude API client for the plan engine.

    from src.ai.llm.anthropic_client import AnthropicClient
    llm = AnthropicClient()          # ANTHROPIC_API_KEY if set, else the team key (team_key.py)

Model: Claude Haiku 5.5, the smallest current model ($0.10 / $0.50 per million input / output tokens for
prompts up to 100K tokens, checked 2026-10-15), at effort "low" to keep the footprint small. Haiku 5.5
thinks adaptively by default; effort is the lever, and `temperature` is not accepted (400).
JSON comes from structured outputs (`output_config.format`): ids are `enum`s in the schema.
No user or researcher identifier is sent (no `metadata`, no `user_profile_id`).
"""
from __future__ import annotations
import json
import time

from .client import LLMResult

DEFAULT_MODEL = "claude-haiku-5-5"
DEFAULT_EFFORT = "low"


class AnthropicClient:
    def __init__(self, model: str = DEFAULT_MODEL, effort: str = DEFAULT_EFFORT,
                 timeout: float = 30.0, max_retries: int = 1, sdk_client=None):
        self.model = model
        self.effort = effort
        if sdk_client is None:
            import anthropic  # imported here so the rest of the repo (and the tests) run without the SDK
            from .team_key import api_key
            sdk_client = anthropic.Anthropic(api_key=api_key(), timeout=timeout, max_retries=max_retries)
        self._sdk = sdk_client

    def complete_json(self, system: str, user: str, schema: dict, max_tokens: int) -> LLMResult:
        start = time.monotonic()
        try:
            response = self._sdk.messages.create(
                model=self.model,
                max_tokens=max_tokens,          # thinking counts toward it: leave room
                system=system,
                messages=[{"role": "user", "content": user}],
                output_config={"effort": self.effort,
                               "format": {"type": "json_schema", "schema": schema}},
            )
        except Exception as e:  # anthropic.APIError (status, connection, timeout) or a client bug: fall back
            return LLMResult(None, self.model, latency_s=time.monotonic() - start,
                             error=f"{type(e).__name__}: {str(e)[:120]}")
        latency = time.monotonic() - start
        usage = _usage(response)
        if response.stop_reason != "end_turn":   # refusal, max_tokens, ...: output may not match the schema
            return LLMResult(None, self.model, usage, latency, error=f"stop_reason={response.stop_reason}")
        text = next((b.text for b in response.content if b.type == "text"), None)
        try:
            data = json.loads(text) if text is not None else None
        except json.JSONDecodeError:
            data = None
        if not isinstance(data, dict):
            return LLMResult(None, self.model, usage, latency, error="no JSON object in the answer")
        return LLMResult(data, self.model, usage, latency)


def _usage(response) -> dict:
    u = getattr(response, "usage", None)
    keys = ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")
    return {k: int(getattr(u, k, 0) or 0) for k in keys} if u is not None else {}
