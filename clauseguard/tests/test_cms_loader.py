"""CMS Exchange PUF loader on a 10-row fixture in the PUF column format."""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from clauseguard.plans.cms_loader import (
    deductible, load_cms_plans, load_rates, metal_level, oop_max, parse_money, parse_pct, premium_monthly, standard_id,
)
from clauseguard.schema import Basis, Relation, SourceTier

FIX = Path(__file__).parent / "fixtures"
PLANS = FIX / "cms_plans_py2026_sample.csv"
RATES = FIX / "cms_rates_py2026_sample.csv"


def test_parsers():
    assert parse_money("$3,000") == Decimal(3000)
    assert parse_money("$250 Copay after deductible") == Decimal(250)
    assert parse_money("No Charge after deductible") == Decimal(0)
    assert parse_money("Not Applicable") is None and parse_money("") is None
    assert parse_pct("20% Coinsurance after deductible") == 20.0
    assert parse_pct("No Charge") == 0.0 and parse_pct("Not Applicable") is None
    assert standard_id("12345AZ0010001-02") == "12345AZ0010001"


def test_one_record_per_standard_plan_with_typed_cost_sharing():
    plans = load_cms_plans(PLANS, rates_path=RATES)
    assert [p.id for p in plans] == ["12345AZ0010001", "12345AZ0010002", "67890AZ0020001"]  # -02 CSR variant folded away
    bronze = plans[0]
    assert bronze.product_type == "health_indemnity" and bronze.basis == Basis.INDEMNITY and bronze.currency == "USD"
    assert bronze.verified and bronze.insurer == "Sample Issuer A" and bronze.product_name == "Sample Bronze HMO"
    covers = {t.object: t for t in bronze.tuples_by(Relation.COVERS)}
    assert set(covers) == {"HOSPITALIZATION", "ICU", "ACCIDENT_MEDICAL", "OUTPATIENT"}
    er = covers["ACCIDENT_MEDICAL"].qualifiers
    assert er.copay_amount == Decimal(500) and er.copay_pct == 40.0
    assert er.deductible_amount == Decimal(7000) and er.copay_cap == Decimal(9200)
    assert er.annual_cap is None and er.basis == Basis.INDEMNITY and er.other_insurance == "EXCESS"
    assert covers["OUTPATIENT"].qualifiers.copay_amount == Decimal(50) and covers["OUTPATIENT"].qualifiers.copay_pct == 0.0
    assert [t.object for t in bronze.tuples_by(Relation.EXCLUDES)] == ["DENTAL"]
    assert deductible(bronze) == Decimal(7000) and oop_max(bronze) == Decimal(9200) and metal_level(bronze) == "Bronze"


def test_evidence_is_the_puf_row_reference_and_verified_tier():
    plans = load_cms_plans(PLANS, rates_path=RATES)
    for p in plans:
        for t in p.tuples:
            assert t.source_tier == SourceTier.POLICY_DOC_VERIFIED
            assert t.evidence.section == p.id
            assert t.evidence.text.startswith(("cms_plans_py2026_sample.csv:", "cms_rates_py2026.csv:"))
            assert f":{p.id}:" in t.evidence.text
    hosp = next(t for t in plans[1].tuples_by(Relation.COVERS) if t.object == "HOSPITALIZATION")
    assert hosp.evidence.text.startswith("cms_plans_py2026_sample.csv:12345AZ0010002:BenefitName=Inpatient Hospital Services (e.g., Hospital Stay); copay=$1,000 Copay per Stay after deductible; coins=20%")


def test_quantity_limits_become_typed_day_limits():
    silver = load_cms_plans(PLANS)[2]
    hosp = next(t for t in silver.tuples_by(Relation.COVERS) if t.object == "HOSPITALIZATION")
    assert hosp.qualifiers.max_days_per_year == 90
    assert "SKILLED" not in {t.object for t in silver.tuples}  # unmapped benefit names are ignored


def test_rates_age_30_non_tobacco_lowest_rating_area():
    rates = load_rates(RATES)
    assert rates == {"12345AZ0010001": Decimal("310.50"), "12345AZ0010002": Decimal("520.25"), "67890AZ0020001": Decimal("410.00")}
    plans = load_cms_plans(PLANS, rates_path=RATES)
    assert premium_monthly(plans[0]) == Decimal("310.50")
    prem = next(t for t in plans[0].tuples if t.object == "PREMIUM")
    assert prem.qualifiers.currency == "USD" and "age 30" in prem.qualifiers.formula


def test_without_rate_puf_premium_is_none():
    plans = load_cms_plans(PLANS, rates_path=FIX / "missing_rates.csv")
    assert all(premium_monthly(p) is None for p in plans)
    assert all(not [t for t in p.tuples if t.object == "PREMIUM"] for p in plans)


def test_missing_file_gives_empty_catalogue():
    assert load_cms_plans(FIX / "nope.csv") == []


def test_wide_layout_one_record_per_standard_component_preferring_on_exchange():
    plans = load_cms_plans(FIX / "cms_plans_py2026_wide_sample.csv")
    assert [p.id for p in plans] == ["11111TX0010001", "22222TX0020001"]
    silver = plans[0]
    assert silver.product_name == "Wide Silver On"  # -01 preferred over -00; -02 (zero cost sharing variant) dropped
    assert deductible(silver) == Decimal(6000) and oop_max(silver) == Decimal(9000) and metal_level(silver) == "Silver"
    covers = {t.object: t.qualifiers for t in silver.tuples_by(Relation.COVERS)}
    assert set(covers) == {"HOSPITALIZATION", "ICU", "ACCIDENT_MEDICAL", "OUTPATIENT", "PREGNANCY"}
    assert covers["HOSPITALIZATION"].copay_amount == Decimal(950) and covers["HOSPITALIZATION"].copay_pct == 20.0
    assert covers["ACCIDENT_MEDICAL"].copay_amount == Decimal(1000) and covers["OUTPATIENT"].copay_amount == Decimal(30) and covers["OUTPATIENT"].copay_pct is None
    hosp = next(t for t in silver.tuples_by(Relation.COVERS) if t.object == "HOSPITALIZATION")
    assert hosp.evidence.text.startswith("cms_plans_py2026_wide_sample.csv:11111TX0010001:inpatient_hospital_*=Inpatient Hospital Services")
    gold = plans[1]
    assert gold.product_name == "Wide Gold" and [t.object for t in gold.tuples_by(Relation.EXCLUDES)] == ["PREGNANCY"]
    assert next(t for t in gold.tuples_by(Relation.COVERS) if t.object == "HOSPITALIZATION").qualifiers.copay_amount is None
    assert all(premium_monthly(p) is None for p in plans)
