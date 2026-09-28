# src/ui: interface (UI team)

The booking assistant's interface. It runs in two ways:

```bash
python3 src/ui/serve.py                # LIVE: http://127.0.0.1:8000, real engine + calculator, plan and feedback saved
python3 src/ui/serve.py --reset-demo   # same, but first delete the saved plan and empty the feedback log
python3 src/ui/serve.py --placeholders # same, but the explanation panels say "to be filled in" (demo)
open src/ui/index.html                 # DEMO: plain file, the baked-in AI output for A1, nothing saved
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
| `app_template.html` | the UI (HTML + CSS + JS, one file). Edit this one |
| `build.py` | bakes a SuggestionSet + a slim lab lookup into the page → `index.html` (`--suggestions` for another file) |
| `index.html` | built output for demo mode |
| `engine.py` | live-mode glue: `price_request()`, `save_feedback()`, `load_plan()` / `save_plan()` (confirmed bookings), `reset_demo()`. Computes nothing itself; see "The JSON boundary" |
| `serve.py` | local server: `GET /`, `GET /api/health`, `GET /api/plan`, `POST /api/suggest`, `POST /api/feedback`, `POST /api/book`; `--reset-demo` |
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
