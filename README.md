# Lab X CO₂ assistant (ENSU DD, TU/e 5ARF0)

A prototype for TU/e's Sustainability Self-Assessment Tool. While planning an experiment, a researcher sees its
**CO₂ footprint (kg CO₂e)**, where it comes from, and **up to 3 greener swaps approved by lab experts**. The plan
then flows into equipment booking. **The researcher always decides**: nothing changes unless they accept.

Every number comes from a deterministic calculator (quantity × emission factor, with a range and a source). An AI
(Claude Haiku 5.5, or a local model) is optional: on request it chooses among the same approved swaps, reads the
researcher's notes and writes the text, and code checks every answer. Lab X is a fictional cell & tissue lab built
on published data; no real TU/e data was used.

## 1. Install and start
Requires Python 3.10 or newer.
```bash
git clone https://github.com/DavideDeLeonardis/ensu-lab-x.git
cd ensu-lab-x
pip install jsonschema anthropic
python3 src/ui/serve.py
```
Open **http://localhost:8000**. The tool works without any AI, using its fixed rules.

**Optional AI** (needed only for the *Ask the AI* button):
- **Claude**: set your own key before starting the server: `export ANTHROPIC_API_KEY=your-key`.
- **Local model** (private, but it did not understand notes in our tests): install [Ollama](https://ollama.com),
  run `ollama pull qwen2.5:3b` once, and keep `ollama serve` running in another terminal.

## 2. Try it in 3 minutes
1. On the start page, click **Plan an experiment**. The demo plan is loaded: one week of valve-scaffold seeding.
2. **Estimate**: about **29.1 kg CO₂e** (range 20.8–39.9). *How sure is this estimate?* shows that about half rests
   on an assumed value. Click **Green contract**: electricity drops to 0 and only the materials remain.
3. **Suggestions**: three expert-approved swaps, each with its saving, its confidence and *What you give up*.
   The locked bioreactor is never touched.
4. **The AI reads your notes** (needs Claude): write
   *Glass Pasteur pipettes are not allowed in our hood because broken glass is a safety risk.*, choose
   *Claude Haiku 5.5* and click **Ask the AI**. The blue box shows that the glass swap was left out, quoting your
   words.
5. **Decide**: **Accept** or **Reject** each card (one click, no reason asked). Then click **Book the machines →**.
6. **Booking page**: *From your plan* lists the machine hours. **Book N h** opens a pre-filled booking;
   **Check footprint** gives booking-time suggestions; **Confirm bookings** saves them.
7. Back on the plan, click **Show design values**: each part of the page is labelled with the ethical value it
   serves (human control, academic freedom, privacy, transparency, contestability, honesty about uncertainty).

To start again: **Reset to demo plan** (plan page) and **Reset to the demo request** (booking page).
A longer test with expected results: `Instruction for TOOL testing.txt`.

## 3. How the AI is kept in check
- It can only pick swaps from the expert list; invented options are dropped.
- It never writes a number: any number in its text must match the calculator, or a template is used instead.
- It may drop a swap only by quoting the researcher's own notes about that item.
- Notes are treated as data: names and e-mails are removed, instructions inside them are ignored.
- Every answer is validated; if anything fails, the fixed rules take over.

Measured on 5 labelled notes, 3 runs each (`EVALUATION.md`): Claude read 15/15 right, the local Qwen models 0–6/15,
and no model ever showed a wrong suggestion, an invented number or an injected claim.

## 4. Data
- **From published sources**: Farley & Nicolet (2023) for tubes, dishes, Pasteur pipettes and 1 L flasks;
  Eppendorf White Paper 114 for pipette tips; Rizan et al. (2021) for gloves; Tran et al. (2026) and My Green Lab
  for equipment; Electricity Maps and Milieu Centraal for electricity. Full list: `data/sources.csv`.
- **Team estimates**, marked as such in the tool: centrifuge, microscopes, bioreactor, fume hood.
- **Synthetic**: the lab, the bookings and the demo quantities.

## 5. For developers
| Command | What it does |
|---|---|
| `python3 -m unittest discover -s tests` | all tests, no network |
| `python3 plan_demo.py --show-prompts` | the exact prompts sent to the AI |
| `python3 evaluate.py [--llm claude]` | accuracy of the calculator and the AI |
| `python3 footprint.py` | the AI's own CO₂e against the savings (Green Algorithms) |
| `python3 src/lab/generate.py` | rebuild `data/` after editing the tables in that file |

More: `CONTRACT.md` (formats and rules), `PROMPTS.md` (prompts and their versions), `EVALUATION.md`,
`FOOTPRINT.md`.
