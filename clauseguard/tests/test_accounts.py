"""Accounts: with CG_AUTH=supabase the open persona/guest login is closed, and one account can never reach
another account's uploads, claims or chats. Supabase itself is replaced by a stub that answers the same
question the real service does: who owns this access token."""
from __future__ import annotations

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from clauseguard import config
from clauseguard.sandbox import api

ALICE = {"sub": "11111111-1111-1111-1111-111111111111", "email": "alice@example.com"}
BOB = {"sub": "22222222-2222-2222-2222-222222222222", "email": "bob@example.com"}
RIZKY = {"sub": "33333333-3333-3333-3333-333333333333", "email": "rizky@demo.clauseguard.id"}
ACCOUNTS = {"tok-alice": ALICE, "tok-bob": BOB, "tok-rizky": RIZKY}


@pytest.fixture
def client(sandbox_db, monkeypatch):
    monkeypatch.setattr(config, "AUTH_MODE", "supabase")

    def verified(token: str):
        if token == "tok-unconfirmed":
            raise HTTPException(403, "confirm your email first")
        if token not in ACCOUNTS:
            raise HTTPException(401, "sign in again")
        return ACCOUNTS[token]

    monkeypatch.setattr(api, "_verified_account", verified)
    api.SESSIONS.clear()
    with TestClient(api.app) as c:
        yield c


def _login(client, token):
    r = client.post("/login", json={"access_token": token})
    assert r.status_code == 200, r.text
    return r.json()


def _h(login):
    return {"X-Session-Token": login["session_token"]}


def test_open_logins_are_closed(client):
    assert client.post("/login", json={"persona": "rizky"}).status_code == 401
    assert client.post("/login", json={"persona": "guest"}).status_code == 401
    assert client.post("/login", json={"persona": "guest", "account_id": "C-GUEST-0123456789ABCDEF"}).status_code == 401
    assert client.get("/personas").json() == []


def test_bad_or_unconfirmed_token_rejected(client):
    assert client.post("/login", json={"access_token": "forged"}).status_code == 401
    assert client.post("/login", json={"access_token": "tok-unconfirmed"}).status_code == 403


def test_new_account_is_empty_and_demo_account_has_policies(client):
    a = _login(client, "tok-alice")
    assert a["user_id"].startswith("U-") and a["demo"] is False and a["account"] == "alice@example.com"
    # the only thing a new account sees is the public statutory scheme, which belongs to nobody
    assert {x["id"] for x in client.get("/policies", headers=_h(a)).json()["policies"]} <= {"JASA-RAHARJA"}
    r = _login(client, "tok-rizky")
    assert r["user_id"] == "C-RIZKY" and r["demo"] is True and r["persona_key"] == "rizky"
    assert len(client.get("/policies", headers=_h(r)).json()["policies"]) > 0


def test_accounts_cannot_see_each_others_uploads(client, tmp_path):
    a, b = _login(client, "tok-alice"), _login(client, "tok-bob")
    up = client.post("/upload", files={"file": ("bill.pdf", b"%PDF-1.4 alice", "application/pdf")}, headers=_h(a)).json()
    doc = up["doc_id"]
    assert client.get(f"/uploads/{doc}", headers=_h(a)).status_code == 200
    assert client.get(f"/uploads/{doc}", headers=_h(b)).status_code == 403
    # naming her file (or a path to it) in a chat turn must not work for Bob either
    for ref in (doc, str(api.UPLOAD_DIR / doc), "../../.env"):
        assert client.post("/chat", json={"text": "read this", "uploads": [ref]}, headers=_h(b)).status_code == 403


def test_accounts_cannot_see_each_others_chats(client):
    a, b = _login(client, "tok-alice"), _login(client, "tok-bob")
    body = {"title": "my claim", "messages": [{"role": "user", "text": "secret"}]}
    assert client.put("/history/c1700000000_abcdef", json=body, headers=_h(a)).status_code == 200
    assert [c["id"] for c in client.get("/history", headers=_h(a)).json()["conversations"]] == ["c1700000000_abcdef"]
    assert client.get("/history", headers=_h(b)).json()["conversations"] == []
    assert client.get("/history/c1700000000_abcdef", headers=_h(b)).status_code == 404
    # Bob writing to Alice's conversation id must neither overwrite nor delete hers
    assert client.put("/history/c1700000000_abcdef", json={**body, "title": "hijack"}, headers=_h(b)).status_code in (403, 404, 409)
    assert client.delete("/history/c1700000000_abcdef", headers=_h(b)).status_code == 404
    assert client.get("/history/c1700000000_abcdef", headers=_h(a)).json()["title"] == "my claim"


def test_accounts_cannot_open_each_others_claims(client):
    a, r = _login(client, "tok-alice"), _login(client, "tok-rizky")
    assert client.get("/claims/CL-RIZKY-HCP-01", headers=_h(a)).status_code == 403
    assert client.get("/claims/CL-RIZKY-HCP-01", headers=_h(r)).status_code == 200
