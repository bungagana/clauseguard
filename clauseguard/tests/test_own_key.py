"""The customer's own Gemini key: used only for their requests, never shared, and a failed AI call is explained in plain words."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from clauseguard import llm
from clauseguard.sandbox import api


@pytest.fixture
def client(sandbox_db):
    api.SESSIONS.clear()
    with TestClient(api.app) as c:
        yield c


def _login(client, persona):
    return {"X-Session-Token": client.post("/login", json={"persona": persona}).json()["session_token"]}


def test_a_rejected_key_is_not_stored(client, monkeypatch):
    monkeypatch.setattr(llm, "test_key", lambda k: "invalid")
    h = _login(client, "rizky")
    r = client.post("/session/api-key", json={"api_key": "A" * 30}, headers=h)
    assert r.status_code == 400 and "AI Studio" in r.json()["detail"]
    assert getattr(api.SESSIONS[h["X-Session-Token"]], "user_api_key", None) is None


def test_an_accepted_key_belongs_to_that_session_only(client, monkeypatch):
    monkeypatch.setattr(llm, "test_key", lambda k: "ok")
    a, b = _login(client, "rizky"), _login(client, "dewi")
    assert client.post("/session/api-key", json={"api_key": "K" * 30}, headers=a).status_code == 200
    assert api.SESSIONS[a["X-Session-Token"]].user_api_key == "K" * 30
    assert getattr(api.SESSIONS[b["X-Session-Token"]], "user_api_key", None) is None
    assert client.delete("/session/api-key", headers=a).status_code == 200
    assert api.SESSIONS[a["X-Session-Token"]].user_api_key is None


def test_malformed_keys_are_refused_before_any_call(client):
    h = _login(client, "rizky")
    assert client.post("/session/api-key", json={"api_key": "short"}, headers=h).status_code == 422
    assert client.post("/session/api-key", json={"api_key": "bad key with spaces and more than twenty"}, headers=h).status_code == 422


def test_ai_failures_are_described_in_the_customers_language():
    q = api._ai_notice("quota", "id", False)
    assert q["kind"] == "quota" and "Layanan AI" in q["text"] and q["can_use_own_key"]
    assert "usage limit" in api._ai_notice("quota", "en", False)["text"]
    assert api._ai_notice(None, "en", False) is None
    assert "Your Gemini key" in api._ai_notice("quota", "en", True)["text"]
