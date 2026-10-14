"""Derived dates and deadlines, the submit gate, alert relevance and mid-conversation corrections."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from clauseguard import llm
from clauseguard.agent import composer, derive
from clauseguard.agent.facts import FactSheet
from clauseguard.agent.facts_fallback import bind_rules
from clauseguard.agent.loop import confirm_pending, handle_turn
from clauseguard.agent.session import Session
from clauseguard.agent.tools import PolicySource, ToolRouter
from clauseguard.sandbox import api
from clauseguard.schema import ScenarioFacts, Slot

AS_OF = date(2026, 10, 14)
SCENE = "I was admitted for dengue on 25 September 2026 for 3 days and discharged. Can I claim on my hospital cash policy, and what is the deadline?"
SCENE_ID = "Saya dirawat karena DBD sejak 25 September 2026 selama 3 hari, kemudian pulang. Bisa klaim ke polis hospital cash? Kapan batas waktunya?"


@pytest.fixture(autouse=True)
def no_llm(monkeypatch):
    monkeypatch.setattr(llm, "generate_json", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("LLM disabled")))


def router() -> ToolRouter:
    return ToolRouter(PolicySource(mode="fixtures"))


def turn(s: Session, text: str, **kw):
    return handle_turn(s, text, router=router(), use_llm=False, **kw)


def session(as_of: date = AS_OF) -> Session:
    return Session("rizky", "rizky", as_of=as_of)


# ------------------------------------------------------------------ P1: derived dates and the deadline
def test_dengue_scene_derives_discharge_and_deadline():
    s = session()
    r = turn(s, SCENE)
    assert r.deadline == date(2026, 11, 26) and r.payable == Decimal(1_500_000)
    assert r.readiness.days_left == 43 and r.readiness.event_date == date(2026, 9, 27) and r.readiness.late_effect == "REJECT"
    assert "Filing deadline for HCP-SOMPO-01: 2026-11-26" in r.text and "43 days left" in r.text
    assert r.derivations == ["Discharge date 2026-09-27: calculated from your admission date 2026-09-25 and 3 days in hospital."]
    assert date(2026, 9, 27) not in s.event_dates.values()


def test_dengue_scene_in_indonesian():
    r = turn(session(), SCENE_ID)
    assert r.deadline == date(2026, 11, 26) and "Batas pengajuan klaim HCP-SOMPO-01: 2026-11-26" in r.text and "tersisa 43 hari" in r.text
    assert r.derivations == ["Tanggal pulang 2026-09-27: dihitung dari tanggal masuk Anda 2026-09-25 dan 3 hari rawat inap."]


def test_deadline_that_has_passed_says_so():
    r = turn(session(date(2026, 12, 1)), SCENE)
    assert r.deadline == date(2026, 11, 26) and r.readiness.days_left == -5
    assert "which passed 5 days ago" in r.text and "a late claim is rejected" in r.text and "LATE_FILING" in r.readiness.denial_codes


def test_deadline_cannot_be_computed_without_a_stay_length_and_says_why():
    r = turn(session(), "I was admitted for dengue on 25 September 2026 and discharged. Can I claim on my hospital cash policy, and what is the deadline?")
    assert r.deadline is None and r.derivations == []
    assert "cannot give the filing deadline" in r.text and "60 days from the end of treatment" in r.text
    assert r.deadline_note and "discharge date" in r.deadline_note


def test_stated_discharge_date_wins_over_a_derived_one():
    r = turn(session(), "I was admitted for dengue on 25 September 2026 and discharged on 30 September 2026. Can I claim, and what is the deadline?")
    assert r.deadline == date(2026, 11, 29) and r.derivations == []
    assert r.verdicts[0].payable == Decimal(3_000_000)


def test_composer_accepts_the_derived_deadline_but_not_an_invented_one():
    s = session()
    r = turn(s, SCENE)
    from clauseguard.agent.loop import _reply_payload
    from clauseguard.agent.planner import Intent, Plan

    pl = Plan(intent=Intent.CLAIM_GUIDANCE, tool_calls=[], needs_facts=True, topics=[], rule_hits=[])
    pols = router().source.policies_for(s) if hasattr(router().source, "policies_for") else []
    payload = _reply_payload(s, pl, SCENE, r.text, pols, [], {"verdicts": r.verdicts, "readiness": r.readiness, "deadline": r.deadline, "payable": r.payable,
                                                             "derivations": r.derivations, "alerts": r.alerts})
    good = "Your deadline is 2026-11-26, calculated from your admission on 2026-09-25 and 3 days; the benefit is IDR 1,500,000. This is indicative; the policy wording prevails."
    assert composer.verify(good, payload) == []
    assert composer.verify(good.replace("2026-11-26", "2026-11-27"), payload) == ["DATE:2026-11-27"]


def test_survival_period_is_shown_as_a_dated_item_when_the_diagnosis_date_is_known():
    s = Session("rizky", "rizky", as_of=date(2026, 10, 11))
    r = turn(s, "I was diagnosed with cancer on 1 October 2026. Can I claim on my critical illness policy?")
    assert "Survival period for CI-CHUBB-05: the insured must survive until 2026-10-31 (diagnosis 2026-10-01 + 30 days, 20 days from today)" in r.text
    assert r.clarification is not None and r.clarification.slot == Slot.SURVIVAL_DAYS


def test_derive_module_is_the_inclusive_day_convention():
    f = ScenarioFacts(values={Slot.DAYS_HOSPITALIZED: 3}, as_of=AS_OF)
    dates, derived = derive.derive_event_dates({"admission": date(2026, 9, 25)}, f)
    assert dates["discharge"] == date(2026, 9, 27) and dates["treatment_end"] == date(2026, 9, 27) and derived["discharge"].days == 3
    assert derive.stay_days(date(2026, 10, 3), date(2026, 10, 7)) == 5


@pytest.fixture
def client(sandbox_db):
    api.SESSIONS.clear()
    with TestClient(api.app) as c:
        yield c


def test_timeline_endpoint_uses_the_same_derivation(client):
    token = client.post("/login", json={"persona": "rizky"}).json()["session_token"]
    h = {"X-Session-Token": token}
    api.SESSIONS[token].as_of = AS_OF
    client.post("/chat", json={"text": SCENE}, headers=h)
    body = client.get("/entitlement/timeline", headers=h).json()
    fd = [e for e in body["events"] if e["kind"] == "FILING_DEADLINE" and e.get("claim_id") == "CHAT-SCENARIO"]
    assert len(fd) == 1 and fd[0]["date"] == "2026-11-26" and fd[0]["days_left"] == 43 and fd[0]["policy_id"] == "HCP-SOMPO-01"


def test_timeline_shows_the_survival_period_end_for_a_chat_diagnosis(client):
    token = client.post("/login", json={"persona": "rizky"}).json()["session_token"]
    h = {"X-Session-Token": token}
    api.SESSIONS[token].as_of = date(2026, 10, 11)
    client.post("/chat", json={"text": "I was diagnosed with cancer on 1 October 2026. Can I claim on my critical illness policy?"}, headers=h)
    body = client.get("/entitlement/timeline", headers=h).json()
    sv = [e for e in body["events"] if e["kind"] == "SURVIVAL_PERIOD_ENDS"]
    assert len(sv) == 1 and sv[0]["date"] == "2026-10-31" and sv[0]["policy_id"] == "CI-CHUBB-05"


# ------------------------------------------------------------------ P2: alerts
def test_lapse_alert_is_shown_once_as_a_heads_up_then_not_again():
    s = session()
    r1 = turn(s, SCENE)
    assert any("TL-ASTRA-07" in a and "Heads-up" in a for a in r1.alerts)
    r2 = turn(s, "What do I need to send?")
    assert r2.alerts == []
    r3 = turn(s, "Correction: it was 5 days, not 3")
    assert r3.alerts == []


def test_unrelated_alert_is_not_shown_after_the_first_turn():
    s = session()
    turn(s, "What is my daily hospital cash benefit?")
    r = turn(s, SCENE)
    assert not any("TL-ASTRA-07" in a for a in r.alerts)


def test_alert_appears_when_the_question_is_about_the_lapsed_policy():
    s = session()
    turn(s, "What is my daily hospital cash benefit?")
    r = turn(s, "If I die, what does my life policy pay?")
    assert any("TL-ASTRA-07" in a and "Heads-up" not in a for a in r.alerts)
    r = turn(s, "Is my life policy still in force?")
    assert any("TL-ASTRA-07" in a for a in r.alerts)


# ------------------------------------------------------------------ P3: submit gate
def _scene_with_missing_documents():
    s = session()
    turn(s, SCENE)
    return s


def test_submit_with_missing_documents_offers_no_confirm_card():
    s = _scene_with_missing_documents()
    r = turn(s, "Submit the HCP claim for me.")
    assert r.actions_pending == [] and not s.pending_actions
    assert "still missing" in r.text and "original claim form" in r.text and "rejected or delayed" in r.text
    assert "attach the documents" in r.text and "submit anyway" in r.text and "Nothing has been submitted" in r.text
    assert "IDR 1,500,000" in r.text and "1500000" not in r.text and "2026-11-26" in r.text and "None" not in r.text
    assert not any(c["tier"] >= 2 and c["allowed"] for c in r.tool_calls) and not s.open_claims


def test_submit_anyway_prepares_a_card_that_lists_the_missing_items():
    s = _scene_with_missing_documents()
    turn(s, "Submit the HCP claim for me.")
    r = turn(s, "submit anyway")
    card = r.actions_pending[0]
    assert card["tool"] == "submit_claim" and card["incomplete"] and card["requires_acknowledgement"]
    assert "original claim form" in card["missing_documents"] and "WITH MISSING DOCUMENTS" in card["summary"] and "IDR 1,500,000" in card["summary"]
    assert "2026-11-26" in card["summary"] and "None" not in card["summary"] and card["acknowledgement_text"]
    assert not s.open_claims


def test_submit_anyway_without_a_prior_offer_does_not_skip_the_gate():
    s = _scene_with_missing_documents()
    r = turn(s, "submit anyway")
    assert r.actions_pending == [] and "still missing" in r.text


def test_confirmed_incomplete_submission_reports_honestly_with_real_amount_and_deadline():
    s = _scene_with_missing_documents()
    turn(s, "Submit the HCP claim for me.")
    turn(s, "submit anyway")
    r = confirm_pending(s, router=router())
    assert s.open_claims and s.open_claims[0]["status"] == "submitted"
    assert s.open_claims[0]["expected_amount"] == 1_500_000 and s.open_claims[0]["deadline"] == "2026-11-26"
    cid = s.open_claims[0]["id"]
    assert f"filed in the sandbox insurer system as {cid}" in r.text and "IDR 1,500,000" in r.text and "Filing deadline: 2026-11-26" in r.text
    assert "submitted with missing documents" in r.text and "None" not in r.text and "1500000" not in r.text


def test_complete_documents_keep_the_plain_confirm_card():
    s = _scene_with_missing_documents()
    r = turn(s, "I have all the documents ready: claim form, receipts, itemised bill, medical resume, prescription and lab results.")
    r = turn(s, "Submit the HCP claim for me.")
    card = r.actions_pending[0]
    assert card["tool"] == "submit_claim" and "incomplete" not in card and "documents missing: none" in card["summary"]
    r = confirm_pending(s, router=router())
    assert s.open_claims and "submitted with missing documents" not in r.text


def test_submit_gate_in_indonesian():
    s = session()
    turn(s, SCENE_ID)
    r = turn(s, "Ajukan klaim HCP untuk saya")
    assert r.actions_pending == [] and "belum saya ajukan" in r.text and "ditolak atau tertunda" in r.text and "IDR 1,500,000" in r.text
    r = turn(s, "ajukan saja")
    assert r.actions_pending and r.actions_pending[0]["incomplete"]


# ------------------------------------------------------------------ P4: corrections
def test_days_correction_recomputes_amount_discharge_and_deadline():
    s = session()
    r1 = turn(s, "I was hospitalised for dengue from 25 Sept 2026, 3 days. Can I claim on my hospital cash plan?")
    assert r1.payable == Decimal(1_500_000) and r1.deadline == date(2026, 11, 26)
    r2 = turn(s, "Correction: it was 5 days, not 3")
    assert r2.payable == Decimal(2_500_000) and r2.deadline == date(2026, 11, 28) and r2.facts["days_hospitalized"] == 5
    assert "Updated: 3 → 5 days in hospital; discharge date 2026-09-27 → 2026-09-29; filing deadline 2026-11-26 → 2026-11-28; the benefit is now IDR 2,500,000 (was IDR 1,500,000)" in r2.text
    assert r2.derivations == ["Discharge date 2026-09-29: calculated from your admission date 2026-09-25 and 5 days in hospital."]
    assert "days_hospitalized" in r2.changed and r2.update_note and "Discharge date 2026-09-27" not in r2.text.replace(r2.update_note, "")


def test_date_correction_moves_discharge_and_deadline():
    s = session()
    turn(s, "I was hospitalised for dengue from 25 Sept 2026, 3 days. Can I claim on my hospital cash plan?")
    r = turn(s, "Sorry, I was admitted on 28 September")
    assert r.deadline == date(2026, 11, 29) and r.payable == Decimal(1_500_000)
    assert "admission date 2026-09-25 → 2026-09-28" in r.text and "discharge date 2026-09-27 → 2026-09-30" in r.text and "filing deadline 2026-11-26 → 2026-11-29" in r.text
    assert s.event_dates["admission"] == date(2026, 9, 28)


def test_diagnosis_correction_is_reported_and_rebinds():
    s = session()
    turn(s, "I was hospitalised for dengue from 25 Sept 2026, 3 days. Can I claim on my hospital cash plan?")
    r = turn(s, "Actually it was typhoid, not dengue")
    assert s.diagnosis_code == "TYPHOID" and "diagnosis dengue → typhoid" in r.text and "diagnosis" in r.changed
    assert r.deadline == date(2026, 11, 26)


def test_contradiction_clears_the_stay_instead_of_keeping_stale_values():
    s = session()
    turn(s, "I was hospitalised for dengue from 25 Sept 2026, 3 days. Can I claim on my hospital cash plan?")
    r = turn(s, "actually I was never admitted")
    assert Slot.EVENT not in s.facts.values and Slot.DAYS_HOSPITALIZED not in s.facts.values
    assert "admission" not in s.event_dates and s.diagnosis_code is None
    assert "removed the hospital stay" in r.text and r.clarification is not None and r.clarification.slot == Slot.EVENT
    assert r.deadline is None and r.payable is None and r.verdicts == []
    later = turn(s, "I was hospitalised for 2 days from 1 October 2026 with fever")
    assert later.facts["days_hospitalized"] == 2 and s.event_dates["admission"] == date(2026, 10, 1)


@pytest.mark.parametrize("text, retracted", [
    ("actually I was never admitted", True), ("I wasn't hospitalised after all", True), ("sebenarnya saya tidak pernah dirawat", True),
    ("I was hospitalised for 3 days", False), ("he was never admitted before this", True),
])
def test_retraction_rule(text, retracted):
    assert bool(bind_rules(text, AS_OF)[1].retracted) == retracted


def test_correction_with_a_bare_number_is_a_stay_length_only_in_a_stay_context():
    prior = ScenarioFacts(values={Slot.EVENT: "HOSPITALIZATION", Slot.DAYS_HOSPITALIZED: 3}, as_of=AS_OF)
    assert bind_rules("Correction: it was 5 days, not 3", AS_OF, prior=prior)[0].values[Slot.DAYS_HOSPITALIZED] == 5
    assert bind_rules("it was not 3 days but 5 days", AS_OF, prior=prior)[0].values[Slot.DAYS_HOSPITALIZED] == 5
    assert bind_rules("Correction: it was 5 days, not 3", AS_OF)[0].values.get(Slot.DAYS_HOSPITALIZED) is None


# ---- the model binder: a correction turn lets it revise a value the rules did not touch
class SheetLLM:
    def __init__(self, sheets: list[dict]):
        self.sheets = sheets
        self.n = 0

    def __call__(self, prompt, *, model=None, schema=None, system=None, **kw):
        name = getattr(schema, "__name__", "")
        if name == "FactSheet":
            sheet = self.sheets[min(self.n, len(self.sheets) - 1)]
            self.n += 1
            return sheet
        if name == "_LLMPlan":
            return {"intent": "CLAIM_GUIDANCE", "tools": ["get_my_policies"], "policy_id_mentioned": None, "needs_facts": True}
        raise RuntimeError("not mocked")


def test_model_binder_revises_a_value_on_a_correction_turn(monkeypatch):
    llm_mock = SheetLLM([{"event": "HOSPITALIZATION", "cause": "ILLNESS", "admission_date": "2026-09-25", "days_hospitalized": 3},
                         {"event": "HOSPITALIZATION", "days_hospitalized": 5}])
    monkeypatch.setattr(llm, "generate_json", llm_mock)
    assert FactSheet.model_validate(llm_mock.sheets[1]).days_hospitalized == 5
    s = session()
    r1 = handle_turn(s, "I was hospitalised for dengue from 25 Sept 2026, 3 days. Can I claim on my hospital cash plan?", router=router(), use_llm=True)
    assert r1.payable == Decimal(1_500_000)
    r2 = handle_turn(s, "Actually, make it five days instead", router=router(), use_llm=True)
    assert r2.facts["days_hospitalized"] == 5 and r2.payable == Decimal(2_500_000) and r2.deadline == date(2026, 11, 28)
    assert "3 → 5 days in hospital" in r2.template_text


def test_model_binder_cannot_resurrect_a_retracted_stay(monkeypatch):
    llm_mock = SheetLLM([{"event": "HOSPITALIZATION", "cause": "ILLNESS", "admission_date": "2026-09-25", "days_hospitalized": 3},
                         {"event": "HOSPITALIZATION", "days_hospitalized": 3, "admission_date": "2026-09-25"}])
    monkeypatch.setattr(llm, "generate_json", llm_mock)
    s = session()
    handle_turn(s, "I was hospitalised for dengue from 25 Sept 2026, 3 days. Can I claim on my hospital cash plan?", router=router(), use_llm=True)
    r = handle_turn(s, "actually I was never admitted", router=router(), use_llm=True)
    assert Slot.EVENT not in s.facts.values and r.verdicts == [] and "admission" not in s.event_dates


def test_model_binder_does_not_override_what_the_rules_bound_this_turn(monkeypatch):
    llm_mock = SheetLLM([{"event": "HOSPITALIZATION", "cause": "ILLNESS", "admission_date": "2026-09-25", "days_hospitalized": 3},
                         {"event": "HOSPITALIZATION", "days_hospitalized": 3}])
    monkeypatch.setattr(llm, "generate_json", llm_mock)
    s = session()
    handle_turn(s, "I was hospitalised for dengue from 25 Sept 2026, 3 days. Can I claim on my hospital cash plan?", router=router(), use_llm=True)
    r = handle_turn(s, "Correction: it was 5 days, not 3", router=router(), use_llm=True)
    assert r.facts["days_hospitalized"] == 5 and r.payable == Decimal(2_500_000)
