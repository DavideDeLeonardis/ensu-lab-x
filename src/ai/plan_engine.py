"""
plan_engine.py: suggestions for an experiment plan (CONTRACT.md §1b, §3b).

    from src.ai.plan_engine import build_plan_suggestion_set
    sset = build_plan_suggestion_set(plan)                      # rules + templates, no LLM
    sset = build_plan_suggestion_set(plan, llm=AnthropicClient())

The LLM proposes, the calculator counts, the rules and the validator filter, the researcher decides:
  1. allowed options   curated equivalences per unlocked line, minus requirement clashes and muted pairs
  2. proposer          the LLM picks among the allowed options (structured JSON, ids only);
                       if it fails, the rule-based proposer takes every allowed option
  3. rule 10           ids not in the allowed list are discarded before anything is priced
  4. pricing           src/lab/plan_calculator.plan_saving() for every candidate (rule 5)
  5. rules 4 / 8       ≥ 0.2 kg, one per line, biggest first, at most 3
  6. phraser           the LLM writes headline / why / tradeoff; the template is used for any text that
                       fails the checks (lengths, names, numbers, validation notice) or if the call fails
  7. validator         the result must pass src/contract/validate.py; otherwise templates are used
`generator` in the output records who proposed and who phrased.
"""
from __future__ import annotations
import re
from typing import Optional

from src.lab import plan_calculator as calc
from src.contract import validate
from .llm.client import LLMClient
from .llm.prompts import (PROPOSER_VERSION, PHRASER_VERSION, PROPOSER_SYSTEM, PHRASER_SYSTEM, PHRASER_SCHEMA,
                          proposer_schema, proposer_user, phraser_user, numbers_outside, scrub)
from .llm.usage_log import DEFAULT_LOG, log_usage

MIN_SAVING_KG = 0.2     # rule 8
MAX_SUGGESTIONS = 3     # rule 4
MAX_HOTSPOTS = 4
LIMITS = {"headline": 80, "why": 200, "tradeoff": 160}
CONFIDENCE = {"estimate": "low", "derived": "medium", "measured": "high"}
_RANK = {"low": 0, "medium": 1, "high": 2}
# "1.9 kg ... per use" / "each tip saves 0.8 kg": the saving is for the whole line, not per unit
_SAME_SENTENCE = r"(?:[^.;]|\.\d)*"   # anything up to the end of the sentence (a decimal point is not an end)
_PER_UNIT = r"\b(?:per|each|every)\s+(?:use|piece|item|unit|tip|tube|dish|pipette|glove)s?\b"
PER_UNIT_CLAIM = re.compile(rf"kg{_SAME_SENTENCE}{_PER_UNIT}|{_PER_UNIT}{_SAME_SENTENCE}kg", re.IGNORECASE)


def _name(item_id: str) -> str:
    """Display name without the '(per use)' qualifier."""
    row = calc.CONSUMABLES.get(item_id) or calc.EQUIPMENT.get(item_id) or {}
    return re.sub(r"\s*\(per use\)\s*$", "", row.get("name", item_id))


def _fit(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


# --- 1. allowed options ------------------------------------------------------------
def allowed_options(plan: dict, muted_pairs: set) -> tuple[dict[str, list[str]], list[dict]]:
    """({line_id: [equivalence_id, ...]}, suppressed entries for locked / conflicting / muted lines)."""
    allowed, suppressed = {}, []
    for ln in plan["lines"]:
        if ln.get("locked"):
            suppressed.append({"line_id": ln["line_id"], "reason": "hard_constraint",
                               "detail": ln.get("lock_reason", "")})
            continue
        pairs = [e for e in calc.EQUIVALENCES.values() if e["item_id"] == ln["item_id"]]
        if not pairs:
            continue  # no curated alternative: nothing to say (not listed, to keep the UI calm)
        reqs = set(ln.get("requirements", []))
        compatible = [e for e in pairs if not reqs & {t for t in e["incompatible_with"].split(";") if t}]
        if not compatible:
            clash = sorted({t for e in pairs for t in e["incompatible_with"].split(";") if t} & reqs)
            suppressed.append({"line_id": ln["line_id"], "reason": "requirement_conflict",
                               "detail": "Every curated alternative conflicts with: " + ", ".join(clash)})
            continue
        open_ = [e for e in compatible if (e["type"], ln["item_id"]) not in muted_pairs]
        if not open_:
            suppressed.append({"line_id": ln["line_id"], "reason": "muted_by_user_feedback",
                               "detail": "Rejected repeatedly in this lab"})
            continue
        allowed[ln["line_id"]] = [e["equivalence_id"] for e in open_]
    return allowed, suppressed


# --- 2–3. proposer -------------------------------------------------------------------
def _proposer_lines(plan: dict, allowed: dict) -> list[dict]:
    """What the LLM sees: item names, quantities, requirements and options. No plan_id, no people."""
    out = []
    for ln in plan["lines"]:
        if ln["line_id"] not in allowed:
            continue
        options = []
        for eq_id in allowed[ln["line_id"]]:
            e = calc.EQUIVALENCES[eq_id]
            options.append({"equivalence_id": eq_id, "alternative": _name(e["alternative_id"]), "type": e["type"],
                            "tradeoff": e["tradeoff"], "requires_validation": e["requires_validation"] == "True"})
        out.append({"line_id": ln["line_id"], "item": _name(ln["item_id"]), "quantity": ln["quantity"],
                    "unit": ln["unit"], "requirements": ln.get("requirements", []), "options": options})
    return out


_QUOTE = re.compile(r'["“”]([^"“”]{8,})["“”]')


def _norm(s: str) -> str:
    return " ".join(re.sub(r"[^\w\s]", " ", (s or "").lower()).split())


def _stems(s: str) -> set[str]:
    return {w[:-1] if w.endswith("s") else w for w in _norm(s).split() if len(w) >= 4}


def grounding_quote(reason: str, researcher_text: str) -> Optional[str]:
    """The part of `reason` that is the researcher's own words (a quote, or the whole reason), at least three
    words long and really in their (scrubbed) text; None if there is none."""
    source = _norm(researcher_text)
    for q in _QUOTE.findall(reason or "") + [reason or ""]:
        if len(_norm(q).split()) >= 3 and _norm(q) in source:
            return q
    return None


def justified(reason: str, researcher_text: str, item_name: str, alternative_name: str) -> bool:
    """An option may be dropped only if the reason quotes the researcher AND the quote names this row's item or
    its alternative (seen live: "reusing tubes is not acceptable" applied to tips and dishes too)."""
    quote = grounding_quote(reason, researcher_text)
    return bool(quote) and bool(_stems(quote) & (_stems(item_name) | _stems(alternative_name)))


def clean_reason(text, researcher_text: str = "") -> Optional[str]:
    """An LLM reason for leaving an option out, shown to the researcher only if it is short, has no number of its
    own and names nobody (rules 7 and 11); otherwise None. A number quoted from the researcher's own text is allowed
    (seen live: "We need 3D confocal stacks" was refused for its "3")."""
    if not isinstance(text, str) or not text.strip() or len(text.strip()) > 140:
        return None
    text = " ".join(text.split())
    if numbers_outside(text, researcher_text) or validate._names_in(text):
        return None
    return text


def notes_exclusions(plan: dict, requested) -> list[dict]:
    """The options the AI left out with a quote from the notes, kept out of later rules-only recalculations
    (seen live: after "Apply", the rules brought back the glass pipettes the notes rule out). The page sends them
    back; each is checked again against the CURRENT notes, so it lapses as soon as the quote is gone."""
    researcher_text = scrub(plan.get("title", "")) + " " + scrub(plan.get("notes", ""))
    items = {ln["item_id"] for ln in plan["lines"]}
    kept = []
    for r in requested if isinstance(requested, list) else []:
        eq = calc.EQUIVALENCES.get(r.get("equivalence_id")) if isinstance(r, dict) else None
        if eq is None or eq["item_id"] not in items:
            continue
        reason = clean_reason(r.get("reason"), researcher_text)
        if reason and justified(reason, researcher_text, _name(eq["item_id"]), _name(eq["alternative_id"])):
            kept.append({"equivalence_id": eq["equivalence_id"], "reason": reason})
    return kept


def propose(plan: dict, allowed: dict, llm: Optional[LLMClient], usage_log, trace: Optional[dict] = None):
    """(candidate (line_id, equivalence_id) pairs, 'llm' | 'rules'). `trace` (optional dict) receives what the
    LLM left out and why, and how many ids it invented; the UI shows it next to the rules' own choice."""
    trace = trace if trace is not None else {}
    trace.update(left_out=[], invalid_ids=0)
    every_option = [(lid, eq) for lid, eqs in allowed.items() for eq in eqs]
    if llm is None or not allowed:
        return every_option, "rules"
    result = llm.complete_json(PROPOSER_SYSTEM,
                               proposer_user(_proposer_lines(plan, allowed), plan.get("title", ""),
                                             plan.get("notes", "")),
                               proposer_schema(allowed), max_tokens=2048)
    log_usage(result, "proposer", PROPOSER_VERSION, usage_log)
    raw = result.data.get("candidates") if result.ok else None
    if not isinstance(raw, list):
        return every_option, "rules"
    # Rule 10: keep only pairs that are in the allowed list, whatever the LLM wrote
    pairs = [(c.get("line_id"), c.get("equivalence_id")) for c in raw if isinstance(c, dict)]
    valid = list(dict.fromkeys(p for p in pairs if p[1] in allowed.get(p[0], [])))
    trace["invalid_ids"] = len(raw) - len([p for p in pairs if p[1] in allowed.get(p[0], [])])
    if raw and not valid:   # it answered, but nothing it said was allowed: don't trust it this time
        return every_option, "rules"
    # The AI may drop an approved option only by quoting the researcher's own words (checked here). Anything it
    # left out without such a quote, or silently omitted, goes back in: no option is lost to an invented reason.
    researcher_text = scrub(plan.get("title", "")) + " " + scrub(plan.get("notes", ""))
    items = {ln["line_id"]: ln["item_id"] for ln in plan["lines"]}
    left = result.data.get("left_out")
    vetoed, unjustified = set(), []
    for c in left if isinstance(left, list) else []:
        if not (isinstance(c, dict) and c.get("equivalence_id") in allowed.get(c.get("line_id"), [])):
            continue
        pair = (c["line_id"], c["equivalence_id"])
        if pair in vetoed or pair in unjustified:
            continue
        reason = clean_reason(c.get("reason"), researcher_text)
        alt = calc.EQUIVALENCES[pair[1]]["alternative_id"]
        if reason and justified(reason, researcher_text, _name(items[pair[0]]), _name(alt)):
            vetoed.add(pair)   # a justified "leave out" wins, even if the same option was also listed as chosen
            trace["left_out"].append({"line_id": pair[0], "equivalence_id": pair[1], "reason": reason})
        else:
            unjustified.append(pair)
    trace["kept_without_quote"] = [{"line_id": a, "equivalence_id": b} for a, b in unjustified]
    restored = [p for p in every_option if p not in valid]
    trace["omitted"] = [{"line_id": a, "equivalence_id": b} for a, b in restored
                        if (a, b) not in vetoed and (a, b) not in unjustified]   # dropped with no word at all
    return [p for p in valid + restored if p not in vetoed], "llm"


# --- 4–5. pricing and ranking ----------------------------------------------------------
def rank(plan: dict, candidates: list[tuple], basis: Optional[str]) -> list[dict]:
    priced = []
    for line_id, eq_id in candidates:
        s = calc.plan_saving(plan, line_id, eq_id, basis)
        if s["saving_kg"]["typ"] >= MIN_SAVING_KG:
            priced.append(s)
    priced.sort(key=lambda s: s["saving_kg"]["typ"], reverse=True)
    top, seen = [], set()
    for s in priced:
        if s["line_id"] not in seen:
            top.append(s)
            seen.add(s["line_id"])
        if len(top) == MAX_SUGGESTIONS:
            break
    return top


# --- 6. phrasing ---------------------------------------------------------------------------
def template_text(s: dict, line: dict, eq: dict) -> dict:
    saved, pct = s["saving_kg"]["typ"], s["saving_pct"]
    return {
        "headline": _fit(f"Switch to: {_name(eq['alternative_id'])}", LIMITS["headline"]),
        "why": _fit(f"About {saved:.1f} kg CO₂e less ({pct:.0f}%) for this line: {_name(eq['alternative_id'])} "
                    f"instead of {line['quantity']:g} × {_name(line['item_id'])}.", LIMITS["why"]),
        "tradeoff": _fit(eq["tradeoff"], LIMITS["tradeoff"]),
    }


def _whole_line(line: dict) -> str:
    """'the whole line: 60 pieces' / 'the whole line: 15 h of use' (the saving is never per item)."""
    q, unit = line["quantity"], line["unit"]
    amount = f"{q:g} h of use" if unit == "h" else f"{q:g} {unit}{'s' if q != 1 and unit == 'piece' else ''}"
    return f"the whole line: {amount}"


def _facts(s: dict, line: dict, eq: dict) -> dict:
    return {"current_item": _name(line["item_id"]), "quantity": line["quantity"], "unit": line["unit"],
            "alternative": _name(eq["alternative_id"]),
            "saving": f"about {s['saving_kg']['typ']:.1f} kg CO₂e", "saving_pct": f"{s['saving_pct']:.0f}%",
            "applies_to": _whole_line(line),
            "tradeoff": eq["tradeoff"], "requires_validation": eq["requires_validation"] == "True",
            "needs_other_party": eq["needs_other_party"] == "True"}


def text_problems(text: dict, suggestion: dict, line: dict) -> list[str]:
    """Why an LLM text cannot be shown: lengths, rule 6 (trade-off, validation), 7 (names), 11 (numbers)."""
    if not isinstance(text, dict) or not all(isinstance(text.get(k), str) and text[k].strip() for k in LIMITS):
        return ["missing field"]
    problems = [f"{k} longer than {n}" for k, n in LIMITS.items() if len(text[k]) > n]
    probe = {**suggestion, **{k: text[k] for k in LIMITS}}
    in_kg = calc.CONSUMABLES.get(line["item_id"], {}).get("unit") == "kg"
    problems += validate._check_text_and_threshold(
        probe, extra_kg=[line["quantity"], suggestion["change"]["new_quantity"]] if in_kg else ())
    if suggestion.get("requires_validation") and "validat" not in text["tradeoff"].lower():
        problems.append("trade-off does not say the change needs validation")
    if PER_UNIT_CLAIM.search(" ".join(text[k] for k in LIMITS)):
        problems.append("states the saving per item/use, but it is for the whole line")
    return problems


def phrase(suggestions: list[dict], plan: dict, llm: Optional[LLMClient], usage_log,
           trace: Optional[dict] = None) -> str:
    """Fill headline/why/tradeoff in place; return 'llm', 'template' or 'mixed'.
    `trace` (optional dict) receives, per suggestion, whether the LLM text was used and why not."""
    lines = {ln["line_id"]: ln for ln in plan["lines"]}
    used_llm = 0
    for sg, s in suggestions:
        line, eq = lines[s["line_id"]], calc.EQUIVALENCES[s["equivalence_id"]]
        text = template_text(s, line, eq)
        if llm is not None:
            result = llm.complete_json(PHRASER_SYSTEM, phraser_user(_facts(s, line, eq)), PHRASER_SCHEMA,
                                       max_tokens=1024)
            log_usage(result, "phraser", PHRASER_VERSION, usage_log)
            problems = text_problems(result.data, sg, line) if result.ok else [f"call failed: {result.error}"]
            if trace is not None:
                trace.setdefault("phraser", []).append({"line_id": s["line_id"], "used": not problems,
                                                        "problems": problems})
            if not problems:
                text = {k: result.data[k].strip() for k in LIMITS}
                used_llm += 1
        sg.update(text)
    if not suggestions or used_llm == 0:
        return "template"
    return "llm" if used_llm == len(suggestions) else "mixed"


# --- dry run -------------------------------------------------------------------------------
CHARS_PER_TOKEN = 4  # rough rule of thumb for English text, NOT a measurement


def preview_prompts(plan: dict, basis: Optional[str] = None, muted_pairs: Optional[set] = None) -> list[dict]:
    """The exact requests an LLM run would send for `plan`, without calling anything.

    One proposer request, then one phraser request per suggestion the rules would keep (the LLM may choose
    others). `est_input_tokens` is a rough estimate (characters / 4), to be replaced by measured tokens."""
    allowed, _ = allowed_options(plan, muted_pairs or set())
    if not allowed:
        return []
    out = [{"purpose": "proposer", "prompt_version": PROPOSER_VERSION, "system": PROPOSER_SYSTEM,
            "user": proposer_user(_proposer_lines(plan, allowed), plan.get("title", ""), plan.get("notes", "")),
            "schema": proposer_schema(allowed)}]
    lines = {ln["line_id"]: ln for ln in plan["lines"]}
    for s in rank(plan, [(l, e) for l, eqs in allowed.items() for e in eqs], basis):
        out.append({"purpose": "phraser", "prompt_version": PHRASER_VERSION, "system": PHRASER_SYSTEM,
                    "user": phraser_user(_facts(s, lines[s["line_id"]], calc.EQUIVALENCES[s["equivalence_id"]])),
                    "schema": PHRASER_SCHEMA})
    for r in out:
        r["est_input_tokens"] = round(len(r["system"] + r["user"]) / CHARS_PER_TOKEN)
    return out


# --- 7. assembly ---------------------------------------------------------------------------
def _confidence(*item_ids: str) -> str:
    labels = [CONFIDENCE.get((calc.CONSUMABLES.get(i) or calc.EQUIPMENT.get(i) or {}).get("confidence"), "low")
              for i in item_ids]
    return min(labels, key=_RANK.get)


def _suggestion(i: int, s: dict) -> dict:
    eq = calc.EQUIVALENCES[s["equivalence_id"]]
    return {
        "id": f"S{i}", "type": eq["type"], "line_ids": [s["line_id"]],
        "headline": "", "change": {"line_id": s["line_id"], "equivalence_id": s["equivalence_id"],
                                   "alternative_id": s["alternative_id"], "new_quantity": s["new_quantity"]},
        "saving_kg": s["saving_kg"], "saving_pct": s["saving_pct"], "why": "", "tradeoff": "",
        "confidence": _confidence(eq["item_id"], eq["alternative_id"]),
        "requires_validation": eq["requires_validation"] == "True",
        "needs_other_party": eq["needs_other_party"] == "True",
    }


def _estimate(est: dict) -> dict:
    per_item: dict[str, dict] = {}
    for ln in est["lines"]:
        d = per_item.setdefault(ln["item_id"], {"kg": 0.0, "locked": True})
        d["kg"] += ln["kg"]["typ"]
        d["locked"] = d["locked"] and ln["locked"]
    total = est["kg"]["typ"]
    hotspots = sorted(({"item_id": i, "kg_typ": round(d["kg"], 2),
                        "share_pct": round(100 * d["kg"] / total, 1) if total else 0.0, "locked": d["locked"]}
                       for i, d in per_item.items()), key=lambda h: h["kg_typ"], reverse=True)[:MAX_HOTSPOTS]
    r2 = lambda rng: {k: round(v, 2) for k, v in rng.items()}  # noqa: E731
    return {"kwh": round(est["kwh"], 2), "kg": r2(est["kg"]),
            "breakdown": {k: r2(v) for k, v in est["breakdown"].items()},
            "electricity": est["electricity"], "hotspots": hotspots,
            "locked_kg": round(sum(ln["kg"]["typ"] for ln in est["lines"] if ln["locked"]), 2)}


def build_plan_suggestion_set(plan: dict, llm: Optional[LLMClient] = None, basis: Optional[str] = None,
                              muted_pairs: Optional[set] = None, usage_log=DEFAULT_LOG,
                              trace: Optional[dict] = None, excluded_eqs: Optional[set] = None) -> dict:
    """ExperimentPlan -> SuggestionSet that passes validate.check_suggestion_set(sset, plan=plan).

    `llm=None` runs rules + templates only. `usage_log=None` disables the token log. `trace` (optional dict)
    receives the LLM's left-out options with their checked reasons, the options it dropped silently, each
    phraser outcome and whether the last defence fired: not part of the SuggestionSet (contract)."""
    errors = validate.check_plan(plan)
    if errors:
        raise ValueError("invalid ExperimentPlan: " + "; ".join(errors))
    est = calc.estimate_plan(plan, basis)
    basis = est["electricity"]["basis"]

    allowed, suppressed = allowed_options(plan, muted_pairs or set())
    if excluded_eqs:   # options the notes rule out (notes_exclusions): not offered again by the rules
        allowed = {l: [e for e in eqs if e not in excluded_eqs] for l, eqs in allowed.items()}
        allowed = {l: eqs for l, eqs in allowed.items() if eqs}
    candidates, proposer = propose(plan, allowed, llm, usage_log, trace)
    top = rank(plan, candidates, basis)
    suggestions = [_suggestion(i, s) for i, s in enumerate(top, start=1)]
    # one failed proposer call means the API is unreachable or misbehaving: don't call it again for text
    phrasing_llm = llm if (llm is not None and proposer == "llm") else None
    phraser = phrase(list(zip(suggestions, top)), plan, phrasing_llm, usage_log, trace)

    used = [v for v, on in ((PROPOSER_VERSION, proposer == "llm"), (PHRASER_VERSION, phraser != "template")) if on]
    sset = {
        "request_id": plan["plan_id"],
        "line_ids": [ln["line_id"] for ln in plan["lines"]],
        "generator": {"proposer": proposer, "phraser": phraser,
                      "model": llm.model if used else None, "prompt_version": "/".join(used) or None},
        "estimate": _estimate(est),
        "suggestions": suggestions,
        "suppressed": suppressed,
    }
    if trace is not None:
        trace["last_defence"] = False
    if validate.check_suggestion_set(sset, plan=plan) and phraser != "template":
        # last line of defence: if anything in the LLM text still breaks the contract, use the templates
        lines = {ln["line_id"]: ln for ln in plan["lines"]}
        for sg, s in zip(suggestions, top):
            sg.update(template_text(s, lines[s["line_id"]], calc.EQUIVALENCES[s["equivalence_id"]]))
        if trace is not None:
            trace["last_defence"] = True
        sset["generator"].update(phraser="template",
                                 prompt_version=PROPOSER_VERSION if proposer == "llm" else None)
        if proposer != "llm":
            sset["generator"]["model"] = None
    return sset
