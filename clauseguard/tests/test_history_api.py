"""Conversation history API: per-user ownership, validation, audit, and that the agent cannot reach it."""
from __future__ import annotations

import importlib
import json

import pytest
from fastapi.testclient import TestClient

from clauseguard import config
from clauseguard.sandbox import api, history_store
from clauseguard.security import audit


@pytest.fixture
def client(sandbox_db, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "HISTORY_DB_PATH", tmp_path / "history.sqlite")
    api.SESSIONS.clear()
    with TestClient(api.app) as c:
        yield c


def login(client, persona="rizky"):
    r = client.post("/login", json={"persona": persona})
    assert r.status_code == 200, r.text
    return {"X-Session-Token": r.json()["session_token"]}


def body(title="Hello there", n=2):
    return {"title": title, "messages": [{"id": f"m{i}", "role": "user", "text": f"secret-body-{i}"} for i in range(n)]}


def test_round_trip(client):
    h = login(client)
    r = client.put("/history/conv_000001", json=body(), headers=h)
    assert r.status_code == 200 and r.json()["created"] is True
    r = client.get("/history", headers=h)
    items = r.json()["conversations"]
    assert [i["id"] for i in items] == ["conv_000001"]
    assert items[0]["persona"] == "rizky" and items[0]["message_count"] == 2
    full = client.get("/history/conv_000001", headers=h).json()
    assert full["title"] == "Hello there" and full["messages"][1]["text"] == "secret-body-1"
    assert client.patch("/history/conv_000001", json={"title": "Renamed"}, headers=h).status_code == 200
    assert client.get("/history/conv_000001", headers=h).json()["title"] == "Renamed"
    r = client.put("/history/conv_000001", json=body("Renamed", 3), headers=h)
    assert r.json()["created"] is False
    assert client.get("/history", headers=h).json()["conversations"][0]["message_count"] == 3
    assert client.delete("/history/conv_000001", headers=h).status_code == 200
    assert client.get("/history/conv_000001", headers=h).status_code == 404
    assert client.get("/history", headers=h).json()["conversations"] == []


def test_list_has_no_message_bodies(client):
    h = login(client)
    client.put("/history/conv_000001", json=body(), headers=h)
    raw = client.get("/history", headers=h).text
    assert "secret-body" not in raw and "messages" not in json.loads(raw)["conversations"][0]


def test_requires_session(client):
    assert client.get("/history").status_code == 401
    assert client.put("/history/conv_000001", json=body()).status_code == 401
    assert client.get("/history", headers={"X-Session-Token": "bogus"}).status_code == 401
    assert client.delete("/history").status_code == 401


def test_other_user_gets_404_everywhere(client):
    a, b = login(client, "rizky"), login(client, "dewi")
    client.put("/history/conv_000001", json=body("A's chat"), headers=a)
    assert client.get("/history/conv_000001", headers=b).status_code == 404
    assert client.put("/history/conv_000001", json=body("hijack"), headers=b).status_code == 404
    assert client.patch("/history/conv_000001", json={"title": "hijack"}, headers=b).status_code == 404
    assert client.delete("/history/conv_000001", headers=b).status_code == 404
    assert client.get("/history", headers=b).json()["conversations"] == []
    mine = client.get("/history/conv_000001", headers=a).json()
    assert mine["title"] == "A's chat" and mine["messages"][0]["text"] == "secret-body-0"


def test_identity_cannot_be_supplied_in_request(client):
    h = login(client)
    r = client.put("/history/conv_000001", json={**body(), "user_id": "C-DEWI"}, headers=h)
    assert r.status_code == 422
    r = client.put("/history/conv_000001", json={**body(), "persona": "dewi"}, headers=h)
    assert r.status_code == 422


def test_clear_only_clears_callers(client):
    a, b = login(client, "rizky"), login(client, "dewi")
    client.put("/history/conv_000001", json=body(), headers=a)
    client.put("/history/conv_000002", json=body(), headers=a)
    client.put("/history/conv_000003", json=body(), headers=b)
    assert client.delete("/history", headers=a).json() == {"deleted": 2}
    assert client.get("/history", headers=a).json()["conversations"] == []
    assert [c["id"] for c in client.get("/history", headers=b).json()["conversations"]] == ["conv_000003"]


def test_validation(client):
    h = login(client)
    assert client.put("/history/conv_000001", json=body("x" * 201), headers=h).status_code == 422
    assert client.put("/history/conv_000001", json=body(""), headers=h).status_code == 422
    assert client.put("/history/conv_000001", json={**body(), "extra": 1}, headers=h).status_code == 422
    assert client.put("/history/abc", json=body(), headers=h).status_code == 400
    assert client.put("/history/bad.id.value", json=body(), headers=h).status_code == 400
    assert client.put("/history/" + "a" * 65, json=body(), headers=h).status_code == 400
    big = {"title": "big", "messages": [{"text": "y" * (history_store.MAX_MESSAGES_BYTES + 10)}]}
    assert client.put("/history/conv_000001", json=big, headers=h).status_code == 413
    assert client.get("/history", headers=h).json()["conversations"] == []


def test_per_user_cap_evicts_oldest(client, monkeypatch):
    monkeypatch.setattr(history_store, "MAX_PER_USER", 3)
    h = login(client)
    for i in range(5):
        r = client.put(f"/history/conv_00000{i}", json={**body(), "updated_at": 1_000_000 + i}, headers=h)
        assert r.status_code == 200
    ids = [c["id"] for c in client.get("/history", headers=h).json()["conversations"]]
    assert ids == ["conv_000004", "conv_000003", "conv_000002"]


def test_history_is_not_a_tool(client):
    names = [t["name"] for t in client.get("/tools").json()]
    assert names and not any("history" in n.lower() for n in names)
    h = login(client)
    r = client.post("/tools/history", json={"args": {}}, headers=h)
    assert r.status_code in (400, 403, 404)


def test_audit_events_carry_no_content(client):
    h = login(client)
    client.put("/history/conv_000001", json=body(), headers=h)
    client.put("/history/conv_000001", json=body(n=3), headers=h)
    client.get("/history", headers=h)
    client.get("/history/conv_000001", headers=h)
    client.delete("/history/conv_000001", headers=h)
    client.delete("/history", headers=h)
    events = [e for e in audit.get_default().read() if str(e["event_type"]).startswith("HISTORY_")]
    kinds = [e["event_type"] for e in events]
    assert kinds.count("HISTORY_SAVE") == 1
    assert {"HISTORY_READ", "HISTORY_DELETE", "HISTORY_CLEAR"} <= set(kinds)
    assert "secret-body" not in json.dumps(events) and "Hello there" not in json.dumps(events)
    assert audit.verify(config.AUDIT_PATH)[0]


def test_persists_across_store_reopen(client, tmp_path):
    h = login(client)
    client.put("/history/conv_000001", json=body(), headers=h)
    user_id = api.SESSIONS[h["X-Session-Token"]].user_id
    reloaded = importlib.reload(history_store)
    row = reloaded.get(user_id, "conv_000001")
    assert row is not None and json.loads(row["messages_json"])[0]["text"] == "secret-body-0"
    assert reloaded.get("someone-else", "conv_000001") is None
