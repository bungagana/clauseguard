"""When more than one policy could take a claim, the agent asks instead of choosing; the model's choice is closed and checked."""
from __future__ import annotations

from types import SimpleNamespace

from clauseguard import llm
from clauseguard.agent import policy_pick

A = SimpleNamespace(id="HCP-SOMPO-01", product_name="Hospital Cash", insurer="Sompo", product_type="hospital_cash")
B = SimpleNamespace(id="BPJS-KES-RIZKY", product_name="JKN", insurer="BPJS", product_type="social_bpjs_kes")


def test_one_candidate_needs_no_question():
    assert policy_pick.pick("submit", [A], None) == "HCP-SOMPO-01"


def test_two_candidates_without_a_model_keeps_the_policy_in_focus_or_asks():
    assert policy_pick.pick("submit my claim", [A, B], None, use_llm=False) is None
    assert policy_pick.pick("submit my claim", [A, B], "HCP-SOMPO-01", use_llm=False) == "HCP-SOMPO-01"


def test_the_model_may_name_one_candidate_or_say_ambiguous(monkeypatch):
    monkeypatch.setattr(llm, "generate_json", lambda *a, **k: {"choice": "BPJS-KES-RIZKY"})
    assert policy_pick.pick("ajukan ke bpjs", [A, B], "HCP-SOMPO-01") == "BPJS-KES-RIZKY"
    monkeypatch.setattr(llm, "generate_json", lambda *a, **k: {"choice": "AMBIGUOUS"})
    assert policy_pick.pick("submit my claim", [A, B], None) is None


def test_an_answer_outside_the_candidates_is_not_accepted(monkeypatch):
    monkeypatch.setattr(llm, "generate_json", lambda *a, **k: {"choice": "TL-ASTRA-07"})
    assert policy_pick.pick("submit my claim", [A, B], None) is None
