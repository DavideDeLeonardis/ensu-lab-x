# The contract: how data, AI and UI fit together

This file is the agreement between the three parts of the prototype. If everyone produces and consumes
exactly these formats, the pieces can be built in parallel and plugged together at the end.

```
 data/ (pseudo-lab)  ──►  src/lab/calculator.py  ──►  AI layer  ──►  SuggestionSet (JSON)  ──►  UI
                             ▲                                                          │
                             └──── prices every proposal                FeedbackEvent ◄─┘
```

| Part | Reads | Produces | Owner |
|---|---|---|---|
| Pseudo-lab | – | `data/*.csv` | Davide |
| Calculator (`src/lab/calculator.py`) | `data/equipment.csv`, `data/grid_intensity.csv`, `data/bookings.csv` | kWh / kg CO₂e numbers | Davide |
| AI layer (`src/ai/`) | the request (`data/scenario_request.csv`) + all of `data/` + calculator | `SuggestionSet` | AI team |
| UI (`src/ui/`) | `SuggestionSet` | screens + `FeedbackEvent` | UI team |

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

Schema: [`contract/schemas/suggestion_set.schema.json`](contract/schemas/suggestion_set.schema.json) ·
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

These come straight from our Phase 1 report. `src/contract/validate.py` checks every rule marked ✔;
`tests/test_contract.py` runs the AI engine on the demo request and validates its output.

1. ✔ **Never touch a booking with `movable = no`.** List it under `suppressed` with `reason: hard_constraint`.
2. ✔ **Never change the experiment itself**: only time, unit, or batching. No "use fewer samples", no "skip a step".
   A reschedule keeps the same duration; a `share` uses a device of the same category and mode.
3. ✔ **Stay inside the `movable` window, and inside lab hours.**

   | `movable` | The new slot must lie within |
   |---|---|
   | `within day` | the same calendar day (00:00–24:00) |
   | `±1 day` | original start − 24 h → original end + 24 h |
   | `within week` | the same calendar week, Monday 00:00 → next Monday 00:00 |

   **Lab hours:** the tool only proposes slots **Mon–Fri, fully inside 08:00–20:00**. The researcher may
   book outside these hours; the tool never suggests it. For `coordinate`, the merge target must be a cycle
   on the same device, fully inside the window, with combined load ≤ 100%.
4. ✔ **At most 3 suggestions, biggest saving first**: this limits alert fatigue.
5. ✔ **Numbers come from `calculator.py`, never from the LLM.** The LLM picks and explains; it does not invent kg.
   The validator re-prices every suggestion and accepts a difference of at most 0.01 kg.
6. ✔ **Always give a range and a trade-off.** `tradeoff` is never empty.
7. ✔ **Don't name other groups or researchers.** Say "another group", and set `needs_other_party: true`.
8. ✔ **Drop suggestions that save less than 0.2 kg CO₂e** (`reason: saving_below_threshold`). Tune later.
9. **Respect muted suggestions**: a (type, equipment) pair rejected 3 times in this lab is not suggested again
   (`muted_by_user_feedback`). Get the pairs with `src.contract.feedback.muted_pairs()`; see §4.

The output's `estimate.hotspots` has **one entry per device** (bookings on the same device summed), largest first, max 4 (✔).

`confidence` = the lowest confidence of the equipment values involved:
`estimate` → `low`, `derived` → `medium`, `measured` → `high`.


A custom GPT / Claude Project with the CSVs uploaded is fine for the demo, **as long as** its prompt includes
the rules above and it returns this exact JSON. Run `python3 src/contract/validate.py <file>` on what it returns.

```python
from src.lab.calculator import saving   # run from the repo root
saving("BK-098", new_start="2026-10-16 12:00", new_end="2026-10-16 16:00", warmup=False)
saving("BK-078", cancel=True)   # merged into BK-075
```

## 4. What the UI sends back: `FeedbackEvent`

Schema: [`contract/schemas/feedback_event.schema.json`](contract/schemas/feedback_event.schema.json) ·
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

### Where feedback is stored
The UI appends every event to **`data/feedback_log.json`** (a JSON list) with
`src.contract.feedback.append_event(event)`, which validates it first. The AI layer calls
`muted_pairs()` before ranking and passes the result as `muted_pairs`. The log is lab-level only.

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
| Constraint violations | `src/contract/validate.py` over all AI outputs | 0 |
| Agreement with gold set | Compare AI output with `examples/A1_suggestion_set.json` (same bookings, same type) | ≥ 2 of 3 |
| Numeric honesty | Every `saving_kg` matches `calculator.py` | 100% |
| Acceptance / rejection rate | From `FeedbackEvent`s in a pilot | tracked, with reasons |
| Alert fatigue | Dismiss rate over repeated requests | should not rise |
| Net benefit | Tool's own footprint (Green Algorithms) vs kg saved | saved ≫ spent |

## Changing the contract
Open a PR that edits the schema **and** the example **and** this file together, and tag the other two parts.
`python3 -m unittest discover tests` must pass (gold examples + engine output).
