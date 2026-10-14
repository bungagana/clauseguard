"""Mock plan catalogue and the PLAN_RECOMMENDATION intent."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from clauseguard import catalogue
from clauseguard.agent.loop import handle_turn
from clauseguard.agent.planner import Intent, rule_plan
from clauseguard.agent.session import Session
from clauseguard.agent.tools import PolicySource, ToolRouter
from clauseguard.catalogue import CATALOGUE, recommend, render
from clauseguard.schema import Basis, Relation

AS_OF = date(2026, 10, 11)


def gap_for(persona: str) -> dict:
    s = Session(persona, persona, as_of=AS_OF)
    r = ToolRouter(PolicySource(mode="fixtures"))
    d, res, _ = r.call(s, "gap_analysis", {})
    assert d.allow
    return res


def ids(recs) -> list[str]:
    return [r.plan_id for r in recs]


def test_catalogue_has_six_labelled_mock_plans():
    assert set(CATALOGUE) == {"CAT-HCASH-01", "CAT-PA-01", "CAT-TERM-01", "CAT-CI-01", "CAT-GTOPUP-01", "CAT-HI-01"}
    types = {p.product_type for p in CATALOGUE.values()}
    assert types == {"hospital_cash", "pa", "term_life", "ci", "group_health_topup", "health_indemnity"}
    for p in CATALOGUE.values():
        assert "MOCK" in p.insurer and "(MOCK)" in p.product_name
        assert all(t.evidence.text.startswith("MOCK:") for t in p.tuples)
        assert catalogue.monthly_premium(p) > 0
        assert p.tuples_by(Relation.COVERS)
    assert CATALOGUE["CAT-HI-01"].basis == Basis.INDEMNITY and CATALOGUE["CAT-TERM-01"].basis == Basis.FIXED_BENEFIT


def test_single_adult_with_lapsed_life_policy():
    gap = gap_for("rizky")
    assert {"person_id": "rizky", "peril": "DEATH"} in gap["gaps"]  # TL-ASTRA-07 is past its grace period today
    recs = recommend(gap)
    assert ids(recs) == ["CAT-TERM-01", "CAT-PA-01"]
    assert any("TL-ASTRA-07" in c and "reinstated" in c for c in recs[0].caveats)


def test_never_duplicates_held_indemnity_cover():
    gap = gap_for("santoso")  # group + individual indemnity already held for hospitalisation
    recs = recommend(gap)
    assert not {"CAT-HI-01", "CAT-GTOPUP-01", "CAT-HCASH-01"} & set(ids(recs))
    term = next(r for r in recs if r.plan_id == "CAT-TERM-01")
    assert "312,000,000" in term.rationale and term.closes_gap_perils == ["DEATH"]
    # children do not get death-cover suggestions
    assert all("children" not in r.rationale for r in recs)


def test_gap_free_portfolio_gets_no_recommendation():
    full = {"matrix": {"p": {}}, "gaps": [], "cells": [], "notes": [], "life_gap": None}
    assert recommend(full) == []
    assert "no open cover gap" in render([], full, None)


def test_budget_greedy_and_named_exclusions():
    gap = gap_for("dewi")
    recs = recommend(gap, 300_000)
    assert ids(recs) == ["CAT-HCASH-01"] and sum(r.monthly_premium_idr for r in recs) <= 300_000
    assert "exceed your budget" in " ".join(recs[0].caveats) and "CAT-HI-01" in " ".join(recs[0].caveats)
    assert recommend(gap, 10_000) == []
    assert "No plan in the catalogue fits the budget" in render([], gap, 10_000)
    assert ids(recommend(gap))[0] == "CAT-HI-01"  # no budget: the highest-priority plan first


def test_group_topup_only_with_an_active_group_base_and_a_gap():
    gap = {"matrix": {"a": {}}, "gaps": [{"person_id": "a", "peril": "HOSPITALIZATION"}], "notes": [], "life_gap": None,
           "cells": [{"person_id": "b", "peril": "HOSPITALIZATION", "policy_id": "GH-NUSA-GRP", "basis": "INDEMNITY"}]}
    assert ids(recommend(gap)) == ["CAT-GTOPUP-01"]
    no_base = dict(gap, cells=[])
    assert ids(recommend(no_base)) == ["CAT-HCASH-01"]  # without a group base the top-up is not eligible
    lapsed_base = dict(gap, notes=[{"policy_id": "GH-NUSA-GRP", "kind": "INACTIVE", "status": "lapsed"}])
    assert ids(recommend(lapsed_base)) == ["CAT-HCASH-01"]


def test_every_recommendation_carries_the_agent_caveat_and_mock_label():
    for persona in ("rizky", "santoso", "dewi"):
        for r in recommend(gap_for(persona)):
            assert any("consult a licensed agent" in c for c in r.caveats)
            assert any("Mock catalogue" in c for c in r.caveats) and r.mock


@pytest.mark.parametrize("text", [
    "What should I buy to close my gaps?", "Can you recommend a plan for me?", "which plan should we add for the family?",
    "should I get another policy?", "rekomendasi asuransi apa yang sebaiknya saya beli?", "what insurance should I get",
])
def test_recommendation_intent_is_rule_detected(text):
    p = rule_plan(text)
    assert p.intent == Intent.PLAN_RECOMMENDATION
    assert all(c.name in ("get_my_policies", "gap_analysis") for c in p.tool_calls)


@pytest.mark.parametrize("text", [
    "Summarise everything I'm covered for.", "Is there a gap in my life cover?", "Can I claim for dengue?", "recommend a good lawyer",
    "Submit the HCP claim for me.", "Change my payout account to 1234567890",
])
def test_other_questions_are_not_recommendation_requests(text):
    assert rule_plan(text).intent != Intent.PLAN_RECOMMENDATION


def test_loop_reply_is_structured_and_executes_no_tier2_tool():
    s = Session("C-BUDI", "santoso", as_of=AS_OF)
    r = handle_turn(s, "which plan should we add for the family? we can afford 400k a month", router=ToolRouter(PolicySource(mode="sandbox")), use_llm=False)
    assert r.intent == Intent.PLAN_RECOMMENDATION
    assert [x["plan_id"] for x in r.recommendations] == ["CAT-TERM-01", "CAT-PA-01"]
    assert sum(x["monthly_premium_idr"] for x in r.recommendations) <= 400_000
    assert "licensed agent" in r.text and not r.actions_pending
    assert not any(c["allowed"] and c["tier"] >= 2 for c in r.tool_calls)
    assert any(c["name"] == "gap_analysis" and c["allowed"] for c in r.tool_calls)


@pytest.mark.parametrize("text, expected", [
    ("my budget is IDR 300,000 per month", 300_000), ("we can afford 400k a month", 400_000), ("budget 500rb sebulan", 500_000),
    ("max 2jt per bulan", 2_000_000), ("budget of Rp 1.500.000 monthly", 1_500_000), ("I want 2 plans", None), ("what should I buy?", None),
])
def test_budget_parsing(text, expected):
    from clauseguard.agent.loop import _budget_from_text

    assert _budget_from_text(text) == expected


def test_no_real_product_names_in_the_catalogue():
    blob = " ".join(p.product_name + p.insurer + " ".join(t.evidence.text for t in p.tuples) for p in CATALOGUE.values())
    for real in ("Prudential", "Allianz", "AIA", "Manulife", "Sinarmas", "Great Eastern", "Zurich", "Chubb", "Sompo", "Astra", "Jasa Raharja"):
        assert real not in blob
    assert Decimal(catalogue.monthly_premium(CATALOGUE["CAT-HI-01"])) > Decimal(catalogue.monthly_premium(CATALOGUE["CAT-GTOPUP-01"]))
