"""
The LLM for booking requests: same pattern as plan_engine.py.

    rules  → every allowed change (candidates.py: flexibility window, lab hours, availability, same kind of unit,
             merge only into a run on the same device with room for the load) priced by the calculator
    LLM    → picks among a short list of those options (structured JSON, option ids only)        [proposer]
    rules  → ids not in the list are dropped; ≥ 0.2 kg, one per booking, biggest first, max 3
    LLM    → writes headline / why / tradeoff; any text that fails the checks keeps the template  [phraser]

Used by build.py when an `llm` is given; without one, build.py runs exactly as before (rules + templates).
The prompts never contain a group or researcher id, the request id, or anything about other groups' bookings
except the time and load of a run to join.
"""
from __future__ import annotations
import json
from datetime import datetime

from .domain import Booking, Equipment
from .phrasing import PhraseContext, PhrasedText, _device, _slot, FMT
from .ranking import _all_candidates_for_booking, RankedProposal, MIN_SAVING_KG, MAX_SUGGESTIONS
from .llm.prompts import (BOOKING_PROPOSER_VERSION, BOOKING_PHRASER_VERSION, BOOKING_PROPOSER_SYSTEM,
                          BOOKING_PHRASER_SYSTEM, PHRASER_SCHEMA, booking_proposer_schema, booking_proposer_user,
                          phraser_user, numbers_outside)
from .llm.usage_log import log_usage

PER_BOOKING_AND_TYPE = 2   # the best few options per booking and type go to the LLM
MAX_OPTIONS = 10
LIMITS = {"headline": 80, "why": 200, "tradeoff": 160}
FLEX = {"within day": "same day", "±1 day": "one day earlier or later", "within week": "same week"}


def option_pool(request_bookings, all_bookings, calc, muted_pairs, alternates, cycle_equipment) -> list[RankedProposal]:
    """All allowed, priced options worth ≥ 0.2 kg; the best PER_BOOKING_AND_TYPE per booking and type, max 10."""
    request_ids = {b.booking_id for b in request_bookings}
    pool = []
    for b in request_bookings:
        if b.movable == "no":
            continue
        by_type: dict[str, list[RankedProposal]] = {}
        for p in _all_candidates_for_booking(b, all_bookings, request_ids, calc, alternates, cycle_equipment):
            if (p.type, b.equipment_id) in (muted_pairs or set()) or p.saving_result["saving_kg"]["typ"] < MIN_SAVING_KG:
                continue
            by_type.setdefault(p.type, []).append(p)
        for props in by_type.values():
            pool += sorted(props, key=lambda p: p.saving_result["saving_kg"]["typ"], reverse=True)[:PER_BOOKING_AND_TYPE]
    pool.sort(key=lambda p: p.saving_result["saving_kg"]["typ"], reverse=True)
    return pool[:MAX_OPTIONS]


def top_three(proposals: list[RankedProposal]) -> list[RankedProposal]:
    """Rules 4 and 8 again on whatever was chosen: biggest first, one per booking, max 3."""
    out, seen = [], set()
    for p in sorted(proposals, key=lambda p: p.saving_result["saving_kg"]["typ"], reverse=True):
        if p.booking_id not in seen and p.saving_result["saving_kg"]["typ"] >= MIN_SAVING_KG:
            out.append(p)
            seen.add(p.booking_id)
        if len(out) == MAX_SUGGESTIONS:
            break
    return out


def _change_text(p: RankedProposal, b: Booking, equipment: dict[str, Equipment], all_by_id: dict[str, Booking]) -> str:
    """The change in words. Another group's run: only its time and load, never who."""
    if p.type == "reschedule":
        s, e = (datetime.strptime(p.change[k], FMT) for k in ("new_start", "new_end"))
        return f"move to {_slot(s, e)}"
    if p.type == "share":
        alt = p.change["new_equipment_id"]
        return f"use {_device(equipment.get(alt), alt)} ({alt}) at the same time"
    t = all_by_id.get(p.change["merge_into_booking_id"])
    if t is None:
        return "join a run that is already scheduled on the same device"
    load = f", {t.load_pct:.0f}% full" if t.load_pct is not None else ""
    return f"join another group's run on {t.start:%a %d %b} at {t.start:%H:%M}{load}"


def propose(pool, request_bookings, equipment, all_by_id, llm, usage_log, free_text="") -> tuple[list, str]:
    """(chosen proposals, 'llm' | 'rules'). Falls back to the rules' own top 3 if the LLM fails or misbehaves."""
    if llm is None or not pool:
        return top_three(pool), "rules"
    by_booking = {b.booking_id: b for b in request_bookings}
    ids = {f"O{i}": p for i, p in enumerate(pool, start=1)}
    options = []
    for oid, p in ids.items():
        b = by_booking[p.booking_id]
        options.append({"option_id": oid, "type": p.type,
                        "device": _device(equipment.get(b.equipment_id), b.equipment_id),
                        "current_slot": _slot(b.start, b.end), "flexibility": FLEX.get(b.movable, b.movable),
                        "change": _change_text(p, b, equipment, all_by_id)})
    result = llm.complete_json(BOOKING_PROPOSER_SYSTEM, booking_proposer_user(options, free_text),
                               booking_proposer_schema(list(ids)), max_tokens=2048)
    log_usage(result, "booking-proposer", BOOKING_PROPOSER_VERSION, usage_log)
    raw = result.data.get("candidates") if result.ok else None
    if not isinstance(raw, list):
        return top_three(pool), "rules"
    picked = [c["option_id"] for c in raw if isinstance(c, dict) and c.get("option_id") in ids]  # rule 10
    if raw and not picked:
        return top_three(pool), "rules"
    return top_three([ids[o] for o in dict.fromkeys(picked)]), "llm"


def facts(p: RankedProposal, ctx: PhraseContext, template: PhrasedText, equipment, all_by_id) -> dict:
    b, s = ctx.booking, p.saving_result
    f = {"type": p.type, "device": _device(ctx.equipment, b.equipment_id), "current_slot": _slot(b.start, b.end),
         "proposed_change": _change_text(p, b, equipment, all_by_id),
         "saving": f"about {s['saving_kg']['typ']:.1f} kg CO₂e less ({s['saving_pct']:.0f}%)",
         "tradeoff": template.tradeoff, "needs_other_party": p.needs_other_party}
    before, after = s["before"].get("avg_grid_g_per_kwh"), s["after"].get("avg_grid_g_per_kwh")
    if p.type == "reschedule" and before and after:
        f["grid"] = f"about {after:.0f} g/kWh in the new slot instead of about {before:.0f} g/kWh now"
    if p.notes.get("warmup_shared"):
        f["note"] = "the device is already warm from the session before"
    return f


def text_problems(text, suggestion: dict, fact_text: str, extra_pct=()) -> list[str]:
    """Why an LLM text cannot be shown: lengths, rules 6/7/11, and any number not given in the facts."""
    from src.contract import validate
    if not isinstance(text, dict) or not all(isinstance(text.get(k), str) and text[k].strip() for k in LIMITS):
        return ["missing field"]
    problems = [f"{k} longer than {n}" for k, n in LIMITS.items() if len(text[k]) > n]
    problems += validate._check_text_and_threshold({**suggestion, **{k: text[k] for k in LIMITS}}, extra_pct=extra_pct)
    problems += [f"number {n} is not in the facts" for n in numbers_outside(" ".join(text[k] for k in LIMITS), fact_text)]
    # the headline must name the real action (seen live: a merge titled "reschedule ... to 16:00")
    joins = "join" in text["headline"].lower()
    if suggestion.get("type") == "coordinate" and not joins:
        problems.append("a coordinate headline must say the researcher joins a run")
    if suggestion.get("type") != "coordinate" and joins:
        problems.append("only a coordinate suggestion joins a run")
    return problems


def phrase(suggestions: list[dict], proposals: list, contexts: list, templates: list, equipment, all_by_id,
           llm, usage_log) -> str:
    """Replace each suggestion's template text with the LLM's when it passes every check. 'llm'|'template'|'mixed'."""
    if llm is None:
        return "template"
    used = 0
    for sg, p, ctx, tpl in zip(suggestions, proposals, contexts, templates):
        f = facts(p, ctx, tpl, equipment, all_by_id)
        fact_text = json.dumps(f, ensure_ascii=False)
        result = llm.complete_json(BOOKING_PHRASER_SYSTEM, phraser_user(f), PHRASER_SCHEMA, max_tokens=1024)
        log_usage(result, "booking-phraser", BOOKING_PHRASER_VERSION, usage_log)
        loads = [x.load_pct for x in (ctx.booking, ctx.merge_target) if x is not None and x.load_pct is not None]
        if result.ok and not text_problems(result.data, sg, fact_text, extra_pct=loads):
            sg.update({k: result.data[k].strip() for k in LIMITS})
            used += 1
    return "template" if used == 0 else "llm" if used == len(suggestions) else "mixed"
