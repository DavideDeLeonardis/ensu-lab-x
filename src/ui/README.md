# src/ui: interface (UI team)

**One app, two assistants.** `serve.py` opens a start page (`home.html`) where the researcher chooses:
- **Plan an experiment** (`/plan`, `plan.html` + `plan_api.py`): the current design, consumables + equipment, AI
  optional. See "Experiment plan assistant" below.
- **Book equipment** (`/bookings`, `app_template.html`): the first prototype, described in the rest of this file.

**AI in both assistants** (live mode, if `ollama serve` runs or a Claude key is available: the team key or `ANTHROPIC_API_KEY`): the "Ask the AI" button
(plans) and a "Let the AI choose and phrase" switch next to *Check footprint* (bookings). A line above the
suggestions says whether the AI or the fixed rules chose them. Unavailable: rules + templates.

**The two pages show each other's choices** (same browser):
- *Plan → bookings*: a "From your plan" card in `/bookings` lists the plan's machine rows (read from the plan kept in
  the browser, `labx.plan.draft`) with planned vs booked hours. "Book N h" opens New booking with the device, the
  hours (one session of up to 4 h, or the whole block for a row locked by the protocol) and the first free slot in
  lab hours already filled in. An accepted swap in the plan (e.g. small workbench) shows up here as the device to book.
- *Bookings → plan*: each machine row in `/plan` shows the hours already booked (confirmed bookings, `GET /api/plan`);
  "Use N h" copies them into the plan.
- Both refresh by themselves when the other tab changes or comes back to the front.

**Plan page interaction**: the estimate and the rule-based suggestions update by themselves as you edit (instant);
"Ask the AI" lets the AI choose among the same approved swaps and write the text (~10 s). Editing the plan again goes
back to the rules. Both pages show the same "Team & lab: …" button (`LabProfile.summary`).

**Shared team profile** (`profile.js`): team name, lab and the devices the team uses, kept **only in the
browser** (`localStorage`) and shared by both pages. Change it in one page ("Your team and lab" in the plan
assistant, "Team & lab" in the booking assistant) and the other updates at once, even in another open tab. The plan
offers only the team's devices; "New booking" lists only the team's devices; a booking or plan line on a device
the team does not use is flagged, never changed silently. The team name is never sent to the server. Labs come
from `GET /api/labs` (`data/labs.json`); no profile = every device, as before. Only bookable devices are listed: always-on
infrastructure (freezers, heat block, water bath) is not part of an experiment. Both pages use the same plain-language
device names (`LabProfile.label`), with the technical name in tooltips.

```bash
python3 src/ui/serve.py                # LIVE: http://127.0.0.1:8000 → start page; real engines + calculators
python3 src/ui/serve.py --reset-demo   # same, but first delete the saved booking plan and empty the feedback log
python3 src/ui/serve.py --placeholders # same, but the booking explanation panels say "to be filled in" (demo)
open src/ui/index.html                 # DEMO: booking page as a plain file, the baked-in AI output for A1, nothing saved
```
**`--placeholders`** (also for `build.py`) keeps the four explanation panels ("What is this assistant…",
"How is this calculated?", "What wasn't touched, and why?", "What's shared if you tick this?") clickable, but
shows a "to be filled in" box saying what each will cover. Leave it off to show the full text. Flags combine:
`python3 src/ui/serve.py --reset-demo --placeholders`.

Live mode needs only the standard library (plus `jsonschema`, like the validator). The chip under the title
says which mode you're in.

The contract points from `CONTRACT.md` §5 that this follows:
- **Input:** `contract/examples/A1_suggestion_set_from_ai_layer.json` (real AI output) in demo mode;
  the engine's answer to the researcher's own request in live mode.
- **Names and times:** looked up in `data/lab_data.json`. Other groups' names and researcher IDs are removed
  by `build.py` before anything reaches the page (rule 7); a merge target shows only its time and load.
- **After Accept:** new estimate = `estimate.kg` − accepted `saving_kg` (exact: one suggestion per booking).
- **Output:** one `FeedbackEvent` per action; reject = one click, reason optional. In live mode they go through
  `append_event()` into `data/feedback_log.json`, **only if the researcher opted in** (see `docs/design-rationale.md`).
  Events carry a random request code (`REQ-8dc76040`, new for every priced request) instead of `REQ-A1-…`, and
  the date only (`YYYY-MM-DD 00:00`), so they can't be traced back to a researcher by ID or exact time.

## Where confirmed bookings are saved
**Confirm bookings** (and **Book without checking**) book the plan: in live mode it's written to
**`data/confirmed_bookings.csv`**, with the same columns as `data/bookings.csv` (`kwh` and `kg_*` priced by
`calculator.estimate()`).
- It holds the researcher's whole confirmed plan: new bookings, edits and deletions, plus the accepted and
  modified suggestions. "Ask to join" stays pending and doesn't change the booking.
- The next visit (and "Start over") opens this plan again.
- **`data/bookings.csv` is never written.** `src/lab/generate.py` regenerates it, and the calculator, the
  validator and the AI load it as the fixed demo lab. Writing into it would be wiped on the next regeneration
  and would change the demo the tests rely on.
- `--reset-demo` deletes the file, so the plan goes back to A1's demo request.

## The JSON boundary
"The CSV is for the dummy data; JSON is the interface the AI outputs and the UI takes as input." The page itself
follows that strictly:

| The page… | File / format |
|---|---|
| takes as input | a **SuggestionSet** (`A1_suggestion_set_from_ai_layer.json`, or the engine's answer in live mode) |
| looks up display data in | **`data/lab_data.json`** (device names, rooms, booking times, own group name) |
| emits | **FeedbackEvents** (schema-valid; checked with `validate.py`) and, for the engine, a **BookingRequest** (§1's booking columns as JSON) |
| never reads | any CSV (the saved plan comes through `GET /api/plan` as JSON) |

The one exception is **`engine.py`** (live mode only). It builds `Booking` objects from `bookings.csv`, calls
`build_suggestion_set`, and patches the calculator's and validator's booking tables to price new bookings.
That's AI-side work living in `src/ui/` as temporary glue. Once the AI team exposes
`suggest(BookingRequest) -> SuggestionSet`, `engine.py` shrinks to calling that plus `append_event()`.

## Files
| File | What |
|---|---|
| `home.html` | start page: choose the plan or the booking assistant |
| `plan.html` + `plan_api.py` | experiment plan assistant (`/plan`, API under `/api/plan/...`) |
| `profile.js` | shared team profile (team, lab, devices), browser only; used by both assistants |
| `app_template.html` | the booking assistant (HTML + CSS + JS, one file). Edit this one |
| `build.py` | bakes a SuggestionSet + a slim lab lookup into the page → `index.html` (`--suggestions` for another file) |
| `index.html`, `index_placeholders.html` | built booking page for demo mode (opened as a file) |
| `engine.py` | live-mode glue: `price_request()`, `save_feedback()`, `load_plan()` / `save_plan()` (confirmed bookings), `reset_demo()`. Computes nothing itself; see "The JSON boundary" |
| `serve.py` | the one server: `/`, `/plan`, `/bookings`, `/profile.js`, `GET /api/labs`, the plan API, and the booking API (`GET /api/health`, `GET /api/plan`, `POST /api/suggest`, `POST /api/feedback`, `POST /api/book`); `--reset-demo` |
| `price_request.py` | command-line pricing of a `request.json` from the page (demo-mode route) |

## Screens
1. **Plan**
   - The researcher's bookings (the last confirmed plan, if there is one). Each row has **Edit · Delete**;
     Delete can be undone. **+ New booking** or **Edit** opens a form with: device (by room),
     start/end, load % (autoclave), shelves (incubator), purpose (optional), flexibility (4 labelled
     choices; "Fixed" asks why).
   - Live availability check (never says whose booking clashes). A lab-hours note. A collapsible
     **grid curve for that day** (information, not a verdict).
   - No CO₂ number while booking: the UI never computes kg.
2. **Review**
   - Estimate as a range bar, and **How is this calculated?** (formula, the basis and type of each device
     value, sources).
   - **Where it comes from**, with the fixed 70% called out, and "What wasn't touched, and why?".
   - A note naming **muted** suggestion types.
   - ≤ 3 suggestion cards (Accept / Ask to join · Pick another time · No thanks). An accepted or re-timed
     suggestion can still be changed (**Change time**) or undone until you confirm.
   - The opt-in checkbox, with **What's shared if you tick this?** listing exactly what is sent, where it goes,
     and what is never sent.
3. **Done**: planned vs booked, what changed, whether the plan was saved, and the feedback that was saved
   (or "Nothing was shared").

## Testing
`python3 -m unittest discover tests` still passes with this folder in place. The UI was clicked through
headlessly in both modes, at desktop and phone width:
- a new booking was created and priced by the engine; the result passes `validate.py`
- three opted-in rejections of the autoclave merge went into `feedback_log.json`, and the pair was then muted
  and named in the UI
- the log was reset to `[]` afterwards

## Experiment plan assistant (`/plan`: `plan.html` + `plan_api.py`)
Served by `serve.py` (API under `/api/plan/...`, next to the booking API, which is unchanged).
- **Your team and lab**: the shared team profile above; only the team's equipment appears in the plan. Labs and their equipment come from `data/labs.json` (table `LABS` in `src/lab/generate.py`); only Lab X
  exists until real lab data is added. Not part of the contract: it only filters the page.
- **Layout**: only what the researcher acts on is open (plan, estimate, suggestions). The team profile, the
  requirement tags of each row ("Needs"), how the estimate is calculated, why a swap helps, the checks and what
  was not touched are dropdowns; each dropdown's summary already says the result (e.g. "✓ All 6 checks passed").
- **Your plan**: edit items (hover for a plain explanation), quantities, needs (`sterile`, `tc_treated`, …) and
  locked lines; starts from `data/plan_A1.json`.
- **Electricity factor** (in the Estimate card): NL grid (location, default) or TU/e's green contract (market).
- **Ask the AI + provider**: local model (if `ollama serve` is running with `qwen2.5:3b`) or Claude (if the
  server has a Claude key); otherwise only the rules. "How do I know it worked?" says who chose and wrote the
  suggestions, the prompt versions, and whether the output passed the contract check.
- **Estimate**: total range, consumables vs electricity, "How sure is this estimate?" (share of measured,
  published and assumed data, from `quality` in the API answer), main sources (locked ones marked).
- **Suggestions**: Accept (or "Accept · ask lab manager" when validation is needed) / Reject in one click;
  "after accepted changes" = `estimate.kg` − accepted `saving_kg`; "Apply accepted changes" swaps the items in
  the plan and recalculates. Once every suggestion is accepted or rejected, "Book the machines →" appears: it
  applies the accepted changes and opens the booking page, whose "From your plan" card lists the machine hours.
  It stays after "Apply accepted changes" (which recalculates and may show new suggestions); it goes away when the
  researcher edits the plan again, until the new suggestions are decided. With no suggestion at all (plan already
  optimised, or the AI left out the last swap because of the notes) the page says why and offers the button at once.
- **Notes keep counting after the AI**: the swaps the AI left out with a quote from the notes are sent back with
  every later rules-only recalculation (`note_exclusions` in `/api/plan/suggest`); the server checks each quote
  against the current notes again, so an exclusion lapses as soon as the sentence is removed. Without this, "Apply"
  brought back the glass pipettes the notes had ruled out.
- **Feedback** goes to `data/feedback_log.json` only if "Share my clicks" is ticked; events carry `item_id`, a
  random request code and the date only (same privacy choices as the booking UI).
