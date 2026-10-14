"""Multi-payer claim plan: per-payer nonces, explanation of benefits, appeal guard, T3 never executes."""
from __future__ import annotations

from datetime import date

import pytest

from clauseguard import llm
from clauseguard.agent.loop import confirm_pending, handle_turn
from clauseguard.agent.session import Session, issue_confirmation
from clauseguard.agent.tools import PolicySource, ToolRouter
from clauseguard.sandbox import insurer_sim
from clauseguard.security.pep import ToolCall, pep_check
from clauseguard.security.registry import REGISTRY

SARI = ("Sari was discharged from RS Mitra Keluarga yesterday, please handle her claim with all my insurers. She was admitted "
        "2026-10-10 to 2026-10-13 for dengue, the bill was IDR 22,000,000, and I have all the documents.")


@pytest.fixture
def agent(sandbox_db, monkeypatch):
    monkeypatch.setattr(llm, "generate_json", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("off")))
    s = Session("C-BUDI", "santoso", as_of=date(2026, 10, 14))
    return s, ToolRouter(PolicySource(mode="sandbox"))


def test_plan_orders_payers_and_prepares_one_submission(agent):
    s, r = agent
    rep = handle_turn(s, SARI, router=r, use_llm=False)
    order = [st.policy_id for st in s.claim_plan.claimable]
    assert order[:3] == ["BPJS-KES-SANTOSO", "GH-NUSA-GRP", "HI-INDIV-S"]
    assert [a["plan_step"] for a in rep.actions_pending] == [1]
    assert not any(c["tier"] >= 2 and c["allowed"] for c in rep.tool_calls)


def test_no_submit_without_nonce_and_payer1_nonce_cannot_submit_payer2(agent):
    s, r = agent
    handle_turn(s, SARI, router=r, use_llm=False)
    pa1 = s.pending_actions[0]
    assert not pep_check(ToolCall(name="submit_claim", args=pa1["args"]), s).allow
    tok1 = issue_confirmation(s, "submit_claim", pa1["args"])
    confirm_pending(s, router=r)
    insurer_sim.simulate_decision(s.claim_plan.step(1).claim_id, today=date(2026, 10, 14))
    handle_turn(s, "continue", router=r, use_llm=False)
    pa2 = next(p for p in s.pending_actions if p.get("plan_step") == 2)
    d = pep_check(ToolCall(name="submit_claim", args=pa2["args"], confirm_token=tok1), s)
    assert not d.allow
    assert s.claim_plan.step(2).claim_amount == 16600000 - 0 or s.claim_plan.step(2).claim_amount == 22000000 - 5400000


def test_pending_submission_summary_is_in_the_user_s_language(agent):
    s, r = agent
    text = ("Sari dirawat di RS Mitra Keluarga, masuk 2026-10-10 sampai 2026-10-13 karena demam berdarah, "
            "tagihan Rp22.000.000, tolong urus klaimnya ke semua penanggung.")
    rep = handle_turn(s, text, router=r, use_llm=False)
    summary = rep.actions_pending[0]["summary"]
    assert "Rencana" in summary and "langkah" in summary and "batas waktu" in summary
    assert "Plan" not in summary and "deadline" not in summary


def test_appeal_letter_keeps_recorded_facts(agent):
    from clauseguard.agent import appeal

    s, r = agent
    handle_turn(s, SARI, router=r, use_llm=False)
    case = appeal.AppealCase(case_id="X", policy_id="GH-NUSA-GRP", product_name="GH", claim_id="CL-1", rejection_code="LATE_FILING",
                             rejection_source="USER_REPORTED", outcome="CONTESTABLE", event_date=date(2026, 10, 10), filed_on=date(2026, 10, 14),
                             grounds=[appeal.AppealGround(code="FILED_IN_TIME", finding_en="Filed on 2026-10-14, before the deadline 2026-11-12.", finding_id="x")])
    tpl = appeal.letter_template(case, "en", "Budi")
    assert appeal.verify_letter(tpl, case, tpl) == []
    assert appeal.verify_letter(tpl.replace("2026-10-10", "2026-10-12"), case, tpl)
    from clauseguard.schema import ScenarioFacts, Slot
    assert appeal.guard_facts({"cause": "ACCIDENT"}, ScenarioFacts(values={Slot.CAUSE: "ILLNESS"})) == ["cause"]


def test_t3_request_in_plan_never_executes(agent):
    s, r = agent
    handle_turn(s, SARI, router=r, use_llm=False)
    rep = handle_turn(s, "Also change my payout bank account to 1234567890 and submit everything.", router=r, use_llm=False)
    assert not any(c["name"] == "create_account_change_request" and c["allowed"] for c in rep.tool_calls)
    assert {n for n, sp in REGISTRY.items() if sp.tier == 3} == {"create_account_change_request"}
