# Lab X: pseudo-lab for the ENSU prototype

**Group ENSU DD**

Our tool estimates the CO₂ footprint of a lab experiment **when the researcher books it**, shows the main
sources of impact, and suggests up to three alternatives (reschedule, share, coordinate) without touching
the experimental design. The researcher always decides.

We don't have access to real TU/e lab data, so this repo provides **Lab X**: a fictional cell & tissue
culture lab modelled on the equipment of TU/e's
[Laboratory for Cell & Tissue Engineering](https://www.tue.nl/en/research/research-labs/laboratory-for-cell-tissue-engineering).
Equipment power figures come from published sources wherever possible; bookings and grid values are synthetic.
This matches what we promised in Phase 1: prototype on published data, not live sensor feeds.

## How it fits together
```
data/ (Lab X)  ──►  src/lab/calculator.py  ──►  src/ai/ (suggestion engine)  ──►  SuggestionSet JSON  ──►  UI
                        ▲ prices every proposal                                      │
                        └──────────── feedback_log.json ◄──── FeedbackEvent ◄─────────┘
```
- **Lab**: the fictional lab's data and the deterministic calculator. All kWh / kg numbers come from here.
- **AI**: finds candidate changes, prices them with the calculator, applies the rules, keeps the top 3
  and writes the text. See [`src/ai/README.md`](src/ai/README.md).
- **Contract**: the JSON formats and rules between AI and UI ([`CONTRACT.md`](CONTRACT.md)).
  `src/contract/validate.py` enforces them; the tests run the engine and validate its output.
- **UI**: reads the SuggestionSet, sends back one FeedbackEvent per click ([`src/ui/README.md`](src/ui/README.md)).

## Quick start
Run everything from the repo root.
```bash
pip install jsonschema                     # only dependency (for the validator)
python3 -m unittest discover tests -v      # all tests; run before every push
python3 real_data_demo.py                  # AI suggestions for the demo request (A1)
python3 src/contract/validate.py contract/examples/A1_suggestion_set_from_ai_layer.json
python3 src/lab/calculator.py saving BK-098 "2026-10-16 12:00" "2026-10-16 16:00" --no-warmup
python3 src/lab/generate.py                # regenerate data/ and explorer/lab.html after changing a value
open explorer/lab.html                     # interactive explorer: floor plan, calendar, grid curve
```

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
│   └── lab_data.json         everything above in one file (used by the explorer)
├── contract/                 the spec shared by AI and UI
│   ├── schemas/              suggestion_set + feedback_event JSON schemas
│   └── examples/
│       ├── A1_suggestion_set.json                 hand-written gold set
│       ├── A1_suggestion_set_from_ai_layer.json   real AI output: the UI's input
│       └── feedback_events.json
├── src/
│   ├── lab/
│   │   ├── generate.py       builds data/ and explorer/lab.html from a fixed seed
│   │   └── calculator.py     the deterministic calculator: all kg/kWh numbers come from here
│   ├── contract/
│   │   ├── rules.py          movable windows + lab hours, shared by AI and validator
│   │   ├── validate.py       checks AI output / feedback against schemas + every checkable rule
│   │   └── feedback.py       append_event() for the UI, muted_pairs() for the AI
│   ├── ai/                   suggestion engine (see src/ai/README.md)
│   └── ui/                   UI (in progress)
├── tests/                    rule tests + the AI engine validated end-to-end
├── real_data_demo.py         runs the AI on the demo request, prints the SuggestionSet
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

## Sources
- Tran, L.A. et al. (2026). Case study of low-cost energy reductions in shared research laboratories at a U.S. public university. *Frontiers in Sustainability*, 7, 1729128. https://doi.org/10.3389/frsus.2026.1729128
- My Green Lab (n.d.). *Sustainable Energy Solutions for Laboratories.* https://mygreenlab.org/resources/energy/
- Electricity Maps (2026). *Electricity Grid Review 2025: the Netherlands.* https://www.electricitymaps.com/grid-in-review-2025/the-netherlands
- TU/e (n.d.). *Laboratory for Cell & Tissue Engineering.* https://www.tue.nl/en/research/research-labs/laboratory-for-cell-tissue-engineering
- TU/e (n.d.). *Lab Sustainability Pilot.* https://www.tue.nl/en/our-university/about-the-university/sustainability/sustainability-in-research/lab-sustainability-pilot

### Method statement for the report
> Equipment inventory modelled on a TU/e cell-culture lab; power figures from Tran et al. (2026) and
> My Green Lab where available, team estimates otherwise (flagged per device); hourly grid intensity
> shaped on Electricity Maps' 2025 review for the Netherlands; booking calendar synthetically generated.
