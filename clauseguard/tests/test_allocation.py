"""Claim allocation optimizer tests: indemnity principle, stacking, excess, circular excess, rule
packs, the optimizer-vs-baseline ordering on generated households, and the persona demo cases."""
from __future__ import annotations

import random
from datetime import date
from decimal import Decimal

import pytest

from clauseguard.agent.demo_fixtures import bpjs_kes, gh_nusa, hcp_rider_b, hcp_sompo, hi_indiv_s, jasa_raharja, pa_chubb, platform_acc
from clauseguard.allocation import BillBreakdown, PolicyTerms, optimize_allocation, policy_terms
from clauseguard.portfolio import cob_plan
from clauseguard.rulepacks import GENERIC_PACK, ID_PACK, get_rule_pack
from clauseguard.schema import (
    Basis,
    ClauseTuple,
    Evidence,
    PolicyRecord,
    Qualifiers,
    Relation,
    ScenarioFacts,
    Slot,
    SourceTier,
)

AS_OF = date(2026, 10, 11)


# --------------------------------------------------------------------------- builders
def _policy(pid: str, q: Qualifiers, *, product_type: str = "health_indemnity", event: str = "HOSPITALIZATION", basis: Basis = Basis.INDEMNITY,
            extra: list[ClauseTuple] | None = None, currency: str = "IDR") -> PolicyRecord:
    q = q.model_copy(update={"basis": basis})
    t = ClauseTuple(id=f"{pid}_cover", policy_id=pid, head=pid, relation=Relation.COVERS, object=event, qualifiers=q,
                    evidence=Evidence(doc_id=f"{pid}-doc", section="Benefits", text="test wording"), source_tier=SourceTier.POLICY_DOC_VERIFIED)
    return PolicyRecord(id=pid, doc_id=f"{pid}-doc", insurer="test", product_name="test", product_type=product_type, basis=basis,
                        currency=currency, tuples=[t] + (extra or []), verified=True, effective_date=date(2025, 1, 1))


def _facts(billed: int, days: int = 4, **over) -> ScenarioFacts:
    v = {Slot.EVENT: "HOSPITALIZATION", Slot.CAUSE: "ILLNESS", Slot.IS_ACCIDENT: False, Slot.IS_EMERGENCY: False, Slot.DAYS_HOSPITALIZED: days,
         Slot.DAYS_SINCE_EFFECTIVE: 400, Slot.MONTHS_SINCE_ISSUE: 13, Slot.DISEASE_IN_SPECIFIED_LIST: False, Slot.DIAGNOSIS_BEFORE_EFFECTIVE: False,
         Slot.BILLED_AMOUNT: billed, Slot.PREMIUM_STATUS: "PAID", Slot.DAYS_SINCE_DISCHARGE: 1}
    v.update(over)
    return ScenarioFacts(values=v, as_of=AS_OF)


def _bill(total: int, **parts) -> BillBreakdown:
    return BillBreakdown(total=Decimal(total), **{k: Decimal(v) for k, v in parts.items()})


def indemnity_sum(res) -> Decimal:
    return sum((s.amount for s in res.steps if s.basis == Basis.INDEMNITY and s.amount is not None), Decimal(0))


# --------------------------------------------------------------------------- rule packs
def test_rule_packs_are_data():
    assert get_rule_pack("id") is ID_PACK and get_rule_pack("GENERIC") is GENERIC_PACK
    assert [r.rule_id for r in ID_PACK.statutory] == ["ID:JASA_RAHARJA_MULTI_VEHICLE", "ID:BPJS_TK_JKK", "ID:BPJS_KES"]
    assert ID_PACK.group_before_individual and not GENERIC_PACK.group_before_individual
    assert ID_PACK.kind_rank("EXCESS") == 2 and ID_PACK.kind_rank(None) == 0 and ID_PACK.kind_rank("PRO_RATA") == 1
    with pytest.raises(KeyError):
        get_rule_pack("MARS")


# --------------------------------------------------------------------------- core properties
def test_indemnity_never_violated_and_excess_pays_remainder():
    primary = _policy("P1", Qualifiers(per_case_limit=Decimal(6_000_000), other_insurance="NONE"))
    excess = _policy("P2", Qualifiers(per_case_limit=Decimal(10_000_000), other_insurance="EXCESS"))
    res = optimize_allocation([excess, primary], _facts(9_000_000), _bill(9_000_000), rule_pack="GENERIC", as_of=AS_OF)
    by = {s.policy_id: s for s in res.steps}
    assert by["P1"].payer_type == "PRIMARY" and by["P1"].amount == Decimal(6_000_000)
    assert by["P2"].payer_type == "EXCESS" and by["P2"].amount == Decimal(3_000_000)  # remainder only, under its 10M cap
    assert by["P1"].order < by["P2"].order
    assert indemnity_sum(res) == Decimal(9_000_000) <= res.bill_total and res.out_of_pocket == 0
    assert not res.circular_excess
    # documents: originals for the first payer, legalised copies + settlement letter for the second
    assert "COB_LETTER" not in by["P1"].documents_required
    assert "COB_LETTER" in by["P2"].documents_required and any(d.startswith("LEGALISED") for d in by["P2"].documents_required)


def test_fixed_benefits_stack_on_top_of_indemnity():
    ind = _policy("IND", Qualifiers(per_case_limit=Decimal(5_000_000)))
    cash = _policy("CASH", Qualifiers(per_day_limit=Decimal(500_000), max_days_per_year=90, other_insurance="STACKABLE"), product_type="hospital_cash", basis=Basis.FIXED_BENEFIT)
    cash2 = _policy("CASH2", Qualifiers(amount=Decimal(1_000_000), other_insurance="STACKABLE"), product_type="hospital_cash", basis=Basis.FIXED_BENEFIT)
    res = optimize_allocation([ind, cash, cash2], _facts(4_000_000, days=4), _bill(4_000_000), rule_pack="GENERIC", as_of=AS_OF)
    by = {s.policy_id: s for s in res.steps}
    assert by["IND"].amount == Decimal(4_000_000)
    assert by["CASH"].payer_type == "FIXED_BENEFIT" and by["CASH"].amount == Decimal(2_000_000)
    assert by["CASH2"].amount == Decimal(1_000_000)
    assert res.fixed_benefit_total == Decimal(3_000_000)
    assert res.total_recovered == Decimal(7_000_000) > res.bill_total  # fixed benefits are not bound by the bill
    assert indemnity_sum(res) <= res.bill_total


def test_circular_excess_resolved_pro_rata_by_limit_and_flagged():
    a = _policy("A", Qualifiers(per_case_limit=Decimal(10_000_000), other_insurance="EXCESS"))
    b = _policy("B", Qualifiers(per_case_limit=Decimal(5_000_000), other_insurance="EXCESS"))
    res = optimize_allocation([a, b], _facts(6_000_000), _bill(6_000_000), rule_pack="GENERIC", as_of=AS_OF)
    by = {s.policy_id: s for s in res.steps}
    assert res.circular_excess and set(res.circular_clause_ids) == {"A_cover", "B_cover"}
    assert by["A"].amount == Decimal(4_000_000) and by["B"].amount == Decimal(2_000_000)  # 10:5 by limit
    assert indemnity_sum(res) == Decimal(6_000_000)
    # the ID pack orders employer group before individual, so group + individual EXCESS is not circular
    grp = _policy("G", Qualifiers(per_case_limit=Decimal(10_000_000), other_insurance="EXCESS"), product_type="group_health")
    res2 = optimize_allocation([b, grp], _facts(6_000_000), _bill(6_000_000), rule_pack="ID", as_of=AS_OF)
    by2 = {s.policy_id: s for s in res2.steps}
    assert not res2.circular_excess and by2["G"].amount == Decimal(6_000_000) and by2["B"].amount == Decimal(0)
    assert by2["G"].order < by2["B"].order


def test_pro_rata_policies_share_by_limit():
    a = _policy("A", Qualifiers(per_case_limit=Decimal(9_000_000), other_insurance="PRO_RATA"))
    b = _policy("B", Qualifiers(per_case_limit=Decimal(3_000_000), other_insurance="PRO_RATA"))
    res = optimize_allocation([a, b], _facts(4_000_000), _bill(4_000_000), rule_pack="GENERIC", as_of=AS_OF)
    by = {s.policy_id: s for s in res.steps}
    assert by["A"].amount == Decimal(3_000_000) and by["B"].amount == Decimal(1_000_000)
    assert by["A"].payer_type == "PRO_RATA" and not res.circular_excess
    # a deductible applies to the policy's share of the charges, not to the whole bill
    c = _policy("C", Qualifiers(per_case_limit=Decimal(9_000_000), deductible_amount=Decimal(1_000_000), other_insurance="PRO_RATA"))
    res2 = optimize_allocation([c, b], _facts(4_000_000), _bill(4_000_000), rule_pack="GENERIC", as_of=AS_OF)
    by2 = {s.policy_id: s for s in res2.steps}
    assert by2["C"].amount == Decimal(2_000_000) and by2["C"].presented == {"total": Decimal(3_000_000)} and by2["B"].amount == Decimal(1_000_000)


def test_deductible_copay_and_member_cost_cap():
    t = PolicyTerms(policy_id="X", pooled=["total"], deductible=Decimal(1000), copay_rate=20.0, copay_cap=Decimal(5000))
    # member pays min(5000, 1000 + 20% of the rest)
    assert t.pay(Decimal(1000)) == 0
    assert t.pay(Decimal(11000)) == Decimal(8000)  # 11000 - (1000 + 2000)
    assert t.pay(Decimal(100_000)) == Decimal(95_000)  # cap reached: member pays 5000
    assert t.limit({"total": Decimal(50_000)}) == Decimal(50_000)  # no inner limit: the whole bill can be presented


def test_optimizer_beats_holdings_greedy_with_deductibles_and_caps():
    """Two co-primary plans with deductibles and out-of-pocket caps: claiming the high-deductible plan
    first lets its cap bind on the full bill and leaves the low-deductible plan a remainder it pays
    well; the holdings order (low-deductible plan first) loses 2,200."""
    a = _policy("A", Qualifiers(deductible_amount=Decimal(6000), copay_pct=30.0, copay_cap=Decimal(9000)), currency="USD")
    b = _policy("B", Qualifiers(deductible_amount=Decimal(1500), copay_pct=20.0, copay_cap=Decimal(7000)), currency="USD")
    bill = BillBreakdown(total=Decimal(20000), currency="USD")
    res = optimize_allocation([b, a], _facts(20000), bill, rule_pack="GENERIC", as_of=AS_OF)
    assert res.solver == "order-search"
    by = {s.policy_id: s for s in res.steps}
    assert by["A"].order == 1 and by["A"].amount == Decimal(11000)  # member pays the 9,000 cap
    assert by["B"].amount == Decimal(6000)  # 9,000 unpaid: deductible 1,500 + 20% of 7,500
    assert res.total_recovered == Decimal(17000) and res.greedy_total == Decimal(14800) and res.single_policy_total == Decimal(14800)
    assert indemnity_sum(res) <= bill.total
    res2 = optimize_allocation([b, a], _facts(20000), bill, rule_pack="GENERIC", as_of=AS_OF)
    assert [(s.policy_id, s.amount) for s in res.steps] == [(s.policy_id, s.amount) for s in res2.steps]


def test_itemised_bill_inner_limits_with_annual_cap_coupling():
    """Room capped per day, other charges pooled, one small annual cap: the optimizer must not
    spend the capped policy on charges the other policy could have paid."""
    small = _policy("SMALL", Qualifiers(per_day_limit=Decimal(2_000_000), max_days=30, per_case_limit=Decimal(20_000_000), annual_cap=Decimal(5_000_000)))
    room_only = _policy("ROOM", Qualifiers(per_day_limit=Decimal(1_000_000), max_days=30, per_case_limit=Decimal(0)))
    bill = _bill(12_000_000, room=4_000_000, drugs=8_000_000)
    res = optimize_allocation([small, room_only], _facts(12_000_000, days=4), bill, rule_pack="GENERIC", as_of=AS_OF)
    assert indemnity_sum(res) == Decimal(9_000_000)  # room-only plan first (4M room), then 5M of the drugs
    assert res.greedy_total == Decimal(7_333_333)  # holdings order: SMALL's 5M eats a third of the room charges first
    by = {s.policy_id: s for s in res.steps}
    assert by["ROOM"].order == 1 and by["ROOM"].amount == Decimal(4_000_000) and by["SMALL"].amount == Decimal(5_000_000)


def test_optimizer_ge_greedy_ge_single_on_50_generated_households():
    """Households of 2-3 co-primary indemnity policies with random typed terms and bills."""
    rng = random.Random(20261011)
    for k in range(50):
        pols = []
        for j in range(rng.choice([2, 3])):
            q = Qualifiers(
                per_case_limit=Decimal(rng.choice([5, 10, 20, 50])) * 1_000_000 if rng.random() < 0.6 else None,
                per_day_limit=Decimal(rng.choice([500_000, 1_000_000, 1_500_000])) if rng.random() < 0.5 else None,
                max_days=30,
                deductible_amount=Decimal(rng.choice([0, 500_000, 1_000_000, 2_000_000])) or None,
                copay_pct=rng.choice([0, 10.0, 20.0]) or None,
                copay_cap=Decimal(rng.choice([2_000_000, 5_000_000])) if rng.random() < 0.5 else None,
                annual_cap=Decimal(rng.choice([8, 30, 100])) * 1_000_000 if rng.random() < 0.4 else None,
            )
            pols.append(_policy(f"H{k}-{j}", q))
        total = rng.choice([3, 8, 15, 30, 60]) * 1_000_000
        room = total // rng.choice([2, 3, 4])
        bill = _bill(total, room=room, drugs=total - room) if rng.random() < 0.6 else _bill(total)
        res = optimize_allocation(pols, _facts(total, days=rng.choice([2, 4, 7])), bill, rule_pack="GENERIC", as_of=AS_OF)
        assert indemnity_sum(res) <= bill.total, k
        assert res.total_recovered >= res.greedy_total >= res.single_policy_total, (k, res.total_recovered, res.greedy_total, res.single_policy_total)
        assert res.solver in ("exact", "order-search")


def test_excluded_and_uncertain_policies_are_reported_with_codes_and_slots():
    lapsed = _policy("L", Qualifiers(per_case_limit=Decimal(5_000_000)))
    lapsed = lapsed.model_copy(update={"status": "lapsed"})
    ok = _policy("OK", Qualifiers(per_case_limit=Decimal(5_000_000)))
    f = _facts(4_000_000)
    f = ScenarioFacts(values={k: v for k, v in f.values.items() if k != Slot.CAUSE}, as_of=AS_OF)
    excl_suicide = ClauseTuple(id="x_suicide", policy_id="U", head="U", relation=Relation.EXCLUDES, object="SUICIDE", qualifiers=Qualifiers(),
                               evidence=Evidence(doc_id="U-doc", text="suicide excluded"), source_tier=SourceTier.POLICY_DOC_VERIFIED)
    unc = _policy("U", Qualifiers(per_case_limit=Decimal(5_000_000)), extra=[excl_suicide])
    res = optimize_allocation([lapsed, ok, unc], f, _bill(4_000_000), rule_pack="GENERIC", as_of=AS_OF)
    assert [e.policy_id for e in res.excluded] == ["L"] and res.excluded[0].code == "LAPSED"
    assert [u.policy_id for u in res.uncertain] == ["U"] and res.uncertain[0].slots == [Slot.CAUSE]
    assert res.uncertain[0].potential_amount == Decimal(4_000_000)  # what it could cover once the question resolves
    assert res.evaluation_order == ["OK", "U", "L"] or set(res.evaluation_order) == {"OK", "U", "L"}


def test_no_bill_lists_payers_without_amounts():
    ok = _policy("OK", Qualifiers(per_case_limit=Decimal(5_000_000)))
    f = _facts(1)
    f = ScenarioFacts(values={k: v for k, v in f.values.items() if k != Slot.BILLED_AMOUNT}, as_of=AS_OF)
    res = optimize_allocation([ok], f, None, rule_pack="GENERIC", as_of=AS_OF)
    assert res.steps[0].amount is None and res.out_of_pocket is None and res.greedy_total is None


def test_bill_breakdown_reconciles_parts():
    assert BillBreakdown(total=Decimal(10)).categories() == {"total": Decimal(10)}
    b = BillBreakdown(total=Decimal(100), room=Decimal(30), drugs=Decimal(20)).categories()
    assert b == {"room": Decimal(30), "other": Decimal(70)}
    b = BillBreakdown(total=Decimal(100), room=Decimal(150), drugs=Decimal(50)).categories()
    assert sum(b.values()) == Decimal(100) and b["room"] == Decimal(75)


def test_policy_terms_from_group_plan_wording():
    t = policy_terms(gh_nusa(), "HOSPITALIZATION", _facts(18_000_000, days=4), ["room", "surgery", "other"])  # a bill with a surgery line
    assert t is not None and t.separate["room"] == Decimal(6_000_000) and t.pool_cap == Decimal(7_700_000)
    assert t.separate["surgery"] == Decimal(25_000_000) and t.payment_cap == Decimal(150_000_000)
    assert t.kind == "EXCESS" and t.is_group and "c_room" in t.clause_ids and "pays_other_inpatient" in t.clause_ids
    assert t.capacity({"room": Decimal(8_000_000), "surgery": Decimal(0), "other": Decimal(10_000_000)})[0] == Decimal(13_700_000)
    t2 = policy_terms(gh_nusa(), "HOSPITALIZATION", _facts(18_000_000, days=4), ["room", "other"])
    assert "c_surgery" not in t2.clause_ids and "surgery" not in t2.separate


# --------------------------------------------------------------------------- persona demo cases
def aditya_facts() -> ScenarioFacts:
    return ScenarioFacts(values={
        Slot.EVENT: "HOSPITALIZATION", Slot.CAUSE: "ILLNESS", Slot.IS_ACCIDENT: False, Slot.IS_EMERGENCY: False,
        Slot.DAYS_HOSPITALIZED: 4, Slot.DAYS_SINCE_DISCHARGE: 1, Slot.BILLED_AMOUNT: 18000000,
        Slot.FACILITY_BPJS_PARTNER: False, Slot.EMPLOYMENT_ACTIVE: True, Slot.PREMIUM_STATUS: "PAID",
        Slot.DISEASE_IN_SPECIFIED_LIST: False, Slot.DIAGNOSIS_BEFORE_EFFECTIVE: True, Slot.MONTHS_SINCE_ISSUE: 11, Slot.DAYS_SINCE_EFFECTIVE: 339,
    }, as_of=AS_OF)


def test_santoso_aditya_case_group_inner_limits_individual_excluded_rider_stacks():
    policies = [gh_nusa(), hi_indiv_s(), hcp_rider_b(), bpjs_kes("BPJS-KES-SANTOSO", "active")]
    rider_view = aditya_facts().bind(Slot.DIAGNOSIS_BEFORE_EFFECTIVE, False)
    bill = _bill(18_000_000, room=8_000_000, drugs=7_000_000, doctor=3_000_000)
    res = optimize_allocation(policies, aditya_facts(), bill, rule_pack="ID", as_of=AS_OF, facts_by_policy={"HCP-RIDER-B": rider_view})
    by = {s.policy_id: s for s in res.steps}
    g = by["GH-NUSA-GRP"]
    assert g.amount == Decimal(13_700_000) and g.presented == {"room": Decimal(6_000_000), "other": Decimal(7_700_000)}
    assert {"c_room", "pays_other_inpatient"} <= set(g.clause_ids) and g.payer_type == "EXCESS"
    assert g.filing_deadline == date(2026, 11, 9)  # discharge 2026-10-10 + 30 days
    excl = {e.policy_id: e for e in res.excluded}
    assert excl["HI-INDIV-S"].code == "PRE_EXISTING" and "x_preexisting_hospitalization" in excl["HI-INDIV-S"].clause_ids
    assert excl["BPJS-KES-SANTOSO"].code == "NON_PARTNER_FACILITY" and excl["BPJS-KES-SANTOSO"].rule_id == "ID:BPJS_KES"
    r = by["HCP-RIDER-B"]
    assert r.payer_type == "FIXED_BENEFIT" and r.amount == Decimal(1_200_000) and "c_hosp_daily" in r.clause_ids
    assert res.indemnity_total == Decimal(13_700_000) and res.fixed_benefit_total == Decimal(1_200_000)
    assert res.total_recovered == Decimal(14_900_000) and res.out_of_pocket == Decimal(4_300_000)
    assert res.evaluation_order.index("GH-NUSA-GRP") < res.evaluation_order.index("HI-INDIV-S")
    # the same plan through the portfolio facade
    steps = cob_plan(policies, aditya_facts(), as_of=AS_OF, bill_breakdown={"room": Decimal(8_000_000), "drugs": Decimal(7_000_000), "doctor": Decimal(3_000_000)},
                     facts_by_policy={"HCP-RIDER-B": rider_view})
    assert {s.payer_policy_id: s.expected_amount for s in steps}["GH-NUSA-GRP"] == Decimal(13_700_000)


def test_rizky_case_bpjs_first_hospital_cash_parallel():
    f = ScenarioFacts(values={
        Slot.EVENT: "HOSPITALIZATION", Slot.CAUSE: "ILLNESS", Slot.IS_ACCIDENT: False, Slot.IS_EMERGENCY: False, Slot.DAYS_SINCE_EFFECTIVE: 44,
        Slot.MONTHS_SINCE_ISSUE: 1, Slot.DISEASE_IN_SPECIFIED_LIST: False, Slot.DIAGNOSIS_BEFORE_EFFECTIVE: False, Slot.DAYS_HOSPITALIZED: 5,
        Slot.DAYS_SINCE_DISCHARGE: 4, Slot.FACILITY_BPJS_PARTNER: True, Slot.BILLED_AMOUNT: 9200000, Slot.PREMIUM_STATUS: "PAID"}, as_of=AS_OF)
    res = optimize_allocation([hcp_sompo(), bpjs_kes("BPJS-KES-RIZKY", "active")], f, _bill(9_200_000), rule_pack="ID", as_of=AS_OF)
    by = {s.policy_id: s for s in res.steps}
    assert by["BPJS-KES-RIZKY"].payer_type == "STATUTORY" and by["BPJS-KES-RIZKY"].amount == Decimal(9_200_000) and by["BPJS-KES-RIZKY"].order == 1
    assert by["HCP-SOMPO-01"].payer_type == "FIXED_BENEFIT" and by["HCP-SOMPO-01"].amount == Decimal(2_500_000)
    assert by["HCP-SOMPO-01"].filing_deadline == date(2026, 12, 6)
    assert res.out_of_pocket == 0 and res.total_recovered == Decimal(11_700_000)


def test_dewi_case_jasa_raharja_first_then_circular_excess_when_licence_valid():
    f = ScenarioFacts(values={
        Slot.EVENT: "HOSPITALIZATION", Slot.CAUSE: "ACCIDENT_TRAFFIC", Slot.IS_ACCIDENT: True, Slot.VEHICLES_INVOLVED: 2, Slot.WORK_RELATED: True,
        Slot.DAYS_HOSPITALIZED: 6, Slot.DAYS_SINCE_EVENT: 6, Slot.DAYS_SINCE_DISCHARGE: 0, Slot.BILLED_AMOUNT: 22000000, Slot.FACILITY_BPJS_PARTNER: True,
        Slot.DAYS_SINCE_EFFECTIVE: 204, Slot.MONTHS_SINCE_ISSUE: 6, Slot.INTOXICATED: False, Slot.LICENSE_VALID: True, Slot.OCCUPATION_CLASS: 1}, as_of=AS_OF)
    policies = [pa_chubb(), platform_acc(), bpjs_kes("BPJS-KES-DEWI", "lapsed"), jasa_raharja()]
    res = optimize_allocation(policies, f, _bill(22_000_000), rule_pack="ID", as_of=AS_OF)
    by = {s.policy_id: s for s in res.steps}
    assert by["JASA-RAHARJA"].order == 1 and by["JASA-RAHARJA"].amount == Decimal(20_000_000) and by["JASA-RAHARJA"].rule_id == "ID:JASA_RAHARJA_MULTI_VEHICLE"
    assert res.circular_excess and set(res.circular_clause_ids) == {"c_accident_medical", "c_medical_on_trip"}
    assert by["PA-CHUBB-03"].amount + by["PLATFORM-ACC"].amount == Decimal(2_000_000)
    assert by["PA-CHUBB-03"].amount > by["PLATFORM-ACC"].amount  # 10M vs 5M limit
    assert {e.policy_id: e.code for e in res.excluded} == {"BPJS-KES-DEWI": "LAPSED"}
    assert indemnity_sum(res) == Decimal(22_000_000) and res.out_of_pocket == 0
    # licence unknown: the PA policy is uncertain on exactly that slot, with the remainder it could cover
    f2 = ScenarioFacts(values={k: v for k, v in f.values.items() if k != Slot.LICENSE_VALID}, as_of=AS_OF)
    res2 = optimize_allocation(policies, f2, _bill(22_000_000), rule_pack="ID", as_of=AS_OF)
    u = {x.policy_id: x for x in res2.uncertain}["PA-CHUBB-03"]
    assert u.slots == [Slot.LICENSE_VALID] and u.potential_amount == Decimal(2_000_000)
    assert not res2.circular_excess


def test_room_limit_uses_per_policy_days_not_only_shared_facts():
    """`DAYS_HOSPITALIZED` derived per policy (facts_by_policy) must size the per-day room cap
    even when the shared scenario facts passed to optimize_allocation do not carry the slot
    themselves; this is the same value claim_plan and the sandbox allocation panel read."""
    policy = _policy("ROOM", Qualifiers(per_day_limit=Decimal(1_000_000), max_days_per_year=30, other_insurance="NONE"))
    shared = _facts(4_000_000)
    shared_no_days = ScenarioFacts(values={k: v for k, v in shared.values.items() if k != Slot.DAYS_HOSPITALIZED}, as_of=AS_OF)
    per_policy = {"ROOM": shared}
    res = optimize_allocation([policy], shared_no_days, _bill(4_000_000), rule_pack="GENERIC", as_of=AS_OF, facts_by_policy=per_policy)
    by = {s.policy_id: s for s in res.steps}
    assert by["ROOM"].amount == Decimal(4_000_000)  # 4 days x 1,000,000 cap, from facts_by_policy, not capped at 0
