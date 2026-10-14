"""Property tests over the date derivation, the solver and the allocation optimizer."""
from __future__ import annotations

import random
from datetime import date, timedelta
from decimal import Decimal

from hypothesis import HealthCheck, given, settings, strategies as st

from clauseguard.agent import derive
from clauseguard.agent.demo_fixtures import ci_chubb, gh_nusa, hcp_sompo, pa_chubb, tl_astra
from clauseguard.allocation import BillBreakdown, optimize_allocation
from clauseguard.portfolio import compute_deadline
from clauseguard.schema import (
    Basis,
    ClauseTuple,
    Condition,
    Evidence,
    Op,
    PolicyRecord,
    Qualifiers,
    Relation,
    ScenarioFacts,
    Slot,
    SourceTier,
    Verdict,
)
from clauseguard.solver import decide
from clauseguard.timeline import OpenClaim, build_timeline

SETTINGS = settings(max_examples=150, deadline=None, suppress_health_check=[HealthCheck.too_slow])
DATES = st.dates(min_value=date(1999, 1, 1), max_value=date(2101, 12, 31))
AS_OF = date(2026, 10, 14)


# --------------------------------------------------------------------------- 1. discharge derivation
@SETTINGS
@given(admission=DATES, n=st.integers(1, 400), m=st.integers(1, 400))
def test_discharge_is_monotone_in_days_and_round_trips(admission, n, m):
    assert derive.stay_days(admission, derive.discharge_on(admission, n)) == n
    assert derive.admission_on(derive.discharge_on(admission, n), n) == admission
    if n < m:
        assert derive.discharge_on(admission, n) < derive.discharge_on(admission, m)
    assert derive.discharge_on(admission, 1) == admission


@SETTINGS
@given(admission=DATES, n=st.integers(1, 400))
def test_event_date_derivation_matches_the_inclusive_convention(admission, n):
    facts = ScenarioFacts(values={Slot.DAYS_HOSPITALIZED: n}, as_of=AS_OF)
    dates, derived = derive.derive_event_dates({"admission": admission}, facts)
    assert dates["discharge"] == admission + timedelta(days=n - 1) and "discharge" in derived
    assert derive.derive_event_dates({"admission": admission, "discharge": admission}, facts)[1] == {}  # stated dates are never replaced


# --------------------------------------------------------------------------- 2. filing deadline
def _with_deadline(policy: PolicyRecord, days: int) -> PolicyRecord:
    tuples = [t.model_copy(update={"qualifiers": t.qualifiers.model_copy(update={"deadline_days": days})}) if t.id == "p_filing_60d" else t for t in policy.tuples]
    return policy.model_copy(update={"tuples": tuples})


@SETTINGS
@given(end=DATES, days=st.integers(1, 400), lead=st.integers(-120, 400))
def test_filing_deadline_is_treatment_end_plus_deadline_days(end, days, lead):
    as_of = end + timedelta(days=lead)
    policy = _with_deadline(hcp_sompo(), days)
    facts = ScenarioFacts(values={Slot.DAYS_SINCE_TREATMENT_END: (as_of - end).days}, as_of=as_of)
    deadline, late_effect, tid, anchor = compute_deadline(policy, facts, as_of)
    assert deadline == end + timedelta(days=days) == derive.filing_deadline(end, days) and anchor == end and tid == "p_filing_60d" and late_effect == "REJECT"
    claim = OpenClaim(claim_id="C1", policy_id=policy.id, event="HOSPITALIZATION", treatment_end_date=end)
    fd = [e for e in build_timeline([policy], [claim], as_of) if e.kind == "FILING_DEADLINE"]
    assert len(fd) == 1 and fd[0].date == deadline and fd[0].days_left == (deadline - as_of).days


def test_filing_deadline_across_leap_days():
    assert derive.filing_deadline(date(2028, 2, 29), 365) == date(2029, 2, 28)
    assert derive.filing_deadline(date(2027, 12, 31), 60) == date(2028, 2, 29)
    assert derive.discharge_on(date(2028, 2, 28), 3) == date(2028, 3, 1)


# --------------------------------------------------------------------------- 3 + 4. solver invariants
POLICIES = [hcp_sompo(), tl_astra(), gh_nusa(), pa_chubb(), ci_chubb()]
EVENTS = ["HOSPITALIZATION", "ICU", "SURGERY", "DEATH", "ACCIDENTAL_DEATH", "CRITICAL_ILLNESS", "ACCIDENT_MEDICAL", "TPD"]
CAUSES = ["ILLNESS", "ACCIDENT", "SUICIDE", "WAR", "INTOXICATION", "CRIMINAL_ACT", "AVIATION", "ACCIDENT_TRAFFIC"]
SLOT_STRATS = {
    Slot.EVENT: st.sampled_from(EVENTS), Slot.CAUSE: st.sampled_from(CAUSES), Slot.IS_ACCIDENT: st.booleans(),
    Slot.DAYS_HOSPITALIZED: st.integers(1, 120), Slot.DAYS_ICU: st.integers(1, 40), Slot.DAYS_SINCE_EFFECTIVE: st.integers(0, 1500),
    Slot.MONTHS_SINCE_ISSUE: st.integers(0, 60), Slot.DIAGNOSIS_BEFORE_EFFECTIVE: st.booleans(), Slot.DISEASE_IN_SPECIFIED_LIST: st.booleans(),
    Slot.PREMIUM_STATUS: st.sampled_from(["PAID", "OVERDUE", "LAPSED"]), Slot.LICENSE_VALID: st.booleans(), Slot.INTOXICATED: st.booleans(),
    Slot.SURVIVAL_DAYS: st.integers(0, 200), Slot.IS_EMERGENCY: st.booleans(), Slot.DAYS_SINCE_DIAGNOSIS: st.integers(0, 400),
    Slot.DAYS_SINCE_DISCHARGE: st.integers(0, 200),
}


@st.composite
def scenario(draw):
    values = {}
    for slot, strat in SLOT_STRATS.items():
        if slot == Slot.EVENT or draw(st.booleans()):
            values[slot] = draw(strat)
    return ScenarioFacts(values=values, as_of=AS_OF)


def _signature(r):
    return (r.verdict, r.payable)


@SETTINGS
@given(policy=st.sampled_from(POLICIES), facts=scenario(), data=st.data())
def test_verdict_is_invariant_to_tuple_order(policy, facts, data):
    shuffled = data.draw(st.permutations(policy.tuples))
    other = policy.model_copy(update={"tuples": list(shuffled)})
    assert _signature(decide(policy, facts)) == _signature(decide(other, facts))


def test_denial_does_not_depend_on_the_order_the_extractor_listed_the_tuples():
    policy = pa_chubb()
    facts = ScenarioFacts(values={Slot.EVENT: "HOSPITALIZATION", Slot.CAUSE: "INTOXICATION", Slot.LICENSE_VALID: False}, as_of=AS_OF)
    expected = _signature(decide(policy, facts))
    rng = random.Random(7)
    for _ in range(25):
        tuples = list(policy.tuples)
        rng.shuffle(tuples)
        assert _signature(decide(policy.model_copy(update={"tuples": tuples}), facts)) == expected


def _exclusion(object_: str, always: bool, slot_value: bool) -> ClauseTuple:
    cond = [] if always else [Condition(slot=Slot.DIAGNOSIS_BEFORE_EFFECTIVE, op=Op.IS_TRUE if slot_value else Op.IS_FALSE)]
    return ClauseTuple(id="x_added", policy_id="P", head="P", relation=Relation.EXCLUDES, object=object_, qualifiers=Qualifiers(applies_if=cond),
                       evidence=Evidence(doc_id="d", section="Exclusions", text="added exclusion"), source_tier=SourceTier.POLICY_DOC_VERIFIED)


@SETTINGS
@given(policy=st.sampled_from(POLICIES), facts=scenario(), obj=st.sampled_from(EVENTS + CAUSES), always=st.booleans(), flag=st.booleans())
def test_adding_an_exclusion_never_turns_denied_into_covered(policy, facts, obj, always, flag):
    before = decide(policy, facts)
    if before.verdict != Verdict.DENIED:
        return
    extended = policy.model_copy(update={"tuples": list(policy.tuples) + [_exclusion(obj, always, flag)]})
    assert decide(extended, facts).verdict != Verdict.COVERED


@SETTINGS
@given(policy=st.sampled_from(POLICIES), facts=scenario(), obj=st.sampled_from(EVENTS + CAUSES))
def test_an_unconditional_exclusion_never_adds_a_payout(policy, facts, obj):
    before = decide(policy, facts)
    after = decide(policy.model_copy(update={"tuples": list(policy.tuples) + [_exclusion(obj, True, True)]}), facts)
    if before.verdict == Verdict.COVERED and after.verdict == Verdict.COVERED:
        assert (after.payable or 0) <= (before.payable or 0)
    if before.verdict == Verdict.DENIED:
        assert after.verdict != Verdict.COVERED


# --------------------------------------------------------------------------- 5. hospital cash amount
def _cash_facts(days: int) -> ScenarioFacts:
    return ScenarioFacts(values={Slot.EVENT: "HOSPITALIZATION", Slot.CAUSE: "ILLNESS", Slot.IS_ACCIDENT: False, Slot.DAYS_HOSPITALIZED: days,
                                 Slot.DAYS_SINCE_EFFECTIVE: 400, Slot.MONTHS_SINCE_ISSUE: 13, Slot.DIAGNOSIS_BEFORE_EFFECTIVE: False,
                                 Slot.DISEASE_IN_SPECIFIED_LIST: False, Slot.PREMIUM_STATUS: "PAID", Slot.DAYS_SINCE_DISCHARGE: 3}, as_of=AS_OF)


@SETTINGS
@given(a=st.integers(1, 200), b=st.integers(1, 200))
def test_hospital_cash_is_non_decreasing_in_days_and_bounded_by_the_cap(a, b):
    policy = hcp_sompo()
    q = next(t.qualifiers for t in policy.tuples if t.id == "c_hosp_daily")
    cap_total = q.per_day_limit * q.max_days_per_year
    lo, hi = sorted((a, b))
    r_lo, r_hi = decide(policy, _cash_facts(lo)), decide(policy, _cash_facts(hi))
    assert r_lo.verdict == r_hi.verdict == Verdict.COVERED
    assert r_lo.payable <= r_hi.payable <= cap_total
    assert r_lo.payable == q.per_day_limit * min(lo, q.max_days_per_year)


# --------------------------------------------------------------------------- 6. allocation
def _indemnity(pid: str, limit: int, kind: str, deductible: int, copay: float) -> PolicyRecord:
    q = Qualifiers(per_case_limit=Decimal(limit), other_insurance=kind, basis=Basis.INDEMNITY,
                   deductible_amount=Decimal(deductible) if deductible else None, copay_pct=copay or None)
    t = ClauseTuple(id=f"{pid}_cover", policy_id=pid, head=pid, relation=Relation.COVERS, object="HOSPITALIZATION", qualifiers=q,
                    evidence=Evidence(doc_id=f"{pid}-doc", section="Benefits", text="test wording"), source_tier=SourceTier.POLICY_DOC_VERIFIED)
    return PolicyRecord(id=pid, doc_id=f"{pid}-doc", insurer="test", product_name="test", product_type="health_indemnity", basis=Basis.INDEMNITY, currency="IDR",
                        tuples=[t], verified=True, effective_date=date(2025, 1, 1))


@st.composite
def household(draw):
    n = draw(st.integers(1, 4))
    policies = [_indemnity(f"P{i}", draw(st.integers(1, 40)) * 500_000, draw(st.sampled_from(["NONE", "EXCESS", "PRO_RATA"])),
                           draw(st.sampled_from([0, 0, 500_000, 1_000_000])), draw(st.sampled_from([0.0, 0.0, 10.0, 20.0]))) for i in range(n)]
    return policies, draw(st.integers(1, 80)) * 500_000, draw(st.sampled_from(["GENERIC", "ID"]))


@SETTINGS
@given(h=household())
def test_allocation_never_pays_more_than_the_bill_or_the_policy_limits(h):
    policies, bill_total, pack = h
    facts = ScenarioFacts(values={Slot.EVENT: "HOSPITALIZATION", Slot.CAUSE: "ILLNESS", Slot.IS_ACCIDENT: False, Slot.IS_EMERGENCY: False,
                                  Slot.DAYS_HOSPITALIZED: 4, Slot.DAYS_SINCE_EFFECTIVE: 400, Slot.MONTHS_SINCE_ISSUE: 13, Slot.BILLED_AMOUNT: bill_total,
                                  Slot.DISEASE_IN_SPECIFIED_LIST: False, Slot.DIAGNOSIS_BEFORE_EFFECTIVE: False, Slot.PREMIUM_STATUS: "PAID",
                                  Slot.DAYS_SINCE_DISCHARGE: 1}, as_of=AS_OF)
    random.Random(bill_total).shuffle(policies)
    res = optimize_allocation(policies, facts, BillBreakdown(total=Decimal(bill_total)), rule_pack=pack, as_of=AS_OF)
    limits = {p.id: p.tuples[0].qualifiers.per_case_limit for p in policies}
    paid = {s.policy_id: s.amount or Decimal(0) for s in res.steps if s.basis == Basis.INDEMNITY}
    assert all(v >= 0 for v in paid.values())
    assert sum(paid.values(), Decimal(0)) <= Decimal(bill_total)
    assert sum(paid.values(), Decimal(0)) <= sum((limits[pid] for pid in paid), Decimal(0))
    assert all(v <= limits[pid] for pid, v in paid.items())
    assert res.indemnity_total == sum(paid.values(), Decimal(0))
