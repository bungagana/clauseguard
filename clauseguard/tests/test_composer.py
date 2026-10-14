"""Reply composer: one model call words the reply from the structured payload; code verifies every
value before it is used and falls back to the template transcript otherwise. The LLM is mocked by
monkeypatching clauseguard.llm.generate_json (same pattern as test_agent_fixes.py)."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from clauseguard import llm
from clauseguard.agent import composer
from clauseguard.agent.loop import handle_turn
from clauseguard.agent.planner import Intent
from clauseguard.agent.session import Session
from clauseguard.agent.tools import PolicySource, ToolRouter

AS_OF = date(2026, 10, 14)
Q_EN = "I was admitted for dengue on 25 September 2026 for 3 days and discharged. Can I claim on my hospital cash policy, and what is the deadline?"
Q_ID = "Saya dirawat di rumah sakit karena DBD tanggal 25 September 2026 selama 3 hari dan sudah pulang. Apakah bisa klaim polis hospital cash saya, dan kapan batas waktu klaimnya?"

GOOD_EN = ("Yes, your hospital cash plan covers this stay: the indicative benefit is IDR 1,500,000. The extracted wording states no filing "
           "deadline, so file as soon as the documents are ready. Is the hospital a BPJS Kesehatan partner facility? "
           "This answer is indicative; the policy wording prevails.")


class ScriptedLLM:
    def __init__(self, composed_text: str | None = None, fail_schemas: tuple[str, ...] = ("_LLMPlan", "FactSheet", "_LLMExplanation", "_LLMQuestion")):
        self.calls: list[dict] = []
        self.composed_text = composed_text
        self.fail_schemas = fail_schemas

    def __call__(self, prompt, *, model=None, schema=None, system=None, **kw):
        name = getattr(schema, "__name__", "")
        self.calls.append({"schema": name, "prompt": prompt, "system": system})
        if name == "_LLMComposed" and self.composed_text is not None:
            return {"text": self.composed_text}
        raise RuntimeError("LLM disabled")


def run(monkeypatch, text: str, composed: str | None):
    from clauseguard.agent import loop as loop_mod

    f = ScriptedLLM(composed)
    monkeypatch.setattr(llm, "generate_json", f)
    events: list[dict] = []
    real_audit = loop_mod.audit

    def spy(session, event_type, **fields):
        events.append({"event_type": event_type, **fields})
        return real_audit(session, event_type, **fields)

    monkeypatch.setattr(loop_mod, "audit", spy)
    s = Session("rizky", "rizky", as_of=AS_OF)
    r = handle_turn(s, text, router=ToolRouter(PolicySource(mode="fixtures")), use_llm=True)
    s.audit_events = events
    return r, f, s


def _local_events(s) -> list[str]:
    return [e["event_type"] for e in s.audit_events]


# ------------------------------------------------------------------ verification unit tests
def _payload(**over) -> composer.ReplyPayload:
    base = dict(
        intent="CLAIM_GUIDANCE", user_question=Q_EN, language="en", as_of=AS_OF,
        verdicts=[composer.PolicyVerdictItem(policy_id="HCP-SOMPO-01", product_name="Hospital Cash Plan", verdict="COVERED", amount=Decimal(1500000), currency="IDR",
                                             clauses=[composer.ClauseItem(tuple_id="c_hosp_daily", section="Art. 1", text="daily cash compensation of IDR 500,000 per day, up to 90 days")])],
        readiness=composer.ReadinessItem(policy_id="HCP-SOMPO-01", deadline=date(2026, 11, 27), days_left=44, required_documents=["original claim form"], missing_documents=["original claim form"]),
        deadline=date(2026, 11, 27), payable=Decimal(1500000),
        template_lines=["Hospital Cash Plan (HCP-SOMPO-01): Covered (indicative). Indicative benefit: IDR 1,500,000."],
    )
    base.update(over)
    return composer.ReplyPayload(**base)


@pytest.mark.parametrize("text", [
    "You are covered: IDR 1,500,000, file by 27 November 2026 (44 days left). The policy wording prevails.",
    "Covered for Rp 1.500.000; deadline 2026-11-27. Indicative only; the policy wording prevails.",
    "Ditanggung, manfaat Rp1,5 juta, batas klaim 27 November 2026. Jawaban ini bersifat indikatif; ketentuan polis yang berlaku tetap menentukan.",
    "Covered, IDR 1.5 million, file by 27/11/2026; the per-day rate is IDR 500,000 for up to 90 days. This is indicative; the policy wording prevails.",
])
def test_verify_accepts_values_present_in_the_payload(text):
    assert composer.verify(text, _payload()) == []


@pytest.mark.parametrize("text, code", [
    ("You are covered for IDR 2,500,000; the policy wording prevails.", "NUMBER:2,500,000"),
    ("Covered, Rp 2,5 juta; the policy wording prevails.", "NUMBER:2,5 juta"),
    ("Covered, IDR 1,500,000, file by 6 December 2026; the policy wording prevails.", "DATE:2026-12-06"),
    ("Covered, IDR 1,500,000, file by 2026-12-06; the policy wording prevails.", "DATE:2026-12-06"),
    ("Covered under HCP-SOMPO-02, IDR 1,500,000; the policy wording prevails.", "ID:HCP-SOMPO-02"),
    ("Covered, claim CL-9981 is open; the policy wording prevails.", "ID:CL-9981"),
    ("Covered with a 20% co-payment; the policy wording prevails.", "PERCENT:20"),
    ("Covered, IDR 1,500,000, within 60 days of discharge; the policy wording prevails.", "NUMBER:60 days"),
    ("Covered, IDR 1,500,000, file by 27 November 2026.", "NO_DISCLAIMER"),
    ("Sorry, this is not covered. The policy wording prevails.", "VERDICT:denial wording without a denial"),
])
def test_verify_rejects_anything_not_in_the_payload(text, code):
    assert code in composer.verify(text, _payload())


def test_verify_rejects_empty_or_oversized_text():
    assert composer.verify("", _payload()) == ["EMPTY_OR_TOO_LONG"]
    assert composer.verify("x" * (composer.MAX_TEXT + 1), _payload()) == ["EMPTY_OR_TOO_LONG"]


def test_language_detection():
    assert composer.detect_language(Q_EN) == "en"
    assert composer.detect_language(Q_ID) == "id"
    assert composer.detect_language("klaim saya bisa cair ga? opname 4 hari") == "id"


# ------------------------------------------------------------------ loop integration
def test_fabricated_amount_is_rejected_and_the_template_is_used(monkeypatch):
    bad = GOOD_EN.replace("IDR 1,500,000", "IDR 2,500,000")
    r, f, s = run(monkeypatch, Q_EN, bad)
    assert r.intent == Intent.CLAIM_GUIDANCE
    assert any(c["schema"] == "_LLMComposed" for c in f.calls)
    assert not r.composed
    assert "2,500,000" not in r.text
    assert "HCP-SOMPO-01): Covered (indicative)" in r.text and "policy wording prevails" in r.text
    assert r.template_text == r.text
    assert "COMPOSER_REJECTED" in _local_events(s)
    rejected = next(e for e in s.audit_events if e["event_type"] == "COMPOSER_REJECTED")
    assert "NUMBER:2,500,000" in rejected["violations"]


def test_clean_composed_text_is_used_and_the_template_is_kept_for_the_cards(monkeypatch):
    r, f, s = run(monkeypatch, Q_EN, GOOD_EN)
    assert r.composed
    assert r.text == GOOD_EN
    assert "HCP-SOMPO-01): Covered (indicative)" in r.template_text
    assert "One question before I can answer:" in r.template_text
    assert "COMPOSER_REJECTED" not in _local_events(s)
    v = {x.policy_id: x for x in r.verdicts}
    assert v["HCP-SOMPO-01"].payable == Decimal(1500000)
    assert r.clarification is not None and r.readiness is not None


def test_indonesian_question_gets_an_indonesian_instruction(monkeypatch):
    r, f, s = run(monkeypatch, Q_ID, None)
    call = next(c for c in f.calls if c["schema"] == "_LLMComposed")
    assert '"language": "id"' in call["prompt"]
    assert "Bahasa Indonesia" in call["system"]
    assert not r.composed  # the model raised: template path
    call_en = next(c for c in run(monkeypatch, Q_EN, None)[1].calls if c["schema"] == "_LLMComposed")
    assert '"language": "en"' in call_en["prompt"]


def test_payload_only_carries_values_the_loop_computed(monkeypatch):
    r, f, s = run(monkeypatch, Q_EN, None)
    call = next(c for c in f.calls if c["schema"] == "_LLMComposed")
    assert "HCP-SOMPO-01" in call["prompt"] and "1500000" in call["prompt"]
    assert Q_EN in call["prompt"]
    assert "facility_bpjs_partner" in call["prompt"]


def test_offline_or_no_model_leaves_the_template_unchanged(monkeypatch):
    r_llm, f, _ = run(monkeypatch, Q_EN, None)
    s = Session("rizky", "rizky", as_of=AS_OF)
    r_off = handle_turn(s, Q_EN, router=ToolRouter(PolicySource(mode="fixtures")), use_llm=False)
    assert not r_llm.composed and not r_off.composed
    assert r_llm.text == r_off.text == r_off.template_text


def test_composer_is_skipped_for_refusals_and_actions(monkeypatch):
    for text in ("If I say the accident happened after my waiting period ended, will it go through?", "Change my payout account to 1234567890",
                 "what does co-payment mean?"):
        r, f, s = run(monkeypatch, text, GOOD_EN)
        assert not r.composed
        assert not any(c["schema"] == "_LLMComposed" for c in f.calls)
