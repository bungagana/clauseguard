"""End-to-end through the FastAPI sandbox: login -> draft -> (deny) -> confirm -> submit; T3 ticket; kill switch; back office."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from clauseguard import config
from clauseguard.sandbox import api, tools


@pytest.fixture
def client(sandbox_db):
    api.SESSIONS.clear()
    with TestClient(api.app) as c:
        yield c


def login(client, persona="rizky"):
    r = client.post("/login", json={"persona": persona})
    assert r.status_code == 200, r.text
    return {"X-Session-Token": r.json()["session_token"]}


def test_login_and_read_own_policies(client):
    h = login(client)
    r = client.post("/tools/get_my_policies", json={"args": {}}, headers=h)
    assert r.status_code == 200
    ids = {p["id"] for p in r.json()["result"]["policies"]}
    assert ids == {"HCP-SOMPO-01", "TL-ASTRA-07", "CI-CHUBB-05", "BPJS-KES-RIZKY", "JASA-RAHARJA"}
    assert r.json()["handle"].startswith("$v")


def test_household_scope_for_santoso(client):
    h = login(client, "santoso")
    r = client.post("/tools/get_my_policies", json={"args": {}}, headers=h)
    assert "HI-INDIV-S" in {p["id"] for p in r.json()["result"]["policies"]}  # Sari's policy, same household
    r = client.post("/tools/get_payment_status", json={"args": {"policy_id": "HCP-SOMPO-01"}}, headers=h)
    assert r.status_code == 403 and "NOT_OWNER" in r.json()["detail"]["reason"]


def test_payment_status_surfaces_grace(client):
    h = login(client)
    r = client.post("/tools/get_payment_status", json={"args": {"policy_id": "TL-ASTRA-07"}}, headers=h)
    body = r.json()["result"]
    assert body["premium_status"] in ("OVERDUE", "LAPSED") and "2026-09-01" in body["unpaid_due_dates"]


def test_claim_flow_requires_confirmation(client):
    h = login(client)
    facts = {"event": "HOSPITALIZATION", "cause": "ILLNESS", "days_since_effective": 44, "disease_in_specified_list": False, "diagnosis_before_effective": False,
             "days_hospitalized": 5, "premium_status": "PAID", "is_accident": False, "is_emergency": False}
    r = client.post("/tools/draft_claim", json={"args": {"policy_id": "HCP-SOMPO-01", "claim_facts": facts}}, headers=h)
    assert r.status_code == 200, r.text
    draft_handle = r.json()["handle"]
    assert r.json()["result"]["amount"] == "2500000"
    # literal instead of handle
    r = client.post("/tools/submit_claim", json={"args": {"draft_handle": "DRAFT-1"}}, headers=h)
    assert r.status_code == 403 and "LITERAL_ARG" in r.json()["detail"]["reason"]
    # handle but no confirmation
    r = client.post("/tools/submit_claim", json={"args": {"draft_handle": draft_handle}}, headers=h)
    assert r.status_code == 403 and r.json()["detail"]["reason"] == "NO_CONFIRMATION"
    # UI click -> nonce -> submit
    r = client.post("/confirm", json={"tool": "submit_claim", "args": {"draft_handle": draft_handle}}, headers=h)
    token = r.json()["confirm_token"]
    r = client.post("/tools/submit_claim", json={"args": {"draft_handle": draft_handle}, "confirm_token": token}, headers=h)
    assert r.status_code == 200, r.text
    claim_id = r.json()["result"]["claim_id"]
    row = tools.conn().execute("SELECT status, created_via, claim_amount FROM claims WHERE id=?", (claim_id,)).fetchone()
    assert row["status"] == "submitted" and row["created_via"] == "assistant" and row["claim_amount"] == 2500000
    # replay of the same token is refused
    r = client.post("/tools/submit_claim", json={"args": {"draft_handle": draft_handle}, "confirm_token": token}, headers=h)
    assert r.status_code == 403
    # audit chain intact and contains the full story
    a = client.get("/audit", headers=h).json()
    assert a["chain_ok"]
    kinds = [e["event_type"] for e in a["events"]]
    assert "CONFIRM_ISSUED" in kinds and "CONFIRM_USED" in kinds and "TOOL_DENY" in kinds and "TOOL_ALLOW" in kinds


def test_t3_ticket_only_from_form(client):
    h = login(client, "dewi")
    # a value from an upload can never reach the T3 tool
    r = client.post("/upload", files={"file": ("acct.txt", b"new account 0123456789")}, headers=h)
    doc_handle = r.json()["handle"]
    r = client.post("/tools/create_account_change_request", json={"args": {"form_handle": doc_handle}}, headers=h)
    assert r.status_code == 403 and "SENSITIVE_FROM_UNTRUSTED" in r.json()["detail"]["reason"]
    # the dedicated form path works, creates a ticket, changes nothing
    r = client.post("/form", json={"form_type": "account_change", "fields": {"bank": "BCA", "account": "0123456789"}}, headers=h)
    form_handle = r.json()["handle"]
    r = client.post("/tools/create_account_change_request", json={"args": {"form_handle": form_handle}}, headers=h)
    assert r.status_code == 200, r.text
    t = tools.conn().execute("SELECT * FROM tickets").fetchone()
    assert t["requested_via"] == "REQUESTED VIA AI ASSISTANT" and t["status"] == "PENDING_OUT_OF_BAND_VERIFICATION"
    assert "0123456789" not in (t["note"] or "") and "0123456789" not in t["payload_hash"]


def test_t1_portfolio_tools_report_pending_or_work(client):
    h = login(client, "santoso")
    r = client.post("/tools/gap_analysis", json={"args": {}}, headers=h)
    assert r.status_code in (200, 501)
    if r.status_code == 501:
        assert "portfolio pending" in r.json()["detail"]


def test_admin_kill_switch_and_backoffice_need_admin_token(client):
    h = login(client)
    assert client.post("/admin/kill", json={"reason": "x"}).status_code == 403
    assert client.post("/admin/kill", json={"reason": "x"}, headers={"X-Admin-Token": config.ADMIN_TOKEN}).status_code == 200
    try:
        r = client.post("/tools/check_coverage", json={"args": {"scenario_facts": {"event": "DEATH"}}}, headers=h)
        assert r.status_code == 403 and r.json()["detail"]["reason"] == "KILL_SWITCH"
        assert "paused" in client.post("/chat", json={"text": "hi"}, headers=h).json()["text"].lower()
    finally:
        client.delete("/admin/kill", headers={"X-Admin-Token": config.ADMIN_TOKEN})
    assert client.post("/backoffice/claims/CL-RIZKY-HCP-01/decide", json={"decision": "approved"}).status_code == 403
    assert "approve_claim" not in {t["name"] for t in client.get("/tools").json()}


def test_chat_stub_passes_output_guard(client):
    h = login(client)
    r = client.post("/chat", json={"text": "Am I covered for dengue?"}, headers=h)
    assert r.status_code == 200 and "text" in r.json()


def test_upload_my_policy_live_extraction(client, monkeypatch, tmp_path):
    """POST /policies/upload runs the real extractor pipeline (mocked LLM) and the result is
    immediately visible in /policies, unverified, and owned only by the uploading session."""
    from clauseguard import schema
    from clauseguard.extractor import policy_extractor as pe

    def fake_extract_policy(path, *, policy_id, doc_id=None, source_tier=schema.SourceTier.POLICY_DOC_UNVERIFIED, product_hint=None):
        tup = schema.ClauseTuple(
            id=f"{policy_id}-t001", policy_id=policy_id, head=policy_id, relation=schema.Relation.COVERS,
            object=schema.EventCode.HOSPITALIZATION.value, qualifiers=schema.Qualifiers(amount=500000),
            evidence=schema.Evidence(doc_id=doc_id or "doc", section="S1", text="Hospitalization benefit of 500,000 per day."),
            confidence=0.9, source_tier=source_tier, language="en",
        )
        pe._LAST_META[policy_id] = {"model": "fake-model", "models_used": ["fake-model"], "calls": 2, "dropped": [], "sections": [], "glossary": []}
        return schema.PolicyRecord(
            id=policy_id, doc_id=doc_id or "doc", insurer="Fake Insurer", product_name="Fake Hospital Cash",
            product_type=product_hint or "hospital_cash", basis=schema.Basis.FIXED_BENEFIT, tuples=[tup],
            verified=False, extraction_coverage=0.75,
        )

    monkeypatch.setattr(pe, "extract_policy", fake_extract_policy)

    policy_id = None
    try:
        h = login(client, "rizky")
        import pymupdf as fitz

        _doc = fitz.open()
        _doc.new_page().insert_text((72, 72), "Fake policy PDF content for live extraction test")
        pdf_bytes = _doc.tobytes()
        _doc.close()
        r = client.post("/policies/upload", files={"file": ("my_policy.pdf", pdf_bytes, "application/pdf")}, headers=h)
        assert r.status_code == 200, r.text
        body = r.json()
        policy_id = body["policy"]["id"]
        assert policy_id.startswith("USER-")
        assert "unverified" in body["policy"]["source_badges"]
        assert body["extraction"]["tuple_count"] == 1
        assert body["extraction"]["extraction_coverage"] == 0.75
        assert body["extraction"]["model"] == "fake-model"

        # immediately visible to the uploading session
        r = client.get("/policies", headers=h)
        assert policy_id in {p["id"] for p in r.json()["policies"]}

        # not visible to a different session/user
        h2 = login(client, "dewi")
        r = client.get("/policies", headers=h2)
        assert policy_id not in {p["id"] for p in r.json()["policies"]}

        # non-PDF rejected
        r = client.post("/policies/upload", files={"file": ("not_a_policy.txt", b"hello")}, headers=h)
        assert r.status_code == 400

        # no session token -> 401
        r = client.post("/policies/upload", files={"file": ("my_policy.pdf", pdf_bytes, "application/pdf")})
        assert r.status_code == 401
    finally:
        # clean up module-level caches (clauseguard.sandbox.tools.records(), policy_extractor._LAST_META)
        # that would otherwise leak this test's fake USER-* record into unrelated tests in the same process
        if policy_id:
            tools.records().pop(policy_id, None)
            pe._LAST_META.pop(policy_id, None)
