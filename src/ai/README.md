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

## Open
- `llm_phraser` is a stub. The template texts are already concrete, so an LLM is optional; if added,
  fall back to `template_phraser` whenever its output fails `validate.py`.
- Candidate search is hour-aligned and does not know about holidays.
