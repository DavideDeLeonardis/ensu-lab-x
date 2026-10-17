# Lab X: pseudo-lab for the ENSU prototype

**Group ENSU DD**

Our tool estimates the CO₂ footprint (kg CO₂e) of a lab experiment, shows the main sources of impact, and
suggests up to three alternatives without touching the experimental design. The researcher always decides.

It exists in two versions, sharing the same contract, calculator principles and safeguards:
- **Experiment plans (current design)**: while planning, inside TU/e's Sustainability Self-Assessment Tool. The
  plan lists quantities of consumables and equipment hours; suggestions are curated substitutes (e.g. reusable
  glassware, biobased tips). **An LLM proposes and phrases, the calculator counts every number, the rules and the
  validator filter, the researcher decides.** See [Experiment plans](#experiment-plans-planning-stage-design).
- **Bookings (first prototype)**: when the researcher books equipment; suggestions move, share or batch
  sessions towards cleaner grid hours. The same optional LLM picks among the moves the rules allow.

We pivoted after TU/e's Lab Sustainability Pilot told us that TU/e buys green electricity, that lab emissions
come mostly from consumables (scope 3), and that many researchers don't use a booking system.

We don't have access to real TU/e lab data, so this repo provides **Lab X**: a fictional cell & tissue
culture lab modelled on the equipment of TU/e's
[Laboratory for Cell & Tissue Engineering](https://www.tue.nl/en/research/research-labs/laboratory-for-cell-tissue-engineering).
Equipment power figures come from published sources wherever possible; bookings and grid values are synthetic.
This matches what we promised in Phase 1: prototype on published data, not live sensor feeds.

## How it fits together
```
data/ (Lab X)  ──►  src/lab/calculator.py        ──►  src/ai/build.py        ──►  SuggestionSet JSON  ──►  UI
                    src/lab/plan_calculator.py   ──►  src/ai/plan_engine.py  ─┘        │
                        ▲ prices every proposal        (LLM: Claude Haiku 5.5)          │
                        └──────────── feedback_log.json ◄──── FeedbackEvent ◄──────────┘
```
- **Lab**: the fictional lab's data and the two deterministic calculators. All kWh / kg numbers come from here.
- **AI**: finds candidate changes, prices them with the calculator, applies the rules, keeps the top 3
  and writes the text. In both assistants an optional LLM picks among the allowed options and writes the text,
  with rules and templates as fallback. See [`src/ai/README.md`](src/ai/README.md) and [`PROMPTS.md`](PROMPTS.md).
- **Contract**: the JSON formats and rules between AI and UI ([`CONTRACT.md`](CONTRACT.md)).
  `src/contract/validate.py` enforces them; the tests run the engine and validate its output.
- **UI**: reads the SuggestionSet, sends back one FeedbackEvent per click ([`src/ui/README.md`](src/ui/README.md)).

## Quick start
Run everything from the repo root.
```bash
pip install jsonschema                     # needed (validator)
python3 src/ui/serve.py                    # the app: http://127.0.0.1:8000 (start page → plan or bookings)
ollama serve                               # optional, own terminal: the local AI (once: ollama pull qwen2.5:3b)
python3 -m unittest discover tests -v      # all tests, no network; run before every push
```
Command-line demos:
```bash
python3 plan_demo.py [--llm [ollama|claude]] [--basis market]   # plan suggestions (rules, or the AI)
python3 plan_demo.py --show-prompts                              # the exact prompts + token estimate
python3 real_data_demo.py                                        # booking suggestions for A1's request (rules)
python3 src/lab/plan_calculator.py estimate data/plan_A1.json    # plan estimate only
python3 src/contract/validate.py data/plan_A1.json               # check an ExperimentPlan
python3 src/contract/validate.py contract/examples/A1_plan_suggestion_set.json --plan data/plan_A1.json
python3 footprint.py                                             # the AI's own CO₂e vs the savings
python3 evaluate.py [--llm ollama --model qwen2.5:7b]            # how accurate are the numbers and the AI
python3 src/lab/generate.py                                      # regenerate data/ after changing a value
```
Optional: `pip install anthropic` for the Claude provider (it uses the team key in `src/ai/llm/team_key.py`, or
`ANTHROPIC_API_KEY` if set; remove the key before the repo is made public); `open explorer/lab.html` for the
interactive view of the lab.

## What's in here
```
ensu-lab-x/
├── README.md
├── CONTRACT.md               ← read this if you work on the AI or the UI
├── data/                     generated pseudo-lab data (don't edit by hand)
│   ├── equipment.csv         16 devices: power/energy, uncertainty, confidence, source, basis
│   ├── bookings.csv          110 bookings, 5–18 Oct 2026, 3 groups, with movable + constraint
│   ├── scenario_request.csv  the demo case: researcher A1's request for 12–16 Oct
│   ├── grid_intensity.csv    hourly gCO₂e/kWh
│   ├── sources.csv
│   ├── feedback_log.json     FeedbackEvents written by the UI, read by the AI for muting (rule 9)
│   ├── consumables.csv       plan catalogue: kg CO₂e and kWh per unit, range, confidence, source
│   ├── equivalences.csv      curated substitutes (the only allowed suggestions for plans)
│   ├── electricity_factors.csv  location (NL grid) and market (green contract) factors
│   ├── plan_A1.json          the demo experiment plan (ExperimentPlan)
│   ├── labs.json             labs a team can choose, with their devices (UI only)
│   ├── lab_data.json         everything above in one file (used by the explorer)
│   └── evaluation/           measured accuracy runs, one JSON per model and prompt version
├── contract/                 the spec shared by AI and UI
│   ├── schemas/              suggestion_set + feedback_event + experiment_plan JSON schemas
│   └── examples/
│       ├── A1_suggestion_set.json                 hand-written gold set
│       ├── A1_suggestion_set_from_ai_layer.json   real AI output: the UI's input
│       ├── A1_plan_suggestion_set.json            plan engine output for data/plan_A1.json
│       └── feedback_events.json
├── src/
│   ├── lab/
│   │   ├── generate.py       builds data/ and explorer/lab.html from a fixed seed
│   │   ├── calculator.py     the deterministic calculator for bookings
│   │   └── plan_calculator.py the deterministic calculator for experiment plans
│   ├── contract/
│   │   ├── rules.py          movable windows + lab hours, shared by AI and validator
│   │   ├── validate.py       checks AI output / feedback against schemas + every checkable rule
│   │   └── feedback.py       append_event() for the UI, muted_pairs() for the AI
│   ├── ai/                   suggestion engine (see src/ai/README.md)
│   └── ui/                   the app: start page, plan and booking assistants (see src/ui/README.md)
├── tests/                    rule tests + the AI engine validated end-to-end
├── real_data_demo.py         runs the AI on the demo request, prints the SuggestionSet
├── plan_demo.py              runs the plan engine on data/plan_A1.json (--llm for the AI)
├── PROMPTS.md                the LLM prompts and their versions
├── FOOTPRINT.md              the LLM's own CO₂e vs the savings
├── footprint.py              recomputes FOOTPRINT.md's numbers (from the token log if present)
├── EVALUATION.md             accuracy of the calculator and of the AI, with measured results
├── evaluate.py               recomputes EVALUATION.md's numbers (results in data/evaluation/)
└── explorer/
    ├── lab.html              interactive view of the lab
    └── lab_template.html
```

## The lab
Five rooms: cell culture, cold storage, microscopy, tissue testing, prep & sterilisation. Three groups:
**Heart valve TE** (A), **Cartilage & disc** (B), **Vascular grafts** (C). Researchers are pseudonyms (A1, B2…).

### Data dictionary: `equipment.csv`
| Column | Meaning |
|---|---|
| `mode` | how energy is counted: `hourly` (kW while booked) · `cycle` (kWh per run) · `shelf` (share of an incubator's daily kWh) · `day` · `continuous` (always on, not bookable) |
| `active_kw`, `idle_kw`, `kwh_per_day`, `kwh_per_cycle` | energy parameters for that mode |
| `warmup_min` | extra minutes counted before each session (confocal lasers) |
| `low`, `high` | multipliers giving the uncertainty range |
| `confidence` | `measured` (value in the source) · `derived` (calculated from a source figure) · `estimate` (team assumption) |
| `basis` | one line explaining the number |
| `shelves` | shelf count of an incubator (`shelf` mode only) |
| `bookable` | can be reserved in the booking system (freezers, heat block, water bath are always on) |
| `shareable` | can serve several groups **at the same time** (incubator shelves, a shared autoclave cycle, back-to-back confocal sessions). It does **not** mean two units are interchangeable: for `share` suggestions, match devices of the same kind |

### Data dictionary: `bookings.csv`
`movable` is one of `no`, `within day`, `±1 day`, `within week` (exact definitions in `CONTRACT.md`, rule 3). When it is `no`, `constraint` says why
(continuous culture, protocol timing, safety). `kwh`, `kg_low`, `kg_typ`, `kg_high` are precomputed by the calculator.

## How the estimate works
For each booking, in 15-minute steps: **energy of the device × grid intensity at that hour**, summed.
The range applies the device's `low`/`high` factors.
- Confocal sessions include a 30-min laser warm-up (skipped if it directly follows another session).
- Autoclave cycles cost 6 kWh regardless of load, which is why merging half-empty cycles helps.
- Incubator shelves carry their pro-rata share of the unit's daily energy.

## What is real and what is synthetic
| Real (from sources) | Team estimates (replace with datasheets) | Synthetic |
|---|---|---|
| ULT freezers, CO₂ & shaking incubators, biosafety cabinets, autoclave standby, heat block, water bath (Tran et al., 2026; My Green Lab) · shape of the NL grid curve (Electricity Maps, 2025 review) | centrifuge, confocal, fluorescence microscope, bioreactor, fume hood, autoclave kWh/cycle | the lab, groups, researchers, all bookings, hourly grid values |

Before the final demo, replace `grid_intensity.csv` with a real hourly export for the Netherlands.

## The demo story (A1's request, 12–16 Oct)
Total ≈ **24.9 kg CO₂e** (range 15.8–36.6), 89.8 kWh.

| What | kg CO₂e | What the AI returns (`python3 real_data_demo.py`) |
|---|---|---|
| Bioreactor, 96 h conditioning | 15.9 (64%) | **Suppressed**: fixed by protocol and safety; shown as locked with the reason |
| Confocal, Thu 19:00–23:00 | 2.7 | **Reschedule** to Fri 12:00–16:00: grid ~128 vs ~381 g/kWh, lasers already warm → −1.9 kg (70%); trade-off "17 hours later than planned" |
| Autoclave, Tue 17:00, 40% load | 2.1 | **Coordinate**: join another group's 45% cycle at 16:00 → −2.1 kg; needs their OK, items ready by 16:00 |
| Biosafety cabinet, 5 × 3 h | 2.4 | No suggestion: BSC-2 is booked at all five times, and moving within the day saves < 0.1 kg (below the 0.2 kg threshold, rule 8) |
| Incubator shelves | 1.7 | **Suppressed**: continuous culture |

Result: 2 suggestions, −4.0 kg together (≈16%); 17.6 kg (71%) is locked by constraints.

The biggest source is the one the tool must *not* touch. That's the point: it respects researcher
autonomy and hard constraints (Phase 1, §3.1), and says so openly.

## Experiment plans (planning-stage design)
Feedback from TU/e's Lab Sustainability Pilot: TU/e buys green electricity, lab emissions come mostly from
consumables (scope 3), and many researchers don't book equipment. So the tool also works on an
**experiment plan**: a list of quantities (consumables and equipment hours) entered while planning, inside the
Sustainability Self-Assessment Tool. Each line costs **quantity × emission factor**; suggestions can only come
from `data/equivalences.csv` (curated substitutes). Format and rules: `CONTRACT.md` §1b and §3b.

The metric is always kg CO₂e. Electricity is priced with a factor chosen by `LABX_ELECTRICITY_BASIS`:
`location` (default, NL grid 2025 mean 262.2 g/kWh) or `market` (green contract, 0 g/kWh direct emissions).

### Data dictionary: `consumables.csv`
| Column | Meaning |
|---|---|
| `kg_per_unit` | kg CO₂e per unit that is not electricity (production, packaging, disposal) |
| `kwh_per_unit` | electricity per unit, e.g. washing and autoclaving a reusable item; priced with the electricity factor |
| `low`, `high` | range multipliers (team estimates: ±10% for measured, −20%/+30% for derived values) |
| `confidence`, `source`, `basis` | as in `equipment.csv` |

For reusable items, Farley & Nicolet's per-use totals are split into a non-electric part and kWh per use (their
UK 2020 electricity factor taken out), so reuse follows our electricity basis.

### The demo plan (`data/plan_A1.json`, one week of valve scaffold seeding)
`python3 src/lab/plan_calculator.py estimate data/plan_A1.json`

| Basis | Total kg CO₂e (range) | Consumables | Electricity |
|---|---|---|---|
| `location` | 29.1 (20.8–39.9) | 10.9 | 18.2 (the locked bioreactor alone: 15.1) |
| `market` | 10.9 (9.3–13.6) | 10.9 | 0 |

Curated savings available (location basis): tips → biobased reload −0.84 kg; 50 mL tubes → reused glass or PP
−1.85 / −1.86 kg (need validation); 6 cm dishes for scaffold handling → reused glass −0.41 kg; Pasteur pipettes
→ reused glass −1.88 kg; large → small clean workbench (BSC-1 → BSC-2) −1.26 kg, electricity only, so 0 with
the green contract. The 20 dishes for adherent culture (`tc_treated`) cannot switch to glass, and
gloves have no curated alternative.

**Data gap, stated openly:** culture media, serum (FBS) and chemicals are not in the catalogue yet: we found
no citable per-litre factor. With them, consumables would weigh more than shown here.

### Status of the LLM part
Two interchangeable providers behind the same interface (`src/ai/llm/`), with the same prompts and safeguards:

| Provider | Model | Status |
|---|---|---|
| **Local (Ollama)** | Qwen2.5 3B (7B also tested), temperature 0 | **Used live**: valid output and good card texts, ~11 s per plan; nothing leaves the laptop. It does **not** understand the researcher's notes (0 of 15 in `EVALUATION.md`), so its choice equals the rules' |
| **Claude API** | Claude Haiku 5.5, effort `low` | **Used live** with the team key (`src/ai/llm/team_key.py`): ~7 s per plan, read 15 of 15 test notes right, 0 errors shown; the plan text (without names) goes to Anthropic |

The LLM is used by **both assistants**: plans (choose among curated swaps, write the cards) and bookings (choose among
the moves the rules allow, write the cards). Live run on the A1 booking request: 1 proposer + 2 phraser calls, ~7 s, valid output.

Without any LLM the tool runs with rules and templates, and the output says so (`generator`).
The live runs and the evaluation led to several prompt revisions (now `proposer-v4` / `phraser-v4`, history in
`PROMPTS.md`) and new code guards: for example, a text that states the saving "per use" or "per piece" is rejected,
because the saving is for the whole line. How well each model does is measured in `EVALUATION.md`.
Token counts per call are logged in `data/llm_usage_log.jsonl` (local, not committed), the input for the
Green Algorithms estimate (`FOOTPRINT.md`).

To use the local model:
```bash
brew install ollama          # once
ollama serve                 # in its own terminal, keep it running
ollama pull qwen2.5:3b       # once, about 1.9 GB
python3 plan_demo.py --llm ollama
```

### Replacing the synthetic data with real data
All plan data live in **`src/lab/generate.py`** (tables `CONSUMABLES`, `EQUIVALENCES`, `ELECTRICITY_FACTORS`,
`EQUIPMENT`, `SOURCES`, `PLAN_A1`). Edit them there, never the CSVs: `generate.py` rewrites `data/`.

| You get… | Change | Then |
|---|---|---|
| a real emission factor (LCA, supplier PCF) | its row in `CONSUMABLES`: `kg_per_unit`, `kwh_per_unit`, `low`/`high`, `confidence`, `source` (+ the reference in `SOURCES`) | every estimate and saving using it changes |
| a new item (e.g. culture medium, once a factor is found) | a new row in `CONSUMABLES` | it can appear in plans; no suggestion until an equivalence exists |
| an expert-approved swap | a new row in `EQUIVALENCES` (`EQ-###`, item → alternative, `ratio`, `incompatible_with`, `requires_validation`, `needs_other_party`, `tradeoff`, `curated_by` as a role) | the AI sees it as an option automatically; the validator accepts it |
| the official electricity factor / TU/e contract data | `ELECTRICITY_FACTORS` | all electricity lines change; savings that are electricity only may cross the 0.2 kg threshold |
| real experiment plans | an `ExperimentPlan` JSON (`CONTRACT.md` §1b), e.g. exported from the Self-Assessment Tool | `python3 src/contract/validate.py plan.json`, then the UI or the engine |

Then run, in this order:
```bash
python3 src/lab/generate.py                 # rewrites data/ from the tables
python3 -m unittest discover tests          # contract and safety tests must stay green
python3 plan_demo.py --save                 # refresh the example output for the UI team
```
What happens automatically: the calculator prices the new values, the allowed options sent to the AI are rebuilt
from `EQUIVALENCES` (no prompt change needed), and the validator re-checks every number and pair.
What needs a hand: plain-language names for new items in `PLAIN` in `src/ui/plan.html` (otherwise the technical
name is shown), and the few tests that pin demo numbers (`tests/test_plan_calculator.py`, the id lists in
`tests/test_plan_engine.py`). The rule and safety tests do not depend on the values.

### What is real and what is synthetic (plans)
| Real (from sources) | Team estimates | Synthetic |
|---|---|---|
| tip PCFs (Eppendorf WP114), tubes / dishes / Pasteur pipettes / 1 L flasks single-use and reuse (Farley & Nicolet 2023, S1 Table), nitrile glove (Rizan et al. 2021), NL electricity factors | range multipliers, the curated equivalence list (stand-in for the lab's expert panel), microscope power draws (confocal → widefield swap, `estimate`) | the quantities in the A1 plan |

Searched but not added (no verified per-item value): other pipette-tip sizes (Eppendorf WP114 gives only the 0.1–10 µL filter tip; no other per-tip figure found) and Drosophila vials (Farley & Nicolet's own sheet says "ignore for now", and Lab X does not use them).

## Sources
- Tran, L.A. et al. (2026). Case study of low-cost energy reductions in shared research laboratories at a U.S. public university. *Frontiers in Sustainability*, 7, 1729128. https://doi.org/10.3389/frsus.2026.1729128
- My Green Lab (n.d.). *Sustainable Energy Solutions for Laboratories.* https://mygreenlab.org/resources/energy/
- Electricity Maps (2026). *Electricity Grid Review 2025: the Netherlands.* https://www.electricitymaps.com/grid-in-review-2025/the-netherlands
- TU/e (n.d.). *Laboratory for Cell & Tissue Engineering.* https://www.tue.nl/en/research/research-labs/laboratory-for-cell-tissue-engineering
- Farley, M. & Nicolet, B.P. (2023). Re-use of laboratory utensils reduces CO2 equivalent footprint and running costs. *PLOS ONE*, 18(4), e0283697. https://doi.org/10.1371/journal.pone.0283697 (PLOS ONE added an Editorial Note on 28 May 2026 about the peer-review process, with no evidence of author involvement)
- Hermuth-Kleinschmidt, K. (n.d.). *Small Tips – Big Impact: The Carbon Footprint of Biobased Pipette Tips.* Eppendorf White Paper No. 114.
- Rizan, C. et al. (2021). Environmental impact of personal protective equipment distributed for use by health and social care services in England in the first six months of the COVID-19 pandemic. *J R Soc Med*, 114(5), 250–263 (glove figure via the National Academy of Medicine's Nitrile Glove Hotspot Analysis, 2026).
- Milieu Centraal / CO2emissiefactoren.nl (2024). *Notitie CO2-emissiefactoren elektriciteit.*
- TU/e (n.d.). *Lab Sustainability Pilot.* https://www.tue.nl/en/our-university/about-the-university/sustainability/sustainability-in-research/lab-sustainability-pilot

### Method statement for the report
> Equipment inventory modelled on a TU/e cell-culture lab; power figures from Tran et al. (2026) and
> My Green Lab where available, team estimates otherwise (flagged per device); hourly grid intensity
> shaped on Electricity Maps' 2025 review for the Netherlands; booking calendar synthetically generated.
