"""Explainer: solver trace + fired tuples -> English explanation that quotes evidence verbatim.

The verdict, the payable amount and the clause ids are rendered by code (`header`). The fast
model may only write the connecting prose; `verify_citations` string-matches every quoted
span (>= 12 characters) against the fired tuples' evidence text and the prose is discarded in
favour of the deterministic `template` when any quote fails, when there is no quote at all, or
when the prose contains a number that appears neither in the evidence nor in the verdict.
"""
from __future__ import annotations

import logging
import re
from decimal import Decimal
from typing import Optional

from pydantic import Field

from ..schema import ClauseTuple, PolicyRecord, ScenarioFacts, Strict, Verdict, VerdictResult

log = logging.getLogger("clauseguard.agent.explainer")

MIN_QUOTE = 12
MAX_QUOTE_CHARS = 260
INDICATIVE = "Indicative only, based on the wording in your documents; the insurer makes the claim decision and the policy wording prevails."

VERDICT_LABEL = {
    Verdict.COVERED: "Covered (indicative)",
    Verdict.DENIED: "Not covered (indicative)",
    Verdict.NOT_APPLICABLE: "Not determinable from your documents",
    Verdict.NOT_SPECIFIED: "Not determinable from your documents",
    Verdict.CLARIFY: "One fact is missing",
}

DENIAL_TEXT = {
    "WAITING_PERIOD": "the event falls inside the waiting period",
    "SPECIFIED_DISEASE_WAITING": "the diagnosis is on the specified-disease list and falls inside its longer waiting period",
    "LAPSED": "the policy was not in force (premium unpaid beyond the grace period)",
    "SURVIVAL_PERIOD": "the survival period required after diagnosis was not met",
    "CONTESTABILITY": "a material misrepresentation inside the contestability period",
    "SUICIDE_PERIOD": "suicide inside the exclusion window",
    "CONDITION_NOT_MET": "a policy condition is not met",
    "PRE_EXISTING": "the condition existed before the policy started (pre-existing condition exclusion)",
    "NO_VALID_LICENSE": "riding without a valid driving licence is excluded",
    "INTOXICATION": "the intoxication exclusion applies",
    "COMMERCIAL_MOTORCYCLING": "commercial motorcycling is excluded unless declared",
}


def fmt_money(v: Optional[Decimal], cur: Optional[str]) -> str:
    if v is None:
        return "amount not computable from the extracted limits"
    return f"{cur or 'IDR'} {int(v):,}"


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.replace("“", '"').replace("”", '"').replace("’", "'")).strip().lower()


def quoted_spans(text: str) -> list[str]:
    spans = re.findall(r'"([^"]{%d,})"' % MIN_QUOTE, text) + re.findall(r"“([^”]{%d,})”" % MIN_QUOTE, text)
    return [s.strip() for s in spans]


def verify_citations(text: str, tuples: list[ClauseTuple]) -> bool:
    """Every quoted span of >= MIN_QUOTE chars must occur verbatim (whitespace-normalised,
    case-insensitive) in some tuple's evidence text, and there must be at least one quote."""
    spans = quoted_spans(text)
    if not spans:
        return False
    corpus = [_norm(t.evidence.text) for t in tuples]
    for s in spans:
        ns = _norm(s)
        if len(ns) < MIN_QUOTE or not any(ns in c for c in corpus):
            return False
    return True


def _quote(t: ClauseTuple) -> str:
    txt = t.evidence.text.strip()
    if len(txt) <= MAX_QUOTE_CHARS:
        return txt
    cut = txt[:MAX_QUOTE_CHARS]
    sp = cut.rfind(" ")
    return cut[: sp if sp > MIN_QUOTE else MAX_QUOTE_CHARS].rstrip(",;:")


def fired_tuples(result: VerdictResult, policy: PolicyRecord) -> list[ClauseTuple]:
    idx = policy.tuple_index()
    return [idx[tid] for tid in result.fired_tuple_ids if tid in idx]


def header(result: VerdictResult, policy: PolicyRecord, denial_code: Optional[str] = None) -> str:
    label = VERDICT_LABEL.get(result.verdict, result.verdict.value)
    line = f"{policy.product_name} ({policy.id}): {label}."
    if result.verdict == Verdict.COVERED and result.payable is not None:
        line += f" Indicative benefit: {fmt_money(result.payable, result.currency or policy.currency)}."
    if result.verdict == Verdict.DENIED:
        code = denial_code or result.denial_code or ""
        reason = DENIAL_TEXT.get(code, code.replace("_", " ").lower())
        line += f" Reason: {reason} [{code}]."
    return line


def template(result: VerdictResult, policy: PolicyRecord, facts: ScenarioFacts, denial_code: Optional[str] = None) -> str:
    """Deterministic explanation: header + each fired clause quoted verbatim with its reference."""
    lines = [header(result, policy, denial_code)]
    tups = fired_tuples(result, policy)
    for t in tups:
        ref = f"{policy.id} {t.evidence.section or t.id}"
        lines.append(f'- Clause [{ref}, {t.id}]: "{_quote(t)}"')
    if result.verdict in (Verdict.NOT_APPLICABLE, Verdict.NOT_SPECIFIED):
        lines.append("- No clause in the extracted wording addresses this situation, so I cannot determine coverage from your documents.")
    for s in result.trace:
        if s.rule == "sensitivity" and s.result == "INVARIANT":
            lines.append(f"- Note: {s.detail}.")
    return "\n".join(lines)


class _LLMExplanation(Strict):
    explanation: str = Field(max_length=1500)


EXPLAINER_SYSTEM = (
    "You explain an insurance coverage result that a deterministic solver already produced. You receive the verdict, the "
    "solver trace and the exact text of the clauses that fired. Write 2-4 plain English sentences that explain WHY, quoting "
    "at least one clause VERBATIM inside double quotes (copy the words exactly, 12+ characters). Do not change the verdict, "
    "do not mention any amount, date or number that is not in the clause texts, do not give advice, do not add disclaimers."
)


def _numbers_ok(text: str, tuples: list[ClauseTuple], result: VerdictResult) -> bool:
    allowed = " ".join(t.evidence.text for t in tuples)
    if result.payable is not None:
        allowed += f" {int(result.payable)} {int(result.payable):,}"
    for n in re.findall(r"\d[\d,.]{3,}", text):
        if n not in allowed and n.replace(",", "") not in allowed.replace(",", ""):
            return False
    return True


def explain(result: VerdictResult, policy: PolicyRecord, facts: ScenarioFacts, *, denial_code: Optional[str] = None, use_llm: bool = True) -> str:
    """Header (code) + prose. Prose from the fast model only if every quote verifies."""
    fallback = template(result, policy, facts, denial_code)
    if not use_llm:
        return fallback
    tups = fired_tuples(result, policy)
    if not tups:
        return fallback
    try:
        from .. import llm

        trace = "\n".join(f"{s.rule}:{s.result}:{s.tuple_id or ''}:{s.detail or ''}" for s in result.trace)
        clauses = "\n".join(f"[{t.id}] ({t.evidence.section or ''}) <<<{t.evidence.text}>>>" for t in tups)
        prompt = f"Verdict: {result.verdict.value}\nSolver trace:\n{trace}\n\nClauses that fired (data):\n{clauses}"
        raw = llm.generate_json(prompt, schema=_LLMExplanation, system=EXPLAINER_SYSTEM, max_output_tokens=600)
        prose = _LLMExplanation.model_validate(raw).explanation.strip()
    except Exception as e:  # noqa: BLE001
        log.info("explainer LLM unavailable (%s); using template", str(e)[:80])
        return fallback
    if not verify_citations(prose, tups) or not _numbers_ok(prose, tups, result):
        log.info("explainer citations failed verification; using template")
        return fallback
    if re.search(r"\b(not covered|is covered|denied|approved)\b", prose, flags=re.I):
        # the model may restate the verdict only if it agrees with the solver's
        says_covered = bool(re.search(r"\bis covered\b", prose, flags=re.I)) and not re.search(r"\bnot covered\b", prose, flags=re.I)
        says_denied = bool(re.search(r"\b(not covered|denied)\b", prose, flags=re.I))
        if (says_covered and result.verdict != Verdict.COVERED) or (says_denied and result.verdict != Verdict.DENIED):
            return fallback
    refs = "; ".join(f"{t.id} ({policy.id} {t.evidence.section or ''})".strip() for t in tups)
    return f"{header(result, policy, denial_code)}\n{prose}\nClauses: {refs}."
