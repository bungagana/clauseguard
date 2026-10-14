"""Evidence verification, recall cross-check and UNMODELED_RULE handling. LLM stubbed."""
from __future__ import annotations

from clauseguard import schema as S
from clauseguard.extractor import policy_extractor as pe
from clauseguard.extractor import refine
from clauseguard.solver import decide
from clauseguard.unmodeled import relevant_unmodeled


def _t(i, rel, obj, text, **q):
    conds = q.pop("applies_if", [])
    return S.ClauseTuple(id=i, policy_id="P", head="P", relation=rel, object=obj,
                         qualifiers=S.Qualifiers(applies_if=conds, **q), evidence=S.Evidence(doc_id="d", section="1", text=text))


def test_object_without_cue_in_evidence_is_removed():
    bad = _t("P-t1", S.Relation.PERMITS, "CONVERSION", "You may change death benefit options subject to evidence of insurability.")
    ok = _t("P-t2", S.Relation.PERMITS, "CONVERSION", "The owner may convert this policy to a permanent policy.")
    kept, log = refine.verify_tuples([bad, ok], pe.window_from_text)
    assert [t.id for t in kept] == ["P-t2"]
    assert log[0]["action"] == "removed"


def test_unsupported_window_is_repaired_from_evidence_then_dropped():
    t = _t("P-t1", S.Relation.HAS_PERIOD, "SUICIDE", "If the insured dies by suicide within 24 months of issue we pay premiums.",
           window_len=2, window_unit=S.TimeUnit.MONTHS, window_from=S.WindowFrom.ISSUE)
    (fixed,), _ = refine.verify_tuples([t], pe.window_from_text)
    assert (fixed.qualifiers.window_len, fixed.qualifiers.window_unit) == (24, S.TimeUnit.MONTHS)
    assert fixed.confidence <= 0.6
    t2 = _t("P-t2", S.Relation.HAS_PERIOD, "CONTESTABILITY", "Incontestable after the policy has been in force.", window_len=2,
            window_unit=S.TimeUnit.YEARS, window_from=S.WindowFrom.ISSUE)
    (fixed2,), _ = refine.verify_tuples([t2], pe.window_from_text)
    assert fixed2.qualifiers.window_len is None


def test_year_month_equivalence_and_number_words_are_supported():
    t = _t("P-t1", S.Relation.HAS_PERIOD, "SUICIDE", "Suicide within two years of the issue date is excluded.", window_len=24,
           window_unit=S.TimeUnit.MONTHS, window_from=S.WindowFrom.ISSUE)
    (kept,), log = refine.verify_tuples([t], pe.window_from_text)
    assert kept.qualifiers.window_len == 24 and not log


def test_condition_value_outside_slot_domain_is_mapped_to_domain():
    t = _t("P-t1", S.Relation.EXCLUDES, "AVIATION", "Death as pilot or crew member of an aircraft is excluded.",
           applies_if=[S.Condition(slot=S.Slot.PILOT_ROLE, op=S.Op.IN, value=["PILOT", "CREW"])])
    (fixed,), log = refine.verify_tuples([t], pe.window_from_text)
    assert set(fixed.qualifiers.applies_if[0].value) == {"PRIVATE_PILOT", "CREW"}
    assert log


def test_uncovered_sentences_exclude_those_inside_evidence():
    text = "5.1 We will pay the death benefit.\n7.2 We shall not pay if the insured dies in war.\n9.3 Upon lapse the cash value is applied to extended term insurance."
    t = _t("P-t1", S.Relation.EXCLUDES, "WAR", "7.2 We shall not pay if the insured dies in war.")
    miss = refine.uncovered_rule_sentences(text, [t])
    got = [s for _, s in miss]
    assert "9.3 Upon lapse the cash value is applied to extended term insurance." in got
    assert not any("war" in x for x in got)


def test_recall_pass_adds_closed_and_unmodeled_tuples(monkeypatch):
    text = "9.3 Upon lapse the cash value is applied to extended term insurance automatically.\n"
    calls = []

    def fake_gen(prompt, *, schema, pdf_bytes, max_output_tokens):
        calls.append(prompt)
        return {"tuples": [
            {"relation": "UNMODELED_RULE", "object": "NONFORFEITURE_ELECTION", "proposed_label": "automatic extended term on lapse",
             "entity_types": ["policy", "benefit"], "evidence_text": text.strip()},
            {"relation": "PERMITS", "object": "SURRENDER", "evidence_text": "cash surrender is allowed"},
            {"relation": "NOT_A_RELATION", "object": "X", "evidence_text": "x"},
        ]}, "stub"

    monkeypatch.setattr(pe, "_gen", fake_gen)

    class O:
        glossary: list = []
        riders: list = []

    ctx = pe._Ctx("P", "doc", S.SourceTier.POLICY_DOC_UNVERIFIED, "en", text)
    out = pe._recall_pass([], text, O(), ctx, set(), {})
    rels = sorted(t.relation.value for t in out)
    assert rels == ["PERMITS", "UNMODELED_RULE"]
    um = next(t for t in out if t.relation == S.Relation.UNMODELED_RULE)
    assert um.qualifiers.proposed_label == "automatic extended term on lapse" and um.confidence <= 0.7
    assert len(calls) == 1 and "extended term" in calls[0]


def _policy(extra):
    base = [_t("P-t1", S.Relation.COVERS, "POLICY_LOAN", "Policy loans are available up to 90% of cash value.")]
    return S.PolicyRecord(id="P", doc_id="d", insurer="x", product_name="x", product_type="life", tuples=base + extra, extraction_coverage=1.0)


def test_unmodeled_rule_marks_uncertain_but_never_changes_verdict():
    um = _t("P-t2", S.Relation.UNMODELED_RULE, "LOAN_INTEREST_SCHEDULE", "The loan interest rate steps up each policy year.", proposed_label="loan interest schedule")
    facts = S.ScenarioFacts(values={S.Slot.EVENT: "POLICY_LOAN", S.Slot.IN_FORCE: True})
    plain = decide(_policy([]), facts)
    flagged = decide(_policy([um]), facts)
    assert flagged.verdict == plain.verdict and not plain.uncertain
    assert flagged.uncertain and flagged.unmodeled_clause_ids == ["P-t2"]
    assert any(s.rule == "unmodeled" for s in flagged.trace)


def test_unrelated_unmodeled_rule_does_not_flag():
    um = _t("P-t2", S.Relation.UNMODELED_RULE, "DIVIDEND_OPTION", "Dividends may be taken in cash.", proposed_label="dividend option")
    facts = S.ScenarioFacts(values={S.Slot.EVENT: "POLICY_LOAN", S.Slot.IN_FORCE: True})
    assert relevant_unmodeled(_policy([um]), facts) == []
    assert not decide(_policy([um]), facts).uncertain


def test_legacy_policy_json_without_new_fields_still_loads():
    rec = _policy([])
    raw = rec.model_dump_json()
    assert S.PolicyRecord.model_validate_json(raw).tuples[0].qualifiers.proposed_label is None


def _row(**kw):
    base = dict(head="POLICY", relation=S.Relation.COVERS if False else "COVERS", object="X", section="S1", evidence_text="verbatim rule text for testing purposes.")
    base.update(kw)
    return pe.ExtractedTuple.model_validate(base)


def _ctx():
    return pe._Ctx("P", "doc", S.SourceTier.POLICY_DOC_UNVERIFIED, "en", None)


def test_map_event_code_prefers_specific_tokens():
    assert refine.map_event_code("ACCELERATED_DEATH_TERMINAL") == "TERMINAL_ILLNESS"
    assert refine.map_event_code("ACCELERATED_DEATH_CHRONIC") == "CHRONIC_ILLNESS"
    assert refine.map_event_code("DEATH") is None
    assert refine.map_event_code("PAID_UP_ADDITIONS") is None


def test_out_of_vocabulary_cover_object_is_mapped_or_kept_as_unmodeled():
    ctx = _ctx()
    mapped = pe._convert_one(_row(object="ACCELERATED_TERMINAL_PAYOUT"), ["P-t001"], 0, ctx, set(), {})
    assert (mapped.relation, mapped.object) == (S.Relation.COVERS, "TERMINAL_ILLNESS") and mapped.confidence <= 0.7
    kept = pe._convert_one(_row(object="DIVIDEND_OPTION"), ["P-t002"], 0, ctx, set(), {})
    assert kept.relation == S.Relation.UNMODELED_RULE and kept.qualifiers.proposed_label == "dividend option"
    permit = pe._convert_one(_row(relation="PERMITS", object="EXTENDED_TERM_INSURANCE"), ["P-t003"], 0, ctx, set(), {})
    assert permit.relation == S.Relation.UNMODELED_RULE and permit.evidence.text.startswith("verbatim rule")


def test_extracted_tuple_schema_is_unchanged_by_the_open_relation():
    rel = pe.TupleBatch.model_json_schema()["$defs"]["Relation"]["enum"]
    assert "UNMODELED_RULE" not in rel and len(rel) == 12
