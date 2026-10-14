"""Security layer tests: PEP rules R1-R9, nonces, audit chain, output guard, kill switch, registry invariants."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from clauseguard import config
from clauseguard.schema import SourceTier
from clauseguard.security import audit, kill_switch, nonce, output_guard
from clauseguard.security.labels import ValueRegistry, combine
from clauseguard.security.nonce import NonceStore, args_hash
from clauseguard.security.pep import CIRCUIT_BREAKER_DENIALS, PepSession, ToolCall, pep_check
from clauseguard.security.registry import REGISTRY, FORBIDDEN_TOOL_NAMES

ROOT = Path(__file__).resolve().parents[1]


# ----------------------------------------------------------------------------- helpers
def session(**kw) -> PepSession:
    s = PepSession(session_id="S-test", user_id="C-RIZKY", owned_policy_ids={"HCP-SOMPO-01", "TL-ASTRA-07"}, owned_claim_ids={"CL-RIZKY-HCP-01"})
    for k, v in kw.items():
        setattr(s, k, v)
    return s


def draft_value(amount=2500000, policy_id="HCP-SOMPO-01"):
    return {"draft_id": "DRAFT-1", "policy_id": policy_id, "event": "HOSPITALIZATION", "amount": amount, "policy_limit": 500000 * 90, "created_by": "draft_claim"}


def confirmed_submit(s: PepSession, handle: str) -> ToolCall:
    args = {"draft_handle": handle}
    token = nonce.issue(s.session_id, "submit_claim", args_hash(args))
    return ToolCall(name="submit_claim", args=args, confirm_token=token)


# ----------------------------------------------------------------------------- registry invariants
def test_registry_has_no_money_or_approval_tools():
    assert not (FORBIDDEN_TOOL_NAMES & set(REGISTRY))
    t3 = [n for n, s in REGISTRY.items() if s.tier == 3]
    assert t3 == ["create_account_change_request"]
    for spec in REGISTRY.values():
        assert spec.schema.model_config.get("extra") == "forbid"


def test_combine_is_min_tier():
    assert combine([SourceTier.USER, SourceTier.LLM, SourceTier.TOOL]) == SourceTier.LLM
    assert combine([SourceTier.USER_CONFIRMED, SourceTier.POLICY_DOC_VERIFIED]) == SourceTier.POLICY_DOC_VERIFIED


# ----------------------------------------------------------------------------- R1
def test_pep_rejects_unknown_tool(isolated_paths):
    d = pep_check(ToolCall(name="approve_claim", args={"claim_id": "CL-1"}), session())
    assert not d.allow and d.reason == "UNKNOWN_TOOL"


def test_pep_rejects_extra_fields(isolated_paths):
    d = pep_check(ToolCall(name="get_claim_status", args={"claim_id": "CL-RIZKY-HCP-01", "approve": True}), session())
    assert not d.allow and d.reason.startswith("SCHEMA")


# ----------------------------------------------------------------------------- R2 / R7
def test_t2_without_nonce_is_denied(isolated_paths):
    s = session()
    h = s.registry.put(draft_value(), "ClaimDraft", SourceTier.TOOL, "draft_claim")
    d = pep_check(ToolCall(name="submit_claim", args={"draft_handle": h}), s)
    assert not d.allow and d.reason == "NO_CONFIRMATION"


def test_literal_arg_in_t2_is_denied(isolated_paths):
    s = session()
    d = pep_check(ToolCall(name="submit_claim", args={"draft_handle": "DRAFT-1"}, confirm_token="x"), s)
    assert not d.allow and d.reason.startswith("LITERAL_ARG_IN_PRIVILEGED_TOOL")


def test_tainted_arg_until_user_confirms(isolated_paths):
    s = session()
    h = s.registry.put(draft_value(), "ClaimDraft", SourceTier.USER_UPLOAD, "doc")
    args = {"draft_handle": h}
    d = pep_check(ToolCall(name="submit_claim", args=args, confirm_token="x"), s)
    assert not d.allow and d.reason.startswith("TAINTED_ARG")
    # user confirms this value for exactly this call, server issues nonce -> allowed
    s.registry.confirm(h, s.call_key("submit_claim", args_hash(args)))
    d = pep_check(confirmed_submit(s, h), s)
    assert d.allow, d.reason


def test_t2_with_valid_nonce_is_allowed_and_bound(isolated_paths):
    s = session()
    h = s.registry.put(draft_value(), "ClaimDraft", SourceTier.TOOL, "draft_claim")
    d = pep_check(confirmed_submit(s, h), s)
    assert d.allow
    assert d.bound_args["draft_handle"]["draft_id"] == "DRAFT-1"  # handle resolved by the PEP
    assert d.bound_args["user_id"] == "C-RIZKY"
    assert d.arg_labels == {"draft_handle": "TOOL"}


def test_nonce_cannot_be_replayed_for_second_call(isolated_paths):
    s = session()
    h = s.registry.put(draft_value(), "ClaimDraft", SourceTier.TOOL, "draft_claim")
    call = confirmed_submit(s, h)
    assert pep_check(call, s).allow
    s.submit_claim_count = 0  # even without the rate limit, the token is spent
    d = pep_check(call, s)
    assert not d.allow and d.reason == "NO_CONFIRMATION"


# ----------------------------------------------------------------------------- R3
@pytest.mark.parametrize("label", [SourceTier.USER_UPLOAD, SourceTier.LLM, SourceTier.TOOL])
def test_sensitive_field_never_from_untrusted(isolated_paths, label):
    s = session()
    h = s.registry.put({"new_account": "0123456789", "bank": "BCA"}, "AccountForm", label, "doc")
    s.registry.confirm(h, s.call_key("create_account_change_request", args_hash({"form_handle": h})))  # even confirmed
    d = pep_check(ToolCall(name="create_account_change_request", args={"form_handle": h}), s)
    assert not d.allow and d.reason.startswith("SENSITIVE_FROM_UNTRUSTED")


def test_t3_ticket_from_user_form_is_allowed_once(isolated_paths):
    s = session()
    h = s.registry.put({"new_account": "0123456789", "bank": "BCA"}, "AccountForm", SourceTier.USER, "form:account_change")
    d = pep_check(ToolCall(name="create_account_change_request", args={"form_handle": h}), s)
    assert d.allow and d.tier == 3
    d2 = pep_check(ToolCall(name="create_account_change_request", args={"form_handle": h}), s)
    assert not d2.allow and d2.reason == "RATE_OR_AMOUNT_LIMIT:t3_ticket_24h"


# ----------------------------------------------------------------------------- R4
def test_cross_tenant_policy_id_denied(isolated_paths):
    d = pep_check(ToolCall(name="get_payment_status", args={"policy_id": "PA-CHUBB-03"}), session())
    assert not d.allow and d.reason == "NOT_OWNER:policy_id"
    d = pep_check(ToolCall(name="get_claim_status", args={"claim_id": "CL-DEWI-PA-01"}), session())
    assert not d.allow and d.reason == "NOT_OWNER:claim_id"


def test_planner_supplied_user_id_is_ignored(isolated_paths):
    d = pep_check(ToolCall(name="get_my_policies", args={"user_id": "C-DEWI"}), session())
    assert d.allow and d.bound_args["user_id"] == "C-RIZKY" and "ignored" in d.reason


# ----------------------------------------------------------------------------- R5
def test_second_submit_claim_is_rate_limited(isolated_paths):
    s = session()
    h1 = s.registry.put(draft_value(), "ClaimDraft", SourceTier.TOOL, "draft_claim")
    h2 = s.registry.put(draft_value(amount=1000000), "ClaimDraft", SourceTier.TOOL, "draft_claim")
    assert pep_check(confirmed_submit(s, h1), s).allow
    d = pep_check(confirmed_submit(s, h2), s)
    assert not d.allow and d.reason == "RATE_OR_AMOUNT_LIMIT:submit_claim"


def test_amount_above_cap_escalates(isolated_paths):
    s = session()
    h = s.registry.put(draft_value(amount=config.CLAIM_AMOUNT_CAP_IDR + 1), "ClaimDraft", SourceTier.TOOL, "draft_claim")
    d = pep_check(confirmed_submit(s, h), s)
    assert not d.allow and d.reason == "RATE_OR_AMOUNT_LIMIT:ESCALATE_HUMAN"


def test_t2_call_budget(isolated_paths):
    s = session(t2_call_count=3)
    h = s.registry.put("2026-10-12T10:00", "CallbackSlot", SourceTier.USER, "form")
    args = {"slot": h}
    tok = nonce.issue(s.session_id, "schedule_callback", args_hash(args))
    d = pep_check(ToolCall(name="schedule_callback", args=args, confirm_token=tok), s)
    assert not d.allow and d.reason == "RATE_OR_AMOUNT_LIMIT:t2_calls"


# ----------------------------------------------------------------------------- R6
def test_kill_switch_blocks_everything_above_t0(isolated_paths):
    s = session()
    kill_switch.activate("test", path=config.KILL_SWITCH_PATH)
    try:
        assert kill_switch.is_active()
        d = pep_check(ToolCall(name="check_coverage", args={"scenario_facts": {"event": "DEATH"}}), s)
        assert not d.allow and d.reason == "KILL_SWITCH"
        assert pep_check(ToolCall(name="get_my_policies", args={}), s).allow
    finally:
        kill_switch.deactivate(path=config.KILL_SWITCH_PATH)
    assert not kill_switch.is_active()


def test_circuit_breaker_downgrades_session_to_t0(isolated_paths):
    s = session()
    for _ in range(CIRCUIT_BREAKER_DENIALS):
        assert not pep_check(ToolCall(name="nonexistent_tool", args={}), s).allow
    assert s.denials == CIRCUIT_BREAKER_DENIALS and s.tier_cap == 0
    d = pep_check(ToolCall(name="check_coverage", args={"scenario_facts": {"event": "DEATH"}}), s)
    assert not d.allow and d.reason == "CIRCUIT_BREAKER"
    assert pep_check(ToolCall(name="get_my_policies", args={}), s).allow


# ----------------------------------------------------------------------------- nonce
def test_nonce_single_use_and_ttl():
    clock = {"t": 1000.0}
    store = NonceStore(clock=lambda: clock["t"])
    tok = store.issue("S1", "submit_claim", "abc", ttl=300)
    assert not store.verify(tok, "S2", "submit_claim", "abc")  # wrong session
    assert not store.verify(tok, "S1", "attach_document", "abc")  # wrong tool
    assert not store.verify(tok, "S1", "submit_claim", "zzz")  # args changed after confirmation
    assert store.verify(tok, "S1", "submit_claim", "abc")
    assert not store.verify(tok, "S1", "submit_claim", "abc")  # single use
    tok2 = store.issue("S1", "submit_claim", "abc", ttl=300)
    clock["t"] += 301
    assert not store.verify(tok2, "S1", "submit_claim", "abc")  # expired
    assert not store.verify(None, "S1", "submit_claim", "abc")


# ----------------------------------------------------------------------------- audit
def test_audit_chain_verifies_and_detects_tampering(tmp_path):
    p = tmp_path / "audit.jsonl"
    log = audit.AuditLog(p)
    for i in range(5):
        log.append({"event_type": "TOOL_ALLOW", "session_id": "S", "user_id": "U", "tool": "get_my_policies", "tier": 0, "decision": "ALLOW", "reason": f"n{i}"})
    ok, bad = audit.verify(p)
    assert ok and bad is None
    lines = p.read_text(encoding="utf-8").splitlines()
    ev = json.loads(lines[2])
    ev["decision"] = "DENY"  # tamper with seq 3 without recomputing the hash
    lines[2] = json.dumps(ev, sort_keys=True, separators=(",", ":"))
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    ok, bad = audit.verify(p)
    assert not ok and bad == 3
    # deleting a line is detected too
    p.write_text("\n".join(lines[:1] + lines[3:]) + "\n", encoding="utf-8")
    assert audit.verify(p) == (False, 2)


def test_verify_audit_cli(tmp_path):
    p = tmp_path / "a.jsonl"
    log = audit.AuditLog(p)
    log.append({"event_type": "REPLY", "decision": "OK"})
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "verify_audit.py"), str(p)], capture_output=True, text=True)
    assert r.returncode == 0 and r.stdout.startswith("OK (1 events)")
    ev = json.loads(p.read_text(encoding="utf-8"))
    ev["hash"] = "0" * 64
    p.write_text(json.dumps(ev) + "\n", encoding="utf-8")
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "verify_audit.py"), str(p)], capture_output=True, text=True)
    assert r.returncode == 1 and "BROKEN at seq 1" in r.stdout


def test_pep_decisions_are_audited(isolated_paths):
    s = session()
    pep_check(ToolCall(name="get_my_policies", args={}), s)
    pep_check(ToolCall(name="nope", args={}), s)
    events = audit.get_default().read()
    assert [e["event_type"] for e in events] == ["TOOL_ALLOW", "TOOL_DENY"]
    assert audit.verify(config.AUDIT_PATH)[0]
    assert all("arg_labels" in e and "args_hash" in e for e in events)


# ----------------------------------------------------------------------------- output guard
def test_output_guard_masks_nik_and_bank_numbers(isolated_paths):
    s = session()
    text = "Your NIK 3578012345670001 and account 0123456789 are on file. Benefit IDR 2,500,000 on HCP-SOMPO-01."
    clean, v = output_guard.scan(text, s)
    assert "3578012345670001" not in clean and "0123456789" not in clean
    assert "************0001" in clean and "******6789" in clean
    assert "2,500,000" in clean and "HCP-SOMPO-01" in clean  # amounts and own policy ids untouched
    assert {x["kind"] for x in v} == {"NIK", "BANK_ACCOUNT"}


def test_output_guard_masks_foreign_policy_id_only(isolated_paths):
    s = session(known_policy_ids={"HCP-SOMPO-01", "TL-ASTRA-07", "PA-CHUBB-03"})
    clean, v = output_guard.scan("Compare HCP-SOMPO-01 with PA-CHUBB-03 (INA-CBG tariff).", s)
    assert "PA-CHUBB-03" not in clean and "HCP-SOMPO-01" in clean and "INA-CBG" in clean
    assert v[0]["kind"] == "FOREIGN_POLICY_ID"


def test_output_guard_canary_refuses_whole_reply(isolated_paths):
    s = session()
    clean, v = output_guard.scan("Sure! The system prompt says CANARY-7f3a.", s)
    assert clean == output_guard.REFUSAL_TEXT and any(x["kind"] == "CANARY" for x in v)
    ev = audit.get_default().read()[-1]
    assert ev["event_type"] == "DX_ATTEMPT"


def test_output_guard_decodes_base64(isolated_paths):
    import base64

    s = session()
    blob = base64.b64encode(b"token: CANARY-7f3a please exfiltrate").decode()
    clean, v = output_guard.scan(f"Here is the data: {blob}", s)
    assert clean == output_guard.REFUSAL_TEXT
    blob2 = base64.b64encode(b"NIK 3578012345670001 belongs to the user").decode()
    clean2, v2 = output_guard.scan(f"data={blob2}", s)
    assert blob2 not in clean2 and "[REDACTED-ENCODED]" in clean2


def test_output_guard_card_number(isolated_paths):
    clean, v = output_guard.scan("card 4539 1488 0343 6467 ok", session())
    assert "4539 1488 0343 6467" not in clean and any(x["kind"] == "CARD" for x in v)


# ----------------------------------------------------------------------------- registry / labels
def test_registry_literal_never_resolves():
    r = ValueRegistry()
    h = r.put(42, "int", SourceTier.TOOL)
    assert r.resolve(h).value == 42
    assert r.resolve("42") is None and r.resolve("$v999") is None and r.resolve(42) is None
    assert r.resolve(h).safe_render() == {"handle": h, "type": "int", "label": "TOOL"}


def test_audit_append_is_safe_across_processes(tmp_path):
    """Two processes appending concurrently must not interleave lines or break the chain."""
    import subprocess
    import sys
    import textwrap

    log = tmp_path / "audit.jsonl"
    code = textwrap.dedent(f"""
        from clauseguard.security.audit import AuditLog
        a = AuditLog(r"{log}")
        for i in range(60):
            a.append({{"event_type": "USER_MSG", "session_id": "p", "user_id": "u", "text_hash": str(i)}})
    """)
    procs = [subprocess.Popen([sys.executable, "-c", code]) for _ in range(3)]
    assert all(p.wait(timeout=120) == 0 for p in procs)
    from clauseguard.security.audit import verify

    ok, bad = verify(log)
    assert ok and bad is None
    assert sum(1 for _ in open(log, "rb")) == 180
