"""
Generate the pseudo-lab dataset for the ENSU prototype.

Lab X is a FICTIONAL cell & tissue culture lab, modelled on the equipment types
of TU/e's Laboratory for Cell & Tissue Engineering. Equipment power figures come
from published sources where available (see `source` / `confidence` columns);
the booking calendar and the hourly grid profile are synthetic.

Run (from the repo root):  python3 src/lab/generate.py
Out:  data/*.csv, data/*.json
"""

import csv
import json
import math
import random
from datetime import datetime, timedelta
from pathlib import Path

SEED = 5  # 5ARF0
random.seed(SEED)

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)

EPOCH = datetime(2026, 10, 5)  # Monday; data covers 2 weeks (5-18 Oct 2026)
DAYS = 14
HOURS = DAYS * 24


def ts(h):
    """Hours since epoch -> 'YYYY-MM-DD HH:MM'."""
    return (EPOCH + timedelta(hours=h)).strftime("%Y-%m-%d %H:%M")


# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------
SOURCES = {
    "TRAN2026": "Tran, L.A. et al. (2026). Case study of low-cost energy reductions in shared research "
                "laboratories at a U.S. public university. Frontiers in Sustainability, 7, 1729128. "
                "https://doi.org/10.3389/frsus.2026.1729128",
    "MGL": "My Green Lab (n.d.). Sustainable Energy Solutions for Laboratories. https://mygreenlab.org/resources/energy/",
    "EMAPS": "Electricity Maps (2026). Electricity Grid Review 2025: the Netherlands. "
             "https://www.electricitymaps.com/grid-in-review-2025/the-netherlands",
    "TUE_LCTE": "TU/e (n.d.). Laboratory for Cell & Tissue Engineering. "
                "https://www.tue.nl/en/research/research-labs/laboratory-for-cell-tissue-engineering",
    "TUE_PILOT": "TU/e (n.d.). Lab Sustainability Pilot. https://www.tue.nl/en/our-university/about-the-university/"
                 "sustainability/sustainability-in-research/lab-sustainability-pilot",
    "ASSUMED": "Team assumption (typical manufacturer spec class); to be replaced by a measured or datasheet value",
    "FARLEY2023": "Farley, M. & Nicolet, B.P. (2023). Re-use of laboratory utensils reduces CO2 equivalent footprint "
                  "and running costs. PLOS ONE, 18(4), e0283697. https://doi.org/10.1371/journal.pone.0283697 "
                  "(per-item values from S1 Table, based on UK government GHG conversion factors 2020). PLOS ONE added an "
                  "Editorial Note on 28 May 2026 about the peer-review process (no evidence of author involvement).",
    "EPP_WP114": "Hermuth-Kleinschmidt, K. (n.d.). Small Tips – Big Impact: The Carbon Footprint of Biobased Pipette "
                 "Tips. Eppendorf White Paper No. 114. https://explore.eppendorf.com/rs/207-WZR-206/images/"
                 "White-Paper_114_Sustainability_Small-Tips-%E2%80%93-Big-Imp_eng_1.pdf",
    "RIZAN2021": "Rizan, C. et al. (2021). Environmental impact of personal protective equipment distributed for use "
                 "by health and social care services in England in the first six months of the COVID-19 pandemic. "
                 "J R Soc Med, 114(5), 250–263. Glove figure as reported in: National Academy of Medicine (2026). "
                 "Nitrile Glove Hotspot Analysis. https://nam.edu/wp-content/uploads/2026/02/Nitrile-Glove-Hotspot-Analysis.pdf",
    "MC2024": "Milieu Centraal / CO2emissiefactoren.nl (2024). Notitie CO2-emissiefactoren elektriciteit "
              "(14 Feb 2024): direct emissions of renewable electricity are set to 0. "
              "https://co2emissiefactoren.nl/media/sources/240214-Notitie-CO2emissiefactoren-elektriciteit-pdf.pdf",
}

# ---------------------------------------------------------------------------
# Equipment
# mode: continuous (always on, not booked) | shelf (incubator shelves, booked per day)
#       day (whole-unit booking, kWh/day) | hourly (kW while in use) | cycle (kWh per cycle)
# low/high: multipliers on energy for the uncertainty range
# confidence: measured (value reported in source) | derived (calculated from a source figure) | estimate
# ---------------------------------------------------------------------------
EQUIPMENT = [
    dict(id="ULT-1", name="ULT freezer −80 °C (newer unit)", category="Cold storage", room="cold",
         mode="continuous", kwh_per_day=14.0, low=0.76, high=1.2, bookable=False, shareable=True,
         confidence="measured", source="TRAN2026",
         basis="14 kWh/day measured at −80 °C; 10.6 kWh/day at −70 °C"),
    dict(id="ULT-2", name="ULT freezer −80 °C (older unit)", category="Cold storage", room="cold",
         mode="continuous", kwh_per_day=20.0, low=0.7, high=1.4, bookable=False, shareable=True,
         confidence="estimate", source="MGL",
         basis="Older ULT units draw more; My Green Lab: 'as much energy as an average household every day'"),
    dict(id="INC-1", name="CO₂ incubator 37 °C", category="Incubation", room="culture",
         mode="shelf", kwh_per_day=2.06, shelves=4, low=0.7, high=1.6, bookable=True, shareable=True,
         confidence="derived", source="TRAN2026",
         basis="752 kWh/yr averted by powering down a 35 °C incubator → ≈2.06 kWh/day"),
    dict(id="INC-2", name="CO₂ incubator 37 °C", category="Incubation", room="culture",
         mode="shelf", kwh_per_day=2.06, shelves=4, low=0.7, high=1.6, bookable=True, shareable=True,
         confidence="derived", source="TRAN2026",
         basis="752 kWh/yr averted by powering down a 35 °C incubator → ≈2.06 kWh/day"),
    dict(id="INC-3", name="CO₂ incubator 37 °C", category="Incubation", room="culture",
         mode="shelf", kwh_per_day=2.06, shelves=4, low=0.7, high=1.6, bookable=True, shareable=True,
         confidence="derived", source="TRAN2026",
         basis="752 kWh/yr averted by powering down a 35 °C incubator → ≈2.06 kWh/day"),
    dict(id="SHK-1", name="Shaking incubator 37 °C", category="Incubation", room="culture",
         mode="day", kwh_per_day=2.47, low=0.7, high=1.5, bookable=True, shareable=False,
         confidence="derived", source="TRAN2026",
         basis="≈900 kWh/yr averted by powering down a 37 °C shaking incubator → ≈2.47 kWh/day"),
    dict(id="BSC-1", name="Biosafety cabinet class II (large, older)", category="Sterile work", room="culture",
         mode="hourly", active_kw=0.78, idle_kw=0.0, low=0.8, high=1.2, bookable=True, shareable=False,
         confidence="derived", source="TRAN2026",
         basis="18.8 kWh/day if run 24 h → 0.78 kW; assumed switched off when not booked"),
    dict(id="BSC-2", name="Biosafety cabinet class II (small)", category="Sterile work", room="culture",
         mode="hourly", active_kw=0.46, idle_kw=0.0, low=0.8, high=1.2, bookable=True, shareable=False,
         confidence="derived", source="TRAN2026",
         basis="11.1 kWh/day if run 24 h → 0.46 kW; assumed switched off when not booked"),
    dict(id="CEN-1", name="Refrigerated centrifuge", category="Sample prep", room="culture",
         mode="hourly", active_kw=1.1, idle_kw=0.25, low=0.6, high=1.4, bookable=True, shareable=True,
         confidence="estimate", source="ASSUMED",
         basis="Benchtop refrigerated centrifuge, 1.1 kW running; compressor keeps 0.25 kW idle"),
    dict(id="HB-1", name="Heat block", category="Sample prep", room="culture",
         mode="continuous", kwh_per_day=0.62, low=0.7, high=1.3, bookable=False, shareable=True,
         confidence="measured", source="TRAN2026",
         basis="0.44–0.81 kWh/day measured across 9 heat-generating devices"),
    dict(id="WB-1", name="Water bath 37 °C", category="Sample prep", room="culture",
         mode="continuous", kwh_per_day=0.23, low=0.6, high=1.6, bookable=False, shareable=True,
         confidence="derived", source="TRAN2026",
         basis="84 kWh/yr averted by powering down a 42 °C water bath → ≈0.23 kWh/day"),
    dict(id="CONF-1", name="Confocal microscope", category="Imaging", room="micro",
         mode="hourly", active_kw=1.6, idle_kw=0.1, warmup_min=30, low=0.6, high=1.5, bookable=True,
         shareable=True, confidence="estimate", source="ASSUMED",
         basis="Lasers + scan head + PC + stage incubator ≈1.6 kW; 30 min laser warm-up before each session"),
    dict(id="FLU-1", name="Widefield fluorescence microscope", category="Imaging", room="micro",
         mode="hourly", active_kw=0.35, idle_kw=0.0, low=0.6, high=1.5, bookable=True, shareable=False,
         confidence="estimate", source="ASSUMED",
         basis="Light source + camera + PC ≈0.35 kW"),
    dict(id="BIO-1", name="Bioreactor / mechanical tester", category="Tissue testing", room="testing",
         mode="hourly", active_kw=0.6, idle_kw=0.05, low=0.6, high=1.5, bookable=True, shareable=False,
         confidence="estimate", source="ASSUMED",
         basis="Cyclic loading bioreactor with actuator and heating ≈0.6 kW"),
    dict(id="AUT-1", name="Autoclave (steam-jacketed)", category="Sterilisation", room="prep",
         mode="cycle", kwh_per_cycle=6.0, idle_kw=3.38, low=0.7, high=1.4, bookable=True, shareable=True,
         confidence="derived", source="TRAN2026",
         basis="Jacket standby ≈3.4 kW (23,400 kWh/yr averted when off 79% of weekly hours); "
               "6 kWh per cycle assumed, largely independent of load"),
    dict(id="FH-1", name="Fume hood (VAV)", category="Chemical work", room="prep",
         mode="hourly", active_kw=1.5, idle_kw=0.4, low=0.5, high=2.0, bookable=True, shareable=False,
         confidence="estimate", source="MGL",
         basis="Mostly building exhaust/HVAC load; sash open ≈1.5 kW, closed ≈0.4 kW (assumed)"),
]
EQ = {e["id"]: e for e in EQUIPMENT}

ROOMS = [
    dict(id="culture", name="Cell culture room"),
    dict(id="cold", name="Cold storage"),
    dict(id="micro", name="Microscopy room"),
    dict(id="testing", name="Tissue testing area"),
    dict(id="prep", name="Prep & sterilisation"),
]

GROUPS = [
    dict(id="A", name="Heart valve TE", researchers=["A1", "A2"]),
    dict(id="B", name="Cartilage & disc", researchers=["B1", "B2"]),
    dict(id="C", name="Vascular grafts", researchers=["C1", "C2"]),
]

# ---------------------------------------------------------------------------
# Grid carbon intensity (gCO2eq/kWh), hourly, synthetic.
# Shape calibrated on Electricity Maps NL 2025: annual mean 262 g, solar trough at
# midday, evening peak around 20:00, hourly extremes 57–534 g. Autumn -> shallower
# solar trough than summer (92 g). Replace with a real export for the final demo.
# ---------------------------------------------------------------------------
AUTUMN_PROFILE = [300, 295, 290, 288, 290, 300, 315, 320, 295, 250, 205, 175,
                  160, 162, 178, 210, 262, 325, 362, 368, 352, 336, 322, 310]
# per-day wind/solar factor (lower = windier/sunnier); fixed so the demo story is stable
DAY_FACTOR = [1.02, 0.95, 1.05, 0.88, 0.92, 0.80, 0.84,   # week 1
              0.98, 1.04, 1.00, 1.08, 0.72, 0.78, 0.90]   # week 2 (Thu 15 dirty, Fri 16 windy+sunny)

grid = []
for d in range(DAYS):
    weekend = d % 7 >= 5
    for h in range(24):
        g = AUTUMN_PROFILE[h] * DAY_FACTOR[d] * (0.95 if weekend else 1.0)
        g *= 1 + random.uniform(-0.04, 0.04)
        grid.append(round(min(534, max(57, g)), 1))


def intensity_at(hour_float):
    i = int(math.floor(hour_float))
    return grid[max(0, min(HOURS - 1, i))]


# ---------------------------------------------------------------------------
# Bookings
# ---------------------------------------------------------------------------
bookings = []
occupancy = {e["id"]: [] for e in EQUIPMENT}
shelf_use = {}  # (eq, day) -> shelves used


def free(eq, s, e):
    return all(e <= a or s >= b for a, b in occupancy[eq])


def add(eq, group, researcher, s, e, purpose, movable, constraint="", load=None, shelves=None,
        scenario=False):
    occupancy[eq].append((s, e))
    bookings.append(dict(
        booking_id="", equipment_id=eq, group=group, researcher=researcher,
        start_h=s, end_h=e, start=ts(s), end=ts(e), purpose=purpose,
        movable=movable, constraint=constraint,
        load_pct=load if load is not None else "", shelves=shelves if shelves is not None else "",
        scenario=scenario))


def H(day, hh, mm=0):
    return day * 24 + hh + mm / 60


# --- Scenario: researcher A1 plans week 2 (Mon 12 - Fri 16 Oct) ---------------
SCENARIO = [
    ("BSC-1", H(7, 9), H(7, 12), "Seeding valve scaffolds", "within day", ""),
    ("BSC-1", H(8, 9), H(8, 12), "Medium change + seeding", "within day", ""),
    ("BSC-1", H(9, 9), H(9, 12), "Medium change", "within day", ""),
    ("BSC-1", H(10, 9), H(10, 12), "Medium change", "within day", ""),
    ("BSC-1", H(11, 9), H(11, 12), "Harvest for imaging", "within day", ""),
    ("INC-2", H(7, 12), HOURS, "Scaffold culture, 2 shelves",
     "no", "Continuous culture: cannot be interrupted"),
    ("BIO-1", H(7, 10), H(11, 10), "Cyclic strain conditioning (96 h)", "no",
     "Protocol timing fixed; safety interlock"),
    ("AUT-1", H(8, 17), H(8, 18, 30), "Sterilise media bottles + tools", "±1 day", ""),
    ("CEN-1", H(9, 14), H(9, 14, 30), "Cell pellet collection", "within day", ""),
    ("CONF-1", H(10, 19), H(10, 23), "Live imaging of seeded valves", "within week", ""),
]
for eq, s, e, purpose, mov, cons in SCENARIO:
    extra = {}
    if eq == "AUT-1":
        extra["load"] = 40
    if eq == "INC-2":
        extra["shelves"] = 2  # culture continues beyond the 18 Oct data window
    add(eq, "A", "A1", s, e, purpose, mov, cons, scenario=True, **extra)

# --- Hand-placed bookings that create sharing opportunities -----------------
add("AUT-1", "C", "C1", H(8, 16), H(8, 17, 30), "Sterilise glassware", "±1 day", load=45)
add("CONF-1", "B", "B2", H(11, 10), H(11, 12), "Chondrocyte imaging", "within week")
add("BIO-1", "C", "C2", H(0, 9), H(4, 9), "Graft burst-pressure conditioning (96 h)", "no",
    "Protocol timing fixed; safety interlock")
add("SHK-1", "C", "C1", H(1, 10), H(3, 16), "Bacterial pre-culture", "no", "Growth curve timing")

# --- Incubator shelves (long, non-movable) ----------------------------------
for eq, grp, res, s, e, n, purpose in [
    ("INC-1", "B", "B1", 0, HOURS, 2, "Chondrocyte pellets"),
    ("INC-1", "C", "C1", 0, H(9, 12), 1, "Endothelial cells"),
    ("INC-2", "A", "A2", 0, H(6, 12), 1, "Valve interstitial cells"),
    ("INC-3", "B", "B2", H(2, 12), HOURS, 1, "Disc explants"),
    ("INC-3", "C", "C2", 0, H(4, 12), 1, "Smooth muscle cells"),
]:
    bookings.append(dict(booking_id="", equipment_id=eq, group=grp, researcher=res,
                         start_h=s, end_h=e, start=ts(s), end=ts(e), purpose=purpose,
                         movable="no", constraint="Continuous culture: cannot be interrupted",
                         load_pct="", shelves=n, scenario=False))

# --- Random background bookings --------------------------------------------
PURPOSES = {
    "BSC": ["Passaging", "Medium change", "Seeding", "Transfection", "Harvest"],
    "CEN": ["Pellet collection", "Cell wash"],
    "CONF": ["Fixed-sample imaging", "Live imaging", "Z-stack acquisition"],
    "FLU": ["Viability staining check", "Immunostaining check"],
    "FH": ["Fixative prep", "Solvent work"],
    "AUT": ["Sterilise glassware", "Sterilise waste", "Sterilise tools"],
}


def researcher_of(g):
    return random.choice(next(x for x in GROUPS if x["id"] == g)["researchers"])


def place(eq, day, dur, window=(8.5, 18), tries=30, group=None, **kw):
    for _ in range(tries):
        start = random.choice([window[0] + 0.5 * k for k in range(int((window[1] - dur - window[0]) * 2) + 1)])
        s, e = H(day, 0) + start, H(day, 0) + start + dur
        if free(eq, s, e):
            g = group or random.choice("ABC")
            add(eq, g, researcher_of(g), s, e, random.choice(PURPOSES[eq.split("-")[0]]),
                kw.pop("movable", "within day"), **kw)
            return True
    return False


for day in range(DAYS):
    if day % 7 >= 5:
        # weekend: a few essential culture sessions only
        place("BSC-2", day, 1.5, window=(10, 14))
        continue
    for eq in ("BSC-1", "BSC-2"):
        for _ in range(random.randint(2, 3)):
            place(eq, day, random.choice([1.5, 2, 2.5, 3]))
    for _ in range(random.randint(1, 3)):
        place("CEN-1", day, 0.5)
    if random.random() < 0.55 and day != 11:  # keep Fri 16 Oct afternoon open for the scenario
        place("CONF-1", day, random.choice([2, 3, 4]), window=(9, 22), movable="within week")
    if random.random() < 0.6:
        place("FLU-1", day, random.choice([1, 1.5, 2]))
    if random.random() < 0.5:
        place("FH-1", day, random.choice([1, 2]))
    for _ in range(random.randint(1, 2)):
        load = random.choice([30, 40, 50, 60, 75, 90])
        place("AUT-1", day, 1.5, window=(8, 18), movable="±1 day", load=load)

bookings.sort(key=lambda b: (b["start_h"], b["equipment_id"]))
for i, b in enumerate(bookings, 1):
    b["booking_id"] = f"BK-{i:03d}"


# ---------------------------------------------------------------------------
# Deterministic estimate (the "calculator" the AI layer sits on top of)
# ---------------------------------------------------------------------------
def energy_profile(b):
    """Yield (hour_float, kWh) chunks in 15-min steps for a booking."""
    e = EQ[b["equipment_id"]]
    step = 0.25
    s, t = b["start_h"], b["end_h"]
    if e["mode"] == "cycle":
        per = e["kwh_per_cycle"] / ((t - s) / step)
        h = s
        while h < t - 1e-9:
            yield h, per
            h += step
        return
    if e["mode"] == "hourly":
        kw = e["active_kw"]
        s0 = s - e.get("warmup_min", 0) / 60
    elif e["mode"] == "shelf":
        kw = e["kwh_per_day"] / 24 / e["shelves"] * int(b["shelves"] or 1)
        s0 = s
    else:  # day
        kw = e["kwh_per_day"] / 24
        s0 = s
    h = s0
    while h < t - 1e-9:
        yield h, kw * step
        h += step


def estimate(b):
    e = EQ[b["equipment_id"]]
    kwh = kg = 0.0
    for h, k in energy_profile(b):
        kwh += k
        kg += k * intensity_at(h) / 1000
    return dict(kwh=round(kwh, 3), kg_typ=round(kg, 3),
                kg_low=round(kg * e["low"], 3), kg_high=round(kg * e["high"], 3))


for b in bookings:
    b.update(estimate(b))

# ---------------------------------------------------------------------------
# Experiment plans: consumables catalogue, curated equivalences, electricity factors
# (CONTRACT.md §1b). No randomness below this point is used for these tables.
#
# kg_per_unit = kg CO2e per unit NOT from electricity; kwh_per_unit = electricity per unit
# (washing/autoclaving/drying a reusable item), priced later with the chosen electricity factor.
# low/high multipliers are team estimates: ±10% for measured values, −20%/+30% for derived ones.
# ---------------------------------------------------------------------------
# Farley & Nicolet (2023), S1 Table: yearly totals (kg CO2e) and the reuse energy (kWh/yr) behind them.
# Their electricity factor (UK 2020) is taken out again, so reuse follows our electricity basis.
FARLEY_UK_KG_PER_KWH = 0.21233
FARLEY = {  # case: (uses per year, single-use kg/yr, {reuse option: kg/yr}, reuse kWh/yr)
    "tube50": (5200, 267.41157617777776, {"glass": 23.751678066911541, "pp": 21.995768429133769},
               19.547872340425531 + 49.096666666666671 + 6.7382617347120073),
    "petri6": (5200, 122.6469764, {"glass": 43.592044052492753},
               28.723404255319149 + 103.9212777777778 + 37.700415733930285),
    "pasteur": (520, 18.251536824559999, {"glass": 1.7222457774141644},
                3.6702127659574471 + 0.24548333333333333 + 1.0705056319511066),
    # sheet "Case 3-connical flasks": 1 L Erlenmeyer, 52 uses/yr; washer 2.697 + autoclave 12.274 + drying 0.787 kWh/yr
    "flask1l": (52, 26.391804926240006, {"glass": 3.8281953560715385, "pc": 3.9689854272035388},
                2.6968085106382977 + 12.274166666666668 + 0.786588920868422),
}


def farley_single_use(case):
    uses, su_kg, _, _ = FARLEY[case]
    return round(su_kg / uses, 6)


def farley_reuse(case, option):
    """(kg CO2e per use without electricity, kWh per use)."""
    uses, _, reuse, kwh = FARLEY[case]
    return round((reuse[option] - kwh * FARLEY_UK_KG_PER_KWH) / uses, 6), round(kwh / uses, 6)


DERIVED = dict(low=0.8, high=1.3, confidence="derived", source="FARLEY2023")
CONSUMABLES = [
    dict(item_id="TIP-10-F-RACK", name="Filter pipette tip 0.1–10 µL, fossil-based, in rack", kind="consumable",
         unit="piece", kg_per_unit=0.00309, kwh_per_unit=0, low=0.9, high=1.1, confidence="measured",
         source="EPP_WP114", basis="3.09 g CO2e per tip, cradle-to-gate PCF incl. rack and packaging (960-tip unit)"),
    dict(item_id="TIP-10-F-BIO-RELOAD", name="Filter pipette tip 0.1–10 µL, biobased, reload system",
         kind="consumable", unit="piece", kg_per_unit=0.00222, kwh_per_unit=0, low=0.9, high=1.1,
         confidence="measured", source="EPP_WP114",
         basis="2.22 g CO2e per tip, cradle-to-gate PCF incl. reload trays and packaging (960-tip unit)"),
    dict(item_id="TUBE-50-SU", name="Conical tube 50 mL, PP, single use", kind="consumable", unit="piece",
         kg_per_unit=farley_single_use("tube50"), kwh_per_unit=0, **DERIVED,
         basis="PP tube + PE cap production and incineration; 267.4 kg CO2e per 5200 tubes"),
    dict(item_id="TUBE-50-GLASS-REUSE", name="Conical tube 50 mL, borosilicate glass, reused (per use)",
         kind="consumable", unit="piece", **dict(zip(("kg_per_unit", "kwh_per_unit"), farley_reuse("tube50", "glass"))),
         **DERIVED, basis="Weekly reuse, 10% breakage/yr; glass + PP cap production, washer, autoclave, drying cabinet"),
    dict(item_id="TUBE-50-PP-REUSE", name="Conical tube 50 mL, PP, reused (per use)", kind="consumable",
         unit="piece", **dict(zip(("kg_per_unit", "kwh_per_unit"), farley_reuse("tube50", "pp"))), **DERIVED,
         basis="Weekly reuse of autoclavable PP tubes, 10% breakage/yr; washer, autoclave, drying cabinet"),
    dict(item_id="PETRI-6-SU", name="Petri dish 6 cm, polystyrene, single use", kind="consumable", unit="piece",
         kg_per_unit=farley_single_use("petri6"), kwh_per_unit=0, **DERIVED,
         basis="7.5 g dish production and incineration; 122.6 kg CO2e per 5200 dishes"),
    dict(item_id="PETRI-6-GLASS-REUSE", name="Petri dish 5.5 cm, borosilicate glass, reused (per use)",
         kind="consumable", unit="piece", **dict(zip(("kg_per_unit", "kwh_per_unit"), farley_reuse("petri6", "glass"))),
         **DERIVED, basis="Weekly reuse, 10% breakage/yr; washer, autoclave, drying cabinet"),
    dict(item_id="PASTEUR-SU", name="Pasteur pipette, HDPE, single use", kind="consumable", unit="piece",
         kg_per_unit=farley_single_use("pasteur"), kwh_per_unit=0, **DERIVED,
         basis="10.6 g pipette production and incineration; 18.3 kg CO2e per 520 pipettes"),
    dict(item_id="PASTEUR-GLASS-REUSE", name="Pasteur pipette, soda-lime glass, reused (per use)",
         kind="consumable", unit="piece", **dict(zip(("kg_per_unit", "kwh_per_unit"), farley_reuse("pasteur", "glass"))),
         **DERIVED, basis="Weekly reuse, 10% breakage/yr; washer, autoclave, drying cabinet"),
    dict(item_id="FLASK-1L-SU", name="Erlenmeyer flask 1 L, polycarbonate, single use", kind="consumable",
         unit="piece", kg_per_unit=farley_single_use("flask1l"), kwh_per_unit=0, **DERIVED,
         basis="154.8 g polycarbonate flask production and incineration; 26.4 kg CO2e per 52 flasks"),
    dict(item_id="FLASK-1L-GLASS-REUSE", name="Erlenmeyer flask 1 L, borosilicate glass, reused (per use)",
         kind="consumable", unit="piece", **dict(zip(("kg_per_unit", "kwh_per_unit"), farley_reuse("flask1l", "glass"))),
         **DERIVED, basis="Weekly reuse, 10% breakage/yr; 270 g glass flask, washer, autoclave, drying cabinet"),
    dict(item_id="FLASK-1L-PC-REUSE", name="Erlenmeyer flask 1 L, polycarbonate, reused (per use)", kind="consumable",
         unit="piece", **dict(zip(("kg_per_unit", "kwh_per_unit"), farley_reuse("flask1l", "pc"))), **DERIVED,
         basis="Weekly reuse of the polycarbonate flask, 10% breakage/yr; washer, autoclave, drying cabinet"),
    dict(item_id="GLOVE-NITRILE", name="Nitrile examination glove", kind="consumable", unit="piece",
         kg_per_unit=0.026, kwh_per_unit=0, low=0.9, high=1.3, confidence="derived", source="RIZAN2021",
         basis="~26 g CO2e per glove incl. incineration; manufacturer LCAs report 25–34 g"),
]

EQUIVALENCES = [
    dict(equivalence_id="EQ-001", item_id="TIP-10-F-RACK", alternative_id="TIP-10-F-BIO-RELOAD",
         type="substitute", ratio=1, incompatible_with="", requires_validation=False, needs_other_party=False,
         tradeoff="You load the tips from reload trays into a rack you keep; same tip, PCR clean and sterile.",
         curated_by="Lab X team (stand-in for the lab's expert panel)", source="EPP_WP114"),
    dict(equivalence_id="EQ-002", item_id="TUBE-50-SU", alternative_id="TUBE-50-GLASS-REUSE",
         type="substitute", ratio=1, incompatible_with="single_use_required", requires_validation=True,
         needs_other_party=False,
         tradeoff="Tubes are washed and autoclaved between uses, and glass has a lower centrifuge rating: "
                  "validate it for your protocol first.",
         curated_by="Lab X team (stand-in for the lab's expert panel)", source="FARLEY2023"),
    dict(equivalence_id="EQ-003", item_id="TUBE-50-SU", alternative_id="TUBE-50-PP-REUSE",
         type="substitute", ratio=1, incompatible_with="single_use_required", requires_validation=True,
         needs_other_party=False,
         tradeoff="Tubes are washed and autoclaved between uses: validate that reuse suits your protocol "
                  "(residues, sterility).",
         curated_by="Lab X team (stand-in for the lab's expert panel)", source="FARLEY2023"),
    dict(equivalence_id="EQ-004", item_id="PETRI-6-SU", alternative_id="PETRI-6-GLASS-REUSE",
         type="substitute", ratio=1, incompatible_with="single_use_required;tc_treated", requires_validation=True,
         needs_other_party=False,
         tradeoff="Glass dishes are not treated for adherent culture and are washed and autoclaved between uses: "
                  "validate them for your use.",
         curated_by="Lab X team (stand-in for the lab's expert panel)", source="FARLEY2023"),
    dict(equivalence_id="EQ-005", item_id="PASTEUR-SU", alternative_id="PASTEUR-GLASS-REUSE",
         type="substitute", ratio=1, incompatible_with="single_use_required", requires_validation=False,
         needs_other_party=False,
         tradeoff="Glass pipettes are washed and autoclaved between uses and can break: handle them with care.",
         curated_by="Lab X team (stand-in for the lab's expert panel)", source="FARLEY2023"),
    # Same kind of device (class II biosafety cabinet, same room), smaller and newer: 0.46 vs 0.78 kW.
    # Saves only on the location basis: with the green contract electricity counts 0, so it drops below 0.2 kg.
    dict(equivalence_id="EQ-006", item_id="BSC-1", alternative_id="BSC-2",
         type="substitute", ratio=1, incompatible_with="", requires_validation=False, needs_other_party=False,
         tradeoff="The small cabinet has less space inside: check that your work fits, and book it instead of "
                  "the large one.",
         curated_by="Lab X team (stand-in for the lab's expert panel)", source="TRAN2026"),
    # A different imaging method, not the same device: widefield instead of confocal when 2D images are enough
    # (no optical sectioning needed). Both power draws are team estimates (ASSUMED: 1.6 vs 0.35 kW), so the saving
    # carries "estimate" confidence; same hours assumed (ratio 1). Electricity only: 0 on the market basis.
    dict(equivalence_id="EQ-007", item_id="CONF-1", alternative_id="FLU-1",
         type="substitute", ratio=1, incompatible_with="", requires_validation=True, needs_other_party=False,
         tradeoff="Widefield images are less sharp in thick samples (no optical sectioning): validate that 2D "
                  "images are enough for your analysis.",
         curated_by="Lab X team (stand-in for the lab's expert panel)", source="ASSUMED"),
    # Farley & Nicolet (2023), S1 Table, sheet "Case 3-connical flasks"
    dict(equivalence_id="EQ-008", item_id="FLASK-1L-SU", alternative_id="FLASK-1L-GLASS-REUSE",
         type="substitute", ratio=1, incompatible_with="single_use_required", requires_validation=True,
         needs_other_party=False,
         tradeoff="Flasks are washed and autoclaved between uses: validate that detergent residues do not affect "
                  "your culture.",
         curated_by="Lab X team (stand-in for the lab's expert panel)", source="FARLEY2023"),
    dict(equivalence_id="EQ-009", item_id="FLASK-1L-SU", alternative_id="FLASK-1L-PC-REUSE",
         type="substitute", ratio=1, incompatible_with="single_use_required", requires_validation=True,
         needs_other_party=False,
         tradeoff="The same plastic flask is washed and autoclaved between uses: validate that reuse suits your "
                  "culture (residues, sterility).",
         curated_by="Lab X team (stand-in for the lab's expert panel)", source="FARLEY2023"),
]

ELECTRICITY_FACTORS = [
    dict(basis="location", g_per_kwh=262.2, source="EMAPS",
         basis_note="NL 2025 annual mean, flow-traced (Electricity Maps); default"),
    dict(basis="market", g_per_kwh=0.0, source="MC2024",
         basis_note="TU/e green electricity contract: direct emissions 0 (NL method); upstream emissions not counted"),
]

# Labs a team can choose in the plan UI, with the equipment each one has (curated by the lab manager).
# Only Lab X exists for now: a new lab is added here once its real equipment data (with sources) is available.
# Not part of the contract: the UI uses it to filter which equipment a team can put in a plan.
LABS = [
    dict(lab_id="LABX", name="Lab X: cell & tissue culture (fictional)", based_on="TUE_LCTE",
         note="Modelled on TU/e's Laboratory for Cell & Tissue Engineering",
         rooms=[r["id"] for r in ROOMS],
         equipment=[e["id"] for e in EQUIPMENT]),
]

# Demo plan for researcher A1 (no researcher or group id inside: privacy). Quantities are
# SYNTHETIC team assumptions for one week of valve scaffold seeding.
PLAN_A1 = dict(
    plan_id="PLAN-2026-0042",
    title="Valve scaffold seeding, week 42",
    notes="Cells are sensitive to serum lot changes.",
    lines=[
        dict(line_id="L1", item_id="TIP-10-F-RACK", quantity=960, unit="piece", requirements=["sterile"]),
        dict(line_id="L2", item_id="TUBE-50-SU", quantity=40, unit="piece", requirements=["sterile"]),
        dict(line_id="L3", item_id="PETRI-6-SU", quantity=30, unit="piece", requirements=["sterile"]),
        dict(line_id="L4", item_id="PETRI-6-SU", quantity=20, unit="piece", requirements=["sterile", "tc_treated"]),
        dict(line_id="L5", item_id="PASTEUR-SU", quantity=60, unit="piece", requirements=["sterile"]),
        dict(line_id="L6", item_id="GLOVE-NITRILE", quantity=100, unit="piece"),
        dict(line_id="L7", item_id="BSC-1", quantity=15, unit="h"),
        dict(line_id="L8", item_id="BIO-1", quantity=96, unit="h", locked=True,
             lock_reason="Protocol timing fixed; safety interlock"),
    ],   # two machines only: one with an expert swap (L7), one locked by protocol (L8)
)


# ---------------------------------------------------------------------------
# Write CSVs
# ---------------------------------------------------------------------------
eq_cols = ["id", "name", "category", "room", "mode", "active_kw", "idle_kw", "kwh_per_day",
           "kwh_per_cycle", "shelves", "warmup_min", "low", "high", "bookable", "shareable",
           "confidence", "source", "basis"]
with open(DATA / "equipment.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=eq_cols)
    w.writeheader()
    for e in EQUIPMENT:
        w.writerow({k: e.get(k, "") for k in eq_cols})

bk_cols = ["booking_id", "equipment_id", "group", "researcher", "start", "end", "purpose", "movable",
           "constraint", "load_pct", "shelves", "scenario", "kwh", "kg_low", "kg_typ", "kg_high"]
with open(DATA / "bookings.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=bk_cols)
    w.writeheader()
    for b in bookings:
        w.writerow({k: b[k] for k in bk_cols})

with open(DATA / "scenario_request.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=bk_cols)
    w.writeheader()
    for b in bookings:
        if b["scenario"]:
            w.writerow({k: b[k] for k in bk_cols})

with open(DATA / "grid_intensity.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["timestamp", "gco2_per_kwh"])
    for h, g in enumerate(grid):
        w.writerow([ts(h), g])

with open(DATA / "sources.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["key", "reference"])
    for k, v in SOURCES.items():
        w.writerow([k, v])

for name, rows in (("consumables", CONSUMABLES), ("equivalences", EQUIVALENCES),
                   ("electricity_factors", ELECTRICITY_FACTORS)):
    with open(DATA / f"{name}.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
(DATA / "plan_A1.json").write_text(json.dumps(PLAN_A1, ensure_ascii=False, indent=2) + "\n")
(DATA / "labs.json").write_text(json.dumps(LABS, ensure_ascii=False, indent=2) + "\n")

payload = dict(epoch=EPOCH.strftime("%Y-%m-%d"), days=DAYS, grid=grid, equipment=EQUIPMENT,
               rooms=ROOMS, groups=GROUPS, bookings=bookings, sources=SOURCES,
               consumables=CONSUMABLES, equivalences=EQUIVALENCES)
(DATA / "lab_data.json").write_text(json.dumps(payload, ensure_ascii=False, indent=1))

scen = [b for b in bookings if b["scenario"]]
print(f"{len(bookings)} bookings ({len(scen)} in scenario), grid mean {sum(grid)/len(grid):.0f} g/kWh")
print(f"Scenario total: {sum(b['kwh'] for b in scen):.1f} kWh, "
      f"{sum(b['kg_low'] for b in scen):.2f}–{sum(b['kg_high'] for b in scen):.2f} kg CO2e "
      f"(typ {sum(b['kg_typ'] for b in scen):.2f})")
for b in scen:
    print(f"  {b['equipment_id']:7} {b['start']} → {b['end']}  {b['kwh']:7.2f} kWh  {b['kg_typ']:6.2f} kg")
