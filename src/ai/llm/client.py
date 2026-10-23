"""
The LLM interface the plan engine depends on. Two implementations:
  - anthropic_client.AnthropicClient: the real Claude API (network, needs ANTHROPIC_API_KEY)
  - fake.FakeLLM: scripted answers for tests (no network)

An LLM here only ever returns JSON constrained by a schema. It never returns kg or kWh:
the calculator prices everything the LLM proposes (CONTRACT.md rule 5).
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, Protocol


@dataclass
class LLMResult:
    data: Optional[dict]                        # parsed JSON, or None on any failure
    model: str
    usage: dict = field(default_factory=dict)   # input_tokens, output_tokens, cache_* (for Green Algorithms)
    latency_s: float = 0.0
    error: Optional[str] = None                 # short reason when data is None

    @property
    def ok(self) -> bool:
        return self.error is None and self.data is not None


class LLMClient(Protocol):
    model: str

    def complete_json(self, system: str, user: str, schema: dict, max_tokens: int) -> LLMResult:
        """One request; the answer must follow `schema`. Never raises for API problems: returns error."""
        ...
