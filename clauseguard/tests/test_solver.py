"""Solver unit tests: deterministic verdicts, closed world, clarification by verdict sensitivity."""
from decimal import Decimal

from clauseguard.schema import (
    ClauseTuple,
    Condition,
    Evidence,
    Op,
    PeriodKind,
    PolicyRecord,
    Qualifiers,
    Relation,
    ScenarioFacts,
    Slot,
    SourceTier,
    TimeUnit,
    Verdict,
    WindowFrom,
)
from clauseguard.solver import decide, evaluate, icd10_covered


def ev(text, section="S1"):
    return Evidence(doc_id="D1", section=section, text=text)


def hcp_policy() -> PolicyRecord:
    """Hospital-cash plan modelled on a real Indonesian RIPLAY (Sompo/Roojai HCP)."""
    pid = "HCP-01"
    tuples = [
        ClauseTuple(
            id="t_cover_hosp", policy_id=pid, head=pid, relation=Relation.COVERS, object="HOSPITALIZATION",
            qualifiers=Qualifiers(per_day_limit=Decimal(500000), currency="IDR", max_days_per_year=90),
            evidence=ev("Daily cash benefit IDR 500,000 per day of hospitalization, max 90 days per policy year.", "Benefits"),
            source_tier=SourceTier.POLICY_DOC_VERIFIED,
        ),
        ClauseTuple(
            id="t_wait", policy_id=pid, head=pid, relation=Relation.HAS_PERIOD, object="WAITING",
            qualifiers=Qualifiers(period_kind=PeriodKind.WAITING, waiting_days=30),
            evidence=ev("This Policy applies a waiting period of 30 calendar days from the beginning of the insurance period. This does not apply to emergencies.", "c"),
            source_tier=SourceTier.POLICY_DOC_VERIFIED,
        ),
        ClauseTuple(
            id="t_wait_spec", policy_id=pid, head=pid, relation=Relation.HAS_PERIOD, object="WAITING_SPECIFIED",
            qualifiers=Qualifiers(period_kind=PeriodKind.WAITING_SPECIFIED, window_len=12, window_unit=TimeUnit.MONTHS, window_from=WindowFrom.EFFECTIVE, diseases=["HERNIA", "CATARACT", "TONSILS"]),
            evidence=ev("12-month waiting period applies to hernia, cataract, tonsils...", "d"),
            source_tier=SourceTier.POLICY_DOC_VERIFIED,
        ),
        ClauseTuple(
            id="t_excl_dental", policy_id=pid, head=pid, relation=Relation.EXCLUDES, object="DENTAL",
            qualifiers=Qualifiers(),
            evidence=ev("Dental treatment is excluded except natural teeth damaged by accident.", "Exclusions 19"),
            source_tier=SourceTier.POLICY_DOC_VERIFIED,
        ),
        ClauseTuple(
            id="t_exc_dental_accident", policy_id=pid, head=pid, relation=Relation.EXCEPTS, object="t_excl_dental",
            qualifiers=Qualifiers(applies_if=[Condition(slot=Slot.IS_ACCIDENT, op=Op.IS_TRUE)]),
            evidence=ev("...except natural teeth damaged by accident.", "Exclusions 19"),
            source_tier=SourceTier.POLICY_DOC_VERIFIED,
        ),
        ClauseTuple(
            id="t_excl_suicide", policy_id=pid, head=pid, relation=Relation.EXCLUDES, object="SUICIDE",
            qualifiers=Qualifiers(),
            evidence=ev("Self-inflicted injury or suicide is excluded.", "Exclusions 2"),
            source_tier=SourceTier.POLICY_DOC_VERIFIED,
        ),
    ]
    return PolicyRecord(id=pid, doc_id="D1", insurer="Sompo", product_name="Hospital Cash Plan", product_type="hospital_cash",
                        tuples=tuples, verified=True, grace_days=30)


def test_covered_after_waiting_with_payable():
    f = ScenarioFacts(values={Slot.EVENT: "HOSPITALIZATION", Slot.CAUSE: "ILLNESS", Slot.DAYS_SINCE_EFFECTIVE: 44,
                              Slot.DISEASE_IN_SPECIFIED_LIST: False, Slot.DAYS_HOSPITALIZED: 5})
    r = decide(hcp_policy(), f)
    assert r.verdict == Verdict.COVERED
    assert r.payable == Decimal(2500000)
    assert "t_cover_hosp" in r.fired_tuple_ids


def test_denied_inside_waiting_period():
    f = ScenarioFacts(values={Slot.EVENT: "HOSPITALIZATION", Slot.CAUSE: "ILLNESS", Slot.DAYS_SINCE_EFFECTIVE: 20,
                              Slot.DISEASE_IN_SPECIFIED_LIST: False, Slot.IS_ACCIDENT: False, Slot.IS_EMERGENCY: False})
    r = decide(hcp_policy(), f)
    assert r.verdict == Verdict.DENIED and r.denial_code == "WAITING_PERIOD"
    assert "t_wait" in r.fired_tuple_ids


def test_waiting_period_exempt_for_accident():
    f = ScenarioFacts(values={Slot.EVENT: "HOSPITALIZATION", Slot.CAUSE: "ACCIDENT", Slot.DAYS_SINCE_EFFECTIVE: 20,
                              Slot.DISEASE_IN_SPECIFIED_LIST: False, Slot.IS_ACCIDENT: True, Slot.DAYS_HOSPITALIZED: 3})
    r = decide(hcp_policy(), f)
    assert r.verdict == Verdict.COVERED


def test_specified_disease_window():
    f = ScenarioFacts(values={Slot.EVENT: "HOSPITALIZATION", Slot.CAUSE: "ILLNESS", Slot.DAYS_SINCE_EFFECTIVE: 200,
                              Slot.MONTHS_SINCE_ISSUE: 6, Slot.DISEASE_IN_SPECIFIED_LIST: True})
    r = decide(hcp_policy(), f)
    assert r.verdict == Verdict.DENIED and r.denial_code == "SPECIFIED_DISEASE_WAITING"


def test_closed_world_not_applicable():
    f = ScenarioFacts(values={Slot.EVENT: "POLICY_LOAN", Slot.CAUSE: "ILLNESS"})
    r = decide(hcp_policy(), f)
    assert r.verdict == Verdict.NOT_APPLICABLE


def test_exception_overrides_exclusion():
    f = ScenarioFacts(values={Slot.EVENT: "DENTAL", Slot.CAUSE: "ACCIDENT", Slot.IS_ACCIDENT: True})
    r = decide(hcp_policy(), f)
    # excluded event with an exception that holds -> no cover clause for DENTAL -> NOT_APPLICABLE here,
    # but the exclusion must not fire.
    assert r.verdict != Verdict.DENIED
    assert "t_exc_dental_accident" in r.fired_tuple_ids


def test_clarify_asks_only_verdict_changing_slot():
    # days_since_effective unbound: waiting period makes it verdict-changing -> CLARIFY on that slot
    f = ScenarioFacts(values={Slot.EVENT: "HOSPITALIZATION", Slot.CAUSE: "ILLNESS", Slot.DISEASE_IN_SPECIFIED_LIST: False,
                              Slot.IS_ACCIDENT: False, Slot.IS_EMERGENCY: False})
    r = decide(hcp_policy(), f)
    assert r.verdict == Verdict.CLARIFY
    assert r.clarification and r.clarification.slot == Slot.DAYS_SINCE_EFFECTIVE
    assert set(r.clarification.verdict_by_value.values()) == {Verdict.DENIED, Verdict.COVERED}


def test_no_clarification_when_slot_irrelevant():
    # cause unbound but event is POLICY_LOAN: no clause governs it regardless of cause -> invariant
    f = ScenarioFacts(values={Slot.EVENT: "POLICY_LOAN"})
    r = decide(hcp_policy(), f)
    assert r.verdict == Verdict.NOT_APPLICABLE
    assert r.clarification is None  # the unbound cause was never needed, so never asked


def test_icd10_covered_matches_ranges_and_exact_codes():
    entries = ["C00-C97", "I21", "N18.5", "N18.6"]
    assert icd10_covered("C50.9", entries)  # breast cancer, within C00-C97
    assert icd10_covered("I21.0", entries)  # acute MI subtype, under the I21 category
    assert icd10_covered("N18.5", entries)  # exact code
    assert not icd10_covered("K80.2", entries)  # gallbladder calculus, not covered
    assert not icd10_covered("I20", entries)  # angina, outside the I21 category


def test_icd10_full_code_is_inside_its_category_and_range():
    """ICD-10-CM full codes (up to 7 characters) selected by the coder must match on their 3-character category."""
    assert icd10_covered("C50.911", ["C00-C97"])
    assert icd10_covered("C50.911", ["C50"])
    assert icd10_covered("I21.02", ["I21"])
    assert icd10_covered("N18.6", ["N18"])
    assert icd10_covered("C50", ["C00-C97"])
    assert not icd10_covered("I21.02", ["I22"])
    assert not icd10_covered("C97.1", ["C00-C96"])
    assert not icd10_covered("I210", ["I22"])
    assert icd10_covered("C50911", ["C00-C97"])  # undotted ICD-10-CM spelling


def test_icd10_mismatch_falls_back_to_closed_world_not_applicable():
    cover = ClauseTuple(
        id="t_ci", policy_id="CI1", head="CI1", relation=Relation.COVERS, object="CRITICAL_ILLNESS",
        qualifiers=Qualifiers(amount=Decimal(100000000), icd10_codes=["C00-C97", "I21"]),
        evidence=ev("Lump sum on first diagnosis of a covered critical illness."),
        source_tier=SourceTier.POLICY_DOC_VERIFIED,
    )
    policy = PolicyRecord(id="CI1", doc_id="D1", insurer="X", product_name="CI", product_type="ci", tuples=[cover])
    base = {Slot.EVENT: "CRITICAL_ILLNESS", Slot.CAUSE: "ILLNESS"}
    r = evaluate(policy, ScenarioFacts(values={**base, Slot.DIAGNOSIS_ICD10: "C50.9"}))
    assert r.verdict == Verdict.COVERED and "t_ci" in r.fired_tuple_ids
    r = evaluate(policy, ScenarioFacts(values={**base, Slot.DIAGNOSIS_ICD10: "K80.2"}))
    assert r.verdict == Verdict.NOT_APPLICABLE
    r = evaluate(policy, ScenarioFacts(values=base))  # no icd10 fact bound at all: generic behaviour, unaffected
    assert r.verdict == Verdict.COVERED


def test_paraphrase_consistency_is_structural():
    """Same bound facts -> identical verdict, regardless of how the user phrased it (facts are the only input)."""
    f = ScenarioFacts(values={Slot.EVENT: "HOSPITALIZATION", Slot.CAUSE: "ILLNESS", Slot.DAYS_SINCE_EFFECTIVE: 44,
                              Slot.DISEASE_IN_SPECIFIED_LIST: False, Slot.DAYS_HOSPITALIZED: 5})
    a, b = evaluate(hcp_policy(), f), evaluate(hcp_policy(), f)
    assert a.model_dump() == b.model_dump()
