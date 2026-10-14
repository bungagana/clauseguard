"""Adjudication twin: every ground listed, document consistency in code, monotone readiness score."""
from datetime import date

from clauseguard.recourse import ActionKind
from clauseguard.sandbox.persona_policies import build_policy_records, policies_for_persona
from clauseguard.schema import ScenarioFacts, Slot, Verdict
from clauseguard.twin import adjudicate_like_insurer, consistency_checks, score, score_after

AS_OF = date(2026, 10, 11)
RECORDS = build_policy_records()


def facts(**over) -> ScenarioFacts:
    v = {Slot.EVENT: "HOSPITALIZATION", Slot.CAUSE: "ILLNESS", Slot.IS_ACCIDENT: False, Slot.IS_EMERGENCY: False,
         Slot.DAYS_SINCE_EFFECTIVE: 44, Slot.MONTHS_SINCE_ISSUE: 1, Slot.DISEASE_IN_SPECIFIED_LIST: False, Slot.DAYS_HOSPITALIZED: 5,
         Slot.DIAGNOSIS_BEFORE_EFFECTIVE: False, Slot.PREMIUM_STATUS: "PAID", Slot.DAYS_SINCE_DISCHARGE: 4, Slot.DAYS_SINCE_TREATMENT_END: 4,
         Slot.BILLED_AMOUNT: 9200000}
    v.update(over)
    return ScenarioFacts(values=v, as_of=AS_OF)


def invoice(**over) -> dict:
    d = {"doc_type": "INVOICE", "issuer_name_hash": "h", "service_start": "2026-10-03", "service_end": "2026-10-07", "currency": "IDR",
         "total_amount": "9200000",
         "line_items": [{"description_category": "ROOM", "qty": 5, "unit_price": "1000000", "amount": "5000000"},
                        {"description_category": "DRUGS", "qty": 1, "unit_price": "4200000", "amount": "4200000"}],
         "diagnosis_codes": ["A90"], "patient_name_matches_policyholder": True, "days_hospitalized": 5,
         "contains_instruction_like_text": False, "consistency_ok": True, "extract_quality": "HIGH", "suspicious": False}
    d.update(over)
    return d


def test_clean_claim_has_full_score_with_documents():
    hcp = RECORDS["HCP-SOMPO-01"]
    rep = adjudicate_like_insurer(hcp, facts(), [invoice(), {**invoice(), "doc_type": "MEDICAL_REPORT", "line_items": [], "total_amount": "0"}],
                                  as_of=AS_OF, documents_present=["CLAIM_FORM", "PRESCRIPTION_COPY"], portfolio=policies_for_persona("rizky"))
    assert rep.verdict == Verdict.COVERED and rep.denial_code is None
    assert rep.grounds == [] and rep.checks == []
    assert rep.readiness_score == 1.0 and rep.after_fix_score == 1.0
    assert rep.readiness is not None and rep.readiness.missing_documents == []


def test_twin_flags_inconsistent_invoice_total_and_name_mismatch():
    bad = invoice(total_amount="9900000", patient_name_matches_policyholder=False)
    rep = adjudicate_like_insurer(RECORDS["HCP-SOMPO-01"], facts(), [bad], as_of=AS_OF)
    codes = {g.code for g in rep.grounds}
    assert {"INVOICE_TOTAL", "NAME_MISMATCH", "BILL_VS_STATED", "INCOMPLETE_DOCS"} <= codes
    inv = next(g for g in rep.grounds if g.code == "INVOICE_TOTAL")
    assert "9200000" in inv.evidence_text and "9900000" in inv.evidence_text and inv.fixable
    assert inv.recourse is not None and inv.recourse.actions[0].kind == ActionKind.PROVIDE_DOCUMENTS
    assert rep.readiness_score < 1.0 and rep.after_fix_score == 1.0  # every ground here is fixable


def test_dates_vs_days_and_diagnosis_vs_cause():
    from clauseguard.extractor.claim_doc import ClaimDocExtract

    doc = ClaimDocExtract.model_validate(invoice(service_end="2026-10-09"))  # 7 days by its dates, 5 stated
    checks = consistency_checks(facts(), [doc])
    assert any(c.code == "DATES_VS_DAYS" for c in checks)
    acc = ClaimDocExtract.model_validate(invoice(diagnosis_codes=["A90"]))
    checks = consistency_checks(facts(**{Slot.IS_ACCIDENT: True, Slot.CAUSE: "ACCIDENT"}), [acc])
    assert any(c.code == "DIAGNOSIS_VS_CAUSE" for c in checks)
    two = [ClaimDocExtract.model_validate(invoice()), ClaimDocExtract.model_validate({**invoice(), "doc_type": "DISCHARGE_SUMMARY", "service_end": "2026-10-08", "line_items": [], "total_amount": "0"})]
    checks = consistency_checks(facts(), two)
    assert any(c.code == "DATES_ACROSS_DOCUMENTS" for c in checks)


def test_every_ground_listed_not_only_the_first():
    # inside the waiting period AND lapsed beyond grace AND late filing: the solver stops at one, the twin lists all
    f = facts(**{Slot.DAYS_SINCE_EFFECTIVE: 12, Slot.MONTHS_SINCE_ISSUE: 0, Slot.PREMIUM_STATUS: "LAPSED", Slot.DAYS_OVERDUE: 45,
                 Slot.DAYS_SINCE_DISCHARGE: 70, Slot.DAYS_SINCE_TREATMENT_END: 70})
    rep = adjudicate_like_insurer(RECORDS["HCP-SOMPO-01"], f, [invoice()], as_of=AS_OF)
    assert rep.verdict == Verdict.DENIED
    codes = [g.code for g in rep.grounds]
    assert "WAITING_PERIOD" in codes and "LAPSED" in codes and "LATE_FILING" in codes
    assert {g.clause_id for g in rep.grounds if g.source == "clause"} >= {"p_waiting_30", "k_premium_paid"}
    late = next(g for g in rep.grounds if g.code == "LATE_FILING")
    assert late.fixable is False and late.clause_id == "p_filing_60d" and "60" in late.evidence_text
    assert rep.readiness_score == 0.0
    assert rep.top_ground is not None and rep.top_ground.source == "clause"


def test_pre_existing_ground_not_fixable_on_policy_but_portfolio_alternative_named():
    pol = policies_for_persona("santoso")
    hi = next(p for p in pol if p.id == "HI-INDIV-S")
    f = facts(**{Slot.DAYS_SINCE_EFFECTIVE: 340, Slot.MONTHS_SINCE_ISSUE: 11, Slot.DIAGNOSIS_BEFORE_EFFECTIVE: True, Slot.DAYS_HOSPITALIZED: 4,
                 Slot.EMPLOYMENT_ACTIVE: True, Slot.FACILITY_BPJS_PARTNER: False, Slot.BILLED_AMOUNT: 18000000})
    rep = adjudicate_like_insurer(hi, f, [], as_of=AS_OF, portfolio=pol)
    g = next(g for g in rep.grounds if g.code == "PRE_EXISTING")
    assert g.clause_id == "x_preexisting_hospitalization" and g.weight == 1.0
    assert g.recourse is not None and g.recourse.actions[0].kind == ActionKind.CLAIM_OTHER_POLICY
    assert g.recourse.actions[0].other_policy_id == "GH-NUSA-GRP"
    assert rep.readiness_score == 0.0


def test_readiness_score_monotone_in_grounds_fixed():
    bad = invoice(total_amount="9900000", patient_name_matches_policyholder=False)
    rep = adjudicate_like_insurer(RECORDS["HCP-SOMPO-01"], facts(**{Slot.DAYS_SINCE_EFFECTIVE: 12, Slot.MONTHS_SINCE_ISSUE: 0}), [bad], as_of=AS_OF)
    codes = [g.code for g in rep.grounds]
    assert len(codes) >= 4
    prev = score_after(rep, set())
    assert prev == rep.readiness_score
    fixed: set[str] = set()
    for c in codes:
        fixed.add(c)
        cur = score_after(rep, fixed)
        assert cur >= prev
        prev = cur
    assert score_after(rep, set(codes)) == rep.after_fix_score
    assert score([], set()) == 1.0
    # an unfixable ground does not count as fixed even if named
    rep2 = adjudicate_like_insurer(RECORDS["HCP-SOMPO-01"], facts(**{Slot.DAYS_SINCE_DISCHARGE: 70, Slot.DAYS_SINCE_TREATMENT_END: 70}), [invoice()], as_of=AS_OF)
    assert any(g.code == "LATE_FILING" and not g.fixable for g in rep2.grounds)
    assert score_after(rep2, {"LATE_FILING"}) == score_after(rep2, set())


def test_twin_is_deterministic():
    a = adjudicate_like_insurer(RECORDS["HCP-SOMPO-01"], facts(), [invoice()], as_of=AS_OF)
    b = adjudicate_like_insurer(RECORDS["HCP-SOMPO-01"], facts(), [invoice()], as_of=AS_OF)
    assert a.model_dump() == b.model_dump()
