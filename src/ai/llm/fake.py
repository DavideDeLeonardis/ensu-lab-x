"""
A scripted LLM for tests: no network, records every prompt it receives.

    llm = FakeLLM(proposer={"candidates": [...]}, phraser=lambda user: {...})
    llm = FakeLLM(fail=True)              # every call fails, like a network error

`proposer` / `phraser` (plans) and `booking_proposer` / `booking_phraser` may be a dict (returned as-is), a callable(user_prompt) -> dict, or None (failure).
The kind of call is recognised from the prompt version written in the system prompt.
"""
from __future__ import annotations
import copy

from .client import LLMResult
from .prompts import PROPOSER_VERSION, PHRASER_VERSION, BOOKING_PROPOSER_VERSION, BOOKING_PHRASER_VERSION


class FakeLLM:
    def __init__(self, proposer=None, phraser=None, fail=False, model="fake-llm",
                 booking_proposer=None, booking_phraser=None):
        self.model = model
        self.proposer = proposer
        self.phraser = phraser
        self.booking_proposer = booking_proposer
        self.booking_phraser = booking_phraser
        self.fail = fail
        self.calls = []   # (kind, system, user, schema)

    def complete_json(self, system, user, schema, max_tokens):
        kind = ("booking_proposer" if f"[{BOOKING_PROPOSER_VERSION}]" in system
                else "booking_phraser" if f"[{BOOKING_PHRASER_VERSION}]" in system
                else "proposer" if f"[{PROPOSER_VERSION}]" in system
                else "phraser" if f"[{PHRASER_VERSION}]" in system else "?")
        self.calls.append((kind, system, user, schema))
        answer = None if self.fail else {"proposer": self.proposer, "phraser": self.phraser,
                                         "booking_proposer": self.booking_proposer,
                                         "booking_phraser": self.booking_phraser}.get(kind)
        if callable(answer):
            answer = answer(user)
        usage = {"input_tokens": len(system + user) // 4, "output_tokens": 50,
                 "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}
        if answer is None:
            return LLMResult(None, self.model, usage, 0.01, error="fake failure")
        return LLMResult(copy.deepcopy(answer), self.model, usage, 0.01)
