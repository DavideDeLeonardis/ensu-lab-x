"""
build.py: the one function the rest of the world calls.

    suggestion_set = build_suggestion_set(request_id, request_bookings,
                                           all_bookings, equipment_by_id, calc)

Wires together, in order:
  1. candidates.py    (deterministic search -- no LLM, no calculator)
  2. ranking.py        (calculator.py numbers + Rules 1/4/7/8/9 -- no LLM)
  3. phrasing.py        (the only step that may use an LLM)
and produces a dict matching the SuggestionSet shape shown in CONTRACT.md.

This does NOT run contract/validate.py itself -- do that separately once
you have the real jsonschema files:
    python3 src/contract/validate.py <output.json>
"""
from __future__ import annotations
from typing import Optional

from .domain import Booking, Equipment, fmt, lowest_confidence_label
from .ports import CalculatorPort
from .ranking import rank_proposals, build_suppressed_list, RankedProposal
from .phrasing import Phraser, PhraseContext, template_phraser
from .candidates import derive_alternates
from . import booking_ai
from .llm.usage_log import DEFAULT_LOG

MAX_HOTSPOTS = 4  # suggestion_set.schema.json: estimate.hotspots maxItems


def _equipment_for_proposal(
    booking: Booking, proposal: RankedProposal, equipment_by_id: dict[str, Equipment]
) -> list[Equipment]:
    ids = {booking.equipment_id}
    if proposal.type == "share":
        ids.add(proposal.change["new_equipment_id"])
    return [equipment_by_id[i] for i in ids if i in equipment_by_id]


def build_suggestion_set(
    request_id: str,
    request_bookings: list[Booking],
    all_bookings: list[Booking],
    equipment_by_id: dict[str, Equipment],
    calc: CalculatorPort,
    phraser: Phraser = template_phraser,
    muted_pairs: Optional[set[tuple[str, str]]] = None,
    llm=None,
    usage_log=DEFAULT_LOG,
    free_text: str = "",
) -> dict:
    """`llm` (optional, see src/ai/llm/): it picks among the allowed options and writes the text
    (booking_ai.py); without it, rules + templates exactly as before. `free_text`: the researcher's own words
    (e.g. booking purposes), passed to the LLM scrubbed and as untrusted data."""
    booking_by_id = {b.booking_id: b for b in request_bookings}
    all_by_id = {b.booking_id: b for b in all_bookings}

    # --- overall estimate + hotspots -------------------------------------
    # Uses calc.estimate() directly (current state), separate from any
    # proposed change -- calc.saving() is only for pricing candidates below.
    per_booking_estimate = {
        b.booking_id: calc.estimate(b.equipment_id, fmt(b.start), fmt(b.end), shelves=b.shelves or 1)
        for b in request_bookings
    }
    total_kwh = sum(e["kwh"] for e in per_booking_estimate.values())
    total_low = sum(e["kg"]["low"] for e in per_booking_estimate.values())
    total_typ = sum(e["kg"]["typ"] for e in per_booking_estimate.values())
    total_high = sum(e["kg"]["high"] for e in per_booking_estimate.values())
    locked_kg = sum(
        per_booking_estimate[b.booking_id]["kg"]["typ"] for b in request_bookings if b.movable == "no"
    )

    # One entry per device (CONTRACT.md: bookings on the same device summed),
    # largest first, max 4. A device is `locked` only if ALL its bookings are fixed.
    per_device: dict[str, dict] = {}
    for b in request_bookings:
        d = per_device.setdefault(b.equipment_id, {"kg": 0.0, "locked": True})
        d["kg"] += per_booking_estimate[b.booking_id]["kg"]["typ"]
        d["locked"] = d["locked"] and b.movable == "no"
    hotspots = sorted(
        (
            {
                "equipment_id": eid,
                "kg_typ": round(d["kg"], 2),
                "share_pct": round(100 * d["kg"] / total_typ, 1) if total_typ else 0.0,
                "locked": d["locked"],
            }
            for eid, d in per_device.items()
        ),
        key=lambda h: h["kg_typ"],
        reverse=True,
    )[:MAX_HOTSPOTS]

    # --- suggestions -------------------------------------------------------
    # calc.saving() already returns saving_kg (low/typ/high) AND saving_pct
    # relative to that specific booking's own current footprint -- no need
    # to recompute either here.
    alternates = derive_alternates(equipment_by_id) or None  # None triggers
                                                              # the fallback in
                                                              # candidates.py
                                                              # until equipment.csv
                                                              # actually has rows
    cycle_equipment = {eid for eid, e in equipment_by_id.items() if e.mode == "cycle"} or None
    if llm is None:
        top_proposals, proposer = rank_proposals(request_bookings, all_bookings, calc, muted_pairs, alternates,
                                                 cycle_equipment), "rules"
    else:
        pool = booking_ai.option_pool(request_bookings, all_bookings, calc, muted_pairs, alternates, cycle_equipment)
        top_proposals, proposer = booking_ai.propose(pool, request_bookings, equipment_by_id, all_by_id, llm,
                                                     usage_log, free_text)
    suggestions, contexts, templates = [], [], []
    for i, proposal in enumerate(top_proposals, start=1):
        booking = booking_by_id[proposal.booking_id]
        alt_id = proposal.change.get("new_equipment_id")
        ctx = PhraseContext(
            booking=booking,
            equipment=equipment_by_id.get(booking.equipment_id),
            alternate=equipment_by_id.get(alt_id) if alt_id else None,
            merge_target=all_by_id.get(proposal.change.get("merge_into_booking_id", "")),
        )
        text = phraser(proposal, ctx)
        contexts.append(ctx)
        templates.append(text)
        equipment_involved = _equipment_for_proposal(booking, proposal, equipment_by_id)

        suggestions.append({
            "id": f"S{i}",
            "type": proposal.type,
            "booking_ids": [booking.booking_id],
            "headline": text.headline,
            "change": proposal.change,
            "saving_kg": proposal.saving_result["saving_kg"],
            "saving_pct": proposal.saving_result["saving_pct"],
            "why": text.why,
            "tradeoff": text.tradeoff,
            "confidence": lowest_confidence_label(equipment_involved) if equipment_involved else "low",
            "needs_other_party": proposal.needs_other_party,
        })

    # one failed proposer call means the API is unreachable or misbehaving: don't call it again for text
    text_llm = llm if proposer == "llm" else None
    phraser_used = booking_ai.phrase(suggestions, top_proposals, contexts, templates, equipment_by_id, all_by_id,
                                     text_llm, usage_log)
    sset = {
        "request_id": request_id,
        "booking_ids": [b.booking_id for b in request_bookings],
        "estimate": {
            "kwh": round(total_kwh, 2),
            "kg": {"low": round(total_low, 2), "typ": round(total_typ, 2), "high": round(total_high, 2)},
            "hotspots": hotspots,
            "locked_kg": round(locked_kg, 2),
        },
        "suggestions": suggestions,
        "suppressed": build_suppressed_list(request_bookings),
    }
    if phraser_used != "template":
        # last line of defence: if any LLM text still breaks the contract, every card goes back to its template
        from src.contract import validate
        if validate.check_suggestion_set(sset):
            for sg, tpl in zip(suggestions, templates):
                sg.update(headline=tpl.headline, why=tpl.why, tradeoff=tpl.tradeoff)
            phraser_used = "template"
    used = [v for v, on in ((booking_ai.BOOKING_PROPOSER_VERSION, proposer == "llm"),
                            (booking_ai.BOOKING_PHRASER_VERSION, phraser_used != "template")) if on]
    sset["generator"] = {"proposer": proposer, "phraser": phraser_used,
                         "model": llm.model if used else None, "prompt_version": "/".join(used) or None}
    return sset
