# src/ai — suggestion engine

## Design

```
candidates.py   deterministic search: "what could this booking change to?"
      │         (no LLM, no calculator numbers)
      ▼
ranking.py      calls calculator.saving() for every candidate's real saving,
      │         applies Rules 1/4/7/8/9, keeps top 3 biggest-saving-first
      │         (no LLM)
      ▼
phrasing.py     writes headline / why / tradeoff for an ALREADY-DECIDED
      │         proposal (the only file that may call an LLM)
      ▼
build.py        assembles the SuggestionSet dict
```

## Status: fully validated end-to-end against the real pipeline

All four `data/` files (bookings.csv, equipment.csv, grid_intensity.csv,
scenario_request.csv) and the real `src/lab/calculator.py` now exist.
`real_data_demo.py` runs the complete real pipeline -- real calculator,
real equipment, real grid intensity, real bookings, zero approximation
anywhere -- and reproduces the README's own hand-written demo story
independently:

```
S1  coordinate  BK-078 -> merge into BK-075   saving 2.052 kg  (100%)
S2  reschedule  BK-098 -> 2026-10-16 12:00    saving 1.925 kg  (70.2%)
```

The reschedule result lands on the exact day and time the README
describes ("reschedule to Fri 12:00-16:00 ... saves ~1.9 kg (70%)"), and
the warm-up-skip logic correctly found that `BK-102` (a different, real
booking) ends at exactly `2026-10-16 12:00` on the same equipment, so
`warmup=False` was applied automatically -- matching the README's own
"lasers already warm" reasoning, not something hard-coded to match it.

`python3 -m unittest tests/test_build.py -v` still passes all 8
rule/regression tests with the real calculator wired in (via
`calculator_adapter.RealCalculator`, swapped in for the mocks).

`mock_calculator.py` is not needed for the real demo, but is kept for the
unit tests in `tests/test_build.py`, which run without the data files.

## equipment.csv corrections (both confirmed against the real 16-row file)

1. `shareable` is NOT the substitutability signal for "share" suggestions
   -- both `BSC-1` and `BSC-2` are `shareable=False`, yet they're
   `CONTRACT.md`'s own worked example. Still worth confirming what
   `shareable` *does* mean with Davide directly.
2. `category`+`room`+`mode` alone is too coarse -- `CONF-1` (confocal) and
   `FLU-1` (widefield) share all three but are different imaging
   techniques. Fixed by also matching equipment `name` with a trailing
   parenthetical qualifier stripped. See `candidates.derive_alternates()`
   and the two regression tests in `tests/test_build.py`.

## Resolved (contract fixes)

- `shareable` = the device serves several groups at once; NOT interchangeable units (README data dictionary).
- Feedback history for rule 9 lives in `data/feedback_log.json`; `real_data_demo.py` passes
  `src.contract.feedback.muted_pairs()` into the engine.
- Movable windows and lab hours come from `src/contract/rules.py`, shared with the validator:
  reschedules are proposed only Mon–Fri 08:00–20:00, inside the contract's window definitions.
- Coordinate candidates use `mode == "cycle"` from equipment.csv and must fit the booking's own window.
- Warm-up is no longer skipped because of the booking's own (moved) original slot.
- `estimate.hotspots` is aggregated per device, max 4.
- `tests/test_contract.py` runs this engine on the A1 request and validates the output.

## Known gaps

- `llm_phraser` is still a stub (`NotImplementedError`). `template_phraser` now writes concrete texts from
  calculator output + data files (grid g/kWh before/after, "17 hours later than planned", "ready by 16:00"),
  so an LLM is optional polish, not required for the demo.
