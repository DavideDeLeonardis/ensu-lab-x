"""
Phrasing: turns an already-ranked, already-calculator-verified proposal into
the human-readable `headline` / `why` / `tradeoff` fields the schema wants.

The templates live here; the LLM versions are in booking_ai.py (bookings) and plan_engine.py
(plans), and fall back to these templates. By the time a proposal reaches here:
  - it has already passed Rule 1 (never touches movable == "no")
  - it has already passed Rule 8 (saving >= 0.2 kg)
  - its saving numbers already came from calculator.py (Rule 5)
  - Rule 4's top-3 selection has already happened

So the phraser (template or LLM) cannot invent a number, cannot suggest
touching a locked booking, and cannot smuggle in a fourth suggestion -- it
only writes English for a decision that's already made.

Every number in the text comes from the proposal (calculator output) or the
PhraseContext (bookings.csv / equipment.csv). No group or researcher is ever
named (Rule 7): the other party is always "another group".

Schema limits: headline <= 80, why <= 200, tradeoff <= 160 characters.
"""
from __future__ import annotations
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Optional

from .domain import Booking, Equipment
from .ranking import RankedProposal

# Rule 7: never name another group or researcher.
ANONYMOUS_OTHER_PARTY = "another group"
FMT = "%Y-%m-%d %H:%M"


@dataclass(frozen=True)
class PhraseContext:
    """Facts the phraser may use, looked up by build.py from the data files."""
    booking: Booking                         # the booking being changed (original times)
    equipment: Optional[Equipment] = None    # its device
    alternate: Optional[Equipment] = None    # share: the device proposed instead
    merge_target: Optional[Booking] = None   # coordinate: the run to join


class PhrasedText:
    def __init__(self, headline: str, why: str, tradeoff: str):
        self.headline = headline
        self.why = why
        self.tradeoff = tradeoff


Phraser = Callable[[RankedProposal, PhraseContext], PhrasedText]


# --- small formatting helpers ------------------------------------------------
def _device(eq: Optional[Equipment], fallback: str) -> str:
    """'Confocal microscope' -> 'confocal microscope'; drops '(large, older)' qualifiers."""
    if eq is None or not eq.name:
        return fallback
    name = re.sub(r"\s*\([^)]*\)\s*$", "", eq.name).strip()
    return name[0].lower() + name[1:] if not name.isupper() else name


def _a(word: str) -> str:
    return f"{'an' if word[:1].lower() in 'aeiou' else 'a'} {word}"


def _part_of_day(t: datetime) -> str:
    return "morning" if t.hour < 12 else "afternoon" if t.hour < 17 else "evening"


def _slot(start: datetime, end: datetime) -> str:
    return f"{start:%a %d %b}, {start:%H:%M}–{end:%H:%M}"


def _shift(old: datetime, new: datetime) -> str:
    hours = round((new - old).total_seconds() / 3600)
    if hours == 0:
        return "at the same time"
    unit = "hour" if abs(hours) == 1 else "hours"
    return f"{abs(hours)} {unit} {'later' if hours > 0 else 'earlier'} than planned"


def _fit(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


# --- default phraser (no LLM, no network) --------------------------------------
def template_phraser(proposal: RankedProposal, ctx: PhraseContext) -> PhrasedText:
    b = ctx.booking
    saving = proposal.saving_result
    saved = saving["saving_kg"]["typ"]
    device = _device(ctx.equipment, b.equipment_id)

    if proposal.type == "reschedule":
        new_start = datetime.strptime(proposal.change["new_start"], FMT)
        new_end = datetime.strptime(proposal.change["new_end"], FMT)
        same_day = new_start.date() == b.start.date()
        when = f"{_part_of_day(new_start)}" if same_day else f"{new_start:%A} {_part_of_day(new_start)}"
        before_g = saving["before"].get("avg_grid_g_per_kwh")
        after_g = saving["after"].get("avg_grid_g_per_kwh")
        why = (f"The grid averages ~{after_g:.0f} g/kWh on {_slot(new_start, new_end)} "
               f"vs ~{before_g:.0f} in your current slot") if before_g and after_g else \
              f"The grid is cleaner on {_slot(new_start, new_end)}"
        if proposal.notes.get("warmup_shared"):
            why += ", and the device is already warm from the session before"
        why += f": about {saved:.1f} kg CO₂e less."
        return PhrasedText(
            headline=_fit(f"Move your {device} session to the {when}" if same_day
                          else f"Move your {device} session to {when}", 80),
            why=_fit(why, 200),
            tradeoff=_fit(f"Your session starts {_shift(b.start, new_start)} "
                          f"({new_start:%a %H:%M} instead of {b.start:%a %H:%M}).", 160),
        )

    if proposal.type == "share":
        alt_id = proposal.change["new_equipment_id"]
        alt = _device(ctx.alternate, alt_id)
        return PhrasedText(
            headline=_fit(f"Use {alt_id} instead of {b.equipment_id} for this slot", 80),
            why=_fit(f"{alt_id} is also {_a(alt)} and is free at the same time; it uses less energy "
                     f"for the same work: about {saved:.1f} kg CO₂e less ({saving['saving_pct']:.0f}%).", 200),
            tradeoff=_fit(f"You work at {alt_id} instead of {b.equipment_id}; check its setup suits "
                          f"your protocol.", 160),
        )

    if proposal.type == "coordinate":
        t = ctx.merge_target
        run = "cycle" if ctx.equipment is not None and ctx.equipment.mode == "cycle" else "run"
        if t is None:  # no booking details available: stay generic but correct
            return PhrasedText(
                headline=_fit(f"Join {_a(device)} {run} that is already scheduled", 80),
                why=_fit(f"Merging into an already-scheduled {run} avoids a separate one: "
                         f"about {saved:.1f} kg CO₂e less.", 200),
                tradeoff=_fit(f"Needs {ANONYMOUS_OTHER_PARTY}'s OK; timing follows their slot.", 160),
            )
        day = "the same day" if t.start.date() == b.start.date() else f"on {t.start:%a %d %b}"
        loads = (f"a {t.load_pct:.0f}% load" if t.load_pct is not None else f"a {run}")
        fits = (f"Your {b.load_pct:.0f}% load fits in it" if b.load_pct is not None else "Your items fit in it")
        if t.start < b.start:
            timing = f"your items must be ready by {t.start:%H:%M} instead of {b.start:%H:%M}"
        else:
            timing = f"your items are processed at {t.start:%H:%M} instead of {b.start:%H:%M}"
        return PhrasedText(
            headline=_fit(f"Join {_a(device)} {run} already running on {t.start:%A}", 80),
            why=_fit(f"{ANONYMOUS_OTHER_PARTY.capitalize()} runs {loads} at {t.start:%H:%M} {day}. "
                     f"{fits}, so one full {run} is avoided: about {saved:.1f} kg CO₂e less.", 200),
            tradeoff=_fit(f"Needs {ANONYMOUS_OTHER_PARTY}'s OK, and {timing}.", 160),
        )

    raise ValueError(f"unknown proposal type: {proposal.type}")
