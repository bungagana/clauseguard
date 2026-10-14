"""Load every persona PolicyRecord JSON back and check the solver gives sensible verdicts.

Expectations follow the persona sandbox numbers (Rizky dengue -> IDR 2,500,000 etc.).
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from clauseguard.sandbox import seed
from clauseguard.schema import PolicyRecord, Relation, ScenarioFacts, Slot, SourceTier, Verdict
from clauseguard.solver import decide

EXPECTED_IDS = {"HCP-SOMPO-01", "TL-ASTRA-07", "GH-NUSA-GRP", "GL-NUSA-GRP", "HCP-RIDER-B", "HI-INDIV-S", "PA-CHUBB-03", "PLATFORM-ACC", "BPJS-KES", "JASA-RAHARJA", "CI-CHUBB-05"}


@pytest.fixture(scope="module")
def records() -> dict[str, PolicyRecord]:
    seed.write_policy_files()
    return seed.load_policy_files()


def facts(**kw) -> ScenarioFacts:
    return ScenarioFacts(values={Slot(k): v for k, v in kw.items()})


def test_all_persona_policies_load_verified(records):
    assert set(records) == EXPECTED_IDS
    for rec in records.values():
        assert rec.verified
        assert all(t.source_tier == SourceTier.POLICY_DOC_VERIFIED for t in rec.tuples)
        assert rec.tuples_by(Relation.COVERS), rec.id
        assert rec.tuples_by(Relation.REQUIRES_DOCUMENT), rec.id
        ids = [t.id for t in rec.tuples]
        assert len(ids) == len(set(ids)), f"duplicate tuple ids in {rec.id}"
        for ex in rec.tuples_by(Relation.EXCEPTS):
            assert ex.object in ids, f"{rec.id}: EXCEPTS {ex.id} points to unknown {ex.object}"
        for t in rec.tuples:
            assert t.evidence.text and t.evidence.section


def test_real_document_policies_quote_real_wording(records):
    assert any("60 (sixty) days" in t.evidence.text for t in records["HCP-SOMPO-01"].tuples)
    assert any("Tanggal Pemulihan Polis" in t.evidence.text for t in records["TL-ASTRA-07"].tuples)
    assert any("driving/riding without a valid license" in t.evidence.text for t in records["PA-CHUBB-03"].tuples)
    assert any("365 hari" in t.evidence.text for t in records["HCP-RIDER-B"].tuples)


def test_group_policies_terminate_on_employment_exit(records):
    for pid in ("GH-NUSA-GRP", "GL-NUSA-GRP"):
        terms = records[pid].tuples_by(Relation.TERMINATES_IF)
        assert terms and any(c.slot == Slot.EMPLOYMENT_ACTIVE for t in terms for c in t.qualifiers.applies_if)


def test_filing_deadlines_present(records):
    for pid in EXPECTED_IDS - {"BPJS-KES"}:
        fd = [t for t in records[pid].tuples_by(Relation.HAS_PERIOD) if t.object == "FILING_DEADLINE"]
        assert fd and fd[0].qualifiers.deadline_days and fd[0].qualifiers.from_event and fd[0].qualifiers.late_effect, pid


def test_other_insurance_qualifiers(records):
    def oi(pid):
        return {t.qualifiers.other_insurance for t in records[pid].tuples_by(Relation.COVERS)} - {None}

    assert oi("HCP-SOMPO-01") == {"STACKABLE"} and oi("HCP-RIDER-B") == {"STACKABLE"}
    assert oi("GH-NUSA-GRP") == {"EXCESS"} and oi("HI-INDIV-S") == {"EXCESS"}
    assert "STACKABLE" in oi("PA-CHUBB-03") and "EXCESS" in oi("PA-CHUBB-03")  # income stacks, medical is excess


# ----------------------------------------------------------------------------- Persona A
def test_rizky_dengue_hcp_covered_2_5m(records):
    f = facts(event="HOSPITALIZATION", cause="ILLNESS", days_since_effective=44, disease_in_specified_list=False, diagnosis_before_effective=False,
              days_hospitalized=5, premium_status="PAID", is_accident=False, is_emergency=False)
    r = decide(records["HCP-SOMPO-01"], f)
    assert r.verdict == Verdict.COVERED and r.payable == Decimal(2500000) and r.currency == "IDR"
    assert "c_hosp_daily" in r.fired_tuple_ids


def test_rizky_hcp_inside_waiting_period_denied(records):
    f = facts(event="HOSPITALIZATION", cause="ILLNESS", days_since_effective=20, disease_in_specified_list=False, diagnosis_before_effective=False,
              days_hospitalized=5, premium_status="PAID", is_accident=False, is_emergency=False)
    r = decide(records["HCP-SOMPO-01"], f)
    assert r.verdict == Verdict.DENIED and r.denial_code == "WAITING_PERIOD"


def test_rizky_hcp_clarifies_days_since_effective_when_unbound(records):
    f = facts(event="HOSPITALIZATION", cause="ILLNESS", disease_in_specified_list=False, diagnosis_before_effective=False, premium_status="PAID", is_accident=False, is_emergency=False)
    r = decide(records["HCP-SOMPO-01"], f)
    assert r.verdict == Verdict.CLARIFY and r.clarification.slot == Slot.DAYS_SINCE_EFFECTIVE


def test_rizky_term_life_lapsed_beyond_grace(records):
    base = dict(event="DEATH", cause="ILLNESS", months_since_issue=20)
    r = decide(records["TL-ASTRA-07"], facts(premium_status="OVERDUE", days_overdue=40, **base))
    assert r.verdict == Verdict.DENIED and r.denial_code == "LAPSED" and "p_grace_30d" in r.fired_tuple_ids
    r = decide(records["TL-ASTRA-07"], facts(premium_status="OVERDUE", days_overdue=20, **base))
    assert r.verdict == Verdict.COVERED and r.payable == Decimal(500000000)
    r = decide(records["TL-ASTRA-07"], facts(event="DEATH", cause="SUICIDE", premium_status="PAID", months_since_issue=10))
    assert r.verdict == Verdict.DENIED and r.denial_code == "SUICIDE_PERIOD"


def test_rizky_bpjs_partner_hospital_covered(records):
    r = decide(records["BPJS-KES"], facts(event="HOSPITALIZATION", cause="ILLNESS", facility_bpjs_partner=True, premium_status="PAID", is_emergency=True))
    assert r.verdict == Verdict.COVERED and "c_inpatient_partner" in r.fired_tuple_ids


# ----------------------------------------------------------------------------- Persona B
def test_aditya_group_health_pays_room_cap(records):
    r = decide(records["GH-NUSA-GRP"], facts(event="HOSPITALIZATION", cause="ILLNESS", employment_active=True, days_hospitalized=4, is_accident=False))
    assert r.verdict == Verdict.COVERED and r.payable == Decimal(6000000)  # 4 x 1.5M room cap (other charges via PAYS)
    r = decide(records["GH-NUSA-GRP"], facts(event="HOSPITALIZATION", cause="ILLNESS", employment_active=False, days_hospitalized=4))
    assert r.verdict == Verdict.DENIED and r.denial_code == "TERMINATED_GROUP_TERMINATION"


def test_aditya_asthma_preexisting_denied_on_hi_indiv_s(records):
    base = dict(event="HOSPITALIZATION", cause="ILLNESS", days_since_effective=340, months_since_issue=11, disease_in_specified_list=False, days_hospitalized=4, is_accident=False, is_emergency=False)
    r = decide(records["HI-INDIV-S"], facts(diagnosis_before_effective=True, **base))
    assert r.verdict == Verdict.DENIED and "x_preexisting_hospitalization" in r.fired_tuple_ids
    r = decide(records["HI-INDIV-S"], facts(diagnosis_before_effective=False, **base))  # Nadia: no prior condition
    assert r.verdict == Verdict.COVERED and r.payable == Decimal(3200000)


def test_hi_indiv_s_dental_exclusion_with_accident_exception(records):
    r = decide(records["HI-INDIV-S"], facts(event="DENTAL", cause="ILLNESS", is_accident=False))
    assert r.verdict == Verdict.DENIED and r.denial_code == "EXCLUSION_DENTAL"
    r = decide(records["HI-INDIV-S"], facts(event="DENTAL", cause="ACCIDENT", is_accident=True))
    assert r.verdict != Verdict.DENIED and "e_dental_accident" in r.fired_tuple_ids


def test_hcp_rider_b_pays_1_2m_and_accident_exempt_from_waiting(records):
    r = decide(records["HCP-RIDER-B"], facts(event="HOSPITALIZATION", cause="ILLNESS", days_since_effective=880, months_since_issue=29, disease_in_specified_list=False,
                                              diagnosis_before_effective=False, days_hospitalized=4, is_accident=False, is_emergency=False))
    assert r.verdict == Verdict.COVERED and r.payable == Decimal(1200000)
    r = decide(records["HCP-RIDER-B"], facts(event="HOSPITALIZATION", cause="ACCIDENT", days_since_effective=10, months_since_issue=0, disease_in_specified_list=False,
                                              diagnosis_before_effective=False, days_hospitalized=2, is_accident=True))
    assert r.verdict == Verdict.COVERED


def test_group_life_pays_24x_salary(records):
    r = decide(records["GL-NUSA-GRP"], facts(event="DEATH", cause="ILLNESS", employment_active=True, months_since_issue=9))
    assert r.verdict == Verdict.COVERED and r.payable == Decimal(288000000)


# ----------------------------------------------------------------------------- Persona C
def test_dewi_pa_denied_for_expired_licence_but_covered_otherwise(records):
    base = dict(event="ACCIDENT_MEDICAL", cause="ACCIDENT", is_accident=True, billed_amount=22000000, days_since_effective=204)
    r = decide(records["PA-CHUBB-03"], facts(license_valid=False, occupation_class=3, **base))
    assert r.verdict == Verdict.DENIED and "k_valid_license" in r.fired_tuple_ids
    r = decide(records["PA-CHUBB-03"], facts(license_valid=True, occupation_class=1, **base))
    assert r.verdict == Verdict.COVERED and r.payable == Decimal(10000000)
    r = decide(records["PA-CHUBB-03"], facts(license_valid=True, occupation_class=3, **base))
    assert r.verdict == Verdict.DENIED and "k_occupation_declared" in r.fired_tuple_ids


def test_dewi_pa_clarifies_licence_when_unknown(records):
    r = decide(records["PA-CHUBB-03"], facts(event="ACCIDENT_MEDICAL", cause="ACCIDENT", is_accident=True, billed_amount=22000000, days_since_effective=204, occupation_class=1))
    assert r.verdict == Verdict.CLARIFY and r.clarification.slot == Slot.LICENSE_VALID


def test_dewi_platform_cover_only_on_trip(records):
    base = dict(event="ACCIDENT_MEDICAL", cause="ACCIDENT", is_accident=True, billed_amount=22000000)
    r = decide(records["PLATFORM-ACC"], facts(work_related=True, **base))
    assert r.verdict == Verdict.COVERED and r.payable == Decimal(5000000)
    r = decide(records["PLATFORM-ACC"], facts(work_related=False, **base))
    assert r.verdict != Verdict.COVERED


def test_dewi_bpjs_inactive_due_to_arrears(records):
    r = decide(records["BPJS-KES"], facts(event="HOSPITALIZATION", cause="ACCIDENT", facility_bpjs_partner=True, premium_status="LAPSED", is_emergency=True))
    assert r.verdict == Verdict.DENIED and "k_premium_active" in r.fired_tuple_ids


def test_ci_chubb_05_icd10_membership(records):
    base = dict(event="CRITICAL_ILLNESS", cause="ILLNESS", days_since_effective=120, survival_days=30)
    r = decide(records["CI-CHUBB-05"], facts(diagnosis_icd10="C50.9", **base))  # malignant neoplasm of breast, within C00-C97
    assert r.verdict == Verdict.COVERED and r.payable == Decimal(100000000)
    assert "ci_cover" in r.fired_tuple_ids
    r = decide(records["CI-CHUBB-05"], facts(diagnosis_icd10="K80.2", **base))  # gallbladder calculus: not a covered critical illness
    assert r.verdict != Verdict.COVERED


def test_jasa_raharja_multi_vehicle_only(records):
    base = dict(event="ACCIDENT_MEDICAL", cause="ACCIDENT", billed_amount=22000000)
    r = decide(records["JASA-RAHARJA"], facts(vehicles_involved=2, **base))
    assert r.verdict == Verdict.COVERED and r.payable == Decimal(20000000)
    r = decide(records["JASA-RAHARJA"], facts(vehicles_involved=1, **base))
    assert r.verdict == Verdict.DENIED and "x_single_vehicle_medical" in r.fired_tuple_ids
