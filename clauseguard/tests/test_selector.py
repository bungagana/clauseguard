"""Plan Selection under Budget: set cover, duplicate-indemnity rule, budget, determinism."""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from clauseguard import catalogue
from clauseguard.catalogue import CATALOGUE
from clauseguard.plans import selector
from clauseguard.plans.cms_loader import load_cms_plans
from clauseguard.plans.selector import select_plans
from clauseguard.schema import Basis, ClauseTuple, Evidence, PolicyRecord, Qualifiers, Relation

FIX = Path(__file__).parent / "fixtures"


def cms_plans():
    return load_cms_plans(FIX / "cms_plans_py2026_sample.csv", rates_path=FIX / "cms_rates_py2026_sample.csv")


def held(perils: list[str], pid: str = "HELD-1", basis: Basis = Basis.INDEMNITY, status: str = "active", product_type: str = "health_indemnity") -> PolicyRecord:
    tuples = [ClauseTuple(id=f"{pid}-{p}", policy_id=pid, head=pid, relation=Relation.COVERS, object=p, qualifiers=Qualifiers(basis=basis),
                          evidence=Evidence(doc_id=pid, text="held")) for p in perils]
    return PolicyRecord(id=pid, doc_id=pid, insurer="x", product_name="held", product_type=product_type, basis=basis, status=status, tuples=tuples)


@pytest.mark.parametrize("use_milp", [None, False])
def test_set_cover_closes_all_closable_gaps_with_fewest_plans(use_milp):
    plans = list(CATALOGUE.values())
    r = select_plans([], plans, ["a"], use_milp=use_milp)
    closable = {t.object for p in plans for t in p.tuples_by(Relation.COVERS)}
    assert set(r.perils_closed) == closable  # every closable peril is closed
    assert r.residual_gaps == []
    assert {c.plan_id for c in r.chosen} == {"CAT-HI-01", "CAT-PA-01", "CAT-TERM-01", "CAT-CI-01"}  # HI covers hospitalisation, surgery and ICU in one plan
    assert "CAT-GTOPUP-01" in {e["plan_id"] for e in r.excluded}  # needs a group base
    assert r.monthly_cost == Decimal(500_000 + 90_000 + 250_000 + 200_000)
    assert all(any("consult a licensed agent" in c for c in ch.caveats) for ch in r.chosen) and "consult a licensed agent" in r.caveats[0]


@pytest.mark.parametrize("use_milp", [None, False])
def test_duplicate_indemnity_plan_is_never_chosen(use_milp):
    plans = cms_plans()
    gold_held = plans[1].model_copy(update={"id": "HELD-GOLD"})
    r = select_plans([gold_held], plans, ["a"], use_milp=use_milp)
    chosen = {c.plan_id for c in r.chosen}
    assert "12345AZ0010002" not in chosen and "67890AZ0020001" not in chosen
    reasons = {e["plan_id"]: e["reason"] for e in r.excluded}
    assert "duplicate" in reasons["12345AZ0010002"] and "duplicate" in reasons["67890AZ0020001"]
    assert r.perils_closed == ["ACCIDENT_MEDICAL"]  # the bronze plan is added only for the one peril the held plan lacks
    # two indemnity plans overlapping on a peril are never chosen together
    r2 = select_plans([], plans, ["a"], use_milp=use_milp)
    ind = [c for c in r2.chosen if c.plan_id in {p.id for p in plans}]
    assert len(ind) == 1


def test_mock_hospital_indemnity_not_added_on_top_of_active_indemnity():
    r = select_plans([held(["HOSPITALIZATION", "SURGERY", "ICU"])], list(CATALOGUE.values()), ["a"])
    assert "CAT-HI-01" not in {c.plan_id for c in r.chosen}
    assert any(e["plan_id"] == "CAT-HI-01" and "duplicate" in e["reason"] for e in r.excluded)
    # fixed-benefit hospital cash is not duplicate cover but the cell is not a gap either, so it is not needed
    assert "CAT-HCASH-01" not in {c.plan_id for c in r.chosen}
    # a lapsed indemnity policy does not block the plan
    r2 = select_plans([held(["HOSPITALIZATION", "SURGERY", "ICU"], status="lapsed")], list(CATALOGUE.values()), ["a"])
    assert "CAT-HI-01" in {c.plan_id for c in r2.chosen}


@pytest.mark.parametrize("use_milp", [None, False])
def test_budget_is_respected_and_best_weight_within_it(use_milp):
    plans = list(CATALOGUE.values())
    r = select_plans([], plans, ["a"], budget_monthly=300_000, use_milp=use_milp)
    assert r.monthly_cost <= 300_000 and r.budget_monthly == Decimal(300_000)
    assert {c.plan_id for c in r.chosen} == {"CAT-PA-01", "CAT-HCASH-01"}  # weight 10 + 7 within 300k
    r_tiny = select_plans([], plans, ["a"], budget_monthly=10_000, use_milp=use_milp)
    assert r_tiny.chosen == [] and r_tiny.residual_gaps == r_tiny.open_gaps
    r_us = select_plans([], cms_plans(), ["a"], budget_monthly=400, use_milp=use_milp)
    assert [c.plan_id for c in r_us.chosen] == ["12345AZ0010001"] and r_us.monthly_cost == Decimal("310.50")


def test_budget_weight_choice_is_the_optimum_not_the_greedy_pick():
    plans = list(CATALOGUE.values())
    r = select_plans([], plans, ["a"], budget_monthly=300_000)
    # within 300k: PA (90k, weight 10) + hospital cash (150k, weight 7) = 17 beats TERM alone (250k, 5) and PA + CI (290k, 14)
    assert {c.plan_id for c in r.chosen} == {"CAT-PA-01", "CAT-HCASH-01"} and r.monthly_cost == Decimal(240_000)


def test_deterministic_and_both_solvers_agree():
    plans = list(CATALOGUE.values()) + cms_plans()
    runs = [select_plans([], plans, ["a", "b"], budget_monthly=1_000_000, use_milp=m) for m in (None, None, False, False)]
    keys = [([c.plan_id for c in r.chosen], r.monthly_cost, [a.plan_ids for a in r.alternatives]) for r in runs]
    assert keys[0] == keys[1] == keys[2] == keys[3]
    assert runs[0].solver == "scipy.optimize.milp" and runs[2].solver == "enumeration<=3+greedy"


def test_alternatives_and_rationale_name_the_puf_fields():
    r = select_plans([], cms_plans(), ["a"])
    assert len(r.alternatives) == 2 and all(a.plan_ids != [c.plan_id for c in r.chosen] for a in r.alternatives)
    c = r.chosen[0]
    assert c.premium_monthly == Decimal("310.50") and c.deductible == Decimal(7000) and c.oop_max == Decimal(9200) and c.metal_level == "Bronze"
    assert any("TEHBInnTier1IndividualMOOP" in f for f in c.fields_used) and any("BenefitName=Inpatient Hospital" in f for f in c.fields_used)
    assert "Monthly premium USD 310.50" in c.rationale and "out-of-pocket maximum USD 9,200" in c.rationale


def test_premium_less_catalogue_uses_oop_cost_and_says_so():
    plans = load_cms_plans(FIX / "cms_plans_py2026_sample.csv", rates_path=FIX / "none.csv")
    r = select_plans([], plans, ["a"])
    assert r.cost_basis == "oop" and r.chosen[0].cost_basis == "oop"
    assert r.chosen[0].plan_id == "12345AZ0010001"  # bronze closes the most weighted gap cells (emergency room included)
    assert r.chosen[0].monthly_cost == (Decimal(7000) + Decimal(9200)) / 12  # deductible + MOOP per month
    r_oop = select_plans([], plans, ["a"], objective="oop", budget_monthly=600)
    assert [c.plan_id for c in r_oop.chosen] == ["12345AZ0010002"]  # gold: (1000 + 6000) / 12 = 583 fits, bronze 1350 does not
    assert any("No premium on record" in c for c in r.caveats) and "no premium on record" in r.chosen[0].rationale


def test_earner_rule_for_death_cover():
    plans = list(CATALOGUE.values())
    r = select_plans([], plans, ["mum", "kid"])  # no earner named: nobody is offered term life
    assert "DEATH" not in r.perils_closed and all(g["peril"] not in selector.EARNER_PERILS for g in r.open_gaps)
    r2 = select_plans([], plans, ["mum", "kid"], earner="mum")
    assert {"peril": "DEATH", "person_id": "mum"} in r2.gaps_closed and {"peril": "DEATH", "person_id": "kid"} not in r2.open_gaps


def test_select_from_gap_report_via_catalogue_recommend(monkeypatch, tmp_path):
    monkeypatch.setattr(catalogue, "CMS_PATH", FIX / "cms_plans_py2026_sample.csv")
    monkeypatch.setattr(catalogue, "CATALOGUE_ID_PATH", tmp_path / "none.json")
    catalogue._CACHE.clear()
    gap = {"matrix": {"a": {}}, "gaps": [{"person_id": "a", "peril": "HOSPITALIZATION"}, {"person_id": "a", "peril": "SURGERY"}],
           "cells": [], "notes": [], "life_gap": None}
    recs = catalogue.recommend(gap, 600, jurisdiction="US")
    assert [r.plan_id for r in recs] == ["12345AZ0010002"] and recs[0].currency == "USD" and not recs[0].mock and recs[0].catalogue == "cms_puf_py2026"
    assert any("consult a licensed agent" in c for c in recs[0].caveats) and any("CMS Health Insurance Exchange PUF" in c for c in recs[0].caveats)
    text = catalogue.render(recs, gap, 600)
    assert "CMS Exchange PUF" in text and "consult a licensed agent" in text
    # held indemnity on both perils: nothing to add
    gap2 = dict(gap, cells=[{"person_id": "a", "peril": p, "policy_id": "HI-X", "basis": "INDEMNITY"} for p in ("HOSPITALIZATION", "SURGERY")], gaps=[])
    assert catalogue.recommend(gap2, None, jurisdiction="US") == []
    # unknown jurisdiction or missing data file -> mock catalogue, labelled
    assert all(r.mock for r in catalogue.recommend(gap, None, jurisdiction="ID"))
    assert all(r.mock for r in catalogue.recommend(gap, None))
    catalogue._CACHE.clear()
