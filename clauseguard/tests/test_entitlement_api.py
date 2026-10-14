"""/entitlement/* read models: session-scoped adapters over the optional entitlement modules.

Both paths are exercised with monkeypatched modules: a stub module installed in sys.modules
(available), and None in sys.modules, which makes the import fail (unavailable)."""
from __future__ import annotations

import importlib
import sys
import types
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel

from clauseguard.sandbox import api, entitlement

MODULES = {
    "allocation": ("clauseguard.allocation", "optimize_allocation"),
    "timeline": ("clauseguard.timeline", "build_timeline"),
    "twin": ("clauseguard.twin", "adjudicate_like_insurer"),
    "recourse": ("clauseguard.recourse", "find_recourse"),
    "plans": ("clauseguard.plans.selector", "select_plans"),
}


@pytest.fixture
def client(sandbox_db):
    api.SESSIONS.clear()
    with TestClient(api.app) as c:
        yield c


def login(client, persona="dewi"):
    r = client.post("/login", json={"persona": persona})
    assert r.status_code == 200, r.text
    return {"X-Session-Token": r.json()["session_token"]}


# ----------------------------------------------------------------------------- stub modules
class Step(BaseModel):
    order: int
    policy_id: str
    payer_type: str
    amount: Decimal
    basis: str
    documents_required: list[str] = []
    filing_deadline: date | None = None
    clause_ids: list[str] = []
    note: str | None = None


class AllocationResult(BaseModel):
    steps: list[Step]
    total_recovered: Decimal
    out_of_pocket: Decimal
    greedy_total: Decimal
    single_policy_total: Decimal
    uncertain: list[dict] = []
    excluded: list[dict] = []
    circular_excess: bool = False
    rule_pack: str = "ID-2026"


class TimelineEvent(BaseModel):
    date: date
    policy_id: str
    kind: str
    money_at_risk: Decimal
    days_left: int
    clause_id: str | None = None
    message: str = ""


SEEN: dict[str, dict] = {}


def install_stubs(monkeypatch):
    """Stub entry points with the signatures the adapter is expected to satisfy."""

    def optimize_allocation(policies, facts, *, facts_by_policy, as_of, bill_breakdown=None, documents_present=None):
        SEEN["allocation"] = {"policies": [p.id for p in policies], "facts": dict(facts.values), "bill": bill_breakdown, "as_of": as_of, "fbp": list(facts_by_policy)}
        return AllocationResult(
            steps=[Step(order=1, policy_id=policies[0].id, payer_type="PRIMARY", amount=Decimal("1000000"), basis="INDEMNITY", documents_required=["ITEMISED_BILL"],
                        filing_deadline=as_of, clause_ids=["c1"], note="stub")],
            total_recovered=Decimal("1000000"), out_of_pocket=Decimal("0"), greedy_total=Decimal("800000"), single_policy_total=Decimal("500000"))

    def build_timeline(policies, open_claims, as_of, *, premium_due=None, pay_rows=None, **kwargs):
        SEEN["timeline"] = {"n": len(policies), "pay_rows": len(pay_rows or []), "open_claims": [(c["claim_id"] if isinstance(c, dict) else c.claim_id) for c in open_claims], "premium_due": premium_due}
        return [TimelineEvent(date=as_of, policy_id=policies[0].id, kind="FILING_DEADLINE", money_at_risk=Decimal("1500000"), days_left=10, clause_id="p1", message="file now")]

    def adjudicate_like_insurer(policy=None, facts=None, policies=None, facts_by_policy=None, **_):
        SEEN["twin"] = {"policies": [p.id for p in policies or []]}
        return {"readiness_score": 62, "after_fix_score": 90, "grounds": [{"code": "WAITING_PERIOD", "clause_id": "w1", "evidence_text": "30 days", "fixable": False, "recourse": None}], "consistency_checks": [{"name": "dates", "ok": True}]}

    def find_recourse(policy, facts, *, policies, as_of):
        SEEN["recourse"] = {"policy": policy.id, "n": len(policies)}
        return {"policy_id": policy.id, "options": [{"actions": ["attach discharge summary"], "resulting_verdict": "COVERED", "payable": "1500000", "clause_ids": ["c1"], "cost": 0}]}

    def select_plans(gap_report, budget=None, jurisdiction="ID", **_):
        SEEN["plans"] = {"budget": budget, "jurisdiction": jurisdiction, "has_gap": "matrix" in gap_report}
        return {"chosen": [{"name": "Plan A", "monthly_cost": 150000}], "perils_closed": ["TPD"], "residual_gaps": [], "monthly_cost": 150000, "rationale": "stub", "alternatives": []}

    fns = {"allocation": optimize_allocation, "timeline": build_timeline, "twin": adjudicate_like_insurer, "recourse": find_recourse, "plans": select_plans}
    if "clauseguard.plans" not in sys.modules:
        try:
            import clauseguard.plans  # noqa: F401
        except ImportError:
            pkg = types.ModuleType("clauseguard.plans")
            pkg.__path__ = []
            monkeypatch.setitem(sys.modules, "clauseguard.plans", pkg)
    for kind, (mod_name, fn_name) in MODULES.items():
        mod = types.ModuleType(mod_name)
        real = sys.modules.get(mod_name)
        if real is None:
            try:
                real = importlib.import_module(mod_name)
            except ImportError:
                real = None
        if real is not None:  # keep the real module's other names: catalogue.py imports constants from the selector
            mod.__dict__.update({k: v for k, v in real.__dict__.items() if not k.startswith("__")})
        setattr(mod, fn_name, fns[kind])
        monkeypatch.setitem(sys.modules, mod_name, mod)
    SEEN.clear()


def uninstall(monkeypatch):
    for mod_name, _ in MODULES.values():
        monkeypatch.setitem(sys.modules, mod_name, None)


# ----------------------------------------------------------------------------- unavailable path
def test_every_endpoint_reports_unavailable_without_the_modules(client, monkeypatch):
    uninstall(monkeypatch)
    h = login(client)
    for path in ("/entitlement/allocation", "/entitlement/allocation?claim=CL-DEWI-PA-01", "/entitlement/timeline", "/entitlement/twin",
                 "/entitlement/recourse?policy=PA-CHUBB-03", "/entitlement/plans?budget=500000&jurisdiction=ID"):
        r = client.get(path, headers=h)
        assert r.status_code == 200, path
        body = r.json()
        assert body["available"] is False and "not installed" in body["reason"], (path, body)


def test_entitlement_requires_a_session(client):
    for path in ("/entitlement/allocation", "/entitlement/timeline", "/entitlement/twin", "/entitlement/recourse?policy=X", "/entitlement/plans"):
        assert client.get(path).status_code == 401, path


def test_incompatible_entry_point_is_reported_not_raised(client, monkeypatch):
    mod = types.ModuleType("clauseguard.allocation")
    mod.optimize_allocation = lambda ledger, *, horizon: None  # arguments the adapter cannot supply
    monkeypatch.setitem(sys.modules, "clauseguard.allocation", mod)
    h = login(client)
    body = client.get("/entitlement/allocation", headers=h).json()
    assert body["available"] is False and "not compatible" in body["reason"] and "ledger" in body["reason"]


def test_failing_module_is_reported_not_raised(client, monkeypatch):
    mod = types.ModuleType("clauseguard.twin")

    def boom(**_):
        raise RuntimeError("solver exploded")

    mod.adjudicate_like_insurer = boom
    monkeypatch.setitem(sys.modules, "clauseguard.twin", mod)
    h = login(client)
    body = client.get("/entitlement/twin", headers=h).json()
    assert body["available"] is False and "RuntimeError" in body["reason"]


# ----------------------------------------------------------------------------- available path
def test_allocation_draft_uses_the_open_claim_and_bill(client, monkeypatch):
    install_stubs(monkeypatch)
    h = login(client, "santoso")
    r = client.get("/entitlement/allocation", headers=h)
    body = r.json()
    assert body["available"] is True
    assert body["steps"][0]["policy_id"] == "GH-NUSA-GRP" and body["steps"][0]["amount"] == "1000000"
    assert body["total_recovered"] == "1000000" and body["greedy_total"] == "800000" and body["single_policy_total"] == "500000"
    assert SEEN["allocation"]["facts"]["event"] == "HOSPITALIZATION" and SEEN["allocation"]["facts"]["billed_amount"] == 18000000
    assert SEEN["allocation"]["bill"] == {"room": Decimal("8000000"), "drugs": Decimal("7000000"), "doctor": Decimal("3000000")}
    assert set(SEEN["allocation"]["fbp"]) == set(SEEN["allocation"]["policies"])
    # an explicit bill overrides the breakdown on file
    r = client.get('/entitlement/allocation?bill={"room": 5000000, "drugs": 1000000}', headers=h)
    assert r.status_code == 200 and SEEN["allocation"]["bill"] == {"room": Decimal("5000000"), "drugs": Decimal("1000000")}
    assert client.get("/entitlement/allocation?bill=notjson", headers=h).status_code == 400


def test_allocation_by_claim_id_is_scoped_to_the_account(client, monkeypatch):
    install_stubs(monkeypatch)
    h = login(client, "dewi")
    body = client.get("/entitlement/allocation?claim=CL-DEWI-PA-01", headers=h).json()
    assert body["available"] is True
    f = SEEN["allocation"]["facts"]
    assert f["event"] == "ACCIDENT_MEDICAL" and f["cause"] == "ACCIDENT_TRAFFIC" and f["vehicles_involved"] == 2 and f["billed_amount"] == 22000000 and f["days_hospitalized"] == 7  # 5-11 Oct, inclusive calendar days (agent/derive.py)
    # another customer's claim: refused as unavailable, never evaluated
    SEEN.clear()
    body = client.get("/entitlement/allocation?claim=CL-RIZKY-HCP-01", headers=h).json()
    assert body["available"] is False and "not on this account" in body["reason"] and "allocation" not in SEEN


def test_allocation_draft_follows_the_conversation_facts(client, monkeypatch):
    install_stubs(monkeypatch)
    h = login(client, "rizky")
    s = api.SESSIONS[h["X-Session-Token"]]
    from clauseguard.agent.session import ensure_state
    from clauseguard.schema import ScenarioFacts, Slot

    ensure_state(s)
    s.facts = ScenarioFacts(values={Slot.EVENT: "HOSPITALIZATION", Slot.DAYS_HOSPITALIZED: 3}, as_of=s.as_of)
    s.event_dates["admission"] = date(2026, 9, 25)
    body = client.get("/entitlement/allocation?claim=draft", headers=h).json()
    assert body["available"] is True and SEEN["allocation"]["facts"] == {"event": "HOSPITALIZATION", "days_hospitalized": 3}


def test_allocation_panel_sees_the_same_day_count_as_the_chat_reply(client):
    h = login(client, "santoso")
    text = ("Sari dirawat di RS Mitra Keluarga, masuk 2026-10-10 sampai 2026-10-13 karena demam berdarah, "
            "tagihan Rp22.000.000.")
    client.post("/chat", json={"text": text}, headers=h)
    alloc = client.get("/entitlement/allocation?claim=draft", headers=h).json()
    assert alloc["available"] is True
    assert not any("days hospitalised unknown" in n for n in alloc.get("notes", []))
    assert Decimal(alloc["total_recovered"]) > 0


def test_timeline_twin_recourse_and_plans(client, monkeypatch):
    install_stubs(monkeypatch)
    h = login(client, "rizky")
    tl = client.get("/entitlement/timeline", headers=h).json()
    assert tl["available"] is True and tl["events"][0]["kind"] == "FILING_DEADLINE" and tl["events"][0]["days_left"] == 10 and tl["events"][0]["money_at_risk"] == "1500000"
    assert SEEN["timeline"]["n"] == 5 and SEEN["timeline"]["pay_rows"] == 5
    assert SEEN["timeline"]["open_claims"] == ["CL-RIZKY-HCP-01"] and SEEN["timeline"]["premium_due"] == {"TL-ASTRA-07": date(2026, 9, 1)}

    tw = client.get("/entitlement/twin", headers=h).json()
    assert tw["available"] is True and tw["readiness_score"] == 62 and tw["after_fix_score"] == 90 and tw["grounds"][0]["code"] == "WAITING_PERIOD"

    rc = client.get("/entitlement/recourse?policy=HCP-SOMPO-01", headers=h).json()
    assert rc["available"] is True and rc["options"][0]["resulting_verdict"] == "COVERED" and SEEN["recourse"]["policy"] == "HCP-SOMPO-01"
    rc = client.get("/entitlement/recourse?policy=GH-NUSA-GRP", headers=h).json()  # not on this account
    assert rc["available"] is False and "not on this account" in rc["reason"]
    assert client.get("/entitlement/recourse", headers=h).status_code == 422

    pl = client.get("/entitlement/plans?budget=300000&jurisdiction=ID", headers=h).json()
    assert pl["available"] is True and pl["chosen"][0]["name"] == "Plan A" and SEEN["plans"] == {"budget": 300000, "jurisdiction": "ID", "has_gap": True}
    assert client.get("/entitlement/plans?jurisdiction=XX", headers=h).status_code == 400


def test_policies_read_model_lists_own_claims(client):
    h = login(client, "dewi")
    claims = client.get("/policies", headers=h).json()["claims"]
    assert [c["id"] for c in claims] == ["CL-DEWI-PA-01"]


# ----------------------------------------------------------------------------- adapter unit
def test_call_with_context_filters_by_signature():
    def f(a, b=2, *, c):
        return (a, b, c)

    assert entitlement.call_with_context(f, a=1, c=3, zzz=9) == (1, 2, 3)
    with pytest.raises(TypeError):
        entitlement.call_with_context(f, a=1)

    def g(**kw):
        return sorted(kw)

    assert entitlement.call_with_context(g, x=1, y=None) == ["x", "y"]


def test_dump_handles_models_decimals_dates_and_enums():
    from clauseguard.schema import Slot

    out = entitlement.dump({"n": Decimal("1.5"), "d": date(2026, 1, 2), Slot.EVENT: [Slot.CAUSE], "m": Step(order=1, policy_id="P", payer_type="X", amount=Decimal("3"), basis="B")})
    assert out == {"n": "1.5", "d": "2026-01-02", "event": ["cause"], "m": {"order": 1, "policy_id": "P", "payer_type": "X", "amount": "3", "basis": "B", "documents_required": [], "filing_deadline": None, "clause_ids": [], "note": None}}
