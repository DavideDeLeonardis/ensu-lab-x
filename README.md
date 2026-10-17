# Lab X CO₂ assistant (ENSU DD)

A prototype for TU/e's Sustainability Self-Assessment Tool. While planning an experiment, a researcher sees its
**CO₂ footprint (kg CO₂e)**, where it comes from, and **up to 3 greener swaps approved by lab experts**. The plan
then flows into equipment booking. **The researcher always decides**: nothing changes unless they accept.

An AI (Claude Haiku 5.5, or a local model) chooses among the approved swaps and writes the text. It never
produces a number: a deterministic calculator computes every kg, and code checks every answer. Lab X is a
fictional cell & tissue lab built on published data (no real TU/e data was available).

## Quick start
```bash
pip install jsonschema anthropic        # once
python3 src/ui/serve.py                 # then open http://localhost:8000
```
- **Claude** works out of the box with the team key (`src/ai/llm/team_key.py`; `ANTHROPIC_API_KEY` wins if set).
- **Local model** (optional, private, but it does not understand notes): `ollama serve` in another terminal,
  once `ollama pull qwen2.5:3b`.
- Without either, the tool runs on its fixed rules and says so.
- After changing Python code, restart `serve.py`; HTML changes only need a page reload.

## How to use it
1. **Start page → Plan an experiment.** Optionally pick your team's devices under *Your team and lab*.
2. **Your plan**: items and quantities (consumables, machine hours). Use *Needs* (e.g. `single_use_required`) and
   *Locked* (with a reason) for what the protocol fixes; the tool never touches those.
3. **Estimate**: total with a range, consumables vs electricity, *How sure is this estimate?*. Switch between the
   Dutch grid and TU/e's green contract (electricity = 0).
4. **Suggestions**: each shows the saving, what you give up and the confidence. **Accept** or **Reject** (one click,
   no reason asked).
5. **Notes for the AI** + **Ask the AI**: the AI may drop a swap only by quoting your notes (e.g. *"Glass Pasteur
   pipettes are not allowed in our hood"*); the blue box shows what it changed and why.
6. **Book the machines →** (after deciding on every suggestion): the booking page lists the plan's machine hours.
   *Book N h* opens a pre-filled booking; *Check footprint* gives booking-time suggestions; *Confirm* saves to
   `data/confirmed_bookings.csv`. Back on the plan, machines show *Booked: X h ✓*.
7. **Show design values** (or `/plan?values=1`) labels each part of the page with the ethical value it serves.

A step-by-step test with expected results: `Instruction for TOOL testing.txt`.

## How the AI is kept in check
- It only picks from `data/equivalences.csv`; invented ids are dropped.
- Every number shown comes from the calculator; text with another number is replaced by a template.
- It drops a swap only with a real quote from the researcher's notes about that item; otherwise the swap stays.
- Notes are treated as data: names and e-mails are removed, instructions in them are ignored.
- Every answer is validated against the contract (`CONTRACT.md`); if anything fails, the rules take over.

Measured on 5 labelled notes (`EVALUATION.md`): Claude read 15/15 right; the local Qwen models 0–6/15. No model
ever showed a wrong drop, an invented number or an injected claim.

## Commands
| Command | What it does |
|---|---|
| `python3 -m unittest discover -s tests` | all tests, no network |
| `python3 plan_demo.py [--llm claude] [--basis market] [--show-prompts]` | plan suggestions in the terminal |
| `python3 real_data_demo.py` | booking suggestions for the demo request |
| `python3 evaluate.py [--llm claude] [--runs 3] [--save]` | accuracy of the calculator and the AI |
| `python3 footprint.py [--log]` | the AI's own CO₂e against the savings |
| `python3 src/lab/generate.py` | rebuild `data/` after editing the data tables |

## Where things are
| Path | Content |
|---|---|
| `src/ui/` | the app: `serve.py`, `home.html`, `plan.html` (+ `plan_api.py`), `app_template.html` (bookings), `profile.js` (shared team profile, plain names) |
| `src/ai/` | `plan_engine.py` (plans), `build.py` + `booking_ai.py` (bookings), `llm/` (clients, prompts, key) |
| `src/lab/` | `plan_calculator.py`, `calculator.py` (bookings), `generate.py` (all data tables) |
| `src/contract/` | `validate.py`: checks plans and AI output against the rules |
| `data/` | generated data: consumables, equipment, swaps, factors, demo plan, bookings, `sources.csv` |
| `contract/` | JSON schemas and examples |

## Data: what is real
- **From sources**: pipette tips (Eppendorf WP114); tubes, dishes, Pasteur pipettes and 1 L flasks, single-use vs
  reused (Farley & Nicolet 2023, S1 Table); nitrile gloves (Rizan et al. 2021); most equipment power (Tran et al.
  2026, My Green Lab); Dutch grid factor (Electricity Maps) and green contract (Milieu Centraal).
- **Team estimates** (`confidence = estimate`): centrifuge, microscopes, bioreactor, fume hood, uncertainty ranges,
  and the swap list itself (a stand-in for the lab's expert panel).
- **Synthetic**: the lab, groups, bookings, hourly grid curve, demo plan quantities.
- **Missing**: culture media, serum and chemicals (no citable factor found).

Full references: `data/sources.csv`.

**Adding real data**: edit the tables in `src/lab/generate.py` (`CONSUMABLES`, `EQUIVALENCES`, `EQUIPMENT`,
`ELECTRICITY_FACTORS`, `SOURCES`), never the CSVs. Every row needs a `source` (a key in `SOURCES`), a
`confidence` (`measured`, `derived` or `estimate`) and a one-line `basis`; equipment `mode` says how energy is
counted (kW per hour, kWh per cycle, per incubator shelf, per day, or always on). Then run `python3 src/lab/generate.py` and the tests. A new
swap is offered to the AI automatically; give new items a plain name in `src/ui/profile.js`.

## More documentation
- `CONTRACT.md`: data formats and rules between calculator, AI and UI.
- `EVALUATION.md`: how accurate the estimate and the AI are, with measured results.
- `FOOTPRINT.md`: the AI's own emissions (Green Algorithms) against the savings.
- `PROMPTS.md`: every prompt sent to the AI, with its version history (report section H).

## Before sharing the repo
Remove `src/ai/llm/team_key.py`'s key and revoke it in the Anthropic console before the repo is made public or
sent outside the team.
