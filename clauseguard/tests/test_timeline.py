"""Entitlement timeline tests on the persona policies."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from clauseguard.agent.demo_fixtures import ci_chubb, persona_policies, tl_astra
from clauseguard.timeline import KINDS, OpenClaim, build_timeline, cover_at_stake

AS_OF = date(2026, 10, 11)


def rizky_claim() -> OpenClaim:
    return OpenClaim(claim_id="CLM-A-001", policy_id="HCP-SOMPO-01", event="HOSPITALIZATION", amount=Decimal(2_500_000),
                     event_date=date(2026, 10, 3), discharge_date=date(2026, 10, 7))


def test_rizky_hcp_filing_deadline_with_money_at_risk():
    ev = build_timeline(persona_policies("rizky"), [rizky_claim()], AS_OF, premium_due={"TL-ASTRA-07": date(2026, 9, 1)})
    fd = [e for e in ev if e.kind == "FILING_DEADLINE"]
    assert len(fd) == 1
    e = fd[0]
    assert e.policy_id == "HCP-SOMPO-01" and e.date == date(2026, 12, 6) and e.days_left == 56
    assert e.money_at_risk == Decimal(2_500_000) and e.clause_id == "p_filing_60d" and e.claim_id == "CLM-A-001"
    assert "rejected" in e.message


def test_tl_astra_grace_end_with_sum_assured_at_risk():
    ev = build_timeline([tl_astra()], [], AS_OF, premium_due={"TL-ASTRA-07": date(2026, 9, 1)})
    g = [e for e in ev if e.kind == "GRACE_ENDS"]
    assert len(g) == 1
    e = g[0]
    assert e.date == date(2026, 10, 1) and e.days_left == -10  # 30-day grace from the 2026-09-01 due date, already over
    assert e.money_at_risk == Decimal(500_000_000) and e.clause_id == "p_grace_30d"
    assert "lapses" in e.message
    # without a due date the grace end cannot be dated and is not invented
    assert not [x for x in build_timeline([tl_astra()], [], AS_OF) if x.kind == "GRACE_ENDS"]


def test_timeline_sorted_and_kinds_closed():
    ev = build_timeline(persona_policies("rizky"), [rizky_claim()], AS_OF, premium_due={"TL-ASTRA-07": date(2026, 9, 1)})
    assert [e.date for e in ev] == sorted(e.date for e in ev)
    assert {e.kind for e in ev} <= set(KINDS)
    kinds = {(e.policy_id, e.kind) for e in ev}
    assert ("HCP-SOMPO-01", "SPECIFIED_WAITING_ENDS") in kinds and ("HCP-SOMPO-01", "POLICY_EXPIRES") in kinds
    assert ("HCP-SOMPO-01", "WAITING_ENDS") not in kinds  # 30 days from 2026-08-20 already passed


def test_survival_period_for_open_critical_illness_claim():
    c = OpenClaim(claim_id="CLM-CI", policy_id="CI-CHUBB-05", event="CRITICAL_ILLNESS", amount=Decimal(100_000_000), diagnosis_date=date(2026, 10, 1))
    ev = build_timeline([ci_chubb()], [c], AS_OF)
    by = {e.kind: e for e in ev}
    assert by["SURVIVAL_PERIOD_ENDS"].date == date(2026, 10, 31) and by["SURVIVAL_PERIOD_ENDS"].money_at_risk == Decimal(100_000_000)
    assert by["FILING_DEADLINE"].date == date(2026, 12, 30) and by["FILING_DEADLINE"].clause_id == "ci_filing"


def test_cover_at_stake_uses_typed_limits():
    pols = {p.id: p for p in persona_policies("santoso")}
    assert cover_at_stake(pols["GH-NUSA-GRP"]) == Decimal(150_000_000)
    assert cover_at_stake(pols["GL-NUSA-GRP"]) == Decimal(288_000_000)
    assert cover_at_stake(tl_astra()) == Decimal(500_000_000)
