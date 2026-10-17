# The contract: how data, AI and UI fit together

This file is the agreement between the three parts of the prototype. If everyone produces and consumes
exactly these formats, the pieces can be built in parallel and plugged together at the end.

```
 data/ (pseudo-lab)  ──►  src/lab/calculator.py  ──►  AI layer  ──►  SuggestionSet (JSON)  ──►  UI
                             ▲                                                          │
                             └──── prices every proposal                FeedbackEvent ◄─┘
```

The AI layer takes one of two inputs: a **booking request** (§1, the first prototype) or an
**experiment plan** (§1b, the planning-stage design). Both return a `SuggestionSet`. The metric is always
**kg CO₂e**; for plans most of it comes from consumables, and electricity is a secondary contributor.

| Part | Reads | Produces | Owner |
|---|---|---|---|
| Pseudo-lab | – | `data/*.csv` | Davide |
| Calculator (`src/lab/calculator.py`) | `data/equipment.csv`, `data/grid_intensity.csv`, `data/bookings.csv` | kWh / kg CO₂e numbers | Davide |
| AI layer (`src/ai/`) | the request (`data/scenario_request.csv`) + all of `data/` + calculator | `SuggestionSet` | AI team |
| UI (`src/ui/`) | `SuggestionSet` | screens + `FeedbackEvent` | UI team |
| Plan engine (`src/ai/plan_engine.py`, LLM in `src/ai/llm/`) | an `ExperimentPlan` + `data/consumables.csv`, `data/equivalences.csv`, `data/electricity_factors.csv` + plan calculator | `SuggestionSet` | AI team |

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

## 1b. Input for an experiment plan: `ExperimentPlan`

Schema: [`contract/schemas/experiment_plan.schema.json`](contract/schemas/experiment_plan.schema.json)

Why plans: TU/e buys green electricity, lab emissions come mostly from consumables (scope 3), and many
researchers don't use a booking system. A plan lists **quantities**; the calculator prices each line as
quantity × emission factor.

```jsonc
{
  "plan_id": "PLAN-2026-0042",          // opaque: never a researcher or group id
  "title": "Valve scaffold seeding",    // free text: untrusted
  "notes": "Cells are sensitive to serum lot changes.",   // free text: untrusted
  "lines": [
    {"line_id": "L1", "item_id": "TIP-200-F", "quantity": 960, "unit": "piece", "requirements": ["sterile"]},
    {"line_id": "L2", "item_id": "FBS", "quantity": 0.5, "unit": "L",
     "locked": true, "lock_reason": "Validated protocol requires this serum"},
    {"line_id": "L3", "item_id": "BSC-1", "quantity": 15, "unit": "h"}
  ]
}
```

| Field | Rule |
|---|---|
| `item_id` | key into `data/consumables.csv` (consumables, chemicals, methods) or `data/equipment.csv` (unit `h`; modes `hourly`, `shelf` (one shelf), `day`, `continuous`: an autoclave cycle is not a plan line yet) |
| `unit` | `piece` · `mL` · `L` · `g` · `kg` · `h` · `run`; must equal the catalogue unit |
| `requirements` | `sterile` · `rnase_free` · `low_retention` · `gmp` · `single_use_required` · `animal_free` · `tc_treated` (surface treated for adherent cell culture) (extending the list is a contract change) |
| `locked` / `lock_reason` | the plan equivalent of `movable = no`; the reason is required and shown to the researcher |

No time fields: plans don't need a booking calendar.

### Data files the plan engine and the validator read
**`data/consumables.csv`** (the catalogue): `item_id`, `name`, `kind` (`consumable` · `chemical` · `method`),
`unit`, `kg_per_unit` (kg CO₂e per unit that does not come from electricity), `kwh_per_unit` (electricity per
unit, e.g. washing and autoclaving a reusable item; priced with the electricity factor, so it follows the
chosen basis), `low`, `high` (range multipliers on the whole item), `confidence` (`measured` · `derived` ·
`estimate`), `source` (key into `sources.csv`), `basis` (one line on the number).
Every value has a source or is marked `estimate`. The demo plan is `data/plan_A1.json`.

**`data/equivalences.csv`** (the curated list, the only source of what counts as equivalent):
`equivalence_id` (`EQ-###`), `item_id` → `alternative_id`, `type` (`substitute` · `method` · `share_material`),
`ratio` (units of the alternative per unit of the original), `incompatible_with` (requirement tags,
`;`-separated), `requires_validation`, `needs_other_party`, `tradeoff`, `curated_by` (a role, not a name),
`source`.

**`data/electricity_factors.csv`**: `basis` (`location` · `market`), `g_per_kwh`, `source`, `basis_note`.
Chosen with `LABX_ELECTRICITY_BASIS`, default `location` (NL grid average); `market` reflects the green
electricity contract. Plans use an annual average, not the hourly curve.

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

### Extra fields for experiment plans
All optional in the schema, so booking outputs are unchanged.

| Where | Field | Meaning |
|---|---|---|
| top level | `request_id` | holds the `plan_id` |
| top level | `line_ids` | the plan's lines (mirror of `booking_ids`) |
| top level | `generator` | `{"proposer": "llm"\|"rules", "phraser": "llm"\|"template"\|"mixed", "model", "prompt_version"}`; always set by the engines (plans and bookings). `rules` = no LLM, or it failed and the rules took over |
| `estimate` | `breakdown` | `{"embodied": range, "electricity": range}` in kg CO₂e |
| `estimate` | `electricity` | `{"basis": "location"\|"market", "g_per_kwh", "source"}`: the factor used |
| `estimate.hotspots[]` | `item_id` | instead of `equipment_id` (exactly one of the two) |
| `suggestions[]` | `line_ids` | instead of `booking_ids` (exactly one of the two, with one id) |
| `suggestions[].change` | `line_id`, `equivalence_id`, `alternative_id`, `new_quantity` | what Accept applies; `new_quantity` = quantity × ratio |
| `suggestions[]` | `requires_validation` | from the equivalence: "check with the lab manager first" |
| `suppressed[]` | `line_id` | instead of `booking_id`; `reason` may also be `requirement_conflict` |

| `type` (plans) | What changes | Demo case |
|---|---|---|
| `substitute` | another consumable, including a reusable one | boxed tips → refill racks |
| `method` | an equivalent procedure | e.g. a different cell-count method |
| `share_material` | shared stock or run with another group (`needs_other_party: true`) | e.g. a shared medium bottle |

**Saving range for plans:** each bound is `before.k − after.k` for `k` in low/typ/high, then the three values
are sorted so that `low ≤ typ ≤ high` (the two items have different uncertainties, so the raw differences
can come out unordered).

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

**Rule 10 for bookings** (when an LLM is used, `src/ai/booking_ai.py`): it only picks option ids from the list the
rules built; anything else is dropped. The output then carries `generator`, as for plans.

**Rule 11** ✔ **Numbers in the text come from the calculator.** A number followed by `kg` must equal a bound of
`saving_kg` at the precision written ("1.9 kg" for 1.93); a number followed by `%` must equal `saving_pct` or
the `load_pct` of the booking or its merge target ("a 45% load"). Applies to plans too (§3b; rule 10 is
plan-only).

### 3b. Rules for experiment plans
Same numbering as above; rules 10 and 12 are new.

| # | Rule | Checked by |
|---|---|---|
| 1 | Never touch a `locked` line; list it under `suppressed` (`hard_constraint`) | validator ✔ |
| 2 | Don't change the experiment: only a pair from `equivalences.csv` for the line's `item_id`, with none of the line's `requirements` in `incompatible_with`, and `new_quantity` = quantity × ratio; `type`, `requires_validation` and `needs_other_party` copied from the pair | validator ✔ |
| 3 | (time windows: not applicable) | – |
| 4 | At most 3, biggest saving first, one per line | validator ✔ |
| 5 | Every `saving_kg` is re-priced with the plan calculator (tolerance 0.01 kg) | validator ✔ |
| 6 | Range + non-empty trade-off; if `requires_validation`, the trade-off says so | validator ✔ |
| 7 | No group or researcher names in the text or in `plan_id` | validator ✔ |
| 8 | Drop suggestions saving less than 0.2 kg CO₂e | validator ✔ |
| 9 | Respect muted (type, item) pairs | engine |
| 10 | The LLM only returns `line_id` / `equivalence_id` values from the list it was given; anything else is discarded before pricing | engine + validator (via rule 2) |
| 11 | Numbers in the text come from the calculator (as above; a quantity of an item counted in kg is also allowed) | validator ✔ |
| 12 | The prompt contains no `plan_id`, group or researcher id; free text is passed as delimited, untrusted data | engine + tests |

The LLM proposes and phrases; it never produces a kg or kWh value. If it fails, the rule-based proposer and the
template texts take over, and `generator` says so.

The validator checks plan outputs **fail-closed**: without the plan, the catalogue or the plan calculator it
reports an error instead of passing. Run `python3 src/contract/validate.py <output.json> --plan <plan.json>`.

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

For plan suggestions the event carries `item_id` (the item of the changed line) instead of `equipment_id`,
`suggestion_type` may be `substitute`, `method` or `share_material`, and `reason` may also be
`not_equivalent_for_my_protocol`. Muting (rule 9) works on (type, `equipment_id` or `item_id`).

### Where feedback is stored
The UI appends every event to **`data/feedback_log.json`** (a JSON list) with
`src.contract.feedback.append_event(event)`, which validates it first. The AI layer calls
`muted_pairs()` before ranking and passes the result as `muted_pairs`. The log is lab-level only.

**No researcher or group ID is stored in feedback.** Feedback is aggregated at lab level only
(Phase 1, §3.1). Rejecting never needs a justification (Phase 1, §2.2.4).

## 5. How the UI should use the contract
- Build against **`contract/examples/A1_suggestion_set_from_ai_layer.json`**: the real AI output for the
  demo request (regenerate with `python3 real_data_demo.py`). `A1_suggestion_set.json` is the hand-written
  gold set, same shape.
- **Display data** (device names, booking times, rooms) is not repeated in the SuggestionSet: look it up by
  `equipment_id` / `booking_id` in **`data/lab_data.json`** (`equipment`, `bookings`). That file also holds
  other groups' names and researcher IDs: **never show them** (rule 7); for a merge target show only its time.
- **Estimate after Accept**: new total = `estimate.kg` − the `saving_kg` of every accepted suggestion
  (low/typ/high separately). This is exact because each suggestion changes a different booking (✔ checked).
  No calculator call is needed in the UI.
- **Plan outputs**: build against **`contract/examples/A1_plan_suggestion_set.json`** (real engine output for
  `data/plan_A1.json`, rules + templates; regenerate with `python3 plan_demo.py --save`). They use `line_ids`, `item_id` hotspots and the types `substitute` / `method` / `share_material`.
  Display names of items come from `data/lab_data.json` (`consumables`, `equivalences`, added with the plan
  data). If `requires_validation` is true, Accept means "ask the lab manager", not "Done".
- Screen 1, booking form: the fields in §1.
- Screen 2, result card: `estimate.kg` as a range, `hotspots` (mark `locked` ones), then `suggestions`
  with Accept / Reject / Modify. A "Why not the bioreactor?" link shows `suppressed`.
- Screen 3, after feedback: updated estimate (accepted) or muted card (rejected).
- If `needs_other_party` is true, Accept means "Request to join", not "Done": the saving counts only once
  the other group agrees (for the demo, show it as pending).
- Every Accept / Reject / Modify / Flag produces one `FeedbackEvent` (§4). In Python, store it with
  `append_event()`; from a web mock-up, build the same JSON and check a saved list with
  `python3 src/contract/validate.py <events.json>`.

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
Schemas: `suggestion_set`, `feedback_event`, `experiment_plan` (all in `contract/schemas/`).
`python3 -m unittest discover tests` must pass (gold examples + engine output).
