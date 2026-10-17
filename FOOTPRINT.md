# Footprint paradox: what the tool's own LLM use costs

A tool that cuts lab emissions with an LLM also emits through the LLM. This file estimates that cost per plan
and per year, compares it with what the suggestions can save, and gives the break-even. Recompute it with
`python3 footprint.py` (estimate) or `python3 footprint.py --log` (measured tokens and runtimes from the usage log).

**Status.** The Claude figures below are an **estimate** made before the first real call: the output tokens were
estimated from the prompts, the schemas and `max_tokens`. **Update 2026-10-16:** the evaluation (`EVALUATION.md`)
measured Claude Haiku 5.5's output tokens on 15 plan runs: **693 per plan run** with the current prompts (752 with
`v3`), below the 1,000 typical estimate. Priced with the same factors, that is 0.12 / 0.42 / 3.1 Wh and
0.015 / 0.12 / 1.5 g CO₂e per run (low / typ / high), 7.4 g / 60 g / 0.73 kg per year (500 runs, **ESTIMATE**), and
one accepted suggestion (1.33 kg) offsets about 900 runs in the high case. The energy per token is still taken from
the literature: Anthropic does not publish it. The demo itself runs a local model
(Qwen2.5 3B through Ollama) on our laptop; its calls are logged and **measured** in
[Local model (Ollama)](#local-model-ollama). Every number below is either taken from a cited source or marked
**ESTIMATE**.

## Method
Carbon per plan run = **output tokens × Wh per output token × g CO₂e per kWh**.

- **Why output tokens.** Generation time, and with it energy, scales with output length; the time to the first
  token covers the input. Our inputs are short (≤ ~850 tokens per request, `python3 plan_demo.py --show-prompts`),
  and EPOCH2025 finds input cost matters only for long inputs (about 2.5 Wh per query at 10k input tokens). The per-token factors are taken from
  JEGHAM2025's 1k-input / 1k-output prompt, which already includes a longer input than ours.
- **Low / typ / high** are combined case by case (low tokens × low Wh × low g/kWh, and so on), so "high" is a
  deliberately pessimistic bound, not a likely value.
- **Scope.** Inference only: GPU and host energy plus data-centre overhead (PUE). Not included: training of the
  model, embodied emissions of the hardware, network and, for Claude calls, the user's device (also excluded by Green Algorithms
  and by ELSWORTH2025), and the LLM use while *developing* the tool (not measured; see the last section).

### Inputs
| Input | low | typ | high | Source |
|---|---|---|---|---|
| Wh per output token | 0.000172 | 0.0006 | 0.00446 | JEGHAM2025 Table 4, 1k in / 1k out: LLaMA-3.1-8B 0.172 Wh, GPT-4.1 nano 0.575 Wh, Claude 3.5 Haiku 4.464 Wh, each / 1,000 tokens. typ also matches EPOCH2025 (0.3 Wh for 500 tokens of GPT-4o) |
| g CO₂e per kWh | 125 | 287 | 475 | low: ELSWORTH2025, 0.03 g / 0.24 Wh per median Gemini prompt (market-based); typ: AWS factor used for Claude in JEGHAM2025; high: world average in LANNELONGUE2021 (from IEA 2019). Anthropic does not disclose the serving region |
| Output tokens per run (A1: 1 proposer + 3 phrasers) | 400 | 1,000 | 5,120 | low: the bare JSON answers, from the schemas and character limits in `PROMPTS.md` (~40 + 3 × 120); typ: **ESTIMATE**, 2.5 × the JSON for adaptive thinking at effort `low`; high: the hard cap, `max_tokens` 2048 + 3 × 1024 (`src/ai/plan_engine.py`) |
| Plan runs per year | 500 | 500 | 500 | **ESTIMATE**: about 10 groups × 1 plan a week × 50 weeks, one run per plan |

No published per-token figure exists for Claude Haiku 5.5. Claude 3.5 Haiku in JEGHAM2025 is inferred from
public API speed and assumed hardware, not measured, and it is the least efficient small model in their table:
we use it as the high case on purpose.

### Cross-check: Green Algorithms
The Green Algorithms calculator (LANNELONGUE2021, green-algorithms.org) computes
`E = t × (n_c × P_c × u_c + n_m × P_m) × PUE / 1000` (kWh) and `C = E × CI`. It was built for jobs whose
hardware and runtime you know; for an API model you know neither. JEGHAM2025's Eq. 1 is the same formula
mapped to an API model, and we use their mapping:

| Green Algorithms field | Value for a Claude API call | Source |
|---|---|---|
| runtime `t` | measured `latency_s` per call (from `data/llm_usage_log.jsonl`) | our log |
| cores × power `n_c × P_c` (+ memory) | one 8-GPU DGX H100/H200 node, 10.2 kW | JEGHAM2025 |
| usage factor `u_c` | 5.5 % / 6.5 % / 7.5 %: the share of the node one request uses under batching | JEGHAM2025 (6.5 % is our midpoint) |
| PUE | 1.14 (AWS) | JEGHAM2025 |
| carbon intensity | as in the inputs table | as above |

`python3 footprint.py --log` prints this as "GA check Wh / run" for Claude calls in the log. Logged latency
includes network and queueing time, so the check overestimates. It needs real Claude latencies, so it has no
value yet. The same values can be typed into the online calculator (GPU, number of cores, usage factor, PUE,
location).

## Result (plan A1, location basis)
`python3 footprint.py`:

| Per plan run | low | typ | high |
|---|---|---|---|
| LLM energy | 0.069 Wh | 0.60 Wh | 22.9 Wh |
| LLM footprint | 0.009 g | 0.17 g | 10.9 g |
| CO₂e the suggestions offer (3 suggestions, calculator) | 4.00 kg | 5.00 kg | 6.37 kg |
| **Per year (500 runs, ESTIMATE)** | | | |
| LLM footprint | 4.3 g | 86 g | 5.4 kg |

For comparison, ELSWORTH2025 reports 0.24 Wh for a median Gemini text prompt: our typical run (4 requests)
lands in the same order of magnitude.

**Break-even (pessimistic pairing: highest LLM footprint against the low bound of the average saving per suggestion, 1.33 kg).**
- One accepted suggestion offsets the LLM use of **about 123 plan runs**; in the typical case, about 9,700.
- A year of LLM use (5.4 kg in the high case) is offset by **about 4 accepted suggestions per year**.
- With the `market` basis (`--basis market`) the offered saving is 3.99–6.17 kg and the break-even is about the
  same (122 runs, 4.1 suggestions a year). We price the LLM with location-type grid factors either way.

So the paradox does not bite at the scale of operation: even if the LLM costs 10.9 g per run, it pays for itself
as soon as researchers accept a handful of suggestions a year. The comparison is only fair, though, if savings
are counted as *accepted*, not offered: the UI feedback events (`data/feedback_log.json`) are what
will turn the offered 5.0 kg into a real number (the log is empty for now).

## Local model (Ollama)
The demo runs Qwen2.5 3B (`qwen2.5:3b`, Q4_K_M, through Ollama) on our own laptop, so data never leaves it and
the hardware is known. For these calls the per-token data-centre factors above do not apply: we use the Green
Algorithms formula directly, `E = t × P × u × PUE`, with the measured latency of every call as `t`.
`footprint.py --log` treats a logged model named `name:tag` (the Ollama format) as local and prices it this way;
Claude calls in the same log keep the data-centre method. `--model` restricts the log to one model (other local
models, such as `qwen2.5:7b`, run on the same laptop and are priced the same way).

| Field | low | typ | high | Source |
|---|---|---|---|---|
| hardware | MacBook Pro 14" (2023), M2 Pro 10-core CPU / 16-core GPU, 16 GB | | | `system_profiler` on the demo laptop |
| runtime `t` per plan run | 9.03 s | 9.03 s | 9.03 s | our log: mean `latency_s` over 84 runs (311 proposer + phraser calls, 15 Oct 2026) |
| device power `P` | 24.5 W | 46.6 W | 71.4 W | NOTEBOOKCHECK2023, same configuration: low = GPU power alone under a GPU stress test; typ = whole laptop at the wall in a GPU-bound game (Witcher 3 ultra); high = whole laptop at the wall, maximum (Prime95 + FurMark). Which load an Ollama call resembles is an **ESTIMATE** (generation runs on the GPU through Metal, hence typ) |
| usage factor `u` | 1 | 1 | 1 | **ESTIMATE**: the device counts as fully busy for the whole call |
| PUE | 1 | 1 | 1 | no data centre; adapter losses are already inside the wall measurement |
| carbon intensity | 262.2 g/kWh | 262.2 g/kWh | 262.2 g/kWh | NL 2025 location-based grid mean (EMAPS, `data/electricity_factors.csv`) |

The 23 `booking-*` calls in the log belong to the booking tool, not to a plan run, and are left out.

**Result, measured (`python3 footprint.py --log --model qwen2.5:3b`, log of 15 Oct 2026; later runs change it),
next to the Claude estimate (plan A1, location basis):**

| Per plan run | Claude Haiku 5.5 (estimate) | Qwen2.5 3B on the laptop (measured runtime) |
|---|---|---|
| output tokens | 400 / 1,000 / 5,120 (**ESTIMATE**) | 363 (measured) |
| energy | 0.069 / 0.60 / 22.9 Wh | 0.061 / 0.117 / 0.179 Wh |
| footprint | 0.009 / 0.17 / 10.9 g CO₂e | 0.016 / 0.031 / 0.047 g CO₂e |
| per year (500 runs, **ESTIMATE**) | 4.3 g / 86 g / 5.4 kg | 8.1 g / 15 g / 24 g |
| worst-case break-even | 1 accepted suggestion = 123 runs | 1 accepted suggestion = about 28,000 runs |

The same 363 tokens priced with the data-centre factors would be 0.062 / 0.22 / 1.6 Wh: the laptop is not more
efficient per token than a batched data-centre GPU (the low cases are equal); it is the small model and the
short, thinking-free answers that keep the local run low. With the local model a full year of use (24 g in the
high case) costs less than 2 % of one accepted suggestion (1.33 kg).

Why the local figures are still upper bounds:
- The mean latency includes the slowest calls (up to 13.5 s), most likely Ollama loading the model into memory
  again after unloading it when idle. With median latencies (2.5 s proposer, 1.4 s phraser) a run takes about
  6.2 s, a third less.
- typ and high count the whole laptop at the wall, display and idle baseline included (5.2 W idle at
  150 cd/m², NOTEBOOKCHECK2023), which would run anyway during a demo. What the LLM adds is lower.
- With the `market` basis (TU/e green contract, MC2024) the footprint is 0 g. That only says the direct emissions
  are allocated to renewables; the energy is still used, so we report the location figure.

Not counted, as for Claude: training of the model, embodied emissions of the laptop, network.

**Measuring the device power yourself** (replaces the published figures with a measurement of this laptop):
1. In one terminal, with the laptop on its adapter and other apps closed, sample the chip power once a second:
   ```bash
   sudo powermetrics --samplers cpu_power,gpu_power -i 1000 -n 60 > power.txt
   ```
2. In a second terminal, during those 60 s, run the demo a few times: `python3 plan_demo.py --llm ollama`
   (this appends the calls to `data/llm_usage_log.jsonl`, which is what we want here).
3. Average the `Combined Power (CPU + GPU + ANE)` lines (mW) of the seconds when the model was generating,
   subtract the average of a sample taken with nothing running, and divide by 1000.
4. `python3 footprint.py --log --device-w <W>` uses that value for all three cases.

`powermetrics` reports the chip only (CPU, GPU, Neural Engine), not the display, memory, SSD or adapter
losses: a measurement lands between our low case and the wall figures, and it is the marginal power of the LLM,
not the whole laptop's.

## What is not settled
- **Claude output tokens are estimates** until the first real Claude calls. Replace them with
  `python3 footprint.py --log`; `summary()` in `src/ai/llm/usage_log.py` gives the totals for the report. The
  local model's tokens and runtimes are already measured (above).
- **Retries** (the client allows one) and re-runs of the same plan multiply the LLM side; the break-even above
  still holds with 10× more runs (about 45 accepted suggestions a year in the high case).
- **Development use is not counted.** Building and testing the tool with an AI coding assistant also used an
  LLM, possibly more than a year of the tool's own use (**ESTIMATE**, not measured). We report no number for
  it and state it as a limitation.
- **Training** of Claude Haiku 5.5 is not disclosed and not amortised here.

## Sources
- **ELSWORTH2025** Elsworth, C., Huang, K., Patterson, D., Schneider, I., Sedivy, R., Goodman, S., Townsend, B.,
  Ranganathan, P., Dean, J., Vahdat, A., Gomes, B. & Manyika, J. (2025). *Measuring the environmental impact of
  delivering AI at Google Scale.* arXiv:2508.15734. https://arxiv.org/abs/2508.15734
- **EMAPS** Electricity Maps (2026). *Electricity Grid Review 2025: the Netherlands.*
  https://www.electricitymaps.com/grid-in-review-2025/the-netherlands
- **EPOCH2025** You, J. (2025, 7 February). *How much energy does ChatGPT use?* Epoch AI, Gradient Updates.
  https://epoch.ai/gradient-updates/how-much-energy-does-chatgpt-use
- **JEGHAM2025** Jegham, N., Abdelatti, M., Koh, C.Y., Elmoubarki, L. & Hendawi, A. (2025). *How Hungry is AI?
  Benchmarking Energy, Water, and Carbon Footprint of LLM Inference.* arXiv:2505.09598 (v6).
  https://arxiv.org/abs/2505.09598
- **LANNELONGUE2021** Lannelongue, L., Grealey, J. & Inouye, M. (2021). Green Algorithms: Quantifying the Carbon
  Footprint of Computation. *Advanced Science*, 8(12), 2100707. https://doi.org/10.1002/advs.202100707 ·
  calculator: https://calculator.green-algorithms.org
- **MC2024** Milieu Centraal / CO2emissiefactoren.nl (2024, 14 February). *Notitie CO2-emissiefactoren
  elektriciteit.* https://co2emissiefactoren.nl/media/sources/240214-Notitie-CO2emissiefactoren-elektriciteit-pdf.pdf
- **NOTEBOOKCHECK2023** Osthoff, A. (2023). *Apple MacBook Pro 14 2023 Entry review: Base model with cut-down
  M2 Pro, SSD downgrade and slightly higher power draws.* Notebookcheck. Power consumption section, measured at
  the wall on the M2 Pro 10-core CPU / 16-core GPU, 16 GB configuration (figures read from the Italian edition).
  https://www.notebookcheck.net/Apple-MacBook-Pro-14-2023-Entry-Review-Base-model-with-cut-down-M2-Pro-SSD-downgrade-and-slightly-higher-power-draws.700015.0.html
