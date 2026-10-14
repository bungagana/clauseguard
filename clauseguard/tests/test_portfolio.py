"""Portfolio tests: gap/overlap matrix, COB payer order and claim readiness on hand-built
persona policies (clauseguard/sandbox/persona_policies.py, re-exported by agent/demo_fixtures.py)."""
from datetime import date, timedelta
from decimal import Decimal

from clauseguard.agent.demo_fixtures import (
    bpjs_kes,
    gh_nusa,
    gl_nusa,
    hcp_rider_b,
    hcp_sompo,
    hi_indiv_s,
    jasa_raharja,
    pa_chubb,
    platform_acc,
    tl_astra,
)
from clauseguard.portfolio import claim_readiness, cob_plan, gap_overlap
from clauseguard.schema import Basis, EventCode, ScenarioFacts, Slot, Verdict


# --------------------------------------------------------------------------- Rizky dengue
def rizky_dengue_facts(as_of=date(2026, 10, 11)) -> ScenarioFacts:
    # admitted 2026-10-03, discharged 2026-10-07, HCP effective 2026-08-20 -> 44 days
    return ScenarioFacts(values={
        Slot.EVENT: "HOSPITALIZATION", Slot.CAUSE: "ILLNESS", Slot.IS_ACCIDENT: False, Slot.IS_EMERGENCY: False,
        Slot.DAYS_SINCE_EFFECTIVE: 44, Slot.MONTHS_SINCE_ISSUE: 1, Slot.DISEASE_IN_SPECIFIED_LIST: False,
        Slot.DIAGNOSIS_BEFORE_EFFECTIVE: False, Slot.DAYS_HOSPITALIZED: 5, Slot.DAYS_SINCE_DISCHARGE: 4,
        Slot.FACILITY_BPJS_PARTNER: True, Slot.BILLED_AMOUNT: 9200000, Slot.PREMIUM_STATUS: "PAID",
    }, as_of=as_of)


def test_rizky_dengue_readiness_covered_and_deadline():
    r = claim_readiness(hcp_sompo(), rizky_dengue_facts(), ["CLAIM_FORM", "DISCHARGE_SUMMARY"], as_of=date(2026, 10, 11))
    assert r.verdict.verdict == Verdict.COVERED
    assert r.verdict.payable == Decimal(2500000)
    assert r.deadline == date(2026, 12, 6)  # discharge 2026-10-07 + 60 days
    assert r.days_left == 56
    assert r.late_effect == "REJECT"
    assert "PRESCRIPTION_COPY" in r.missing_documents and "CLAIM_FORM" not in r.missing_documents
    assert r.denial_codes == ["INCOMPLETE_DOCS"]
    assert r.deadline_tuple_id == "p_filing_60d"


def test_rizky_late_filing_flagged():
    f = rizky_dengue_facts(as_of=date(2026, 12, 20)).bind(Slot.DAYS_SINCE_DISCHARGE, 74)
    r = claim_readiness(hcp_sompo(), f, [], as_of=date(2026, 12, 20))
    assert r.days_left == -14
    assert "LATE_FILING" in r.denial_codes


def test_rizky_cob_bpjs_first_hcp_parallel():
    steps = cob_plan([hcp_sompo(), bpjs_kes("BPJS-KES-RIZKY", "active")], rizky_dengue_facts(), as_of=date(2026, 10, 11))
    by = {s.payer_policy_id: s for s in steps}
    assert by["BPJS-KES-RIZKY"].status == "PAYER" and by["BPJS-KES-RIZKY"].expected_amount == Decimal(9200000)
    assert by["HCP-SOMPO-01"].status == "PARALLEL" and by["HCP-SOMPO-01"].expected_amount == Decimal(2500000)
    assert by["HCP-SOMPO-01"].basis == Basis.FIXED_BENEFIT
    assert by["HCP-SOMPO-01"].deadline == date(2026, 12, 6)
    assert by["BPJS-KES-RIZKY"].order < by["HCP-SOMPO-01"].order


# --------------------------------------------------------------------------- Santoso: Aditya asthma
def aditya_facts() -> ScenarioFacts:
    # admitted 2026-10-06, 4 days, Siloam (non-BPJS partner, network N1), bill 18M; asthma diagnosed 2024-05.
    # Policy-relative slots are bound from the HI-INDIV-S view (effective 2025-11-01 -> 11 months,
    # diagnosis before effective); the group plan and the rider never touch those slots.
    return ScenarioFacts(values={
        Slot.EVENT: "HOSPITALIZATION", Slot.CAUSE: "ILLNESS", Slot.IS_ACCIDENT: False, Slot.IS_EMERGENCY: False,
        Slot.DAYS_HOSPITALIZED: 4, Slot.DAYS_SINCE_DISCHARGE: 1, Slot.BILLED_AMOUNT: 18000000,
        Slot.FACILITY_BPJS_PARTNER: False, Slot.EMPLOYMENT_ACTIVE: True, Slot.PREMIUM_STATUS: "PAID",
        Slot.DISEASE_IN_SPECIFIED_LIST: False,
        Slot.DIAGNOSIS_BEFORE_EFFECTIVE: True, Slot.MONTHS_SINCE_ISSUE: 11, Slot.DAYS_SINCE_EFFECTIVE: 339,
    }, as_of=date(2026, 10, 11))


BREAKDOWN = {"room": Decimal(8000000), "drugs": Decimal(7000000), "doctor": Decimal(3000000)}


def test_aditya_cob_group_pays_inner_limits_individual_denied_rider_stacks():
    policies = [gh_nusa(), hi_indiv_s(), hcp_rider_b(), bpjs_kes("BPJS-KES-SANTOSO", "active")]
    # the loop binds policy-relative slots per policy: asthma (2024-05-01) is not before the rider's effective date (2024-05-01)
    rider_view = aditya_facts().bind(Slot.DIAGNOSIS_BEFORE_EFFECTIVE, False)
    steps = cob_plan(policies, aditya_facts(), as_of=date(2026, 10, 11), bill_breakdown=BREAKDOWN, facts_by_policy={"HCP-RIDER-B": rider_view})
    by = {s.payer_policy_id: s for s in steps}
    assert by["BPJS-KES-SANTOSO"].status == "NOT_CLAIMABLE" and by["BPJS-KES-SANTOSO"].denial_code == "NON_PARTNER_FACILITY"
    g = by["GH-NUSA-GRP"]
    assert g.status == "PAYER" and g.expected_amount == Decimal(13700000)  # room 1.5M x 4 + other 7.7M
    assert "c_room" in g.tuple_ids and "pays_other_inpatient" in g.tuple_ids
    i = by["HI-INDIV-S"]
    assert i.status == "NOT_CLAIMABLE" and i.denial_code == "PRE_EXISTING"
    r = by["HCP-RIDER-B"]
    assert r.status == "PARALLEL" and r.expected_amount == Decimal(1200000) and r.basis == Basis.FIXED_BENEFIT
    assert g.order < i.order  # group before individual
    payers = [s for s in steps if s.status == "PAYER" and s.basis == Basis.INDEMNITY]
    assert sum(s.expected_amount for s in payers) <= Decimal(18000000)


def test_second_indemnity_payer_needs_cob_documents():
    # make the individual plan claimable (no pre-existing) so it is the second indemnity payer
    f = aditya_facts().bind(Slot.DIAGNOSIS_BEFORE_EFFECTIVE, False)
    steps = cob_plan([gh_nusa(), hi_indiv_s()], f, as_of=date(2026, 10, 11), bill_breakdown=BREAKDOWN)
    by = {s.payer_policy_id: s for s in steps}
    assert by["GH-NUSA-GRP"].expected_amount == Decimal(13700000)
    i = by["HI-INDIV-S"]
    assert i.status == "PAYER"
    assert "LEGALISED_BILL_COPY" in i.documents and "COB_LETTER" in i.documents
    assert Decimal(0) < i.expected_amount <= Decimal(4300000)
    assert sum(s.expected_amount for s in steps if s.basis == Basis.INDEMNITY and s.status == "PAYER") <= Decimal(18000000)


def test_gap_overlap_santoso():
    policies = [gh_nusa(), gl_nusa(), hcp_rider_b(), hi_indiv_s()]
    persons = ["budi", "sari", "aditya", "nadia"]
    insured = {"GH-NUSA-GRP": persons, "GL-NUSA-GRP": ["budi"], "HCP-RIDER-B": persons, "HI-INDIV-S": ["sari", "aditya", "nadia"]}
    perils = [EventCode.HOSPITALIZATION, EventCode.CRITICAL_ILLNESS, EventCode.DEATH, EventCode.ACCIDENT_MEDICAL, EventCode.TEMPORARY_DISABILITY]
    g = gap_overlap(policies, persons, perils, insured=insured, liabilities=Decimal(600000000), liabilities_person="budi")
    ov = [o for o in g["overlaps"] if o["person_id"] == "aditya" and o["peril"] == "HOSPITALIZATION"]
    assert ov and ov[0]["policy_ids"] == ["GH-NUSA-GRP", "HI-INDIV-S"]
    st = [s for s in g["stackable"] if s["person_id"] == "aditya" and s["peril"] == "HOSPITALIZATION"]
    assert st and st[0]["policy_ids"] == ["HCP-RIDER-B"]
    assert {"person_id": "budi", "peril": "CRITICAL_ILLNESS"} in g["gaps"]
    assert {"person_id": "sari", "peril": "DEATH"} in g["gaps"]
    lg = g["life_gap"]
    assert lg["death_cover"] == "288000000" and lg["gap"] == "312000000"
    assert lg["conditional_on"] and lg["conditional_on"][0]["object"] == "GROUP_TERMINATION"
    cell = g["matrix"]["budi"]["HOSPITALIZATION"][0]
    assert "1,500,000/day" in cell["limit_text"]
    pre = [n for n in g["notes"] if n["kind"] == "PRE_EXISTING_EXCLUDED" and n["policy_id"] == "HI-INDIV-S"]
    assert pre and {n["until"] for n in pre} == {"2027-11-01"}


# --------------------------------------------------------------------------- Dewi crash
def dewi_facts(**over) -> ScenarioFacts:
    v = {
        Slot.EVENT: "HOSPITALIZATION", Slot.CAUSE: "ACCIDENT_TRAFFIC", Slot.IS_ACCIDENT: True, Slot.VEHICLES_INVOLVED: 2,
        Slot.WORK_RELATED: True, Slot.DAYS_HOSPITALIZED: 6, Slot.DAYS_SINCE_EVENT: 6, Slot.DAYS_SINCE_DISCHARGE: 0,
        Slot.BILLED_AMOUNT: 22000000, Slot.FACILITY_BPJS_PARTNER: True, Slot.DAYS_SINCE_EFFECTIVE: 204, Slot.MONTHS_SINCE_ISSUE: 6,
        Slot.INTOXICATED: False,
    }
    v.update(over)
    return ScenarioFacts(values=v, as_of=date(2026, 10, 11))


def test_dewi_cob_jasa_raharja_first_bpjs_blocked_pa_uncertain_license():
    policies = [pa_chubb(), platform_acc(), bpjs_kes("BPJS-KES-DEWI", "lapsed"), jasa_raharja()]
    steps = cob_plan(policies, dewi_facts(), as_of=date(2026, 10, 11))
    by = {s.payer_policy_id: s for s in steps}
    jr = by["JASA-RAHARJA"]
    assert jr.status == "PAYER" and jr.order == 1 and jr.expected_amount == Decimal(20000000)
    assert jr.jurisdiction_rule == "ID:JASA_RAHARJA_MULTI_VEHICLE"
    assert by["BPJS-KES-DEWI"].status == "NOT_CLAIMABLE" and by["BPJS-KES-DEWI"].denial_code == "LAPSED"
    pa = by["PA-CHUBB-03"]
    assert pa.status == "UNCERTAIN" and pa.uncertain_slots == [Slot.LICENSE_VALID]
    assert pa.expected_amount == Decimal(2000000)  # remainder after Jasa Raharja, within the 10M cap
    plat = by["PLATFORM-ACC"]
    assert plat.order > pa.order  # PA (other-insurance NONE) before platform (EXCESS)
    assert plat.status == "PAYER" and plat.expected_amount <= Decimal(5000000)
    assert "POLICE_REPORT" in jr.documents and "JASA_RAHARJA_FORM" in jr.documents
    assert plat.deadline == date(2026, 10, 12) and "filing deadline" in (plat.note or "")


def test_dewi_license_invalid_denies_pa_with_readable_code():
    f = dewi_facts(**{Slot.LICENSE_VALID: False})
    steps = cob_plan([pa_chubb(), jasa_raharja()], f, as_of=date(2026, 10, 11))
    pa = {s.payer_policy_id: s for s in steps}["PA-CHUBB-03"]
    assert pa.status == "NOT_CLAIMABLE" and pa.denial_code == "NO_VALID_LICENSE"


def test_dewi_single_vehicle_skips_jasa_raharja():
    f = dewi_facts(**{Slot.VEHICLES_INVOLVED: 1, Slot.LICENSE_VALID: True, Slot.OCCUPATION_CLASS: 1})
    steps = cob_plan([pa_chubb(), jasa_raharja()], f, as_of=date(2026, 10, 11))
    by = {s.payer_policy_id: s for s in steps}
    assert by["JASA-RAHARJA"].status == "NOT_CLAIMABLE"
    assert by["PA-CHUBB-03"].status == "PAYER" and by["PA-CHUBB-03"].expected_amount == Decimal(10000000)


def test_dewi_vehicles_unknown_is_uncertain():
    f = dewi_facts()
    f = ScenarioFacts(values={k: v for k, v in f.values.items() if k != Slot.VEHICLES_INVOLVED}, as_of=f.as_of)
    steps = cob_plan([jasa_raharja()], f, as_of=date(2026, 10, 11))
    assert steps[0].status == "UNCERTAIN" and steps[0].uncertain_slots == [Slot.VEHICLES_INVOLVED]


def test_term_life_lapsed_in_readiness():
    p = tl_astra()
    f = ScenarioFacts(values={Slot.EVENT: "DEATH", Slot.CAUSE: "ILLNESS", Slot.MONTHS_SINCE_ISSUE: 20,
                              Slot.PREMIUM_STATUS: "OVERDUE", Slot.DAYS_OVERDUE: 40, Slot.DAYS_SINCE_DEATH: 2}, as_of=date(2026, 10, 11))
    r = claim_readiness(p, f, [], as_of=date(2026, 10, 11))
    assert r.verdict.verdict == Verdict.DENIED and r.verdict.denial_code == "LAPSED"
    assert r.deadline == date(2026, 10, 9) + timedelta(days=90)
