# Lab X: pseudo-lab for the ENSU prototype

**5ARF0 Ethics of AI · TU/e · Group ENSU DD**

Our tool estimates the CO₂ footprint of a lab experiment **when the researcher books it**, shows the main
sources of impact, and suggests up to three alternatives (reschedule, share, coordinate) without touching
the experimental design. The researcher always decides.

We don't have access to real TU/e lab data, so this repo provides **Lab X**: a fictional cell & tissue
culture lab modelled on the equipment of TU/e's
[Laboratory for Cell & Tissue Engineering](https://www.tue.nl/en/research/research-labs/laboratory-for-cell-tissue-engineering).
Equipment power figures come from published sources wherever possible; bookings and grid values are synthetic.
This matches what we promised in Phase 1: prototype on published data, not live sensor feeds.

## Quick start
```bash
open explorer/lab.html                     # interactive explorer: floor plan, calendar, grid curve, demo request
python3 src/lab/calculator.py estimate CONF-1 "2026-10-16 12:00" "2026-10-16 16:00"
python3 src/lab/calculator.py saving BK-098 "2026-10-16 12:00" "2026-10-16 16:00" --no-warmup
python3 src/lab/generate.py                # regenerate data/ and explorer/lab.html after changing a value
pip install jsonschema && python3 src/contract/validate.py contract/examples/A1_suggestion_set.json
```
Run everything from the repo root. No dependencies except Python 3.9+ (and `jsonschema` for the validator).

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
│   └── lab_data.json         everything above in one file (used by the explorer)
├── contract/                 the spec shared by AI and UI
│   ├── schemas/              suggestion_set + feedback_event JSON schemas
│   └── examples/             worked A1 output + feedback events (the gold set)
├── src/
│   ├── lab/
│   │   ├── generate.py       builds data/ and explorer/lab.html from a fixed seed
│   │   └── calculator.py     the deterministic calculator: all kg/kWh numbers come from here
│   ├── contract/
│   │   └── validate.py       checks AI output / feedback against schemas + rules
│   ├── ai/                   AI team works here
│   └── ui/                   UI team works here
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

### Data dictionary: `bookings.csv`
`movable` is one of `no`, `within day`, `±1 day`, `within week`. When it is `no`, `constraint` says why
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

| What | kg CO₂e | What the tool should do |
|---|---|---|
| Bioreactor, 96 h conditioning | 15.9 (64%) | **Nothing.** Fixed by protocol and safety. Show it as locked and explain why. |
| Confocal, Thu 19:00–23:00 | 2.7 | **Reschedule** to Fri 12:00–16:00: cleaner grid, lasers already warm → saves ≈1.9 kg (70%) |
| Autoclave, Tue 17:00, 40% load | 2.1 | **Coordinate**: another group runs a 45% load at 16:00 → merge, saves ≈2.1 kg |
| Biosafety cabinet, 5 × 3 h | 2.4 | Possible **share** candidate (smaller BSC-2) if free |
| Incubator shelves | 1.7 | **Nothing.** Continuous culture. |

The biggest source is the one the tool must *not* touch. That's the point: it respects researcher
autonomy and hard constraints (Phase 1, §3.1), and says so openly.

## Sources
- Tran, L.A. et al. (2026). Case study of low-cost energy reductions in shared research laboratories at a U.S. public university. *Frontiers in Sustainability*, 7, 1729128. https://doi.org/10.3389/frsus.2026.1729128
- My Green Lab (n.d.). *Sustainable Energy Solutions for Laboratories.* https://mygreenlab.org/resources/energy/
- Electricity Maps (2026). *Electricity Grid Review 2025: the Netherlands.* https://www.electricitymaps.com/grid-in-review-2025/the-netherlands
- TU/e (n.d.). *Laboratory for Cell & Tissue Engineering.* https://www.tue.nl/en/research/research-labs/laboratory-for-cell-tissue-engineering
- TU/e (n.d.). *Lab Sustainability Pilot.* https://www.tue.nl/en/our-university/about-the-university/sustainability/sustainability-in-research/lab-sustainability-pilot


> Equipment inventory modelled on a TU/e cell-culture lab; power figures from Tran et al. (2026) and
> My Green Lab where available, team estimates otherwise (flagged per device); hourly grid intensity
> shaped on Electricity Maps' 2025 review for the Netherlands; booking calendar synthetically generated.
