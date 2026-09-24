# The contract: how data, AI and UI fit together

This file is the agreement between the three parts of the prototype. If everyone produces and consumes
exactly these formats, the pieces can be built in parallel and plugged together at the end.

```
 data/ (pseudo-lab)  ──►  calculator.py  ──►  AI layer  ──►  SuggestionSet (JSON)  ──►  UI
                             ▲                                                          │
                             └──── prices every proposal                FeedbackEvent ◄─┘
```

| Part | Reads | Produces | Owner |
|---|---|---|---|
| Pseudo-lab | – | `data/*.csv` | Davide |
| Calculator | `data/equipment.csv`, `data/grid_intensity.csv`, `data/bookings.csv` | kWh / kg CO₂e numbers | Davide |
| AI layer | the request (`data/scenario_request.csv`) + all of `data/` + calculator | `SuggestionSet` | AI team |
| UI | `SuggestionSet` | screens + `FeedbackEvent` | UI team |

---

## 1. Input to the AI layer: a booking request

A request is a set of booking rows with the same columns as `data/bookings.csv`. The demo request is
`data/scenario_request.csv` (researcher A1, 12–16 Oct, 10 rows). The columns that matter:

| Column | Meaning |
|---|---|
| `booking_id` | `BK-###` |
| `equipment_id` | key into `equipment.csv` |
| `start`, `end` | `YYYY-MM-DD HH:MM` |
| `movable` | `no` · `within day` · `±1 day` · `within week`: how far the tool may move it |
| `constraint` | why it is fixed (only when `movable = no`) |
| `load_pct` | autoclave load, 0–100 |
| `shelves` | incubator shelves used |

The researcher enters nothing beyond these booking fields (Phase 1, §2.2.4).

## 2. Output of the AI layer: `SuggestionSet`

Schema: [`contract/suggestion_set.schema.json`](contract/suggestion_set.schema.json) ·
Worked example: [`contract/examples/A1_suggestion_set.json`](contract/examples/A1_suggestion_set.json)

```jsonc
{
  "request_id": "REQ-A1-2026-10-12",
  "booking_ids": ["BK-056", "..."],
  "estimate": {
    "kwh": 89.75,
    "kg": {"low": 15.79, "typ": 24.9, "high": 36.59},          // always a range
    "hotspots": [{"equipment_id": "BIO-1", "kg_typ": 15.94, "share_pct": 64.0, "locked": true}, "..."],
    "locked_kg": 17.64                                          // out of the tool's reach
  },
  "suggestions": [                                              // max 3, biggest saving first
    {
      "id": "S1",
      "type": "coordinate",                                     // reschedule | share | coordinate
      "booking_ids": ["BK-078"],
      "headline": "Join an autoclave cycle that is already running on Tuesday",
      "change": {"merge_into_booking_id": "BK-075"},            // what Accept applies
      "saving_kg": {"low": 1.44, "typ": 2.05, "high": 2.87},
      "saving_pct": 100.0,
      "why": "Another group runs a 45% load at 16:00 ...",
      "tradeoff": "Your items must be ready by 16:00 instead of 17:00.",
      "confidence": "medium",
      "needs_other_party": true
    }
  ],
  "suppressed": [                                               // what the tool chose NOT to touch
    {"booking_id": "BK-057", "reason": "hard_constraint", "detail": "Bioreactor conditioning ..."}
  ]
}
```

### The three suggestion types (from Phase 1, §2.3)
| `type` | What changes | `change` fields | Demo case |
|---|---|---|---|
| `reschedule` | time only, within the `movable` window | `new_start`, `new_end` | Confocal Thu 19:00 → Fri 12:00 |
| `share` | another unit, or a device already running | `new_equipment_id` (+ times) | e.g. BSC-1 → smaller BSC-2 |
| `coordinate` | merge or batch energy-intensive runs | `merge_into_booking_id` | Autoclave merged with another group's cycle |

## 3. Rules the AI layer must follow

These come straight from our Phase 1 report. `contract/validate.py` checks the ones marked ✔.

1. ✔ **Never touch a booking with `movable = no`.** List it under `suppressed` with `reason: hard_constraint`.
2. **Never change the experiment itself**: only time, unit, or batching. No "use fewer samples", no "skip a step".
3. **Stay inside the `movable` window** (`within day`, `±1 day`, `within week`).
4. ✔ **At most 3 suggestions, biggest saving first**: this limits alert fatigue.
5. **Numbers come from `calculator.py`, never from the LLM.** The LLM picks and explains; it does not invent kg.
6. **Always give a range and a trade-off.** `tradeoff` is never empty.
7. **Don't name other groups or researchers.** Say "another group", and set `needs_other_party: true`.
8. **Drop suggestions that save less than 0.2 kg CO₂e** (`reason: saving_below_threshold`). Tune later.
9. **Respect muted suggestions**: a type/equipment pair rejected 3 times by the same lab is suppressed (`muted_by_user_feedback`).

`confidence` = the lowest confidence of the equipment values involved:
`estimate` → `low`, `derived` → `medium`, `measured` → `high`.

### Suggested pipeline (keeps the LLM honest)
1. **Generate candidates in code**: for every movable booking, try the cleanest-grid slot in its window where the
   unit is free; look for autoclave cycles on the same day with combined load ≤ 100%; look for confocal sessions
   that can follow another one (no warm-up).
2. **Price them** with `calculator.saving(...)`.
3. **Filter** with rules 1, 3, 8, 9, and keep the top 3.
4. **Ask the LLM** to fill `headline`, `why` and `tradeoff` only, given the numbers.

A custom GPT / Claude Project with the CSVs uploaded is fine for the demo, **as long as** its prompt includes
the rules above and it returns this exact JSON. Run `validate.py` on what it returns.

```python
from calculator import saving
saving("BK-098", new_start="2026-10-16 12:00", new_end="2026-10-16 16:00", warmup=False)
saving("BK-078", cancel=True)   # merged into BK-075
```

## 4. What the UI sends back: `FeedbackEvent`

Schema: [`contract/feedback_event.schema.json`](contract/feedback_event.schema.json) ·
Example: [`contract/examples/feedback_events.json`](contract/examples/feedback_events.json)

```json
{"event_id": "FB-0002", "request_id": "REQ-A1-2026-10-12", "suggestion_id": "S1",
 "suggestion_type": "coordinate", "equipment_id": "AUT-1",
 "action": "reject", "reason": "time_sensitive_sample", "timestamp": "2026-10-09 14:03"}
```

| `action` | UI behaviour | What the system learns |
|---|---|---|
| `accept` | Booking updated, estimate recomputed | Counts toward acceptance rate |
| `reject` | **One click**, reason optional; card disappears | Repeated rejects → pattern muted (rule 9) |
| `modify` | Researcher edits the proposed time; `modified_change` stored | Window preferences for this lab |
| `flag_error` | Short comment sent to the lab manager | Equipment value reviewed (VSD cycle 3) |

**No researcher or group ID is stored in feedback.** Feedback is aggregated at lab level only
(Phase 1, §3.1). Rejecting never needs a justification (Phase 1, §2.2.4).

## 5. How the UI should use the contract
- Build against `contract/examples/A1_suggestion_set.json` **now**; swap in the real AI output later.
- Screen 1, booking form: the fields in §1.
- Screen 2, result card: `estimate.kg` as a range, `hotspots` (mark `locked` ones), then `suggestions`
  with Accept / Reject / Modify. A "Why not the bioreactor?" link shows `suppressed`.
- Screen 3, after feedback: updated estimate (accepted) or muted card (rejected).
- If `needs_other_party` is true, Accept means "Request to join", not "Done".

## 6. How we evaluate outputs (for the coaching session and Phase 2)
| Metric | How | Target |
|---|---|---|
| Constraint violations | `validate.py` over all AI outputs | 0 |
| Agreement with gold set | Compare AI output with `examples/A1_suggestion_set.json` (same bookings, same type) | ≥ 2 of 3 |
| Numeric honesty | Every `saving_kg` matches `calculator.py` | 100% |
| Acceptance / rejection rate | From `FeedbackEvent`s in a pilot | tracked, with reasons |
| Alert fatigue | Dismiss rate over repeated requests | should not rise |
| Net benefit | Tool's own footprint (Green Algorithms) vs kg saved | saved ≫ spent |

## Changing the contract
Open a PR that edits the schema **and** the example **and** this file together, and tag the other two parts.
`validate.py` must pass on the examples.
