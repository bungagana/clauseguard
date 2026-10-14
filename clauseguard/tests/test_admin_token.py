"""Admin/back-office token must have no hardcoded default: unset -> disabled (403)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from clauseguard import config
from clauseguard.sandbox import api


@pytest.fixture
def client(sandbox_db):
    api.SESSIONS.clear()
    with TestClient(api.app) as c:
        yield c


def test_no_token_configured_disables_admin_endpoints(client, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_TOKEN", "")
    # no header at all
    assert client.post("/admin/kill", json={"reason": "x"}).status_code == 403
    # the old literal hardcoded default must not work even if someone still sends it
    r = client.post("/admin/kill", json={"reason": "x"}, headers={"X-Admin-Token": "sandbox-admin-token"})
    assert r.status_code == 403
    r = client.post(
        "/backoffice/claims/CL-RIZKY-HCP-01/decide",
        json={"decision": "approved"},
        headers={"X-Admin-Token": "sandbox-admin-token"},
    )
    assert r.status_code == 403
    assert client.get("/backoffice/tickets", headers={"X-Admin-Token": "sandbox-admin-token"}).status_code == 403


def test_configured_token_required_exactly(client, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_TOKEN", "a-real-secret")
    assert client.post("/admin/kill", json={"reason": "x"}, headers={"X-Admin-Token": "wrong"}).status_code == 403
    r = client.post("/admin/kill", json={"reason": "x"}, headers={"X-Admin-Token": "a-real-secret"})
    assert r.status_code == 200
    client.delete("/admin/kill", headers={"X-Admin-Token": "a-real-secret"})


def test_non_ascii_header_does_not_500(monkeypatch):
    """secrets.compare_digest raises TypeError on mismatched str/bytes or encodings; _admin must
    handle a non-ASCII header value cleanly (403), not crash. Exercised directly since an HTTP
    client itself typically refuses to send a raw non-ASCII header."""
    monkeypatch.setattr(config, "ADMIN_TOKEN", "a-real-secret")
    with pytest.raises(Exception) as e:
        api._admin(x_admin_token="é")
    from fastapi import HTTPException

    assert isinstance(e.value, HTTPException) and e.value.status_code == 403


def test_app_still_works_with_no_admin_token_configured(client, monkeypatch):
    """Rest of the API (the scored demo surface) must not crash when admin is disabled."""
    monkeypatch.setattr(config, "ADMIN_TOKEN", "")
    r = client.post("/login", json={"persona": "rizky"})
    assert r.status_code == 200
    h = {"X-Session-Token": r.json()["session_token"]}
    assert client.post("/tools/get_my_policies", json={"args": {}}, headers=h).status_code == 200


def test_env_example_has_no_hardcoded_secret():
    text = (config.ROOT / ".env.example").read_text(encoding="utf-8")
    assert "sandbox-admin-token" not in text
    assert "CG_ADMIN_TOKEN=" in text


def test_no_source_file_hardcodes_the_old_default():
    # Scoped to the app's own source/UI/scripts, not arbitrary docs or generated evidence
    # (which may legitimately discuss or log the old literal for audit purposes).
    root = config.ROOT
    dirs = [root / "clauseguard", root / "ui", root / "scripts"]
    hits = []
    for d in dirs:
        if not d.exists():
            continue
        for pattern in ("*.py", "*.js", "*.ts", "*.ps1", "*.sh"):
            for p in d.rglob(pattern):
                if "__pycache__" in p.parts:
                    continue
                if "sandbox-admin-token" in p.read_text(encoding="utf-8", errors="ignore"):
                    hits.append(str(p))
    if (root / ".env.example").read_text(encoding="utf-8").find("sandbox-admin-token") != -1:
        hits.append(".env.example")
    assert hits == [], f"old hardcoded admin token literal still present in: {hits}"
