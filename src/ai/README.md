# src/ai — AI layer (AI team)

Put the suggestion engine here. It reads a booking request (`data/scenario_request.csv`), prices every
candidate change with `src/lab/calculator.py`, and returns a `SuggestionSet` as defined in `CONTRACT.md`.

Suggested layout:
- `candidates.py`: generate reschedule / share / coordinate candidates in code, priced by the calculator
- `explain.py` or `prompt.md`: the LLM step (fills `headline`, `why`, `tradeoff` only), or the prompt for the custom GPT / Claude Project
- `outputs/`: saved `SuggestionSet` JSON files, each checked with `python3 src/contract/validate.py <file>`
