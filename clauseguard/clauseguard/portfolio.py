"""Portfolio reasoning over typed clause tuples: gap/overlap matrix, coordination-of-benefits
payer order and claim readiness. Pure Python, deterministic; the LLM never runs here.

Rules follow the Indonesian coordination-of-benefits rule pack (`clauseguard/rulepacks.py`). The payer order and the
statutory layers are data in `rulepacks.py` (jurisdiction "ID" is the default and every statutory
step is tagged with its rule id); the amounts come from the claim allocation optimizer in
`allocation.py`. Statutory amounts (Jasa Raharja, INA-CBG) are sandbox stubs and every step that
uses them says "verify with insurer".
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from pydantic import Field

from .schema import (
    Basis,
    ClauseTuple,
    Condition,
    EventCode,
    MissingSlot,
    PeriodKind,
    PolicyRecord,
    Qualifiers,
    Relation,
    ScenarioFacts,
    Slot,
    Strict,
    TimeUnit,
    TraceStep,
    Verdict,
    VerdictResult,
    WindowFrom,
)
from .agent.derive import filing_deadline
from .solver import decide

# --------------------------------------------------------------------------- constants
STATUTORY_TYPES = {"jasa_raharja", "social_bpjs_kes", "social_bpjs_tk"}
GROUP_TYPES = {"group_health", "group_life", "group_accident"}
ACTIVE_STATUSES = {"active", "grace"}

BASE_DOCUMENTS = [
    "CLAIM_FORM",
    "DOCTOR_STATEMENT",
    "ITEMISED_BILL",
    "DISCHARGE_SUMMARY",
    "ID_CARD",
    "POLICY_NUMBER",
    "BANK_ACCOUNT",
]
ACCIDENT_DOCUMENTS = ["POLICE_REPORT", "ACCIDENT_CHRONOLOGY"]
TRAFFIC_DOCUMENTS = ["JASA_RAHARJA_FORM", "POLICE_REPORT"]
WORK_ACCIDENT_DOCUMENTS = ["EMPLOYER_REPORT", "JKK_FORM"]
DEATH_DOCUMENTS = ["DEATH_CERT", "BENEFICIARY_ID", "RELATIONSHIP_PROOF"]
CI_DOCUMENTS = ["PATHOLOGY_REPORT", "SPECIALIST_CONFIRMATION"]
SECOND_PAYER_DOCUMENTS = ["LEGALISED_BILL_COPY", "COB_LETTER"]

FILING_WARNING_DAYS = 14

# anchor of a filing deadline -> the "days since" slot the facts carry
FROM_EVENT_SLOT = {
    WindowFrom.DISCHARGE: Slot.DAYS_SINCE_DISCHARGE,
    WindowFrom.TREATMENT_END: Slot.DAYS_SINCE_TREATMENT_END,
    WindowFrom.EVENT: Slot.DAYS_SINCE_EVENT,
    WindowFrom.ACCIDENT: Slot.DAYS_SINCE_EVENT,
    WindowFrom.DEATH: Slot.DAYS_SINCE_DEATH,
    WindowFrom.DIAGNOSIS: Slot.DAYS_SINCE_DIAGNOSIS,
}
# treatment end falls back to discharge when only discharge is known
FROM_EVENT_FALLBACK = {WindowFrom.TREATMENT_END: Slot.DAYS_SINCE_DISCHARGE, WindowFrom.EVENT: Slot.DAYS_SINCE_DISCHARGE}


# --------------------------------------------------------------------------- models
class CoverageCell(Strict):
    person_id: str
    peril: EventCode
    policy_id: str
    basis: Basis
    limit_text: str
    tuple_ids: list[str] = Field(default_factory=list)


class PayerStep(Strict):
    order: int
    payer_policy_id: str
    expected_amount: Optional[Decimal] = None
    basis: Basis
    documents: list[str] = Field(default_factory=list)
    deadline: Optional[date] = None
    tuple_ids: list[str] = Field(default_factory=list)
    uncertain_slots: list[Slot] = Field(default_factory=list)
    # additive fields (not in the minimal contract, display/structured checks only)
    status: str = Field(default="PAYER", pattern=r"^(PAYER|PARALLEL|UNCERTAIN|NOT_CLAIMABLE)$")
    denial_code: Optional[str] = None
    note: Optional[str] = Field(default=None, max_length=300)
    currency: str = "IDR"
    jurisdiction_rule: Optional[str] = Field(default=None, max_length=80)


class ReadinessReport(Strict):
    verdict: VerdictResult
    deadline: Optional[date] = None
    days_left: Optional[int] = None
    late_effect: Optional[str] = None
    required_documents: list[str] = Field(default_factory=list)
    missing_documents: list[str] = Field(default_factory=list)
    denial_codes: list[str] = Field(default_factory=list)
    deadline_tuple_id: Optional[str] = None
    event_date: Optional[date] = None


# --------------------------------------------------------------------------- helpers
def _fmt_idr(v: Decimal | int | float, cur: str = "IDR") -> str:
    return f"{cur} {int(Decimal(v)):,}"


def limit_text(q: Qualifiers, policy: PolicyRecord) -> str:
    """Human-readable limit derived from typed qualifiers only (never from free text)."""
    cur = q.currency or policy.currency
    parts: list[str] = []
    if q.per_day_limit is not None:
        s = f"{_fmt_idr(q.per_day_limit, cur)}/day"
        cap = q.max_days_per_year or q.max_days
        if cap:
            s += f", max {cap} days" + ("/year" if q.max_days_per_year else "")
        parts.append(s)
    if q.per_case_limit is not None:
        parts.append(f"{_fmt_idr(q.per_case_limit, cur)}/case")
    if q.per_week_amount is not None:
        s = f"{_fmt_idr(q.per_week_amount, cur)}/week"
        if q.max_weeks:
            s += f", max {q.max_weeks} weeks"
        parts.append(s)
    if q.amount is not None:
        parts.append(_fmt_idr(q.amount, cur))
    elif q.pct_of_sum_assured is not None and policy.sum_assured is not None:
        parts.append(f"{q.pct_of_sum_assured:g}% of sum assured ({_fmt_idr(policy.sum_assured, cur)})")
    if q.multiplier_of_daily is not None:
        parts.append(f"{q.multiplier_of_daily:g}x daily benefit")
    if q.annual_cap is not None:
        parts.append(f"annual cap {_fmt_idr(q.annual_cap, cur)}")
    if q.lifetime_cap is not None:
        parts.append(f"lifetime cap {_fmt_idr(q.lifetime_cap, cur)}")
    if q.copay_pct:
        s = f"co-payment {q.copay_pct:g}%"
        if q.copay_cap:
            s += f" (cap {_fmt_idr(q.copay_cap, cur)})"
        parts.append(s)
    if q.copay_amount:
        parts.append(f"co-payment {_fmt_idr(q.copay_amount, cur)}")
    if q.copay_cap and not q.copay_pct:
        parts.append(f"out-of-pocket cap {_fmt_idr(q.copay_cap, cur)}")
    if q.deductible_amount:
        parts.append(f"deductible {_fmt_idr(q.deductible_amount, cur)}")
    if q.deductible_days:
        parts.append(f"deductible {q.deductible_days} days")
    if not parts and policy.sum_assured is not None:
        parts.append(f"sum assured {_fmt_idr(policy.sum_assured, cur)}")
    return "; ".join(parts) if parts else "limit not stated in the extracted clauses"


def cell_basis(t: ClauseTuple, policy: PolicyRecord) -> Basis:
    return t.qualifiers.basis or policy.basis


def is_group(policy: PolicyRecord) -> bool:
    return policy.product_type in GROUP_TYPES or policy.product_type.startswith("group")


def is_statutory(policy: PolicyRecord) -> bool:
    return policy.product_type in STATUTORY_TYPES


def other_insurance_kind(policy: PolicyRecord) -> Optional[str]:
    for t in policy.tuples:
        if t.qualifiers.other_insurance:
            return t.qualifiers.other_insurance
    return None


def normalise_denial_code(result: VerdictResult, policy: PolicyRecord) -> Optional[str]:
    """Map solver codes to the claims-desk denial vocabulary using the
    typed conditions of the fired tuple, never its text."""
    code = result.denial_code
    if not code:
        return None
    if code.startswith("EXCLUSION_"):
        idx = policy.tuple_index()
        for tid in result.fired_tuple_ids:
            t = idx.get(tid)
            if t is None or t.relation != Relation.EXCLUDES:
                continue
            slots = {c.slot for c in t.qualifiers.applies_if}
            if Slot.DIAGNOSIS_BEFORE_EFFECTIVE in slots or t.object == EventCode.PRE_EXISTING_CONDITION.value:
                return "PRE_EXISTING"
            if Slot.LICENSE_VALID in slots or t.object == EventCode.NO_VALID_LICENSE.value:
                return "NO_VALID_LICENSE"
            if Slot.INTOXICATED in slots or t.object == EventCode.INTOXICATION.value:
                return "INTOXICATION"
            if t.object == EventCode.COMMERCIAL_MOTORCYCLING.value:
                return "COMMERCIAL_MOTORCYCLING"
        return code
    if code == "CONDITION_NOT_MET":
        idx = policy.tuple_index()
        for tid in result.fired_tuple_ids:
            t = idx.get(tid)
            if t is not None and t.relation == Relation.CONDITIONED_ON and any(c.slot == Slot.LICENSE_VALID for c in t.qualifiers.applies_if):
                return "NO_VALID_LICENSE"
            if t is not None and t.relation == Relation.CONDITIONED_ON and any(c.slot == Slot.PREMIUM_STATUS for c in t.qualifiers.applies_if):
                return "LAPSED"
        return code
    if code.startswith("TERMINATED_LAPSE") or code == "TERMINATED_GROUP_TERMINATION":
        return "LAPSED" if "LAPSE" in code and "GROUP" not in code else "GROUP_TERMINATED"
    return code


def covers_event(policy: PolicyRecord, event: str) -> bool:
    return any(t.object == event for t in policy.tuples_by(Relation.COVERS))


def event_for_policy(policy: PolicyRecord, facts: ScenarioFacts) -> Optional[str]:
    """Pick the event vocabulary a policy uses for the scenario (e.g. an accident admission is
    HOSPITALIZATION for a hospital-cash plan but ACCIDENT_MEDICAL for a PA policy)."""
    if not facts.has(Slot.EVENT):
        return None
    ev = str(facts.get(Slot.EVENT))
    if covers_event(policy, ev):
        return ev
    accident = facts.has(Slot.IS_ACCIDENT) and bool(facts.get(Slot.IS_ACCIDENT))
    if accident and ev in ("HOSPITALIZATION", "OUTPATIENT", "SURGERY", "ICU") and covers_event(policy, "ACCIDENT_MEDICAL"):
        return "ACCIDENT_MEDICAL"
    if accident and ev == "DEATH" and covers_event(policy, "ACCIDENTAL_DEATH"):
        return "ACCIDENTAL_DEATH"
    return ev


def with_policy_defaults(policy: PolicyRecord, facts: ScenarioFacts) -> ScenarioFacts:
    """Bind slots that follow from the policy record itself (status -> premium status / in force)
    so the solver does not ask the user what the record already states."""
    f = facts
    if not f.has(Slot.PREMIUM_STATUS):
        if policy.status == "active":
            f = f.bind(Slot.PREMIUM_STATUS, "PAID")
        elif policy.status in ("lapsed", "cancelled", "terminated"):
            f = f.bind(Slot.PREMIUM_STATUS, "LAPSED")
    if not f.has(Slot.IN_FORCE):
        f = f.bind(Slot.IN_FORCE, policy.status in ACTIVE_STATUSES)
    return f


def decide_mapped(policy: PolicyRecord, facts: ScenarioFacts) -> VerdictResult:
    """solver.decide with the policy's event vocabulary and record-level defaults bound."""
    ev = event_for_policy(policy, facts)
    f = with_policy_defaults(policy, facts)
    if ev is not None and (not f.has(Slot.EVENT) or ev != f.get(Slot.EVENT)):
        f = f.bind(Slot.EVENT, ev)
    if ev is not None and not covers_event(policy, ev) and not any(x.object == ev for x in policy.tuples_by(Relation.EXCLUDES)):
        # closed world: no clause of this policy governs the event at all (the solver would still
        # run period checks such as grace/lapse, which are irrelevant to an event it never covers)
        r = VerdictResult(policy_id=policy.id, verdict=Verdict.NOT_APPLICABLE)
        r.trace.append(TraceStep(rule="closed_world", result="NOT_APPLICABLE", detail=f"no clause governs event {ev}"))
        return r
    return decide(policy, f)


def _holds_or_unknown(conds: list[Condition], facts: ScenarioFacts) -> bool:
    """Condition evaluation that treats unbound slots as 'might apply' (for document lists)."""
    from .solver import eval_condition

    for c in conds:
        try:
            if not eval_condition(c, facts):
                return False
        except MissingSlot:
            continue
    return True


def required_documents(policy: PolicyRecord, facts: ScenarioFacts, *, second_indemnity_payer: bool = False) -> tuple[list[str], list[str]]:
    """Documents from REQUIRES_DOCUMENT tuples (typed codes), with base/per-event additions
    from the default checklist per product type when the policy lists none. Returns (docs, tuple_ids)."""
    docs: list[str] = []
    tids: list[str] = []
    ev = str(facts.get(Slot.EVENT)) if facts.has(Slot.EVENT) else None
    tuples = policy.tuples_by(Relation.REQUIRES_DOCUMENT)
    events = {e.value for e in EventCode}
    if ev is not None:
        wanted = {ev, event_for_policy(policy, facts) or ev}
        if any(t.object in wanted for t in tuples):
            tuples = [t for t in tuples if t.object not in events or t.object in wanted]  # a checklist keyed to another event does not apply
    for t in tuples:
        if t.head != policy.id and t.head not in ("*", ev or ""):
            # tuple scoped to an event code: only when it matches
            if t.head != ev:
                continue
        if not _holds_or_unknown(t.qualifiers.applies_if, facts):
            continue
        codes = t.qualifiers.document_codes or [t.object]
        for c in codes:
            if c not in docs:
                docs.append(c)
        tids.append(t.id)
    if not docs:
        docs = list(BASE_DOCUMENTS)
    accident = facts.has(Slot.IS_ACCIDENT) and bool(facts.get(Slot.IS_ACCIDENT))
    cause = str(facts.get(Slot.CAUSE)) if facts.has(Slot.CAUSE) else ""
    extra: list[str] = []
    if accident:
        extra += ACCIDENT_DOCUMENTS
    traffic = cause == "ACCIDENT_TRAFFIC" or (facts.has(Slot.VEHICLES_INVOLVED) and int(facts.get(Slot.VEHICLES_INVOLVED) or 0) >= 2)
    if traffic:
        extra += TRAFFIC_DOCUMENTS if policy.product_type == "jasa_raharja" else ["POLICE_REPORT"]
    if facts.has(Slot.WORK_RELATED) and bool(facts.get(Slot.WORK_RELATED)) and accident and policy.product_type == "social_bpjs_tk":
        extra += WORK_ACCIDENT_DOCUMENTS
    if ev in ("DEATH", "ACCIDENTAL_DEATH"):
        extra += DEATH_DOCUMENTS
    if ev in ("CRITICAL_ILLNESS", "TERMINAL_ILLNESS"):
        extra += CI_DOCUMENTS
    if second_indemnity_payer:
        extra += SECOND_PAYER_DOCUMENTS
    for c in extra:
        if c not in docs:
            docs.append(c)
    return docs, tids


def filing_deadline_tuple(policy: PolicyRecord) -> Optional[ClauseTuple]:
    for t in policy.tuples_by(Relation.HAS_PERIOD):
        q = t.qualifiers
        if q.period_kind == PeriodKind.FILING_DEADLINE or t.object == PeriodKind.FILING_DEADLINE.value:
            return t
    return None


def _event_date_from_facts(anchor: WindowFrom, facts: ScenarioFacts, as_of: date) -> Optional[date]:
    slot = FROM_EVENT_SLOT.get(anchor)
    if slot is None:
        return None
    if not facts.has(slot):
        slot = FROM_EVENT_FALLBACK.get(anchor)
        if slot is None or not facts.has(slot):
            return None
    try:
        return as_of - timedelta(days=int(facts.get(slot)))
    except (TypeError, ValueError):
        return None


def compute_deadline(policy: PolicyRecord, facts: ScenarioFacts, as_of: date) -> tuple[Optional[date], Optional[str], Optional[str], Optional[date]]:
    """(deadline, late_effect, tuple_id, event_date) from the FILING_DEADLINE tuple."""
    t = filing_deadline_tuple(policy)
    if t is None:
        return None, None, None, None
    q = t.qualifiers
    days = q.deadline_days if q.deadline_days is not None else (q.window_len if q.window_unit in (None, "DAYS") else None)
    if days is None:
        return None, q.late_effect, t.id, None
    anchor = q.from_event or q.window_from or WindowFrom.DISCHARGE
    ev_date = _event_date_from_facts(anchor, facts, as_of)
    if ev_date is None:
        return None, q.late_effect, t.id, None
    return filing_deadline(ev_date, int(days)), q.late_effect, t.id, ev_date


def add_months(d: date, n: int) -> date:
    y, m = d.year, d.month + n
    y += (m - 1) // 12
    m = (m - 1) % 12 + 1
    return date(y, m, min(d.day, 28))


def exclusion_window_end(policy: PolicyRecord, t: ClauseTuple) -> Optional[date]:
    """Calendar end of a tuple's time window anchored at the policy's effective/issue date."""
    q = t.qualifiers
    anchor = policy.effective_date if (q.window_from in (None, WindowFrom.EFFECTIVE)) else (policy.issue_date or policy.effective_date)
    if q.window_from == WindowFrom.REINSTATEMENT and policy.reinstatement_date:
        anchor = policy.reinstatement_date
    if anchor is None or q.window_len is None:
        return None
    unit = q.window_unit or TimeUnit.MONTHS
    n = int(q.window_len)
    if unit == TimeUnit.MONTHS:
        return add_months(anchor, n)
    if unit == TimeUnit.DAYS:
        return anchor + timedelta(days=n)
    return date(anchor.year + n, anchor.month, anchor.day)


# --------------------------------------------------------------------------- gap / overlap
def gap_overlap(
    policies: list[PolicyRecord],
    persons: list[str],
    perils: list[EventCode],
    *,
    insured: Optional[dict[str, list[str]]] = None,
    liabilities: Optional[Decimal] = None,
    liabilities_person: Optional[str] = None,
) -> dict:
    """Matrix person x peril x policy with limit text; overlaps (same peril, >=2 INDEMNITY
    policies); stackable (FIXED_BENEFIT); gaps (perils nobody covers), plus a quantified life
    gap when `liabilities` is given. `insured` maps policy_id -> person ids (default: all)."""
    insured = insured or {}
    cells: list[CoverageCell] = []
    notes: list[dict] = []
    for p in policies:
        if p.status not in ACTIVE_STATUSES:
            notes.append({"policy_id": p.id, "kind": "INACTIVE", "status": p.status})
        people = insured.get(p.id, persons)
        for t in p.tuples_by(Relation.COVERS):
            try:
                peril = EventCode(t.object)
            except ValueError:
                continue
            if peril not in perils:
                continue
            for person in people:
                if person not in persons:
                    continue
                cells.append(
                    CoverageCell(
                        person_id=person, peril=peril, policy_id=p.id, basis=cell_basis(t, p),
                        limit_text=limit_text(t.qualifiers, p), tuple_ids=[t.id],
                    )
                )
        for t in p.tuples_by(Relation.TERMINATES_IF):
            notes.append({"policy_id": p.id, "kind": "TERMINATES_IF", "object": t.object, "tuple_id": t.id})
        for t in p.tuples_by(Relation.EXCLUDES):
            slots = {c.slot for c in t.qualifiers.applies_if}
            if Slot.DIAGNOSIS_BEFORE_EFFECTIVE in slots or t.object == EventCode.PRE_EXISTING_CONDITION.value:
                until = exclusion_window_end(p, t)
                notes.append({"policy_id": p.id, "kind": "PRE_EXISTING_EXCLUDED", "until": until.isoformat() if until else None, "tuple_id": t.id})

    matrix: dict[str, dict[str, list[dict]]] = {person: {peril.value: [] for peril in perils} for person in persons}
    for c in cells:
        matrix[c.person_id][c.peril.value].append(c.model_dump(mode="json"))

    statutory_ids = {p.id: is_statutory(p) for p in policies}
    active_ids = {p.id for p in policies if p.status in ACTIVE_STATUSES}  # a lapsed policy stays in the matrix (with an INACTIVE note) but is not cover
    overlaps: list[dict] = []
    stackable: list[dict] = []
    gaps: list[dict] = []
    for person in persons:
        for peril in perils:
            cs = [c for c in cells if c.person_id == person and c.peril == peril and c.policy_id in active_ids]
            indemnity = sorted({c.policy_id for c in cs if c.basis == Basis.INDEMNITY and not statutory_ids.get(c.policy_id)})
            fixed = sorted({c.policy_id for c in cs if c.basis == Basis.FIXED_BENEFIT})
            if len(indemnity) >= 2:
                overlaps.append({"person_id": person, "peril": peril.value, "policy_ids": indemnity,
                                 "note": "indemnity policies do not stack: only the remainder after the first payer is recoverable"})
            if fixed:
                stackable.append({"person_id": person, "peril": peril.value, "policy_ids": fixed,
                                  "note": "fixed-benefit cover pays its stated amount regardless of other policies"})
            if not cs:
                gaps.append({"person_id": person, "peril": peril.value})

    life_gap: Optional[dict] = None
    if liabilities is not None:
        who = liabilities_person or (persons[0] if persons else None)
        death_cover = Decimal(0)
        death_policies: list[str] = []
        for p in policies:
            people = insured.get(p.id, persons)
            if who not in people or p.status not in ACTIVE_STATUSES:
                continue
            for t in p.tuples_by(Relation.COVERS):
                if t.object != EventCode.DEATH.value:
                    continue
                q = t.qualifiers
                amt = q.amount
                if amt is None and q.pct_of_sum_assured is not None and p.sum_assured is not None:
                    amt = p.sum_assured * Decimal(str(q.pct_of_sum_assured)) / Decimal(100)
                if amt is None and p.sum_assured is not None:
                    amt = p.sum_assured
                if amt is not None:
                    death_cover += amt
                    death_policies.append(p.id)
        conditional = [n for n in notes if n["kind"] == "TERMINATES_IF" and n["policy_id"] in death_policies]
        life_gap = {
            "person_id": who,
            "liabilities": str(liabilities),
            "death_cover": str(death_cover),
            "gap": str(max(Decimal(0), Decimal(liabilities) - death_cover)),
            "death_policy_ids": death_policies,
            "conditional_on": conditional,
        }
    return {"matrix": matrix, "cells": [c.model_dump(mode="json") for c in cells], "overlaps": overlaps,
            "stackable": stackable, "gaps": gaps, "notes": notes, "life_gap": life_gap}


# --------------------------------------------------------------------------- COB
def _money(v) -> Decimal:
    return Decimal(str(v)) if v is not None else Decimal(0)


def cob_plan(
    policies: list[PolicyRecord],
    facts: ScenarioFacts,
    jurisdiction: str = "ID",
    *,
    as_of: Optional[date] = None,
    bill_breakdown: Optional[dict[str, Decimal]] = None,
    bpjs_tk_member: bool = False,
    facts_by_policy: Optional[dict[str, ScenarioFacts]] = None,
) -> list[PayerStep]:
    """Deterministic payer order (rule pack layers), computed by the claim allocation
    optimizer (`allocation.optimize_allocation`) under the jurisdiction's rule pack:

    1. statutory (Jasa Raharja if traffic accident with >=2 vehicles; BPJS TK JKK if work
       related; BPJS Kesehatan if active + partner facility + referral/emergency)
    2. commercial INDEMNITY: group before individual, other-insurance NONE before PRO_RATA
       before EXCESS; deductible -> co-payment -> inner limits -> annual cap, never above the bill
    3. FIXED_BENEFIT policies in parallel
    Policies the solver denies are listed as NOT_CLAIMABLE with the denial code; CLARIFY
    outcomes become UNCERTAIN steps carrying the unbound slots and the amount the policy could
    still cover. `facts_by_policy` supplies policy-relative derived slots (days since that
    policy's effective date, pre-existing flag); `facts` carries the shared scenario (bill, days,
    cause). `bpjs_tk_member` is accepted for interface stability; JKK membership is read from the
    holdings (a `social_bpjs_tk` record). An unknown jurisdiction uses the GENERIC rule pack.
    """
    from .allocation import SILENT_CODES, BillBreakdown, optimize_allocation
    from .rulepacks import RULE_PACKS

    as_of = as_of or facts.as_of or date.today()
    currency = policies[0].currency if policies else "IDR"
    bill = BillBreakdown.from_facts(facts, bill_breakdown, currency=currency)
    pack = jurisdiction if jurisdiction in RULE_PACKS else "GENERIC"
    res = optimize_allocation(policies, facts, bill, rule_pack=pack, as_of=as_of, facts_by_policy=facts_by_policy)
    paying = {s.policy_id: s for s in res.steps}
    uncertain = {u.policy_id: u for u in res.uncertain}
    excluded = {e.policy_id: e for e in res.excluded}

    steps: list[PayerStep] = []

    def push(**kw) -> PayerStep:
        st = PayerStep(order=len(steps) + 1, currency=currency, **kw)
        steps.append(st)
        return st

    for pid in res.evaluation_order:
        if pid in paying:
            s = paying[pid]
            push(payer_policy_id=pid, expected_amount=s.amount, basis=s.basis, documents=s.documents_required, deadline=s.filing_deadline,
                 tuple_ids=s.clause_ids, status="PAYER" if s.basis == Basis.INDEMNITY else "PARALLEL", note=(s.note or None) and s.note[:300],
                 jurisdiction_rule=s.rule_id)
        elif pid in uncertain:
            u = uncertain[pid]
            push(payer_policy_id=pid, expected_amount=u.potential_amount, basis=u.basis, documents=u.documents_required, deadline=u.filing_deadline,
                 tuple_ids=u.clause_ids, uncertain_slots=u.slots, status="UNCERTAIN", note=(u.note or None) and u.note[:300], jurisdiction_rule=u.rule_id)
        elif pid in excluded:
            e = excluded[pid]
            if e.code in SILENT_CODES and not e.rule_id:
                continue  # no clause of this commercial policy governs the event: not a payer, not a denial
            push(payer_policy_id=pid, expected_amount=Decimal(0), basis=e.basis or Basis.INDEMNITY, status="NOT_CLAIMABLE", denial_code=e.code,
                 tuple_ids=e.clause_ids, deadline=e.filing_deadline, note=(e.note or None) and e.note[:300], jurisdiction_rule=e.rule_id)

    # ---- filing warnings
    for st in steps:
        if st.deadline is not None and st.status in ("PAYER", "PARALLEL", "UNCERTAIN"):
            left = (st.deadline - as_of).days
            if left < FILING_WARNING_DAYS:
                warn = f"filing deadline {st.deadline.isoformat()} is {left} days away" if left >= 0 else f"filing deadline {st.deadline.isoformat()} has passed"
                st.note = (f"{st.note}; {warn}" if st.note else warn)[:300]
    return steps


# --------------------------------------------------------------------------- readiness
def claim_readiness(policy: PolicyRecord, facts: ScenarioFacts, documents_present: list[str], as_of: date) -> ReadinessReport:
    """Coverage verdict + filing deadline + document checklist + deterministic denial checks
    (LATE_FILING, INCOMPLETE_DOCS, LAPSED and the solver's code)."""
    result = decide_mapped(policy, facts) if facts.has(Slot.EVENT) else VerdictResult(policy_id=policy.id, verdict=Verdict.CLARIFY, missing_slots=[Slot.EVENT])
    deadline, late_effect, tid, ev_date = compute_deadline(policy, facts, as_of)
    days_left = (deadline - as_of).days if deadline else None
    docs, _ = required_documents(policy, facts)
    present = {d.strip().upper() for d in documents_present}
    missing = [d for d in docs if d.upper() not in present]
    codes: list[str] = []
    nc = normalise_denial_code(result, policy)
    if result.verdict == Verdict.DENIED and nc:
        codes.append(nc)
    if policy.status not in ACTIVE_STATUSES and "LAPSED" not in codes:
        codes.append("LAPSED")
    if facts.has(Slot.PREMIUM_STATUS) and facts.get(Slot.PREMIUM_STATUS) == "LAPSED" and "LAPSED" not in codes:
        codes.append("LAPSED")
    if days_left is not None and days_left < 0:
        codes.append("LATE_FILING" if late_effect in (None, "REJECT") else "LATE_FILING_DISCRETIONARY")
    if missing:
        codes.append("INCOMPLETE_DOCS")
    return ReadinessReport(verdict=result, deadline=deadline, days_left=days_left, late_effect=late_effect,
                           required_documents=docs, missing_documents=missing, denial_codes=codes,
                           deadline_tuple_id=tid, event_date=ev_date)
