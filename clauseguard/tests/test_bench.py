"""Bench: oracle mapping sanity, solver adapter semantics, metrics."""
from pathlib import Path

import pytest

from bench import metrics
from bench.abox_to_tuples import ABOX_PATH, build_all
from bench.solve import decide_bench, solver_view
from clauseguard.schema import Relation, ScenarioFacts, Slot, Verdict

pytestmark = pytest.mark.skipif(not Path(ABOX_PATH).exists(), reason="benchmark ABox not present")


@pytest.fixture(scope="module")
def oracle():
    recs, _ = build_all()
    return recs


def test_oracle_has_all_contracts_and_core_periods(oracle):
    assert set(oracle) == {f"C{i}" for i in range(1, 11)}
    for cid, p in oracle.items():
        kinds = {t.object for t in p.tuples_by(Relation.HAS_PERIOD)}
        assert "SUICIDE" in kinds and "CONTESTABILITY" in kinds, cid
        assert all(t.source_tier.value == "POLICY_DOC_VERIFIED" for t in p.tuples)
    suicide = {cid: next(t for t in p.tuples_by(Relation.HAS_PERIOD) if t.object == "SUICIDE").qualifiers.window_len for cid, p in oracle.items()}
    assert suicide["C6"] == 12 and suicide["C1"] == 24
    assert oracle["C6"].grace_days is None  # ABox gives no day count for the group certificate
    assert oracle["C8"].grace_days == 60


def test_oracle_riders_and_exclusions(oracle):
    c7 = oracle["C7"]
    assert {r.rider_type for r in c7.riders} >= {"AccidentalDeathBenefitRider", "ChildrenTermRider", "WaiverOfPremiumRider"}
    assert any(t.relation == Relation.COVERS and t.object == "ACCIDENTAL_DEATH" and t.head != "C7" for t in c7.tuples)
    c4 = oracle["C4"]
    excl = {t.object for t in c4.tuples_by(Relation.EXCLUDES)}
    assert {"WAR", "AVIATION"} <= excl
    assert any(t.relation == Relation.EXCEPTS for t in c4.tuples)
    assert any(t.relation == Relation.PERMITS and t.object == "FREE_LOOK" for t in oracle["C2"].tuples)
    assert not any(t.relation == Relation.PERMITS and t.object == "FREE_LOOK" for t in oracle["C1"].tuples)


def test_adapter_permits_become_covers_and_conditions_are_event_scoped(oracle):
    c8 = oracle["C8"]
    view = solver_view(c8, "POLICY_LOAN")
    assert any(t.relation == Relation.COVERS and t.object == "POLICY_LOAN" for t in view.tuples)
    assert all(t.object == "POLICY_LOAN" for t in view.tuples_by(Relation.CONDITIONED_ON))
    # 1 year in force: C8 requires 2 -> DENIED, C2 requires 1 -> COVERED, C1 has no loans -> NOT_APPLICABLE
    f = ScenarioFacts(values={Slot.EVENT: "POLICY_LOAN", Slot.MONTHS_SINCE_ISSUE: 12, Slot.PREMIUM_STATUS: "PAID"})
    assert decide_bench(c8, f)[1] == Verdict.DENIED
    assert decide_bench(oracle["C2"], f)[1] == Verdict.COVERED
    assert decide_bench(oracle["C1"], f)[1] == Verdict.NOT_APPLICABLE


def test_suicide_boundary_and_rider_scoped_exclusion(oracle):
    f = ScenarioFacts(values={Slot.EVENT: "DEATH", Slot.CAUSE: "SUICIDE", Slot.MONTHS_SINCE_ISSUE: 13, Slot.PREMIUM_STATUS: "PAID",
                              Slot.MISREPRESENTATION: False, Slot.PARTIES_BOTH_DEAD: False, Slot.EMPLOYMENT_ACTIVE: True})
    assert decide_bench(oracle["C1"], f)[1] == Verdict.DENIED
    assert decide_bench(oracle["C6"], f)[1] == Verdict.COVERED  # 12-month clause
    # child rider: age 10 covered, age 25 terminated; base policy unaffected
    kid = ScenarioFacts(values={Slot.EVENT: "CHILD_DEATH", Slot.AGE: 10, Slot.PREMIUM_STATUS: "PAID"})
    assert decide_bench(oracle["C7"], kid)[1] == Verdict.COVERED
    assert decide_bench(oracle["C7"], kid.bind(Slot.AGE, 25))[1] == Verdict.DENIED
    assert decide_bench(oracle["C1"], kid)[1] == Verdict.NOT_APPLICABLE


def test_clarify_is_resolved_by_majority_and_flagged(oracle):
    # pilot_role unbound with an aviation cause on C4 -> CLARIFY (passenger vs pilot) -> majority DENIED, flagged
    f = ScenarioFacts(values={Slot.EVENT: "DEATH", Slot.CAUSE: "AVIATION", Slot.PREMIUM_STATUS: "PAID", Slot.MISREPRESENTATION: False,
                              Slot.PARTIES_BOTH_DEAD: False, Slot.MONTHS_SINCE_ISSUE: 30})
    r, v, flags = decide_bench(oracle["C4"], f)
    assert r.verdict == Verdict.CLARIFY and flags["clarify_slot"] == "pilot_role"
    assert v == Verdict.DENIED


def test_metrics_basics():
    recs = [
        {"scenario_id": "S1", "contract_id": "C1", "pred": "COVERED", "gt": "COVERED", "gt_source": "Section 5.1: 'We will pay the death benefit to the beneficiary if the insured dies while this policy is in force'", "evidence_section": "5.1", "evidence_text": ""},
        {"scenario_id": "S1", "contract_id": "C2", "pred": "DENIED", "gt": "NOT_APPLICABLE", "gt_source": "Contract is silent on free look.", "evidence_section": "", "evidence_text": ""},
        {"scenario_id": "S2", "contract_id": "C1", "pred": "NOT_SPECIFIED", "gt": "NOT_APPLICABLE", "gt_source": "", "evidence_section": "", "evidence_text": ""},
    ]
    recs = [dict(r, pred=metrics.norm_label(r["pred"]), gt=metrics.norm_label(r["gt"])) for r in recs]
    assert metrics.accuracy(recs) == pytest.approx(2 / 3)
    assert metrics.na_to_denied(recs) == pytest.approx(0.5)
    assert metrics.evidence_hit(recs[0]) is True and metrics.evidence_hit(recs[1]) is None
    lo, hi = metrics.bootstrap_ci(recs, n_boot=200)
    assert 0 <= lo <= hi <= 1
    mc = metrics.mcnemar(recs, recs)
    assert mc["b01"] == 0 and mc["p_exact"] == 1.0
