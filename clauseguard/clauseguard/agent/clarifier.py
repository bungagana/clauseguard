"""Clarifier: one question for exactly the slot whose value changes the verdict.

`phrase(clarification, tuple)` asks the fast model to word the question given the slot, the
verdict under each candidate value and the evidence text of the clause that makes the slot
matter. The model output is accepted only if it is a single question that mentions nothing
the template does not already know (no numbers that are absent from the evidence, exactly one
question mark). Otherwise the fixed template is used. The verdict mapping itself is never
produced by the model.
"""
from __future__ import annotations

import logging
import re
from typing import Optional

from pydantic import Field

from ..schema import ClarificationRequest, ClauseTuple, Slot, Strict, Verdict

log = logging.getLogger("clauseguard.agent.clarifier")

SLOT_QUESTIONS: dict[Slot, str] = {
    Slot.CAUSE: "Was the hospitalisation caused by an illness or by an accident?",
    Slot.IS_ACCIDENT: "Was this caused by an accident?",
    Slot.IS_EMERGENCY: "Was this an emergency admission?",
    Slot.DAYS_SINCE_EFFECTIVE: "On what date did the policy start (effective date), and on what date did the event happen?",
    Slot.MONTHS_SINCE_ISSUE: "On what date was the policy issued?",
    Slot.MONTHS_SINCE_REINSTATEMENT: "Was the policy ever reinstated, and if so on what date?",
    Slot.DAYS_SINCE_DIAGNOSIS: "On what date was the diagnosis made?",
    Slot.DAYS_SINCE_EVENT: "On what date did the event happen?",
    Slot.DAYS_SINCE_DISCHARGE: "On what date were you discharged?",
    Slot.DAYS_SINCE_DEATH: "On what date did the death occur?",
    Slot.PREMIUM_STATUS: "Are the premiums paid up to date?",
    Slot.DAYS_OVERDUE: "How many days is the premium overdue?",
    Slot.IN_FORCE: "Is the policy currently in force?",
    Slot.AGE: "How old is the insured person?",
    Slot.RIDER_ATTACHED: "Is the rider attached to the policy?",
    Slot.DIAGNOSIS_BEFORE_EFFECTIVE: "Was this condition diagnosed or treated before the policy started?",
    Slot.DISEASE_IN_SPECIFIED_LIST: "What is the diagnosis? (The policy has a longer waiting period for a list of specified diseases.)",
    Slot.SURVIVAL_DAYS: "How many days did the insured survive after the diagnosis?",
    Slot.EMPLOYMENT_ACTIVE: "Is the employee still employed by the company that sponsors the group plan?",
    Slot.FACILITY_IN_NETWORK: "Is the hospital in the insurer's network?",
    Slot.FACILITY_BPJS_PARTNER: "Is the hospital a BPJS Kesehatan partner facility?",
    Slot.WORK_RELATED: "Did this happen while you were working (for example on an active delivery order)?",
    Slot.VEHICLES_INVOLVED: "Was another motor vehicle involved in the accident, or was it a single-vehicle accident?",
    Slot.LICENSE_VALID: "Did you hold a valid driving licence on the date of the accident?",
    Slot.INTOXICATED: "Were you under the influence of alcohol or drugs at the time?",
    Slot.PILOT_ROLE: "Were you a passenger, crew or private pilot?",
    Slot.MILITARY_SERVICE: "Were you on military service at the time?",
    Slot.DAYS_HOSPITALIZED: "How many days were you hospitalised?",
    Slot.BILLED_AMOUNT: "What was the total hospital bill?",
    Slot.EVENT: "What happened (hospitalisation, surgery, accident, death, critical illness, ...)?",
    Slot.MISREPRESENTATION: "Was any material fact misstated at application?",
    Slot.OCCUPATION_CLASS: "Which occupation class applies to the work you were doing: 1 (office or administrative work), 2 (light manual work) or 3 (riding for hire, for example as a courier or ojek driver)?",
}

_VERDICT_WORD = {Verdict.COVERED: "covered", Verdict.DENIED: "not covered", Verdict.NOT_APPLICABLE: "not addressed by the policy",
                 Verdict.NOT_SPECIFIED: "not determinable", Verdict.CLARIFY: "still open"}


def _value_label(slot: Slot, v: str) -> str:
    if v in ("True", "False"):
        return "yes" if v == "True" else "no"
    return v.replace("_", " ").lower()


def branch_labels(slot: Slot, verdict_by_value: dict) -> list[tuple[str, Verdict]]:
    """(value label, verdict) pairs. Many numeric candidate values (day counts) are merged into
    ranges with the same verdict: "0-29: not covered; 30-45: covered" instead of one entry per value."""
    keys = list(verdict_by_value)
    try:
        nums = sorted((int(k), verdict_by_value[k]) for k in keys)
    except (TypeError, ValueError):
        nums = []
    if len(nums) >= 4 and len(nums) == len(keys):
        out: list[tuple[str, Verdict]] = []
        lo = prev = nums[0][0]
        cur = nums[0][1]
        for n, v in nums[1:]:
            if v == cur:
                prev = n
                continue
            out.append((f"{lo}" if lo == prev else f"{lo}-{prev}", cur))
            lo = prev = n
            cur = v
        out.append((f"{lo}" if lo == prev else f"{lo}-{prev}", cur))
        return out
    return [(_value_label(slot, k), v) for k, v in verdict_by_value.items()]


def template(clarification: ClarificationRequest, tup: Optional[ClauseTuple]) -> str:
    q = SLOT_QUESTIONS.get(clarification.slot, f"Please tell me the value of '{clarification.slot.value}'.")
    why = ""
    if clarification.verdict_by_value:
        parts = []
        seen: set[str] = set()
        for label, verdict in branch_labels(clarification.slot, clarification.verdict_by_value):
            w = _VERDICT_WORD.get(verdict, verdict.value)
            key = f"{label}->{w}"
            if key in seen:
                continue
            seen.add(key)
            parts.append(f"{label}: {w}")
        if len(parts) > 6:
            parts = parts[:6] + ["..."]
        why = " It matters because the answer changes the outcome (" + "; ".join(parts) + ")."
    cite = ""
    if tup is not None:
        cite = f' The clause that makes this matter ({tup.policy_id}, {tup.evidence.section or tup.id}) says: "{tup.evidence.text}"'
    return f"One question before I can answer: {q}{why}{cite}"


class _LLMQuestion(Strict):
    question: str = Field(max_length=400)


CLARIFIER_SYSTEM = (
    "You word a single clarification question for an insurance assistant. You receive the fact slot that is missing, "
    "the outcome under each candidate value (computed by a solver, do not change it) and the clause text that makes the slot matter. "
    "Write ONE short, polite question in English. Do not state a verdict, do not add amounts or dates that are not in the clause text, "
    "do not answer the question yourself."
)


def _acceptable(q: str, tup: Optional[ClauseTuple], clarification: ClarificationRequest) -> bool:
    q = q.strip()
    if q.count("?") != 1 or not q.endswith("?") or len(q) < 10 or len(q) > 400:
        return False
    allowed = (tup.evidence.text if tup else "") + " ".join(clarification.verdict_by_value.keys())
    for num in re.findall(r"\d[\d,.]{2,}", q):
        if num not in allowed:
            return False
    if re.search(r"\b(you are covered|you are not covered|is covered|is not covered|will be paid|will pay)\b", q, flags=re.I):
        return False
    return True


def phrase(clarification: ClarificationRequest, tup: Optional[ClauseTuple] = None, *, use_llm: bool = True) -> str:
    """One question, citing why. Fast model with the fixed template as fallback."""
    fallback = template(clarification, tup)
    if not use_llm:
        return fallback
    try:
        from .. import llm

        outcomes = "; ".join(f"{k} -> {v.value}" for k, v in clarification.verdict_by_value.items())
        prompt = (
            f"Missing slot: {clarification.slot.value}\nOutcome by value: {outcomes or 'unknown'}\n"
            f"Clause text (data): <<<{tup.evidence.text if tup else ''}>>>\n"
            f"Default wording: {SLOT_QUESTIONS.get(clarification.slot, '')}"
        )
        raw = llm.generate_json(prompt, schema=_LLMQuestion, system=CLARIFIER_SYSTEM, max_output_tokens=256)
        q = _LLMQuestion.model_validate(raw).question.strip()
    except Exception as e:  # noqa: BLE001
        log.info("clarifier LLM unavailable (%s); using template", str(e)[:80])
        return fallback
    if not _acceptable(q, tup, clarification):
        return fallback
    cite = f' The clause that makes this matter ({tup.policy_id}, {tup.evidence.section or tup.id}) says: "{tup.evidence.text}"' if tup else ""
    return f"One question before I can answer: {q}{cite}"
