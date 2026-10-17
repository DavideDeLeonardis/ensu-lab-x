# src/ai — suggestion engine

Takes a booking request, finds possible changes, prices each one with `src/lab/calculator.py`,
applies the contract rules and returns a `SuggestionSet` (see `CONTRACT.md`).

## Pipeline
```
candidates.py   what could each movable booking change to?       (no LLM, no numbers)
      ▼
ranking.py      price every candidate with calculator.saving(),  (no LLM)
                apply the rules, keep the top 3
      ▼
phrasing.py     headline / why / tradeoff for the chosen ones     (the only place an LLM may be used)
      ▼
build.py        estimate + hotspots + suggestions + suppressed → SuggestionSet dict
```
Supporting files: `domain.py` (Booking / Equipment loaded from `data/`), `ports.py` (the calculator
interface), `calculator_adapter.py` (the real calculator behind that interface), `mock_calculator.py`
(fake calculator for `tests/test_build.py`, which runs without the data files).

## Run
From the repo root:
```bash
python3 real_data_demo.py                                   # SuggestionSet for the A1 demo request
python3 -m unittest discover tests -v                       # rule tests + this engine validated end-to-end
```
To refresh the UI's input, save the demo output (without the sanity-check line) to
`contract/examples/A1_suggestion_set_from_ai_layer.json` and run `validate.py` on it.

## Where each rule is applied
| Rule (CONTRACT.md §3) | Where |
|---|---|
| 1 never touch `movable = no` | `ranking.rank_proposals` (only movable bookings) + `build_suppressed_list` |
| 2 don't change the experiment | `candidates`: same duration; `share` only between units of the same kind (`derive_alternates`) |
| 3 movable window + lab hours | `candidates`, using `src/contract/rules.py` (same code as the validator) |
| 4 max 3, biggest first, one per booking | `ranking.rank_proposals` |
| 5 numbers from the calculator | `ranking` calls `calc.saving()`; `build` calls `calc.estimate()` |
| 6 range + trade-off, 7 no names | `phrasing.template_phraser` ("another group", never IDs) |
| 8 ≥ 0.2 kg | `ranking.MIN_SAVING_KG` |
| 9 muted pairs | `rank_proposals(muted_pairs=…)`, from `src.contract.feedback.muted_pairs()` |

Two design choices worth knowing:
- **Share alternates** are units with the same name (qualifier in brackets stripped), category, room and
  mode: BSC-1 ↔ BSC-2 pair up, confocal ↔ widefield do not. `shareable` is not used for this (it means
  "serves several groups at once").
- **Warm-up** is skipped when the new slot starts exactly when *another* session on the same device ends.

## Experiment plans: `plan_engine.py` + `llm/`
The planning-stage design (CONTRACT.md §1b, §3b). **The LLM proposes, the calculator counts, the rules and the
validator filter, the researcher decides.**
```
allowed_options   curated equivalences per unlocked line − requirement clashes − muted pairs   (no LLM)
      ▼
propose           LLM picks among the allowed options: JSON, ids are enums in the schema        (LLM)
                  rule 10: ids not in the list are dropped; LLM failure → every allowed option ("rules")
      ▼
rank              plan_calculator.plan_saving() for each; ≥ 0.2 kg, one per line, top 3        (no LLM)
      ▼
phrase            LLM writes headline/why/tradeoff; any text failing lengths, names (7),         (LLM)
                  numbers (11) or the validation notice (6) → template for that suggestion
      ▼
validate          validate.check_suggestion_set(sset, plan); if the LLM text still fails → templates
```
`generator` in the output says `llm` / `rules` / `template` / `mixed`, the model and the prompt versions.

**What the AI may do with the options (since proposer-v3).** It reads the researcher's "Notes for the AI", which the
rules cannot. It may *drop* an approved option only with a reason that quotes the researcher's own words (at
least three words, really in the scrubbed notes) **and** names that row's item or its alternative; the code checks
both (`justified()`). Options it drops without such a quote, or silently omits, come back. Seen live with Qwen2.5 3B:
without this check it applied "reusing tubes is not acceptable" to tips and dishes, and gave invented reasons.
The UI shows what changed against the rules (`/api/plan/suggest` returns `ai`: the rules' choice, what was dropped
and why, what was kept for lack of a quote, what it skipped silently); this is not part of the SuggestionSet.
Measured on five labelled notes (`EVALUATION.md`): Claude Haiku reads them all right; the local Qwen models did not
understand them, and the check kept every option they tried to drop without a real quote.

| File | Role |
|---|---|
| `plan_engine.py` | `build_plan_suggestion_set(plan, llm=None, basis=None, muted_pairs=None)` |
| `llm/client.py` | `LLMClient` protocol, `LLMResult` (data or error, usage, latency) |
| `llm/anthropic_client.py` | Claude Haiku 5.5, effort `low`, structured outputs; key from `ANTHROPIC_API_KEY`, else the team key in `llm/team_key.py` |
| `llm/ollama_client.py` | local Qwen2.5 3B through Ollama (`format` = JSON schema, temperature 0); stdlib only |
| `llm/providers.py` | `get_llm()`: `ollama` if running, else `claude` if a key is set, else None (or `LABX_LLM`) |
| `llm/fake.py` | scripted LLM for tests; records every prompt |
| `llm/prompts.py` | versioned prompts (see `PROMPTS.md`), `scrub()` for free text, schemas |
| `llm/team_key.py` | the team's Claude key, used when `ANTHROPIC_API_KEY` is not set (private repo only: remove and revoke before sharing) |
| `llm/usage_log.py` | one line per call in `data/llm_usage_log.jsonl` (tokens, latency; no ids) |

Privacy: the prompts contain item names, quantities, requirements and the allowed options. No `plan_id`, group
or researcher id; locked lines are not sent. The researcher's title/notes are scrubbed (ids, names, e-mails,
tags) and wrapped in `<untrusted_researcher_text>`. Injection can at most make the LLM pick among the
allowed options or none, because the schema and the code accept nothing else.

```bash
python3 plan_demo.py                 # rules + templates
python3 plan_demo.py --llm ollama    # local model (ollama serve + ollama pull qwen2.5:3b); tokens logged
python3 plan_demo.py --llm claude    # uses the team key (or ANTHROPIC_API_KEY)
python3 plan_demo.py --show-prompts  # dry run: exact prompts + token estimate, no API call
python3 -m unittest tests/test_plan_engine.py -v
```

## Bookings with the LLM: `booking_ai.py`
`build_suggestion_set(..., llm=client)` uses the same pattern as plans: the rules generate and the calculator
prices every allowed move (`option_pool`: the best 2 per booking and type, max 10); the LLM picks among them by
option id (`booking-proposer-v1`); rules 4 and 8 run again on its choice; the LLM writes the text
(`booking-phraser-v2`), and any text with a number not given in the facts, a name, or a wrong length keeps the
template. If the LLM fails, `rank_proposals` and the templates run as before. Without `llm`, nothing changes.
The output's `generator` says who proposed and phrased (also for bookings now).

## Open
- Live runs: the local Qwen2.5 3B/7B and Claude Haiku 5.5 (team key); measured in `EVALUATION.md`.
- Candidate search is hour-aligned and does not know about holidays.
