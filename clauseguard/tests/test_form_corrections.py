"""Typed corrections of free-text claim-form fields while a form waits for Confirm."""
from __future__ import annotations

from types import SimpleNamespace

from clauseguard.agent import loop


def _session(pending=True):
    return SimpleNamespace(pending_actions=[{"tool": "submit_claim"}] if pending else [], facility_name="RS Sehat Sentosa",
                           form_overrides=None, rebuild_submit=None, turn=1, session_id="S-x", user_id="U-1")


def test_hospital_and_names_are_applied_and_form_withdrawn(monkeypatch):
    monkeypatch.setattr(loop, "audit", lambda *a, **k: "E-1")
    s = _session()
    assert loop._form_text_correction(s, "The hospital is RS Harapan Kita.") == "facility_name"
    assert s.facility_name == "RS Harapan Kita" and s.pending_actions == [] and s.rebuild_submit["changes"]
    s = _session()
    assert loop._form_text_correction(s, "The insured person's name is Rizky Pratama Putra.") == "insured_name"
    assert s.form_overrides == {"insured_name": "Rizky Pratama Putra"}


def test_no_effect_without_a_waiting_form_or_with_odd_values(monkeypatch):
    monkeypatch.setattr(loop, "audit", lambda *a, **k: "E-1")
    assert loop._form_text_correction(_session(pending=False), "The hospital is RS Harapan Kita.") is None
    assert loop._form_text_correction(_session(), "The hospital is <script>alert(1)</script>") is None
    assert loop._form_text_correction(_session(), "What is covered?") is None
