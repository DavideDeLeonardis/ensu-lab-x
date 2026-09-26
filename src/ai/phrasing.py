"""
Phrasing: turns an already-ranked, already-calculator-verified proposal into
the human-readable `headline` / `why` / `tradeoff` fields the schema wants.

This is deliberately the ONLY file in src/ai/ that may call an LLM. By the
time a proposal reaches here:
  - it has already passed Rule 1 (never touches movable == "no")
  - it has already passed Rule 8 (saving >= 0.2 kg)
  - its saving numbers already came from calculator.py (Rule 5)
  - Rule 4's top-3 selection has already happened

So the LLM (or, by default, the template function below) cannot invent a
number, cannot suggest touching a locked booking, and cannot smuggle in a
fourth suggestion -- it only writes English for a decision that's already
made. That's the whole point of splitting ranking.py from this file.

Default implementation (`template_phraser`) needs no API key and no network
call, so the pipeline runs end-to-end with the same "no dependencies" spirit
as the rest of the repo. Swap in `llm_phraser` (below, stubbed) once you've
picked a provider -- same function signature, so build.py doesn't change.
"""
from __future__ import annotations
from typing import Callable, Protocol

from .ranking import RankedProposal

# Rule 7: never name another group or researcher.
ANONYMOUS_OTHER_PARTY = "another group"


class Phrased(Protocol):
    headline: str
    why: str
    tradeoff: str


class PhrasedText:
    def __init__(self, headline: str, why: str, tradeoff: str):
        self.headline = headline
        self.why = why
        self.tradeoff = tradeoff


Phraser = Callable[[RankedProposal], PhrasedText]


def template_phraser(proposal: RankedProposal) -> PhrasedText:
    """Zero-dependency default: plain but always rule-compliant text.
    Good enough to get the pipeline running and to unit-test against;
    swap for an LLM once you want more natural headlines."""
    saved = proposal.saving_result["saving_kg"]["typ"]

    if proposal.type == "reschedule":
        new_start = proposal.change["new_start"]
        return PhrasedText(
            headline=f"Move this session to {new_start}",
            why=f"The grid is cleaner at the new time, saving about {saved:.2f} kg CO2e.",
            tradeoff="Your booking moves to a different time slot.",
        )
    if proposal.type == "share":
        alt = proposal.change["new_equipment_id"]
        return PhrasedText(
            headline=f"Use {alt} instead, if it's free",
            why=f"Running this on {alt} instead saves about {saved:.2f} kg CO2e.",
            tradeoff=f"Depends on {alt} being free at your booked time.",
        )
    if proposal.type == "coordinate":
        return PhrasedText(
            headline=f"Join {ANONYMOUS_OTHER_PARTY}'s run on this equipment",
            why=f"Merging into an already-scheduled run on the same equipment saves "
                f"about {saved:.2f} kg CO2e instead of running two partial loads.",
            tradeoff=f"Timing depends on {ANONYMOUS_OTHER_PARTY}'s slot, and needs their agreement.",
        )
    raise ValueError(f"unknown proposal type: {proposal.type}")


def llm_phraser(proposal: RankedProposal) -> PhrasedText:
    """
    STUB -- wire up your provider of choice here. The prompt should pass in
    ONLY: proposal.type, proposal.change, proposal.saving_result (already
    computed), and ANONYMOUS_OTHER_PARTY as the required stand-in for any other-party
    reference. Never pass raw booking/researcher/group identifiers into the
    prompt for a `coordinate` proposal (Rule 7) -- the LLM should not need
    them to write good text, and if it doesn't have them, it can't leak them.

    Suggested guardrail: run template_phraser() as a fallback if the LLM
    call fails or returns text mentioning a real group id, so a flaky
    network call never blocks the whole SuggestionSet from being produced.
    """
    raise NotImplementedError("plug in your LLM call here; template_phraser() works meanwhile")
