"""Adjudication Twin: evaluate a claim the way an insurer's claims desk would, before filing.

The solver stops at the first clause that denies. A claims assessor lists *every* ground, so
the twin isolates each denial-capable clause t (EXCLUDES, HAS_PERIOD, CONDITIONED_ON,
TERMINATES_IF) in a one-clause view of the policy P_t = grants(P) + exceptions(P) + {t} and
runs the frozen solver on it: a DENIED verdict on P_t is a ground attributable to t. The
filing deadline and the document checklist come from `portfolio.claim_readiness`, and the
uploaded documents are cross-checked in code (dates vs stated days, diagnosis codes vs cause,
invoice total vs line items, invoice vs stated bill, policyholder name match).

Readiness score. With grounds G, weights w: G -> (0, 1] and F subset of G the fixable grounds,

    readiness_score  = max(0, 1 - sum_{g in G} w(g))
    after_fix_score  = max(0, 1 - sum_{g in G \\ F} w(g))

so fixing any ground never lowers the score (monotone) and a fatal ground (weight 1) alone
makes it 0. Every ground carries the clause id, the verbatim evidence text and, when a
legitimate action can remove it, a `RecourseOption` from `recourse.find_recourse`.
Deterministic; no language model runs here.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional, Union

from pydantic import Field

from . import portfolio as pf
from .extractor.claim_doc import TOTAL_TOLERANCE, ClaimDocExtract, DocType
from .recourse import COST_TABLE, ActionKind, RecourseAction, RecourseOption, document_recourse, find_recourse
from .schema import (
    PeriodKind,
    PolicyRecord,
    Relation,
    ScenarioFacts,
    Slot,
    Strict,
    Verdict,
)

GRANT_RELATIONS = {Relation.COVERS, Relation.PERMITS, Relation.PAYS, Relation.EXCEPTS, Relation.DEFINES, Relation.REQUIRES_DOCUMENT, Relation.REFERS_TO, Relation.HAS_RIDER}
DENIAL_RELATIONS = {Relation.EXCLUDES, Relation.HAS_PERIOD, Relation.CONDITIONED_ON, Relation.TERMINATES_IF}

#: Weight of each ground in the readiness score (1 = fatal on its own).
GROUND_WEIGHTS: dict[str, float] = {
    "PRE_EXISTING": 1.0, "CONTESTABILITY": 1.0, "SUICIDE_PERIOD": 1.0, "SURVIVAL_PERIOD": 1.0,
    "NO_VALID_LICENSE": 1.0, "INTOXICATION": 1.0, "COMMERCIAL_MOTORCYCLING": 1.0,
    "WAITING_PERIOD": 0.8, "SPECIFIED_DISEASE_WAITING": 0.8, "LAPSED": 0.8, "GROUP_TERMINATED": 1.0,
    "CONDITION_NOT_MET": 0.7, "LATE_FILING": 0.8, "LATE_FILING_DISCRETIONARY": 0.5,
    "INCOMPLETE_DOCS": 0.3, "NAME_MISMATCH": 0.3, "INVOICE_TOTAL": 0.3, "BILL_VS_STATED": 0.2,
    "DATES_VS_DAYS": 0.2, "DATES_ACROSS_DOCUMENTS": 0.2, "DIAGNOSIS_VS_CAUSE": 0.4, "DOCUMENT_SUSPICIOUS": 0.3,
}
DEFAULT_EXCLUSION_WEIGHT = 1.0
DEFAULT_WEIGHT = 0.5

#: Uploaded document type -> required-document codes (prefix match) that it satisfies.
DOC_TYPE_SATISFIES: dict[DocType, tuple[str, ...]] = {
    DocType.INVOICE: ("ITEMISED_BILL", "RECEIPT", "MEDICAL_BILL", "RECEIPT_DETAILS"),
    DocType.RECEIPT: ("RECEIPT", "ITEMISED_BILL"),
    DocType.MEDICAL_REPORT: ("DOCTOR_STATEMENT", "MEDICAL_REPORT", "MEDICAL_RESUME", "MEDICAL_RESULTS", "DIAGNOSTIC_RESULTS", "SPECIALIST_CONFIRMATION", "PATHOLOGY_REPORT", "PHYSICIAN_CERTIFICATE"),
    DocType.DISCHARGE_SUMMARY: ("DISCHARGE_SUMMARY", "MEDICAL_RESUME"),
    DocType.DEATH_CERT: ("DEATH_CERT",),
    DocType.POLICE_REPORT: ("POLICE_REPORT",),
    DocType.ID_CARD: ("ID_CARD", "ID_COPY", "ID_AND_RELATIONSHIP", "BENEFICIARY_ID", "HEIR_ID"),
}
#: ICD-10 chapters that describe injury or an external cause (consistent with an accident).
INJURY_CHAPTERS = ("S", "T", "V", "W", "X", "Y")


class DocumentCheck(Strict):
    code: str
    detail: str = Field(max_length=300)
    doc_index: list[int] = Field(default_factory=list)


class DenialGround(Strict):
    code: str
    clause_id: Optional[str] = None
    evidence_text: str = Field(max_length=1200)
    fixable: bool
    recourse: Optional[RecourseOption] = None
    weight: float = Field(ge=0, le=1)
    source: str = Field(default="clause", pattern=r"^(clause|deadline|documents|consistency)$")


class TwinReport(Strict):
    policy_id: str
    verdict: Verdict
    denial_code: Optional[str] = None
    grounds: list[DenialGround] = Field(default_factory=list)
    open_slots: list[Slot] = Field(default_factory=list, description="clauses that could not be evaluated without these facts")
    checks: list[DocumentCheck] = Field(default_factory=list)
    readiness: Optional[pf.ReadinessReport] = None
    documents_present: list[str] = Field(default_factory=list)
    readiness_score: float = Field(ge=0, le=1)
    after_fix_score: float = Field(ge=0, le=1)
    payable: Optional[Decimal] = None
    currency: Optional[str] = None

    @property
    def top_ground(self) -> Optional[DenialGround]:
        """Heaviest ground; ties broken by clause grounds first, then by order of appearance."""
        if not self.grounds:
            return None
        order = {"clause": 0, "deadline": 1, "documents": 2, "consistency": 3}
        return min(self.grounds, key=lambda g: (-g.weight, order[g.source]))


# --------------------------------------------------------------------------- scoring
def ground_weight(code: str) -> float:
    if code in GROUND_WEIGHTS:
        return GROUND_WEIGHTS[code]
    if code.startswith("EXCLUSION_") or code.startswith("TERMINATED_"):
        return DEFAULT_EXCLUSION_WEIGHT
    return DEFAULT_WEIGHT


def score(grounds: list[DenialGround], fixed: Optional[set[str]] = None) -> float:
    """max(0, 1 - sum of weights of grounds not in `fixed`), rounded to 3 places."""
    fixed = fixed or set()
    total = sum(g.weight for g in grounds if g.code not in fixed)
    return round(max(0.0, 1.0 - total), 3)


def score_after(report: TwinReport, fixed: set[str]) -> float:
    """Readiness after the grounds with these codes are fixed (only fixable grounds count as fixed)."""
    fixable = {g.code for g in report.grounds if g.fixable}
    return score(report.grounds, fixed & fixable)


# --------------------------------------------------------------------------- documents
def _as_extract(d: Union[ClaimDocExtract, dict]) -> ClaimDocExtract:
    return d if isinstance(d, ClaimDocExtract) else ClaimDocExtract.model_validate(d)


def documents_satisfied(required: list[str], docs: list[ClaimDocExtract], explicit: list[str]) -> list[str]:
    """Required codes that an uploaded document (by type) or an explicit code satisfies."""
    explicit_up = {e.strip().upper() for e in explicit}
    prefixes = tuple(p for d in docs for p in DOC_TYPE_SATISFIES.get(d.doc_type, ()))
    out = []
    for code in required:
        up = code.upper()
        if up in explicit_up or any(up.startswith(p) for p in prefixes):
            out.append(code)
    return out


def consistency_checks(facts: ScenarioFacts, docs: list[ClaimDocExtract]) -> list[DocumentCheck]:
    """Cross-document and document-vs-facts checks, all in code."""
    out: list[DocumentCheck] = []
    stated_days = int(facts.get(Slot.DAYS_HOSPITALIZED)) if facts.has(Slot.DAYS_HOSPITALIZED) else None  # type: ignore[arg-type]
    spans: list[tuple[int, date, date]] = []
    for i, d in enumerate(docs):
        # admission / discharge vs days (inclusive calendar days, the convention used for facts)
        if d.service_start and d.service_end:
            n = (d.service_end - d.service_start).days + 1
            if n < 1:
                out.append(DocumentCheck(code="DATES_VS_DAYS", detail=f"document {i}: discharge {d.service_end} precedes admission {d.service_start}", doc_index=[i]))
            else:
                spans.append((i, d.service_start, d.service_end))
                if d.days_hospitalized is not None and d.days_hospitalized != n:
                    out.append(DocumentCheck(code="DATES_VS_DAYS", detail=f"document {i}: {d.service_start}..{d.service_end} is {n} days but the document states {d.days_hospitalized}", doc_index=[i]))
                if stated_days is not None and stated_days != n and d.doc_type in (DocType.DISCHARGE_SUMMARY, DocType.MEDICAL_REPORT, DocType.INVOICE):
                    out.append(DocumentCheck(code="DATES_VS_DAYS", detail=f"document {i}: {n} days from its dates, {stated_days} days stated in the claim", doc_index=[i]))
        # invoice total vs line items
        if d.doc_type in (DocType.INVOICE, DocType.RECEIPT) and d.line_items:
            s = sum((li.amount for li in d.line_items), Decimal(0))
            tol = max(Decimal(1), d.total_amount * TOTAL_TOLERANCE)
            if abs(s - d.total_amount) > tol:
                out.append(DocumentCheck(code="INVOICE_TOTAL", detail=f"document {i}: line items sum to {s} but the total printed is {d.total_amount}", doc_index=[i]))
        # invoice vs the bill stated in the claim
        if d.doc_type == DocType.INVOICE and facts.has(Slot.BILLED_AMOUNT) and d.total_amount:
            billed = Decimal(str(facts.get(Slot.BILLED_AMOUNT)))
            if abs(billed - d.total_amount) > max(Decimal(1), billed * TOTAL_TOLERANCE):
                out.append(DocumentCheck(code="BILL_VS_STATED", detail=f"document {i}: invoice total {d.total_amount} differs from the stated bill {billed}", doc_index=[i]))
        # name
        if not d.patient_name_matches_policyholder:
            out.append(DocumentCheck(code="NAME_MISMATCH", detail=f"document {i}: the patient or subject name is not the policyholder's", doc_index=[i]))
        if d.suspicious or d.contains_instruction_like_text:
            out.append(DocumentCheck(code="DOCUMENT_SUSPICIOUS", detail=f"document {i}: hidden or instruction-like text was found; the insurer will ask for a re-issued original", doc_index=[i]))
        # diagnosis codes vs cause
        if d.diagnosis_codes and facts.has(Slot.IS_ACCIDENT):
            injury = [c for c in d.diagnosis_codes if c[:1].upper() in INJURY_CHAPTERS]
            accident = bool(facts.get(Slot.IS_ACCIDENT))
            if accident and not injury:
                out.append(DocumentCheck(code="DIAGNOSIS_VS_CAUSE", detail=f"document {i}: the claim states an accident but the codes {d.diagnosis_codes} describe illness, not injury", doc_index=[i]))
            if not accident and injury and len(injury) == len(d.diagnosis_codes):
                out.append(DocumentCheck(code="DIAGNOSIS_VS_CAUSE", detail=f"document {i}: the claim states illness but every code {injury} is an injury or external-cause code", doc_index=[i]))
    # the same stay must have the same dates across documents
    for (i, s1, e1), (j, s2, e2) in zip(spans, spans[1:]):
        if (s1, e1) != (s2, e2):
            out.append(DocumentCheck(code="DATES_ACROSS_DOCUMENTS", detail=f"documents {i} and {j}: {s1}..{e1} vs {s2}..{e2}", doc_index=[i, j]))
    # de-duplicate identical (code, detail)
    seen: set[tuple[str, str]] = set()
    uniq = []
    for c in out:
        if (c.code, c.detail) not in seen:
            seen.add((c.code, c.detail))
            uniq.append(c)
    return uniq


# --------------------------------------------------------------------------- clause isolation
def _isolated_view(policy: PolicyRecord, clause_id: str) -> PolicyRecord:
    keep = [t for t in policy.tuples if t.relation in GRANT_RELATIONS or t.id == clause_id]
    return policy.model_copy(update={"tuples": keep})


def _evidence(policy: PolicyRecord, clause_id: Optional[str]) -> str:
    t = policy.tuple_index().get(clause_id or "")
    return t.evidence.text if t else ""


def clause_grounds(policy: PolicyRecord, facts: ScenarioFacts, *, as_of: date, portfolio: Optional[list[PolicyRecord]] = None,
                   facts_by_policy: Optional[dict[str, ScenarioFacts]] = None) -> tuple[list[DenialGround], list[Slot]]:
    """One ground per denial-capable clause that denies on its own; open slots the isolated
    views could not resolve."""
    grounds: list[DenialGround] = []
    open_slots: list[Slot] = []
    facts = pf.with_policy_defaults(policy, facts)
    for t in policy.tuples:
        if t.relation not in DENIAL_RELATIONS:
            continue
        if t.relation == Relation.HAS_PERIOD and (t.qualifiers.period_kind in (PeriodKind.FILING_DEADLINE, PeriodKind.NOTICE_DEADLINE, PeriodKind.FREE_LOOK) or t.object in ("FILING_DEADLINE", "NOTICE_DEADLINE", "FREE_LOOK")):
            continue  # deadlines are evaluated from the calendar, not by the coverage solver
        view = _isolated_view(policy, t.id)
        r = pf.decide_mapped(view, facts)
        if r.verdict == Verdict.CLARIFY:
            for s in r.missing_slots or ([r.clarification.slot] if r.clarification else []):
                if s not in open_slots:
                    open_slots.append(s)
            continue
        if r.verdict != Verdict.DENIED or t.id not in r.fired_tuple_ids:
            continue
        code = pf.normalise_denial_code(r, view) or r.denial_code or "DENIED"
        rec = find_recourse(view, facts, as_of=as_of, portfolio=portfolio, facts_by_policy=facts_by_policy)
        best = rec.best()
        grounds.append(DenialGround(code=code, clause_id=t.id, evidence_text=t.evidence.text, fixable=best is not None, recourse=best,
                                    weight=ground_weight(code), source="clause"))
    return grounds, open_slots


# --------------------------------------------------------------------------- main
def adjudicate_like_insurer(
    policy: PolicyRecord,
    facts: ScenarioFacts,
    documents: list[Union[ClaimDocExtract, dict]],
    *,
    as_of: date,
    documents_present: Optional[list[str]] = None,
    portfolio: Optional[list[PolicyRecord]] = None,
    facts_by_policy: Optional[dict[str, ScenarioFacts]] = None,
) -> TwinReport:
    """Every ground an assessor would raise, with evidence, fixability and recourse.

    `documents` are quarantined extracts of the uploaded claim documents (typed fields only);
    `documents_present` adds document codes the claimant says they hold. Scores follow the
    module docstring."""
    docs = [_as_extract(d) for d in documents]
    facts = pf.with_policy_defaults(policy, facts)
    required, _ = pf.required_documents(policy, facts)
    present = documents_satisfied(required, docs, documents_present or [])
    readiness = pf.claim_readiness(policy, facts, present, as_of)
    grounds, open_slots = clause_grounds(policy, facts, as_of=as_of, portfolio=portfolio, facts_by_policy=facts_by_policy)

    # the solver's own verdict decides the headline; the isolated views explain every ground
    verdict = readiness.verdict
    if verdict.verdict == Verdict.DENIED and not any(g.clause_id in verdict.fired_tuple_ids for g in grounds):
        code = pf.normalise_denial_code(verdict, policy) or verdict.denial_code or "DENIED"
        cid = verdict.fired_tuple_ids[0] if verdict.fired_tuple_ids else None
        rec = find_recourse(policy, facts, as_of=as_of, portfolio=portfolio, facts_by_policy=facts_by_policy)
        grounds.append(DenialGround(code=code, clause_id=cid, evidence_text=_evidence(policy, cid), fixable=rec.best() is not None,
                                    recourse=rec.best(), weight=ground_weight(code), source="clause"))
    if verdict.verdict == Verdict.NOT_APPLICABLE and not grounds:
        rec = find_recourse(policy, facts, as_of=as_of, portfolio=portfolio, facts_by_policy=facts_by_policy)
        grounds.append(DenialGround(code="NOT_APPLICABLE", clause_id=None, evidence_text="no clause of this policy grants the event",
                                    fixable=rec.best() is not None, recourse=rec.best(), weight=1.0, source="clause"))

    # filing deadline
    if readiness.days_left is not None and readiness.days_left < 0:
        code = "LATE_FILING" if readiness.late_effect in (None, "REJECT") else "LATE_FILING_DISCRETIONARY"
        grounds.append(DenialGround(code=code, clause_id=readiness.deadline_tuple_id, evidence_text=_evidence(policy, readiness.deadline_tuple_id),
                                    fixable=False, weight=ground_weight(code), source="deadline"))

    # documents
    if readiness.missing_documents:
        act = document_recourse(policy, facts, present)
        opt = None
        if act is not None:
            opt = RecourseOption(policy_id=policy.id, actions=[act], verdict=verdict.verdict, payable=verdict.payable, currency=verdict.currency,
                                 clause_ids=[], cost=act.cost, description=act.description)
        grounds.append(DenialGround(code="INCOMPLETE_DOCS", clause_id=None, evidence_text="required: " + ", ".join(readiness.missing_documents),
                                    fixable=True, recourse=opt, weight=ground_weight("INCOMPLETE_DOCS"), source="documents"))

    # consistency
    checks = consistency_checks(facts, docs)
    for c in checks:
        fix = RecourseAction(kind=ActionKind.PROVIDE_DOCUMENTS, cost=COST_TABLE[ActionKind.PROVIDE_DOCUMENTS], description=_fix_text(c.code))
        opt = RecourseOption(policy_id=policy.id, actions=[fix], verdict=verdict.verdict, payable=verdict.payable, currency=verdict.currency,
                             clause_ids=[], cost=fix.cost, description=fix.description)
        grounds.append(DenialGround(code=c.code, clause_id=None, evidence_text=c.detail, fixable=c.code != "DIAGNOSIS_VS_CAUSE", recourse=opt if c.code != "DIAGNOSIS_VS_CAUSE" else None,
                                    weight=ground_weight(c.code), source="consistency"))

    return TwinReport(
        policy_id=policy.id, verdict=verdict.verdict, denial_code=pf.normalise_denial_code(verdict, policy), grounds=grounds, open_slots=open_slots,
        checks=checks, readiness=readiness, documents_present=present,
        readiness_score=score(grounds), after_fix_score=score(grounds, {g.code for g in grounds if g.fixable}),
        payable=verdict.payable, currency=verdict.currency,
    )


def _fix_text(code: str) -> str:
    return {
        "INVOICE_TOTAL": "Ask the hospital for a corrected itemised invoice whose line items add up to the printed total.",
        "BILL_VS_STATED": "Submit the invoice as printed; the claimed amount must equal the invoice total.",
        "DATES_VS_DAYS": "Ask the hospital to re-issue the document with the admission and discharge dates that match the stay.",
        "DATES_ACROSS_DOCUMENTS": "Ask the hospital to align the admission and discharge dates across the invoice and the medical resume.",
        "NAME_MISMATCH": "Confirm the patient is an insured person under this policy (dependant schedule) and attach relationship proof.",
        "DOCUMENT_SUSPICIOUS": "Obtain a clean, re-issued original from the issuer.",
        "DIAGNOSIS_VS_CAUSE": "The diagnosis codes and the stated cause disagree; the assessor will decide on the medical record, which cannot be changed.",
    }.get(code, "Provide a corrected document.")


__all__ = ["DenialGround", "DocumentCheck", "GROUND_WEIGHTS", "TwinReport", "adjudicate_like_insurer", "clause_grounds", "consistency_checks",
           "documents_satisfied", "ground_weight", "score", "score_after"]
