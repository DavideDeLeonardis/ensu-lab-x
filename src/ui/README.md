# src/ui — interface (UI team)

Look `CONTRACT.md`:

- **Input:** `contract/examples/A1_suggestion_set_from_ai_layer.json` (real AI output for the demo request).
- **Names and times:** `data/lab_data.json` (look up `equipment_id` / `booking_id`). Never show other groups' names or researcher IDs.
- **After Accept:** new estimate = `estimate.kg` − accepted `saving_kg`.
- **Output:** one `FeedbackEvent` per action (`contract/schemas/feedback_event.schema.json`); reject = one click, reason optional.

