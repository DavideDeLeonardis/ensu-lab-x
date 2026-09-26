"""
Turns candidates (candidates.py) into ranked, rule-filtered proposals, using
ONLY calculator.py's saving() -- via CalculatorPort -- for every number.
No LLM involved here either.

Enforces, directly from CONTRACT.md:
  Rule 4: at most 3 suggestions, biggest saving first.
  Rule 7: never name the other party for a coordinate suggestion.
  Rule 8: drop suggestions saving < 0.2 kg CO2e.
  Rule 9: respect muted (type, equipment_id) pairs.
          -- see the open question raised in chat: this function accepts
          `muted_pairs` as a plain argument for now, since CONTRACT.md's
          input section doesn't yet say where that history comes from.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from .domain import Booking, fmt
from .ports import CalculatorPort, SavingResult
from .candidates import (
    generate_reschedule_candidates,
    generate_share_candidates,
    generate_coordinate_candidates,
)

MIN_SAVING_KG = 0.2   # Rule 8 -- tune later, per CONTRACT.md's own note
MAX_SUGGESTIONS = 3   # Rule 4


@dataclass(frozen=True)
class RankedProposal:
    booking_id: str
    type: str                      # "reschedule" | "share" | "coordinate"
    saving_result: SavingResult    # the exact dict calculator.saving() returned
    change: dict                   # exact shape the schema expects under "change"
    needs_other_party: bool = False


def _follows_another_session(equipment_id: str, new_start: datetime, all_bookings: list[Booking]) -> bool:
    """README: confocal-style warm-up is skipped if the new slot directly
    follows another session on the same equipment. A ~zero-gap match is
    treated as "directly follows"."""
    return any(
        b.equipment_id == equipment_id and b.end == new_start
        for b in all_bookings
    )


def _all_candidates_for_booking(
    booking: Booking, all_bookings: list[Booking], request_ids: set[str], calc: CalculatorPort,
    alternates: Optional[dict[str, list[str]]] = None,
) -> list[RankedProposal]:
    out: list[RankedProposal] = []

    for c in generate_reschedule_candidates(booking, all_bookings):
        warmup = not _follows_another_session(booking.equipment_id, c.new_start, all_bookings)
        result = calc.saving(
            booking.booking_id, new_start=fmt(c.new_start), new_end=fmt(c.new_end), warmup=warmup,
        )
        out.append(RankedProposal(
            booking_id=booking.booking_id, type="reschedule", saving_result=result,
            change={"new_start": fmt(c.new_start), "new_end": fmt(c.new_end)},
        ))

    for c in generate_share_candidates(booking, all_bookings, alternates):
        result = calc.saving(booking.booking_id, new_equipment=c.new_equipment_id)
        out.append(RankedProposal(
            booking_id=booking.booking_id, type="share", saving_result=result,
            change={"new_equipment_id": c.new_equipment_id},
        ))

    for c in generate_coordinate_candidates(booking, all_bookings):
        result = calc.saving(booking.booking_id, cancel=True)
        out.append(RankedProposal(
            booking_id=booking.booking_id, type="coordinate", saving_result=result,
            change={"merge_into_booking_id": c.merge_into_booking_id},
            # Rule 7: only a real concern if the merge target isn't the
            # requester's own booking -- true in every case we generate
            # today (candidates.py only looks at *other* bookings), but
            # checked explicitly here so this stays correct if that changes.
            needs_other_party=c.merge_into_booking_id not in request_ids,
        ))

    return out


def rank_proposals(
    request_bookings: list[Booking],
    all_bookings: list[Booking],
    calc: CalculatorPort,
    muted_pairs: Optional[set[tuple[str, str]]] = None,
    alternates: Optional[dict[str, list[str]]] = None,
) -> list[RankedProposal]:
    """
    Returns at most MAX_SUGGESTIONS proposals, biggest saving first, drawn
    from every movable booking in the request -- at most one proposal per
    booking, so 3 suggestions don't all target the same experiment.

    `alternates` should come from candidates.derive_alternates(equipment_by_id)
    once equipment.csv has real rows; omit it to fall back to the
    hand-written placeholder (see candidates.py).
    """
    muted_pairs = muted_pairs or set()
    request_ids = {b.booking_id for b in request_bookings}
    movable = [b for b in request_bookings if b.movable != "no"]

    candidates: list[RankedProposal] = []
    for booking in movable:
        for proposal in _all_candidates_for_booking(booking, all_bookings, request_ids, calc, alternates):
            if (proposal.type, booking.equipment_id) in muted_pairs:
                continue
            if proposal.saving_result["saving_kg"]["typ"] < MIN_SAVING_KG:
                continue
            candidates.append(proposal)

    candidates.sort(key=lambda p: p.saving_result["saving_kg"]["typ"], reverse=True)

    seen_bookings: set[str] = set()
    top: list[RankedProposal] = []
    for p in candidates:
        if p.booking_id in seen_bookings:
            continue
        top.append(p)
        seen_bookings.add(p.booking_id)
        if len(top) == MAX_SUGGESTIONS:
            break
    return top


def build_suppressed_list(request_bookings: list[Booking]) -> list[dict]:
    """Rule 1: every movable == 'no' booking must be listed, not silently
    dropped, with its constraint as the reason a human can check."""
    return [
        {"booking_id": b.booking_id, "reason": "hard_constraint", "detail": b.constraint}
        for b in request_bookings
        if b.movable == "no"
    ]
