"""Tool routing for the agent loop.

Order of preference at runtime:
1. `security.pep.pep_check` guards every call when importable (its own ToolCall type,
   strict schemas, nonce, limits, circuit breaker); otherwise `local_pep_check` applies the
   same rules in miniature. The router never calls a tier-2 tool without a nonce and never
   calls tier 3 more than once per session, so legitimate users are not tripped into the
   circuit breaker by the loop's own bookkeeping.
2. Policies come from a `PolicySource`: the sandbox records (`sandbox.tools.user_records`)
   when the user is a sandbox customer and mode is "auto"/"sandbox", else the same records built
   from `sandbox.persona_policies` without a DB (the single source of truth). T1 compute tools
   always run here on `clauseguard.portfolio` / `solver`. T2 tools execute through the sandbox
   when it is present (DB side effects) else in memory. T3 is never executed by the loop.
3. Every call is appended to the audit log (`security.audit` when present, else a local
   hash chain on the session); the event ids are returned on the Reply.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Optional

from .. import config, portfolio
from ..schema import EventCode, PolicyRecord, Relation, ScenarioFacts, SourceTier
from .planner import TOOL_TIERS, ToolCall
from .session import args_hash, ensure_state, verify_confirmation_local

log = logging.getLogger("clauseguard.agent.tools")

ALLOWED_T2_LABELS = {SourceTier.USER, SourceTier.USER_CONFIRMED, SourceTier.POLICY_DOC_VERIFIED, SourceTier.TOOL, SourceTier.SYSTEM}
SENSITIVE_FIELDS = {"form_handle", "bank_account", "account_number", "beneficiary", "beneficiary_id", "payout_account", "payment_destination", "iban", "nik"}
UNTRUSTED_FOR_SENSITIVE = {SourceTier.LLM, SourceTier.USER_UPLOAD, SourceTier.TOOL, SourceTier.POLICY_DOC_UNVERIFIED}
ARG_SCHEMA: dict[str, set[str]] = {
    "get_my_policies": set(), "get_policy_clause": {"policy_id", "tuple_id"}, "get_claim_status": {"claim_id"},
    "get_payment_status": {"policy_id"}, "get_deadline_digest": set(), "check_coverage": {"scenario_facts"}, "gap_analysis": set(),
    "claim_readiness": {"policy_id", "claim_facts"}, "cob_plan": {"claim_facts"},
    "draft_claim": {"policy_id", "claim_facts", "document_handles"}, "estimate_payout": {"policy_id", "claim_facts"},
    "extract_document": {"doc_handle"}, "submit_claim": {"draft_handle", "confirm_token"},
    "attach_document": {"claim_id", "doc_handle", "confirm_token"}, "schedule_callback": {"slot", "confirm_token"},
    "create_account_change_request": {"form_handle"}, "claim_plan": {"claim_facts"}, "draft_appeal": {"policy_id", "claim_id"},
    "file_appeal": {"appeal_handle", "confirm_token"},
}
LIMITS = {"submit_claim": 1, "t2": 3, "total": 60, "breaker": 3, "plan_submissions": 4}
SANDBOX_USER_IDS = {"C-RIZKY": "rizky", "C-BUDI": "santoso", "C-DEWI": "dewi"}


class Decision:
    def __init__(self, allow: bool, reason: str = "", bound_args: Optional[dict] = None):
        self.allow = allow
        self.reason = reason
        self.bound_args = bound_args or {}


def _jsonable(v: Any) -> Any:
    if isinstance(v, ScenarioFacts):
        return {"values": {k.value: _jsonable(x) for k, x in v.values.items()}, "as_of": v.as_of.isoformat() if v.as_of else None}
    if hasattr(v, "model_dump"):
        return json.loads(v.model_dump_json())
    if isinstance(v, Decimal):
        return str(v)
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    if isinstance(v, dict):
        return {str(k.value if hasattr(k, "value") else k): _jsonable(x) for k, x in v.items()}
    if isinstance(v, (list, tuple, set)):
        return [_jsonable(x) for x in v]
    return v


# --------------------------------------------------------------------------- audit bridge
def audit(session: Any, event_type: str, **fields: Any) -> str:
    ev = {"session_id": session.session_id, "user_id": session.user_id, "event_type": event_type, **_jsonable(fields)}
    try:
        from ..security import audit as _audit  # type: ignore

        out = _audit.append(ev)
        return f"seq:{out.get('seq')}" if isinstance(out, dict) else uuid.uuid4().hex[:16]
    except Exception:  # noqa: BLE001 - security layer absent (or rejected the event): local chain
        eid = uuid.uuid4().hex[:16]
        ev["event_id"] = eid
        ev["ts_utc"] = datetime.now(timezone.utc).isoformat()
        prev = session.audit_local[-1]["hash"] if session.audit_local else "0" * 64
        ev["prev_hash"] = prev
        ev["hash"] = hashlib.sha256((prev + json.dumps(ev, sort_keys=True, default=str)).encode()).hexdigest()
        session.audit_local.append(ev)
        return eid


# --------------------------------------------------------------------------- policy source
class PolicySource:
    """Serves the authenticated user's policies and persona meta.

    Single source of truth: `clauseguard.sandbox.persona_policies` (records, holdings, persona meta)
    and the sandbox tables that mirror it. mode "sandbox" reads the owned policy rows from the sandbox
    DB, mode "auto" does so only for sandbox customer ids (C-*), and "fixtures" (kept as an alias,
    also the fallback when no DB is reachable) builds the same records straight from
    `persona_policies.PERSONA_HOLDINGS` without a database."""

    def __init__(self, policies: Optional[dict[str, list[PolicyRecord]]] = None, meta: Optional[dict[str, dict]] = None, mode: str = "auto"):
        self._policies = policies or {}
        self._meta = meta or {}
        self.mode = mode

    def persona_of(self, session: Any) -> str:
        from ..sandbox.persona_policies import PERSONA_BY_USER

        uid = session.user_id
        return PERSONA_BY_USER.get(uid) or getattr(session, "persona", None) or uid

    def meta_for(self, session: Any) -> dict:
        from ..sandbox.persona_policies import PERSONA_META

        if session.user_id in self._meta:
            return self._meta[session.user_id]
        persona = self.persona_of(session)
        return PERSONA_META.get(persona, {"user_id": session.user_id, "persons": {session.user_id: session.user_id}, "insured": {}})

    def _sandbox_records(self, session: Any) -> Optional[list[PolicyRecord]]:
        try:
            from ..sandbox import tools as sb  # type: ignore

            recs = sb.user_records(session.user_id)
            if not recs:
                return None
            from ..sandbox.persona_policies import PERSONA_HOLDINGS

            order = {pid: i for i, (pid, _r, _s) in enumerate(PERSONA_HOLDINGS.get(self.persona_of(session), []))}
            return sorted(recs, key=lambda p: (order.get(p.id, 999), p.id))  # private products first, statutory last
        except Exception as e:  # noqa: BLE001
            log.info("sandbox records unavailable for %s (%s)", session.user_id, str(e)[:80])
            return None

    def policies_for(self, session: Any) -> list[PolicyRecord]:
        if session.user_id in self._policies:
            return self._policies[session.user_id]
        cache = getattr(session, "policies_cache", None)
        if cache is not None:
            return cache
        recs: Optional[list[PolicyRecord]] = None
        if self.mode in ("sandbox", "auto") and session.user_id in SANDBOX_USER_IDS:
            recs = self._sandbox_records(session)
        if recs is None:
            from ..sandbox.persona_policies import policies_for_persona

            try:
                recs = policies_for_persona(self.persona_of(session))
            except KeyError:
                recs = []
        session.policies_cache = recs
        session.owned_policy_ids = set(getattr(session, "owned_policy_ids", set()) or set()) | {p.id for p in recs}
        if self.mode in ("sandbox", "auto") and session.user_id in SANDBOX_USER_IDS:
            try:
                from ..sandbox import tools as sb  # type: ignore

                session.owned_claim_ids = set(getattr(session, "owned_claim_ids", set()) or set()) | sb.owned_claim_ids(session.user_id)
            except Exception:  # noqa: BLE001
                pass
        if getattr(session, "known_policy_ids", None) is None:
            session.known_policy_ids = all_known_policy_ids()
        return recs

    def owns(self, session: Any, policy_id: str) -> bool:
        return any(p.id == policy_id for p in self.policies_for(session))


def all_known_policy_ids() -> set[str]:
    """Every policy id the system knows (so the output guard masks only real foreign policy ids)."""
    from ..sandbox.persona_policies import PERSONA_HOLDINGS

    ids: set[str] = set()
    for rows in PERSONA_HOLDINGS.values():
        for pid, rid, _st in rows:
            ids |= {pid, rid}
    try:
        from ..sandbox import tools as sb  # type: ignore

        ids |= set(sb.all_policy_ids())
    except Exception:  # noqa: BLE001
        pass
    return ids


# --------------------------------------------------------------------------- PEP
def kill_switch_active() -> bool:
    try:
        from ..security import kill_switch  # type: ignore

        return bool(kill_switch.is_active())
    except Exception:  # noqa: BLE001
        return Path(config.KILL_SWITCH_PATH).exists() or os.getenv("CG_AGENT_HALT", "") == "1"


def _local_plan_binding(session: Any, args: dict) -> Optional[bool]:
    tv = session.registry.resolve(args.get("draft_handle"))
    draft = tv.value if tv is not None else None
    if not isinstance(draft, dict) or not draft.get("plan_id"):
        return None
    plan = getattr(session, "claim_plan", None)
    if plan is None or plan.plan_id != draft.get("plan_id"):
        return False
    step = next((s for s in plan.steps if s.n == draft.get("plan_step")), None)
    return bool(step and step.status == "AWAITING_CONFIRMATION" and step.policy_id == draft.get("policy_id") and step.draft_id == draft.get("draft_id")
                and step.policy_id not in session.plan_submitted_policies)


def local_pep_check(call: ToolCall, session: Any, source: PolicySource) -> Decision:
    """Fallback for security.pep.pep_check: R1-R7 in miniature. Counters mirror PepSession."""
    tier = TOOL_TIERS.get(call.name)

    def deny(reason: str) -> Decision:
        session.denials += 1
        if session.denials >= LIMITS["breaker"]:
            session.tier_cap = 0
        return Decision(False, reason)

    if tier is None:
        return deny("UNKNOWN_TOOL")
    extra = set(call.args) - ARG_SCHEMA.get(call.name, set())
    if extra:
        return deny(f"SCHEMA:unknown fields {sorted(extra)}")
    if kill_switch_active() and tier > 0:
        return deny("KILL_SWITCH")
    if (session.denials >= LIMITS["breaker"] or session.tier_cap < tier) and tier > 0:
        return deny("CIRCUIT_BREAKER")
    if session.tool_call_count >= LIMITS["total"]:
        return deny("RATE_OR_AMOUNT_LIMIT:tool_calls")
    if tier == 3:
        return deny("T3_REQUIRES_USER_FORM:form_handle")  # the loop never executes T3
    args_wo = {k: v for k, v in call.args.items() if k != "confirm_token"}
    planned = _local_plan_binding(session, args_wo) if call.name == "submit_claim" else None
    if planned is False:
        return deny("PLAN_BINDING:draft is not the plan step awaiting confirmation")
    if tier >= 2:
        if not planned and session.t2_call_count >= LIMITS["t2"]:
            return deny("RATE_OR_AMOUNT_LIMIT:t2_calls")
        if planned and session.plan_submit_count >= LIMITS["plan_submissions"]:
            return deny("RATE_OR_AMOUNT_LIMIT:plan_submissions")
        if call.name == "submit_claim" and not planned and session.submit_claim_count >= LIMITS["submit_claim"]:
            return deny("RATE_OR_AMOUNT_LIMIT:submit_claim")
        for k, val in args_wo.items():
            tv = session.registry.resolve(val)
            if tv is None:
                return deny(f"LITERAL_ARG_IN_PRIVILEGED_TOOL:{k}")
            if k in SENSITIVE_FIELDS and tv.label in UNTRUSTED_FOR_SENSITIVE:
                return deny(f"SENSITIVE_FROM_UNTRUSTED:{k}")
            if tv.label not in ALLOWED_T2_LABELS and not tv.user_confirmed_for(f"{session.session_id}:{call.name}:{args_hash(args_wo)}"):
                return deny(f"TAINTED_ARG:{k}:{tv.label.value}")
        if not verify_confirmation_local(session, call.args.get("confirm_token"), call.name, args_wo):
            return deny("NO_CONFIRMATION")
    bound: dict[str, Any] = {}
    for k, val in args_wo.items():
        tv = session.registry.resolve(val)
        bound[k] = tv.value if tv is not None else val
    pid = bound.get("policy_id")
    if isinstance(pid, str) and pid and not source.owns(session, pid):
        return deny("NOT_OWNER:policy_id")
    cid = bound.get("claim_id")
    if isinstance(cid, str) and cid and cid not in session.owned_claim_ids:
        return deny("NOT_OWNER:claim_id")
    session.tool_call_count += 1
    if planned:
        session.plan_submit_count += 1
        session.plan_submitted_policies = set(session.plan_submitted_policies) | {bound["draft_handle"]["policy_id"]}
    elif tier == 2:
        session.t2_call_count += 1
    if call.name == "submit_claim" and not planned:
        session.submit_claim_count += 1
    bound["user_id"] = session.user_id
    return Decision(True, "OK", bound)


def pep_check(call: ToolCall, session: Any, source: PolicySource) -> tuple[Decision, bool]:
    """Returns (decision, audited_by_pep)."""
    try:
        from ..security import pep as _pep  # type: ignore
    except ImportError:
        return local_pep_check(call, session, source), False
    try:
        source.policies_for(session)  # makes sure owned_policy_ids is populated for R4
        args = {k: v for k, v in call.args.items() if k != "confirm_token"}
        c = _pep.ToolCall(name=call.name, args=args, confirm_token=call.args.get("confirm_token"))
        d = _pep.pep_check(c, session)
        return Decision(bool(d.allow), str(d.reason), dict(d.bound_args or {})), True
    except Exception as e:  # noqa: BLE001 - security layer present but incompatible: local rules
        log.warning("security.pep failed (%s); falling back to local PEP", str(e)[:120])
        return local_pep_check(call, session, source), False


# --------------------------------------------------------------------------- router
class ToolRouter:
    def __init__(self, source: Optional[PolicySource] = None):
        self.source = source or PolicySource()

    def call(self, session: Any, name: str, args: Optional[dict] = None, **kw: Any) -> tuple[Decision, Any, str]:
        """(decision, result, audit_event_id). Result is None when denied."""
        ensure_state(session)
        call = ToolCall(name=name, args=args or {})
        tier = TOOL_TIERS.get(name, -1)
        d, audited = pep_check(call, session, self.source)
        ah = args_hash(call.args)
        if not d.allow:
            eid = audit(session, "TOOL_DENY", tool=name, tier=tier, reason=d.reason, args_hash=ah) if not audited else f"pep:{name}:{d.reason}"
            return d, None, eid
        eid = audit(session, "TOOL_ALLOW", tool=name, tier=tier, args_hash=ah) if not audited else f"pep:{name}:OK"
        fn = getattr(self, f"_t_{name}", None)
        if fn is None:
            return Decision(False, "NOT_IMPLEMENTED"), None, eid
        result = fn(session, d.bound_args, **kw)
        audit(session, "TOOL_RESULT", tool=name, tier=tier, result_hash=hashlib.sha256(json.dumps(_jsonable(result), sort_keys=True, default=str).encode()).hexdigest()[:16])
        return d, result, eid

    # ---- T0
    def _t_get_my_policies(self, session: Any, args: dict) -> list[PolicyRecord]:
        return self.source.policies_for(session)

    def _t_get_policy_clause(self, session: Any, args: dict) -> list[dict]:
        pid, tid = args.get("policy_id"), args.get("tuple_id")
        out = []
        for p in self.source.policies_for(session):
            if p.id != pid:
                continue
            for t in p.tuples:
                if tid in (None, "*") or t.id == tid:
                    out.append({"policy_id": p.id, "tuple_id": t.id, "relation": t.relation.value, "object": t.object,
                                "section": t.evidence.section, "text": t.evidence.text, "source_tier": t.source_tier.value, "display_only": True})
        return out

    def _t_get_claim_status(self, session: Any, args: dict) -> list[dict]:
        cid = args.get("claim_id")
        rows = self._sandbox_claims(session, cid)
        if rows:
            return rows
        meta = self.source.meta_for(session)
        claims = list(meta.get("claims", [])) + list(session.open_claims)
        return [c for c in claims if cid is None or c.get("id") == cid]

    def _sandbox_claims(self, session: Any, claim_id: Optional[str] = None) -> list[dict]:
        """The household's claims in the sandbox insurer system, with what each payer paid."""
        if self.source.mode == "fixtures" or session.user_id not in SANDBOX_USER_IDS:
            return []
        try:
            from ..sandbox import tools as sb  # type: ignore

            ids = sb.household_ids(session.user_id)
            q = ",".join("?" * len(ids))
            rows = sb._rows(f"SELECT * FROM claims WHERE customer_id IN ({q})" + (" AND id=?" if claim_id else "") + " ORDER BY id", *ids, *([claim_id] if claim_id else []))
            for r in rows:
                pays = sb._rows("SELECT payer, amount, paid_date FROM claim_payments WHERE claim_id=?", r["id"])
                r["paid"] = sum(int(x["amount"] or 0) for x in pays)
                r["payments"] = pays
            return rows
        except Exception as e:  # noqa: BLE001
            log.info("sandbox claims unavailable (%s)", str(e)[:80])
            return []

    def _t_get_payment_status(self, session: Any, args: dict) -> dict:
        meta = self.source.meta_for(session)
        pid = args.get("policy_id")
        p = next((p for p in self.source.policies_for(session) if p.id == pid), None)
        if p is None:
            return {"policy_id": pid, "found": False}
        bpjs = meta.get("bpjs", {})
        if p.product_type == "social_bpjs_kes":
            status = "active" if (bpjs.get("status") == "active" and p.status in portfolio.ACTIVE_STATUSES) else "lapsed"
            return {"policy_id": p.id, "status": status, "arrears_months": bpjs.get("arrears_months", 0), "days_overdue": 0, "grace_end": None, "due_date": None}
        pay = meta.get("payments", {}).get(p.id, {})
        due = pay.get("due_date")
        paid = pay.get("paid_date")
        due_d = date.fromisoformat(due) if isinstance(due, str) else due
        overdue = (session.as_of - due_d).days if (due_d and not paid and session.as_of >= due_d) else 0
        grace_end = (due_d + timedelta(days=p.grace_days or 0)) if due_d and not paid else None
        status = p.status if p.status != "grace" or overdue else p.status
        if overdue:
            status = "lapsed" if overdue > (p.grace_days or 0) else "grace"
        elif p.status == "grace":
            status = "active"
        return {"policy_id": p.id, "status": status, "days_overdue": overdue, "due_date": due, "last_paid": pay.get("last_paid") or paid,
                "grace_days": p.grace_days, "grace_end": grace_end.isoformat() if grace_end else None}

    def _t_get_deadline_digest(self, session: Any, args: dict, *, extra_claims: Optional[list] = None) -> list:
        from .digest import build_digest, digest_for_user

        if self.source.mode != "fixtures" and session.user_id in SANDBOX_USER_IDS:
            try:
                return digest_for_user(session.user_id, self.source.persona_of(session), session.as_of, extra_claims=extra_claims)
            except Exception as e:  # noqa: BLE001
                log.info("sandbox digest unavailable (%s); policies only", str(e)[:80])
        return build_digest(self.source.policies_for(session), as_of=session.as_of, open_claims=list(extra_claims or []))

    # ---- T1
    def _t_check_coverage(self, session: Any, args: dict, *, facts_by_policy: Optional[dict[str, ScenarioFacts]] = None, policies=None) -> list[dict]:
        policies = policies or self.source.policies_for(session)
        out = []
        for p in policies:
            f = (facts_by_policy or {}).get(p.id, session.facts)
            r = portfolio.decide_mapped(p, f)
            out.append({"policy_id": p.id, "result": r, "denial_code": portfolio.normalise_denial_code(r, p)})
        return out

    def _effective_policies(self, session: Any, policies: list[PolicyRecord]) -> list[PolicyRecord]:
        """Policies with their status as of the session date: a premium past its grace period means the policy is lapsed today."""
        out = []
        for p in policies:
            st = self._t_get_payment_status(session, {"policy_id": p.id}).get("status")
            out.append(p.model_copy(update={"status": "lapsed"}) if st == "lapsed" and p.status != "lapsed" else p)
        return out

    def _t_gap_analysis(self, session: Any, args: dict, *, policies=None, perils: Optional[list[EventCode]] = None) -> dict:
        policies = self._effective_policies(session, policies or self.source.policies_for(session))
        meta = self.source.meta_for(session)
        persons = list(meta.get("persons", {session.user_id: session.user_id}).keys())
        perils = perils or [EventCode.HOSPITALIZATION, EventCode.SURGERY, EventCode.ICU, EventCode.OUTPATIENT, EventCode.CRITICAL_ILLNESS,
                            EventCode.DEATH, EventCode.ACCIDENTAL_DEATH, EventCode.ACCIDENT_MEDICAL, EventCode.TEMPORARY_DISABILITY, EventCode.TPD]
        liab = meta.get("liabilities")
        return portfolio.gap_overlap(policies, persons, perils, insured=meta.get("insured"),
                                     liabilities=Decimal(liab) if liab else None, liabilities_person=persons[0] if persons else None)

    def _t_claim_readiness(self, session: Any, args: dict, *, facts: Optional[ScenarioFacts] = None, policy: Optional[PolicyRecord] = None,
                           documents_present: Optional[list[str]] = None) -> Optional[portfolio.ReadinessReport]:
        if policy is None:
            policy = next((p for p in self.source.policies_for(session) if p.id == args.get("policy_id")), None)
        if policy is None:
            return None
        return portfolio.claim_readiness(policy, facts or session.facts, documents_present or [], session.as_of)

    def _t_cob_plan(self, session: Any, args: dict, *, facts_by_policy: Optional[dict[str, ScenarioFacts]] = None, policies=None,
                    bill_breakdown: Optional[dict] = None, facts: Optional[ScenarioFacts] = None) -> list[portfolio.PayerStep]:
        policies = policies or self.source.policies_for(session)
        meta = self.source.meta_for(session)
        return portfolio.cob_plan(policies, facts or session.facts, as_of=session.as_of, bill_breakdown=bill_breakdown,
                                  bpjs_tk_member=bool(meta.get("bpjs_tk_member")), facts_by_policy=facts_by_policy)

    def _t_draft_claim(self, session: Any, args: dict, *, facts: Optional[ScenarioFacts] = None, readiness: Optional[portfolio.ReadinessReport] = None,
                       policy: Optional[PolicyRecord] = None) -> dict:
        pid = args.get("policy_id")
        f = facts or session.facts
        limit = _policy_limit(policy, f) if policy else None
        payable = readiness.verdict.payable if readiness and readiness.verdict.payable is not None else None
        return {"draft_id": f"DRAFT-{uuid.uuid4().hex[:8]}", "policy_id": pid, "event": f.values.get(portfolio.Slot.EVENT),
                "facts": _jsonable(f), "amount": str(payable) if payable is not None else None, "expected_amount": str(payable) if payable is not None else None,
                "currency": policy.currency if policy else "IDR", "policy_limit": limit,
                "deadline": readiness.deadline.isoformat() if readiness and readiness.deadline else None,
                "required_documents": readiness.required_documents if readiness else [], "documents_missing": readiness.missing_documents if readiness else [],
                "document_handles": list(args.get("document_handles") or []), "created_by": "draft_claim",
                "min_source_tier": readiness.verdict.min_source_tier.value if readiness and readiness.verdict.min_source_tier else None}

    def _t_estimate_payout(self, session: Any, args: dict, *, facts: Optional[ScenarioFacts] = None, policy: Optional[PolicyRecord] = None) -> Optional[dict]:
        if policy is None:
            return None
        r = portfolio.decide_mapped(policy, facts or session.facts)
        return {"policy_id": policy.id, "verdict": r.verdict.value, "payable": str(r.payable) if r.payable is not None else None}

    def _t_extract_document(self, session: Any, args: dict, *, policyholder_name: str = "") -> dict:
        path = args.get("doc_handle")
        path = path.get("path") if isinstance(path, dict) else path
        try:
            from ..extractor.claim_doc import extract_claim_document  # type: ignore

            res = extract_claim_document(path, policyholder_name=policyholder_name)
            return res.model_dump(mode="json") if hasattr(res, "model_dump") else dict(res)
        except Exception as e:  # noqa: BLE001
            return {"doc_type": "UNKNOWN", "suspicious": False, "extract_quality": "LOW", "total_amount": None, "stub": True, "error": str(e)[:80]}

    def _t_claim_plan(self, session: Any, args: dict, *, policies=None, facts: Optional[ScenarioFacts] = None,
                      facts_by_policy: Optional[dict[str, ScenarioFacts]] = None, dates: Optional[dict] = None, person_id: Optional[str] = None,
                      person_name: Optional[str] = None, facility: Optional[str] = None, documents_present: Optional[list[str]] = None,
                      diagnosis: Optional[str] = None) -> Any:
        from .claim_plan import build_plan

        policies = policies if policies is not None else self.source.policies_for(session)
        facts = facts or session.facts
        meta = self.source.meta_for(session)
        estimates: dict = {}
        try:
            from ..sandbox.insurer_sim import package_tariff  # type: ignore

            cls = (meta.get("bpjs") or {}).get("class")
            for p in policies:
                if p.product_type == "social_bpjs_kes":
                    t = package_tariff(diagnosis, cls)
                    if t is not None:
                        estimates[p.id] = t
        except Exception:  # noqa: BLE001
            pass
        return build_plan(policies, facts, facts_by_policy or {p.id: facts for p in policies}, as_of=session.as_of, person_id=person_id,
                          person_name=person_name, dates=dates or {}, facility=facility, documents_present=documents_present or [],
                          existing_claims=self._sandbox_claims(session), statutory_estimates=estimates)

    def _t_draft_appeal(self, session: Any, args: dict, *, build=None) -> Any:
        return build() if build is not None else None

    # ---- T2 (only reached with a valid nonce)
    def _sandbox_run(self, session: Any, name: str, bound: dict) -> Optional[dict]:
        if self.source.mode == "fixtures" or session.user_id not in SANDBOX_USER_IDS:
            return None
        try:
            from ..sandbox import tools as sb  # type: ignore

            return sb.run_tool(name, session, bound)
        except Exception as e:  # noqa: BLE001
            log.info("sandbox %s unavailable (%s); in-memory", name, str(e)[:80])
            return None

    def _t_submit_claim(self, session: Any, args: dict) -> dict:
        draft = args.get("draft_handle") or {}
        res = self._sandbox_run(session, "submit_claim", args)
        cid = (res or {}).get("claim_id") or f"CLM-{uuid.uuid4().hex[:8].upper()}"
        rec = {"id": cid, "policy_id": draft.get("policy_id"), "status": "submitted", "submitted_on": session.as_of.isoformat(),
               "expected_amount": draft.get("expected_amount"), "deadline": draft.get("deadline"), "created_via": "assistant"}
        session.open_claims.append(rec)
        session.owned_claim_ids.add(cid)
        return rec

    def _t_attach_document(self, session: Any, args: dict) -> dict:
        res = self._sandbox_run(session, "attach_document", args)
        return res or {"claim_id": args.get("claim_id"), "attached": True, "document_id": f"DOC-{uuid.uuid4().hex[:8]}"}

    def _t_file_appeal(self, session: Any, args: dict) -> dict:
        res = self._sandbox_run(session, "file_appeal", args)
        a = args.get("appeal_handle") or {}
        return res or {"appeal_id": f"APL-{uuid.uuid4().hex[:8].upper()}", "claim_id": a.get("claim_id"), "policy_id": a.get("policy_id"), "status": "FILED"}

    def _t_schedule_callback(self, session: Any, args: dict) -> dict:
        res = self._sandbox_run(session, "schedule_callback", args)
        return res or {"ticket_id": f"CB-{uuid.uuid4().hex[:8].upper()}", "type": "CALLBACK", "slot": str(args.get("slot"))}


def _policy_limit(policy: PolicyRecord, facts: ScenarioFacts) -> Optional[int]:
    ev = portfolio.event_for_policy(policy, facts)
    best: Optional[Decimal] = None
    for t in policy.tuples_by(Relation.COVERS):
        if t.object != ev:
            continue
        q = t.qualifiers
        cands = []
        if q.per_day_limit is not None and (q.max_days_per_year or q.max_days):
            cands.append(q.per_day_limit * (q.max_days_per_year or q.max_days))
        if q.per_week_amount is not None and q.max_weeks:
            cands.append(q.per_week_amount * q.max_weeks)
        for v in (q.annual_cap, q.per_case_limit, q.amount, q.lifetime_cap):
            if v is not None:
                cands.append(v)
        if cands:
            best = max(cands) if best is None else max(best, max(cands))
    return int(best) if best is not None else None
