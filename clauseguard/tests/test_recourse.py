"""Counterfactual recourse: legitimate actions only, correct dates, portfolio alternatives."""
from datetime import date

import pytest

from clauseguard.recourse import (
    IMMUTABLE_SLOTS,
    MISREPRESENTATION_GUARD,
    ActionKind,
    FactChange,
    GuardViolation,
    RecourseAction,
    apply_action,
    candidate_actions,
    document_recourse,
    find_recourse,
    guard_change,
)
from clauseguard.sandbox.persona_policies import build_policy_records, policies_for_persona
from clauseguard.schema import ScenarioFacts, Slot, Verdict

AS_OF = date(2026, 10, 11)
RECORDS = build_policy_records()


def hosp_facts(**over) -> ScenarioFacts:
    v = {Slot.EVENT: "HOSPITALIZATION", Slot.CAUSE: "ILLNESS", Slot.IS_ACCIDENT: False, Slot.IS_EMERGENCY: False,
         Slot.DAYS_SINCE_EFFECTIVE: 200, Slot.MONTHS_SINCE_ISSUE: 6, Slot.DISEASE_IN_SPECIFIED_LIST: False,
         Slot.DAYS_HOSPITALIZED: 3, Slot.DIAGNOSIS_BEFORE_EFFECTIVE: False, Slot.PREMIUM_STATUS: "PAID"}
    v.update(over)
    return ScenarioFacts(values=v, as_of=AS_OF)


def test_waiting_period_recourse_is_wait_until_correct_date():
    # HCP-SOMPO-01 effective 2026-08-20, 30-day waiting period -> cover from 2026-09-19
    f = hosp_facts(**{Slot.DAYS_SINCE_EFFECTIVE: 12, Slot.MONTHS_SINCE_ISSUE: 0})
    r = find_recourse(RECORDS["HCP-SOMPO-01"], f, as_of=date(2026, 9, 5))
    assert r.baseline_verdict == Verdict.DENIED and r.baseline_denial_code == "WAITING_PERIOD"
    best = r.best()
    assert best is not None and best.verdict == Verdict.COVERED
    assert [a.kind for a in best.actions] == [ActionKind.WAIT]
    assert best.actions[0].earliest_date == date(2026, 9, 19)
    assert best.cost.days == 14
    assert "2026-09-19" in best.description
    assert best.clause_ids == ["c_hosp_daily"]
    # a longer wait on the same slot is dominated and not returned
    assert all(a.changes[0].to_value == 30 for o in r.options for a in o.actions if a.kind == ActionKind.WAIT)


def test_lapsed_in_grace_recourse_is_pay_arrears_before_grace_end():
    # TL-ASTRA-07: 30-day grace; 10 days overdue -> pay before as_of + 20 days
    f = ScenarioFacts(values={Slot.EVENT: "DEATH", Slot.CAUSE: "ILLNESS", Slot.MONTHS_SINCE_ISSUE: 20, Slot.DAYS_SINCE_EFFECTIVE: 600,
                              Slot.PREMIUM_STATUS: "LAPSED", Slot.DAYS_OVERDUE: 10, Slot.MISREPRESENTATION: False}, as_of=AS_OF)
    r = find_recourse(RECORDS["TL-ASTRA-07"], f, as_of=AS_OF)
    assert r.baseline_verdict == Verdict.DENIED
    best = r.best()
    assert best is not None and best.actions[0].kind == ActionKind.SETTLE_ARREARS
    assert best.actions[0].deadline == date(2026, 10, 31)
    assert "before the grace period ends on 2026-10-31" in best.description
    assert best.verdict == Verdict.COVERED


def test_lapsed_beyond_grace_has_no_arrears_recourse():
    f = ScenarioFacts(values={Slot.EVENT: "DEATH", Slot.CAUSE: "ILLNESS", Slot.MONTHS_SINCE_ISSUE: 20, Slot.DAYS_SINCE_EFFECTIVE: 600,
                              Slot.PREMIUM_STATUS: "LAPSED", Slot.DAYS_OVERDUE: 45, Slot.MISREPRESENTATION: False}, as_of=AS_OF)
    r = find_recourse(RECORDS["TL-ASTRA-07"], f, as_of=AS_OF)
    assert r.baseline_verdict == Verdict.DENIED
    assert not any(a.kind == ActionKind.SETTLE_ARREARS for o in r.options for a in o.actions)


def test_missing_documents_are_listed():
    f = hosp_facts()
    act = document_recourse(RECORDS["HCP-SOMPO-01"], f, ["CLAIM_FORM", "RECEIPT_ORIGINAL_OR_LEGALISED"])
    assert act is not None and act.kind == ActionKind.PROVIDE_DOCUMENTS
    assert "CLAIM_FORM" not in act.documents
    assert {"RECEIPT_DETAILS", "MEDICAL_RESUME_INPATIENT", "PRESCRIPTION_COPY", "DIAGNOSTIC_RESULTS"} <= set(act.documents)
    assert act.changes == []  # documents never change a fact about the event
    full = document_recourse(RECORDS["HCP-SOMPO-01"], f, act.documents + ["CLAIM_FORM", "RECEIPT_ORIGINAL_OR_LEGALISED"])
    assert full is None


def test_pre_existing_exclusion_no_recourse_on_policy_but_alternative_in_portfolio():
    # Aditya's asthma on HI-INDIV-S (24-month pre-existing window, 11 months in); GH-NUSA-GRP covers it
    pol = policies_for_persona("santoso")
    hi = next(p for p in pol if p.id == "HI-INDIV-S")
    f = hosp_facts(**{Slot.DAYS_SINCE_EFFECTIVE: 340, Slot.MONTHS_SINCE_ISSUE: 11, Slot.DIAGNOSIS_BEFORE_EFFECTIVE: True,
                      Slot.DAYS_HOSPITALIZED: 4, Slot.EMPLOYMENT_ACTIVE: True, Slot.FACILITY_BPJS_PARTNER: False, Slot.BILLED_AMOUNT: 18000000})
    alone = find_recourse(hi, f, as_of=AS_OF)
    assert alone.baseline_denial_code == "EXCLUSION_HOSPITALIZATION"
    assert Slot.DIAGNOSIS_BEFORE_EFFECTIVE in alone.blocked_by_immutable
    # the only on-policy option is to wait out the 24-month window for a *future* admission
    assert all(a.kind == ActionKind.WAIT for o in alone.options for a in o.actions)
    assert all(o.cost.days > 300 for o in alone.options)
    assert not any(ch.slot == Slot.DIAGNOSIS_BEFORE_EFFECTIVE for o in alone.options for a in o.actions for ch in a.changes)
    with_portfolio = find_recourse(hi, f, as_of=AS_OF, portfolio=pol)
    best = with_portfolio.best()
    assert best is not None and best.actions[0].kind == ActionKind.CLAIM_OTHER_POLICY
    assert best.actions[0].other_policy_id == "GH-NUSA-GRP" and best.verdict == Verdict.COVERED
    assert best.cost.days == 0


def test_survival_period_denial_has_no_recourse():
    f = ScenarioFacts(values={Slot.EVENT: "CRITICAL_ILLNESS", Slot.CAUSE: "ILLNESS", Slot.DAYS_SINCE_EFFECTIVE: 400, Slot.MONTHS_SINCE_ISSUE: 15,
                              Slot.SURVIVAL_DAYS: 19, Slot.PREMIUM_STATUS: "PAID"}, as_of=AS_OF)
    r = find_recourse(RECORDS["CI-CHUBB-05"], f, as_of=AS_OF)
    assert r.baseline_denial_code == "SURVIVAL_PERIOD" and not r.options
    assert r.blocked_by_immutable == [Slot.SURVIVAL_DAYS]


def test_immutable_slots_are_never_proposed():
    """Across every persona policy and a denial that depends on what happened, no option changes an immutable slot."""
    denied = [
        ("PA-CHUBB-03", {Slot.EVENT: "ACCIDENT_MEDICAL", Slot.CAUSE: "ACCIDENT_TRAFFIC", Slot.IS_ACCIDENT: True, Slot.LICENSE_VALID: False, Slot.OCCUPATION_CLASS: 3,
                         Slot.INTOXICATED: False, Slot.DAYS_SINCE_EFFECTIVE: 200, Slot.MONTHS_SINCE_ISSUE: 6, Slot.PREMIUM_STATUS: "PAID", Slot.BILLED_AMOUNT: 22000000}),
        ("HCP-SOMPO-01", dict(hosp_facts(**{Slot.CAUSE: "INTOXICATION", Slot.INTOXICATED: True}).values)),
        ("GL-NUSA-GRP", {Slot.EVENT: "DEATH", Slot.CAUSE: "SUICIDE", Slot.MONTHS_SINCE_ISSUE: 6, Slot.DAYS_SINCE_EFFECTIVE: 180, Slot.EMPLOYMENT_ACTIVE: True, Slot.PREMIUM_STATUS: "PAID"}),
        ("GH-NUSA-GRP", dict(hosp_facts(**{Slot.EMPLOYMENT_ACTIVE: False}).values)),
    ]
    for pid, values in denied:
        r = find_recourse(RECORDS[pid], ScenarioFacts(values=values, as_of=AS_OF), as_of=AS_OF, max_changes=2)
        assert r.baseline_verdict == Verdict.DENIED, pid
        for o in r.options:
            for a in o.actions:
                for ch in a.changes:
                    assert ch.slot not in IMMUTABLE_SLOTS, (pid, ch)
        assert not r.options or all(a.kind != ActionKind.CLAIM_OTHER_POLICY for o in r.options for a in o.actions)
    # the guard itself refuses a direct attempt
    f = hosp_facts(**{Slot.CAUSE: "SUICIDE"})
    with pytest.raises(GuardViolation):
        guard_change(FactChange(slot=Slot.CAUSE, from_value="SUICIDE", to_value="ILLNESS"), f)
    with pytest.raises(GuardViolation):
        apply_action(f, RecourseAction(kind=ActionKind.WAIT, changes=[FactChange(slot=Slot.LICENSE_VALID, from_value=False, to_value=True)], description="x"))
    assert Slot.IS_EMERGENCY in MISREPRESENTATION_GUARD and Slot.IS_EMERGENCY not in IMMUTABLE_SLOTS


def test_emergency_only_proposed_when_unknown_and_time_only_advances():
    stated = hosp_facts(**{Slot.DAYS_SINCE_EFFECTIVE: 12, Slot.MONTHS_SINCE_ISSUE: 0})  # is_emergency False is stated
    acts = candidate_actions(RECORDS["HCP-SOMPO-01"], stated, AS_OF)
    assert not any(a.kind == ActionKind.OBTAIN_EMERGENCY_CLASSIFICATION for a in acts)
    unknown = ScenarioFacts(values={k: v for k, v in stated.values.items() if k != Slot.IS_EMERGENCY}, as_of=AS_OF)
    acts = candidate_actions(RECORDS["HCP-SOMPO-01"], unknown, AS_OF)
    assert any(a.kind == ActionKind.OBTAIN_EMERGENCY_CLASSIFICATION for a in acts)
    with pytest.raises(GuardViolation):
        guard_change(FactChange(slot=Slot.DAYS_SINCE_EFFECTIVE, from_value=200, to_value=10), hosp_facts())


def test_partner_facility_recourse_for_bpjs():
    pol = policies_for_persona("rizky")
    bpjs = next(p for p in pol if p.id == "BPJS-KES-RIZKY")
    f = hosp_facts(**{Slot.FACILITY_BPJS_PARTNER: False})
    r = find_recourse(bpjs, f, as_of=AS_OF)
    assert r.baseline_verdict == Verdict.NOT_APPLICABLE or r.baseline_verdict == Verdict.DENIED
    kinds = {a.kind for o in r.options for a in o.actions}
    assert ActionKind.CHOOSE_PARTNER_FACILITY in kinds
    assert ActionKind.OBTAIN_EMERGENCY_CLASSIFICATION not in kinds  # is_emergency False is stated


def test_covered_needs_no_recourse_and_result_is_deterministic():
    f = hosp_facts()
    a = find_recourse(RECORDS["HCP-SOMPO-01"], f, as_of=AS_OF)
    b = find_recourse(RECORDS["HCP-SOMPO-01"], f, as_of=AS_OF)
    assert a.baseline_verdict == Verdict.COVERED and not a.options
    assert a.model_dump() == b.model_dump()
