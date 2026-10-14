"""Per-conversation state. Only typed slots persist (rule R9): facts, typed event
dates, open claims, counters, pending confirmations and a typed-only history. No free-text
summaries, never bank accounts.

Attribute names follow `security.pep.PepSession` so the PEP can read/update the same
counters (`denials`, `tool_call_count`, `t2_call_count`, `submit_claim_count`, `tier_cap`,
`owned_policy_ids`, ...). `sandbox.api` hands a bare PepSession to `handle_turn`;
`ensure_state()` attaches the loop's typed fields to it lazily, so both work.

The value registry is `security.labels.ValueRegistry` when importable, else a local
registry with the same surface (`put` -> "$v<n>", `resolve`, `confirm`).
"""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional

from ..schema import ScenarioFacts, SourceTier


# --------------------------------------------------------------------------- registry fallback
@dataclass
class TypedValue:
    value: Any
    type: str
    label: SourceTier
    source_id: Optional[str] = None
    confirmed_for: set = field(default_factory=set)
    handle: Optional[str] = None

    def user_confirmed_for(self, call_key: str) -> bool:
        return call_key in self.confirmed_for


class LocalValueRegistry:
    """Fallback for security.labels.ValueRegistry."""

    def __init__(self) -> None:
        self._items: dict[str, TypedValue] = {}
        self._n = 0

    def put(self, value: Any, type: str, label: SourceTier, source_id: Optional[str] = None) -> str:
        self._n += 1
        h = f"$v{self._n}"
        self._items[h] = TypedValue(value=value, type=type, label=label, source_id=source_id, handle=h)
        return h

    register = put

    def resolve(self, handle: Any) -> Optional[TypedValue]:
        if not isinstance(handle, str):
            return None
        return self._items.get(handle)

    def confirm(self, handle: str, call_key: str) -> bool:
        tv = self._items.get(handle)
        if tv is None:
            return False
        tv.confirmed_for.add(call_key)
        return True

    def handles(self) -> list[str]:
        return list(self._items)


def make_registry():
    try:
        from ..security.labels import ValueRegistry  # type: ignore

        return ValueRegistry()
    except Exception:  # noqa: BLE001
        return LocalValueRegistry()


def registry_put(registry, value: Any, type: str, label: SourceTier, source_id: Optional[str] = None) -> str:
    for name in ("put", "register", "add"):
        fn = getattr(registry, name, None)
        if callable(fn):
            return fn(value, type, label, source_id)
    raise RuntimeError("value registry has no put-like method")


def args_hash(args: dict) -> str:
    """Same canonical hash as security.nonce.args_hash (confirm_token excluded)."""
    try:
        from ..security import nonce  # type: ignore

        return nonce.args_hash(args)
    except Exception:  # noqa: BLE001
        clean = {k: v for k, v in args.items() if k != "confirm_token"}
        return hashlib.sha256(json.dumps(clean, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- typed loop state
LOOP_DEFAULTS: dict[str, Any] = {
    "persona": None,
    "turn": 0,
    "event_dates": dict,
    "diagnosis_code": None,
    "person_id": None,
    "effective_override": None,
    "focus_policy_id": None,
    "last_clarification_slot": None,
    "last_verdicts": dict,
    "pending_actions": list,
    "confirm_tokens": dict,  # args_hash -> token (fallback nonce store)
    "open_claims": list,
    "t3_tickets": list,
    "history_typed_only": list,
    "audit_local": list,
    "policies_cache": None,
    "alerts_shown": False,
    "alerts_seen": set,
    "docs_present": list,
    "docs_attached": list,  # requirement codes proven by an uploaded file (subset of docs_present); the rest are only declared
    "doc_uploads": list,  # [{"path", "type"}] of the customer's uploads this scenario; attached to the claim on submit
    "eff_dates": dict,
    "lang": "en",
    "submit_offer": None,
    "rebuild_submit": None,  # set when a pending submission was withdrawn after a correction; the next draft carries the acknowledgement
    "derived": dict,
    "last_payable": None,
    "last_stay": dict,
    "focus_types": set,
    "pay_rows_cache": None,
    "claim_plan": None,
    "plan_submit_count": 0,
    "plan_submitted_policies": set,
    "appeal_case": None,
    "facility_name": None,
    "plan_requested": False,
    "denials": 0,
    "tool_call_count": 0,
    "t2_call_count": 0,
    "submit_claim_count": 0,
    "t3_tickets_last_24h": 0,
    "tier_cap": 3,
    "owned_policy_ids": set,
    "owned_claim_ids": set,
    "known_policy_ids": None,
}


def ensure_state(session: Any, as_of: Optional[date] = None) -> Any:
    """Attach the loop's typed fields to any session object (ours or a PepSession)."""
    for k, default in LOOP_DEFAULTS.items():
        if not hasattr(session, k):
            setattr(session, k, default() if callable(default) else default)
    if not hasattr(session, "as_of") or session.as_of is None:
        session.as_of = as_of or date.today()
    if not hasattr(session, "facts") or session.facts is None:
        session.facts = ScenarioFacts(values={}, as_of=session.as_of)
    if not hasattr(session, "registry") or session.registry is None:
        session.registry = make_registry()
    if not hasattr(session, "session_id") or not session.session_id:
        session.session_id = uuid.uuid4().hex[:12]
    return session


class Session:
    """Server-side identity + typed state. `user_id` is never taken from tool arguments."""

    def __init__(self, user_id: str, persona: Optional[str] = None, *, facts: Optional[ScenarioFacts] = None, registry=None,
                 open_claims: Optional[list[dict]] = None, as_of: Optional[date] = None, session_id: Optional[str] = None) -> None:
        self.session_id = session_id or uuid.uuid4().hex[:12]
        self.user_id = user_id
        self.persona = persona or user_id
        self.as_of: date = as_of or date.today()
        self.facts: ScenarioFacts = facts or ScenarioFacts(values={}, as_of=self.as_of)
        self.registry = registry if registry is not None else make_registry()
        ensure_state(self, self.as_of)
        if open_claims:
            self.open_claims = list(open_claims)

    # ----- helpers
    def register_value(self, value: Any, type: str, label: SourceTier, source_id: Optional[str] = None) -> str:
        return registry_put(self.registry, value, type, label, source_id)

    def resolve(self, handle: Any):
        return self.registry.resolve(handle)


def register_value(session: Any, value: Any, type: str, label: SourceTier, source_id: Optional[str] = None) -> str:
    return registry_put(session.registry, value, type, label, source_id)


def issue_confirmation(session: Any, tool: str, args: dict) -> str:
    """Simulates the UI confirmation click: a server-side nonce bound to (session, tool, args).
    The model never sees this path. Uses security.nonce when present."""
    h = args_hash(args)
    try:
        from ..security import nonce  # type: ignore

        token = nonce.issue(session.session_id, tool, h)
    except Exception:  # noqa: BLE001
        token = uuid.uuid4().hex
    session.confirm_tokens[h] = token
    return token


def verify_confirmation_local(session: Any, token: Optional[str], tool: str, args: dict) -> bool:
    """Fallback single-use verification when security.nonce is absent."""
    h = args_hash(args)
    expected = session.confirm_tokens.get(h)
    if token and expected and token == expected:
        session.confirm_tokens.pop(h, None)
        return True
    return False
