"""Policy Enforcement Point: runs before every tool call. Pure Python, no LLM.

Implements enforcement rules R1-R9 (see SECURITY.md):
  R1 registry allow-list + strict schema          R6 kill switch + per-session circuit breaker
  R2 T2+ args are registry handles, labels gated  R7 confirmation nonce (server-issued, single use)
  R3 sensitive fields never from DOC/LLM/TOOL     R8 output guard (see output_guard.py)
  R4 identity binding from the server session     R9 typed memory only (enforced by the Session type)
  R5 rate / amount limits (plan-bound submissions: one per payer, own budget)

Security guarantee: the planner can propose any tool call it likes; nothing executes unless
`pep_check` returns `allow=True`, and the arguments the tool receives are the ones the PEP
bound (`Decision.bound_args`), not the ones the planner wrote. Every decision is appended to
the hash-chained audit log.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, ValidationError

from .. import config
from ..schema import SourceTier
from . import audit, kill_switch, nonce
from .labels import ALLOWED_T2_LABELS, UNTRUSTED_FOR_SENSITIVE, ValueRegistry
from .registry import NONCE_FIELD, REGISTRY, SENSITIVE_FIELDS, ToolSpec

# R5 limits (per session unless stated)
MAX_SUBMIT_CLAIM_PER_SESSION = 1
MAX_T2_PER_SESSION = 3
MAX_TOOL_CALLS_PER_SESSION = 60
MAX_T3_TICKETS_PER_24H = 1
MAX_PLAN_STEPS = 8
CIRCUIT_BREAKER_DENIALS = 3
# A multi-payer claim plan files one claim per payer, each with its own nonce. Those submissions
# have their own budget: at most one per payer and MAX_PLAN_SUBMISSIONS per session, and only for
# the draft the server-side plan step awaiting confirmation points to.
MAX_PLAN_SUBMISSIONS = 4

IDENTITY_FIELDS = ("user_id", "customer_id")


class ToolCall(BaseModel):
    """What the planner emits. `args` values are literals copied from the user turn or '$v' handles."""

    model_config = ConfigDict(extra="forbid")
    name: str
    args: dict[str, Any] = {}
    confirm_token: Optional[str] = None


@dataclass
class Decision:
    allow: bool
    reason: str
    bound_args: dict[str, Any] = field(default_factory=dict)
    tier: Optional[int] = None
    arg_labels: dict[str, str] = field(default_factory=dict)

    def __bool__(self) -> bool:
        return self.allow


@dataclass
class PepSession:
    """Server-side session state the PEP needs. `agent.session.Session` embeds/duck-types this.

    user_id comes from /login, never from tool arguments (R4). Counters are updated by the
    PEP itself on allow/deny so the limits cannot be reset by the planner.
    """

    session_id: str
    user_id: str
    registry: ValueRegistry = field(default_factory=ValueRegistry)
    owned_policy_ids: set[str] = field(default_factory=set)
    owned_claim_ids: set[str] = field(default_factory=set)
    known_policy_ids: Optional[set[str]] = None
    denials: int = 0
    tool_call_count: int = 0
    t2_call_count: int = 0
    submit_claim_count: int = 0
    t3_tickets_last_24h: int = 0
    tier_cap: int = 3  # lowered to 0 by the circuit breaker
    persona: Optional[str] = None

    def call_key(self, tool: str, args_hash: str) -> str:
        return f"{self.session_id}:{tool}:{args_hash}"


def _get(session: Any, name: str, default: Any = None) -> Any:
    return getattr(session, name, default)


def _audit(session: Any, event_type: str, spec: Optional[ToolSpec], call: ToolCall, decision: str, reason: str, labels: dict[str, str], ah: str) -> None:
    try:
        audit.append(
            {
                "event_type": event_type,
                "session_id": _get(session, "session_id"),
                "user_id": _get(session, "user_id"),
                "tool": call.name,
                "tier": spec.tier if spec else None,
                "args_hash": ah,
                "arg_labels": labels,
                "decision": decision,
                "reason": reason[:200],
            }
        )
    except Exception:
        # The log must never make the PEP *allow* something; if logging fails we still return the decision.
        pass


def _deny(session: Any, spec: Optional[ToolSpec], call: ToolCall, reason: str, labels: Optional[dict[str, str]] = None, ah: str = "") -> Decision:
    try:
        session.denials = int(_get(session, "denials", 0)) + 1
        if session.denials >= CIRCUIT_BREAKER_DENIALS:
            session.tier_cap = 0
    except AttributeError:
        pass
    _audit(session, "TOOL_DENY", spec, call, "DENY", reason, labels or {}, ah)
    return Decision(False, reason, tier=spec.tier if spec else None, arg_labels=labels or {})


def _amount_of(value: Any) -> Optional[Decimal]:
    if isinstance(value, dict):
        for k in ("amount", "payable", "claim_amount"):
            if value.get(k) is not None:
                try:
                    return Decimal(str(value[k]))
                except Exception:
                    return None
    return None


def plan_binding(session: Any, draft: Any) -> Optional[bool]:
    """None: not a plan submission. True: the draft is the one the session's claim plan is waiting
    to submit (same plan, step, payer and draft id, step awaiting confirmation). False: it claims a
    plan binding the server-side plan does not back."""
    if not isinstance(draft, dict) or not draft.get("plan_id"):
        return None
    plan = _get(session, "claim_plan")
    if plan is None or getattr(plan, "plan_id", None) != draft.get("plan_id"):
        return False
    step = next((s for s in getattr(plan, "steps", []) if getattr(s, "n", None) == draft.get("plan_step")), None)
    if step is None:
        return False
    return (step.status == "AWAITING_CONFIRMATION" and step.policy_id == draft.get("policy_id")
            and step.draft_id == draft.get("draft_id") and step.policy_id not in set(_get(session, "plan_submitted_policies", set()) or set()))


def pep_check(call: ToolCall, session: Any) -> Decision:
    """Return Decision(allow, reason, bound_args). See module docstring for the rule order."""
    args_in = dict(call.args or {})
    # R4: identity never comes from the planner. Strip and overwrite silently (logged in reason on allow).
    identity_stripped = [k for k in IDENTITY_FIELDS if k in args_in]
    for k in identity_stripped:
        args_in.pop(k)
    if NONCE_FIELD in args_in and call.confirm_token is None:
        call = ToolCall(name=call.name, args={k: v for k, v in args_in.items() if k != NONCE_FIELD}, confirm_token=args_in.get(NONCE_FIELD))
        args_in.pop(NONCE_FIELD, None)
    ah = nonce.args_hash(args_in)

    # R1 registry
    spec = REGISTRY.get(call.name)
    if spec is None:
        return _deny(session, None, call, "UNKNOWN_TOOL", ah=ah)

    # R6 kill switch: only T0 survives
    if kill_switch.is_active() and spec.tier > 0:
        return _deny(session, spec, call, "KILL_SWITCH", ah=ah)

    # R1 schema (extra='forbid')
    schema_input = dict(args_in)
    if NONCE_FIELD in spec.schema.model_fields:
        schema_input[NONCE_FIELD] = call.confirm_token
    try:
        validated = spec.schema.model_validate(schema_input)
    except ValidationError as e:
        first = e.errors()[0] if e.errors() else {}
        return _deny(session, spec, call, f"SCHEMA:{first.get('type', 'invalid')}:{'.'.join(str(x) for x in first.get('loc', ()))}", ah=ah)
    args = validated.model_dump()
    args.pop(NONCE_FIELD, None)

    # R6 circuit breaker
    if (int(_get(session, "denials", 0)) >= CIRCUIT_BREAKER_DENIALS or int(_get(session, "tier_cap", 3)) < spec.tier) and spec.tier > 0:
        return _deny(session, spec, call, "CIRCUIT_BREAKER", ah=ah)

    # resolve handles (all tiers) and collect labels
    registry: Optional[ValueRegistry] = _get(session, "registry")
    labels: dict[str, str] = {}
    bound: dict[str, Any] = {}
    call_key = f"{_get(session, 'session_id')}:{call.name}:{ah}"
    for name, val in args.items():
        tv = registry.resolve(val) if registry is not None else None
        if tv is None:
            if spec.tier >= 2:  # R2: no literals in privileged tools
                return _deny(session, spec, call, f"LITERAL_ARG_IN_PRIVILEGED_TOOL:{name}", labels, ah)
            labels[name] = SourceTier.USER.value if val is not None else "NONE"
            bound[name] = val
            continue
        labels[name] = tv.label.value
        if (name in SENSITIVE_FIELDS or name in spec.sensitive_fields) and tv.label in UNTRUSTED_FOR_SENSITIVE:
            return _deny(session, spec, call, f"SENSITIVE_FROM_UNTRUSTED:{name}:{tv.label.value}", labels, ah)  # R3 (even if confirmed)
        if spec.tier >= 2:
            if tv.label not in ALLOWED_T2_LABELS and not tv.user_confirmed_for(call_key):
                return _deny(session, spec, call, f"TAINTED_ARG:{name}:{tv.label.value}", labels, ah)  # R2
        if spec.tier == 3 and tv.label not in (SourceTier.USER, SourceTier.USER_CONFIRMED):
            return _deny(session, spec, call, f"T3_REQUIRES_USER_FORM:{name}:{tv.label.value}", labels, ah)
        bound[name] = tv.value

    # R7 confirmation nonce for T2
    if spec.tier == 2:
        if not nonce.verify(call.confirm_token, _get(session, "session_id"), call.name, ah):
            return _deny(session, spec, call, "NO_CONFIRMATION", labels, ah)
        _audit(session, "CONFIRM_USED", spec, call, "OK", "nonce consumed", labels, ah)

    # T3: only the ticket tool exists (registry asserts this; re-checked here for defence in depth)
    if spec.tier == 3 and call.name != "create_account_change_request":
        return _deny(session, spec, call, "T3_FORBIDDEN", labels, ah)

    # R4 identity binding + ownership
    bound["user_id"] = _get(session, "user_id")
    owned_p = set(_get(session, "owned_policy_ids", set()) or set())
    owned_c = set(_get(session, "owned_claim_ids", set()) or set())
    for name, val in list(bound.items()):
        pid = val.get("policy_id") if isinstance(val, dict) else (val if name == "policy_id" else None)
        if pid is not None and pid not in owned_p:
            return _deny(session, spec, call, "NOT_OWNER:policy_id", labels, ah)
        cid = val.get("claim_id") if isinstance(val, dict) else (val if name == "claim_id" else None)
        if cid is not None and cid not in owned_c:
            return _deny(session, spec, call, "NOT_OWNER:claim_id", labels, ah)

    # R5 limits
    planned = plan_binding(session, bound.get("draft_handle")) if call.name == "submit_claim" else None
    if planned is False:
        return _deny(session, spec, call, "PLAN_BINDING:draft is not the plan step awaiting confirmation", labels, ah)
    if int(_get(session, "tool_call_count", 0)) >= MAX_TOOL_CALLS_PER_SESSION:
        return _deny(session, spec, call, "RATE_OR_AMOUNT_LIMIT:tool_calls", labels, ah)
    if spec.tier == 2 and not planned and int(_get(session, "t2_call_count", 0)) >= MAX_T2_PER_SESSION:
        return _deny(session, spec, call, "RATE_OR_AMOUNT_LIMIT:t2_calls", labels, ah)
    if call.name == "submit_claim":
        if planned and int(_get(session, "plan_submit_count", 0)) >= MAX_PLAN_SUBMISSIONS:
            return _deny(session, spec, call, "RATE_OR_AMOUNT_LIMIT:plan_submissions", labels, ah)
        if not planned and int(_get(session, "submit_claim_count", 0)) >= MAX_SUBMIT_CLAIM_PER_SESSION:
            return _deny(session, spec, call, "RATE_OR_AMOUNT_LIMIT:submit_claim", labels, ah)
        draft = bound.get("draft_handle")
        amount = _amount_of(draft)
        if amount is not None:
            limit = _amount_of({"amount": draft.get("policy_limit")}) if isinstance(draft, dict) and draft.get("policy_limit") is not None else None
            if amount > Decimal(config.CLAIM_AMOUNT_CAP_IDR) or (limit is not None and amount > limit):
                return _deny(session, spec, call, "RATE_OR_AMOUNT_LIMIT:ESCALATE_HUMAN", labels, ah)
    if spec.tier == 3 and int(_get(session, "t3_tickets_last_24h", 0)) >= MAX_T3_TICKETS_PER_24H:
        return _deny(session, spec, call, "RATE_OR_AMOUNT_LIMIT:t3_ticket_24h", labels, ah)

    # bookkeeping (counters live on the server session; the planner cannot touch them)
    try:
        session.tool_call_count = int(_get(session, "tool_call_count", 0)) + 1
        if planned:
            session.plan_submit_count = int(_get(session, "plan_submit_count", 0)) + 1
            session.plan_submitted_policies = set(_get(session, "plan_submitted_policies", set()) or set()) | {bound["draft_handle"]["policy_id"]}
        elif spec.tier == 2:
            session.t2_call_count = int(_get(session, "t2_call_count", 0)) + 1
        if call.name == "submit_claim" and not planned:
            session.submit_claim_count = int(_get(session, "submit_claim_count", 0)) + 1
        if spec.tier == 3:
            session.t3_tickets_last_24h = int(_get(session, "t3_tickets_last_24h", 0)) + 1
    except AttributeError:
        pass
    reason = "OK" + (f" (ignored planner-supplied {','.join(identity_stripped)})" if identity_stripped else "")
    _audit(session, "TOOL_ALLOW", spec, call, "ALLOW", reason, labels, ah)
    return Decision(True, reason, bound_args=bound, tier=spec.tier, arg_labels=labels)


def check_plan_depth(n_steps: int) -> bool:
    """R5: per-plan depth <= 8 steps. The planner wrapper calls this before executing a plan."""
    return n_steps <= MAX_PLAN_STEPS
