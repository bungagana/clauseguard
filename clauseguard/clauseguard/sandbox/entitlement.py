"""Entitlement read models for the demo UI: claim allocation, insurer twin pre-check, timeline,
recourse and plan selection.

These are session-scoped adapters over the optional entitlement modules (`clauseguard.allocation`,
`clauseguard.timeline`, `clauseguard.twin`, `clauseguard.recourse`, `clauseguard.plans.selector`).
Each module is imported lazily; when it is missing, or when its entry point does not accept the
context this adapter can build, the result is `{"available": False, "reason": ...}` so the UI can
show a graceful placeholder. Identity always comes from the session: only the session's own
policies and claims are read, and nothing is written. None of this is a tool: the planner cannot
reach it.
"""
from __future__ import annotations

import importlib
import inspect
import json
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any, Callable, Optional

from ..agent import derive
from ..schema import PolicyRecord, ScenarioFacts, Slot
from . import tools as _tools

MODULES = {
    "allocation": ("clauseguard.allocation", "optimize_allocation"),
    "timeline": ("clauseguard.timeline", "build_timeline"),
    "twin": ("clauseguard.twin", "adjudicate_like_insurer"),
    "recourse": ("clauseguard.recourse", "find_recourse"),
    "plans": ("clauseguard.plans.selector", "select_plans"),
}

_CAUSE_FROM_ROW = {
    "illness": ("ILLNESS", None), "accident": ("ACCIDENT", None), "accident_traffic": ("ACCIDENT_TRAFFIC", 1),
    "accident_traffic_multi": ("ACCIDENT_TRAFFIC", 2), "accident_work": ("ACCIDENT_WORK", None),
}


def unavailable(reason: str) -> dict[str, Any]:
    return {"available": False, "reason": reason}


def load(kind: str) -> tuple[Optional[Callable[..., Any]], Optional[str]]:
    """Import the entry point for `kind`; (None, reason) when the module is not installed."""
    mod_name, fn_name = MODULES[kind]
    try:
        mod = importlib.import_module(mod_name)
    except ImportError as e:
        return None, f"{mod_name} not installed ({e})"
    fn = getattr(mod, fn_name, None)
    if fn is None or not callable(fn):
        return None, f"{mod_name}.{fn_name} missing"
    return fn, None


def call_with_context(fn: Callable[..., Any], **candidates: Any) -> Any:
    """Call `fn` with the subset of `candidates` its signature accepts. A required parameter this
    adapter cannot supply raises TypeError, which the caller reports as unavailable."""
    sig = inspect.signature(fn)
    params = sig.parameters
    if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values()):
        return fn(**candidates)
    kwargs = {}
    for name, p in params.items():
        if p.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
            continue
        if name in candidates:
            kwargs[name] = candidates[name]
        elif p.default is inspect.Parameter.empty:
            raise TypeError(f"cannot supply required argument '{name}'")
    return fn(**kwargs)


def dump(v: Any) -> Any:
    if hasattr(v, "model_dump_json"):
        return json.loads(v.model_dump_json())
    if hasattr(v, "model_dump"):
        return dump(v.model_dump())
    if isinstance(v, Decimal):
        return str(v)
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, dict):
        return {str(k.value if hasattr(k, "value") else k): dump(x) for k, x in v.items()}
    if isinstance(v, (list, tuple, set)):
        return [dump(x) for x in v]
    if hasattr(v, "value") and not isinstance(v, (str, int, float, bool)):
        return v.value
    if hasattr(v, "__dataclass_fields__"):
        return {k: dump(getattr(v, k)) for k in v.__dataclass_fields__}
    return v


def finish(result: Any, kind: str) -> dict[str, Any]:
    out = dump(result)
    if isinstance(out, list):
        out = {"events" if kind == "timeline" else "items": out}
    if not isinstance(out, dict):
        return unavailable(f"{kind} returned an unexpected type ({type(result).__name__})")
    out.setdefault("available", True)
    return out


# --------------------------------------------------------------------------- context
@dataclass
class Context:
    """Everything the entitlement modules can ask for, built from the session's own data."""

    user_id: str
    policies: list[PolicyRecord]
    facts: ScenarioFacts
    facts_by_policy: dict[str, ScenarioFacts]
    as_of: date
    event_dates: dict[str, date] = field(default_factory=dict)
    documents_present: list[str] = field(default_factory=list)
    bill_breakdown: Optional[dict[str, Decimal]] = None
    claim: Optional[dict[str, Any]] = None
    claim_id: Optional[str] = None
    meta: dict[str, Any] = field(default_factory=dict)
    persona: Optional[str] = None

    def focus_policy(self, policy_id: Optional[str] = None) -> Optional[PolicyRecord]:
        """The policy a single-policy module should look at: the one asked for, the claim's own, or
        the first private policy that covers the event."""
        from .. import portfolio

        wanted = policy_id or (self.claim or {}).get("policy_id")
        if wanted:
            return next((p for p in self.policies if p.id == wanted), None)
        for p in self.policies:
            ev = portfolio.event_for_policy(p, self.facts_by_policy.get(p.id, self.facts))
            if ev and not portfolio.is_statutory(p) and portfolio.covers_event(p, ev):
                return p
        return self.policies[0] if self.policies else None

    def candidates(self, **extra: Any) -> dict[str, Any]:
        bill = self.bill_breakdown
        return {
            "policies": self.policies, "records": self.policies, "facts": self.facts, "scenario_facts": self.facts, "claim_facts": self.facts,
            "portfolio": self.policies, "current_policies": self.policies,
            "facts_by_policy": self.facts_by_policy, "as_of": self.as_of, "today": self.as_of, "event_dates": self.event_dates, "dates": self.event_dates,
            "documents_present": self.documents_present, "bill_breakdown": bill, "bill": bill, "claim": self.claim, "claim_id": self.claim_id,
            "meta": self.meta, "persona_meta": self.meta, "persona": self.persona, "user_id": self.user_id, "jurisdiction": "ID", **extra,
        }


def _meta_for(session: Any) -> dict[str, Any]:
    from .persona_policies import PERSONA_BY_USER, PERSONA_META

    key = session.persona or PERSONA_BY_USER.get(session.user_id, "")
    return PERSONA_META.get(key, {"user_id": session.user_id, "persons": {}, "insured": {}, "claims": []})


def _records(session: Any) -> list[PolicyRecord]:
    from .persona_policies import PERSONA_HOLDINGS

    recs = _tools.user_records(session.user_id)
    order = {pid: i for i, (pid, _r, _s) in enumerate(PERSONA_HOLDINGS.get(session.persona or "", []))}
    return sorted(recs, key=lambda p: (order.get(p.id, 999), p.id))


def _claim_row(session: Any, claim_id: str) -> Optional[dict[str, Any]]:
    if claim_id not in session.owned_claim_ids:
        return None
    rows = _tools._rows("SELECT * FROM claims WHERE id=?", claim_id)
    return rows[0] if rows else None


def _facts_from_claim(row: dict[str, Any], meta: dict[str, Any], as_of: date) -> tuple[ScenarioFacts, dict[str, date], Optional[dict], Optional[dict[str, Decimal]]]:
    values: dict[Slot, Any] = {Slot.EVENT: row.get("event_type") or "HOSPITALIZATION"}
    cause, vehicles = _CAUSE_FROM_ROW.get(str(row.get("cause") or "").lower(), (None, None))
    if cause:
        values[Slot.CAUSE] = cause
        values[Slot.IS_ACCIDENT] = cause.startswith("ACCIDENT")
    if vehicles is not None:
        values[Slot.VEHICLES_INVOLVED] = vehicles
    if row.get("facility_is_bpjs_partner") is not None:
        values[Slot.FACILITY_BPJS_PARTNER] = bool(row["facility_is_bpjs_partner"])
    if row.get("is_emergency") is not None:
        values[Slot.IS_EMERGENCY] = bool(row["is_emergency"])
    if row.get("billed_amount"):
        values[Slot.BILLED_AMOUNT] = int(row["billed_amount"])
    dates: dict[str, date] = {}
    for key, col in (("admission", "admission_date"), ("discharge", "discharge_date"), ("event", "event_date")):
        if row.get(col):
            dates[key] = date.fromisoformat(row[col])
    if cause == "ACCIDENT_TRAFFIC" and "event" in dates:
        dates["accident"] = dates["event"]
    if "admission" in dates and "discharge" in dates:
        values[Slot.DAYS_HOSPITALIZED] = derive.stay_days(dates["admission"], dates["discharge"])
    persona_claim = next((c for c in meta.get("claims", []) if c.get("policy_id") == row.get("policy_id")), None)
    breakdown = {k: Decimal(v) for k, v in (persona_claim or {}).get("breakdown", {}).items()} or None
    return ScenarioFacts(values=values, as_of=as_of), dates, persona_claim, breakdown


def _derive(session: Any, policies: list[PolicyRecord], facts: ScenarioFacts, dates: dict[str, date], as_of: date, meta: dict[str, Any],
            diagnosis: Optional[str], person: Optional[str]) -> dict[str, ScenarioFacts]:
    from .. import portfolio
    from ..agent.facts_fallback import derive_for_policy

    conditions = {k: date.fromisoformat(v) for k, v in meta.get("conditions", {}).get(person or session.user_id, {}).items()}
    out: dict[str, ScenarioFacts] = {}
    for p in policies:
        override = getattr(session, "effective_override", None)
        if override and (portfolio.is_statutory(p) or not portfolio.covers_event(p, portfolio.event_for_policy(p, facts) or "")):
            override = None
        f = derive_for_policy(facts, p, dates=dates, as_of=as_of, diagnosis=diagnosis, diagnosis_dates=conditions, effective_override=override,
                              payment=meta.get("payments", {}).get(p.id), employment_active=meta.get("employment_active"))
        if p.product_type == "social_bpjs_kes" and not facts.has(Slot.PREMIUM_STATUS):
            pay = _tools.get_payment_status(session, policy_id=p.id)
            f = f.bind(Slot.PREMIUM_STATUS, "PAID" if pay.get("premium_status") == "PAID" else "LAPSED")
        out[p.id] = f
    return out


def _uploaded_extracts(session: Any) -> list[Any]:
    """Typed claim-document extracts registered in this session (the quarantined extractor's output)."""
    registry = getattr(session, "registry", None)
    if registry is None or not hasattr(registry, "handles"):
        return []
    out = []
    for h in registry.handles():
        tv = registry.resolve(h)
        if tv is not None and tv.type == "ClaimDocExtract":
            out.append(tv.value)
    return out


def build_context(session: Any, claim: Optional[str] = None, bill: Optional[dict[str, Any]] = None) -> Context:
    """`claim` is a claim id on this account, or "draft" / None for the conversation's own facts.
    A draft with no event yet falls back to the persona's open claim so the cards can render
    before the first chat turn."""
    from ..agent.session import ensure_state

    ensure_state(session)
    meta = _meta_for(session)
    policies = _records(session)
    as_of: date = session.as_of
    facts: ScenarioFacts = session.facts
    dates: dict[str, date] = dict(session.event_dates)
    diagnosis = session.diagnosis_code
    person = session.person_id
    claim_row = None
    claim_id = None
    breakdown: Optional[dict[str, Decimal]] = None
    if claim and claim != "draft":
        row = _claim_row(session, claim)
        if row is None:
            raise KeyError(claim)
        facts, dates, persona_claim, breakdown = _facts_from_claim(row, meta, as_of)
        claim_row = {**row, "person": (persona_claim or {}).get("person")}
        claim_id = row["id"]
        diagnosis = (persona_claim or {}).get("diagnosis") or diagnosis
        person = (persona_claim or {}).get("person") or person
    elif not facts.has(Slot.EVENT):
        open_claims = [c for c in meta.get("claims", []) if c.get("status") == "draft"]
        if open_claims:
            c = open_claims[0]
            claim_row = dict(c)
            claim_id = c.get("id")
            values: dict[Slot, Any] = {Slot.EVENT: c.get("event", "HOSPITALIZATION")}
            cause = c.get("cause") or ("ILLNESS" if c.get("diagnosis") else None)
            if cause:
                values[Slot.CAUSE] = cause
                values[Slot.IS_ACCIDENT] = str(cause).startswith("ACCIDENT")
            if c.get("facility_bpjs_partner") is not None:
                values[Slot.FACILITY_BPJS_PARTNER] = bool(c["facility_bpjs_partner"])
            if c.get("billed"):
                values[Slot.BILLED_AMOUNT] = int(c["billed"])
            for k in ("admission", "discharge", "accident"):
                if c.get(k):
                    dates[k] = date.fromisoformat(c[k])
            if "admission" in dates and "discharge" in dates:
                values[Slot.DAYS_HOSPITALIZED] = derive.stay_days(dates["admission"], dates["discharge"])
            facts = ScenarioFacts(values=values, as_of=as_of)
            diagnosis = c.get("diagnosis") or diagnosis
            person = c.get("person") or person
            breakdown = {k: Decimal(v) for k, v in c.get("breakdown", {}).items()} or None
    if bill:
        try:
            breakdown = {str(k): Decimal(str(v)) for k, v in bill.items()}
        except (ArithmeticError, TypeError, ValueError):
            pass
        if breakdown and not facts.has(Slot.BILLED_AMOUNT):
            facts = facts.bind(Slot.BILLED_AMOUNT, int(sum(breakdown.values())))
    derived: dict[str, Any] = {}
    if facts.has(Slot.EVENT):
        dates, derived = derive.derive_event_dates(dates, facts)
    if not facts.has(Slot.EVENT):
        facts_by_policy = {p.id: facts for p in policies}
    else:
        facts_by_policy = _derive(session, policies, facts, dates, as_of, meta, diagnosis, person)
    docs = list(facts.values.get(Slot.DOCUMENTS_PRESENT) or []) if isinstance(facts.values.get(Slot.DOCUMENTS_PRESENT), (list, tuple)) else []
    return Context(user_id=session.user_id, policies=policies, facts=facts, facts_by_policy=facts_by_policy, as_of=as_of, event_dates=dates,
                   documents_present=docs, bill_breakdown=breakdown, claim=claim_row, claim_id=claim_id, meta=meta, persona=session.persona)


# --------------------------------------------------------------------------- read models
def _run(kind: str, session: Any, build: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    fn, reason = load(kind)
    if fn is None:
        return unavailable(reason or kind)
    try:
        candidates = build()
    except KeyError as e:
        return unavailable(f"{e.args[0]} is not on this account")
    except Exception as e:  # noqa: BLE001 - context inputs (catalogue, payment rows) are best effort
        return unavailable(f"{kind} context could not be built: {type(e).__name__}: {str(e)[:120]}")
    try:
        out = finish(call_with_context(fn, **candidates), kind)
        if candidates.get("currency") and "currency" not in out:
            out["currency"] = candidates["currency"]
        return out
    except TypeError as e:
        return unavailable(f"{MODULES[kind][0]} entry point not compatible with the session context: {e}")
    except Exception as e:  # noqa: BLE001 - a failing optional module must not break the UI
        return unavailable(f"{MODULES[kind][0]} failed: {type(e).__name__}: {str(e)[:120]}")


_BILL_PARTS = ("room", "surgery", "doctor", "drugs", "other")


def _bill_model(ctx: Context) -> Any:
    """The allocation module's own `BillBreakdown` (total + optional itemised parts) when it defines
    one, else the plain part -> amount dict. Unknown part names are folded into `other`."""
    total = int(ctx.facts.get(Slot.BILLED_AMOUNT)) if ctx.facts.has(Slot.BILLED_AMOUNT) else None
    parts = ctx.bill_breakdown or {}
    if total is None and parts:
        total = int(sum(parts.values()))
    if total is None:
        return None
    try:
        from ..allocation import BillBreakdown  # type: ignore
    except (ImportError, AttributeError):
        return {"total": Decimal(total), **parts}
    fields: dict[str, Any] = {"total": Decimal(total)}
    other = Decimal(0)
    for k, v in parts.items():
        key = str(k).lower()
        if key in _BILL_PARTS and key != "other":
            fields[key] = Decimal(v)
        else:
            other += Decimal(v)
    if other:
        fields["other"] = other
    return BillBreakdown(**fields)


def allocation(session: Any, claim: Optional[str], bill: Optional[dict[str, Any]]) -> dict[str, Any]:
    def build() -> dict[str, Any]:
        ctx = build_context(session, claim, bill)
        return ctx.candidates(bill=_bill_model(ctx))

    return _run("allocation", session, build)


def _open_claims(session: Any) -> list[Any]:
    """Unfiled claims on the account as the timeline module's `OpenClaim` (or plain dicts when the
    module does not define one)."""
    ids = _tools.household_ids(session.user_id)
    rows = _tools._rows(f"SELECT * FROM claims WHERE customer_id IN ({','.join('?' * len(ids))}) AND status='draft' ORDER BY id", *ids)
    try:
        from ..timeline import OpenClaim  # type: ignore
    except (ImportError, AttributeError):
        OpenClaim = dict  # noqa: N806
    out = []
    for r in rows:
        amount = r.get("claim_amount") or r.get("billed_amount")
        out.append(OpenClaim(claim_id=r["id"], policy_id=r["policy_id"], event=r.get("event_type") or "HOSPITALIZATION",
                             amount=Decimal(amount) if amount else None,
                             event_date=date.fromisoformat(r["event_date"]) if r.get("event_date") else None,
                             discharge_date=date.fromisoformat(r["discharge_date"]) if r.get("discharge_date") else None))
    chat = _chat_claim(session, {(r["policy_id"], r.get("event_date")) for r in rows}, OpenClaim)
    if chat is not None:
        out.append(chat)
    return out


def _chat_claim(session: Any, taken: set, OpenClaim: Any) -> Any:
    """The scenario the user described in chat (event, stay or diagnosis dates), dated with the same derivation the agent uses."""
    facts = getattr(session, "facts", None)
    pid = getattr(session, "focus_policy_id", None)
    if facts is None or not facts.has(Slot.EVENT) or not pid or pid not in getattr(session, "owned_policy_ids", {pid}):
        return None
    dates, _ = derive.derive_event_dates(dict(session.event_dates), facts)
    if not any(k in dates for k in ("admission", "discharge", "accident", "diagnosis", "death", "event")):
        return None
    amount = getattr(session, "last_payable", None)
    started = dates.get("admission") or dates.get("accident") or dates.get("event")
    if (pid, started.isoformat() if started else None) in taken:
        return None
    return OpenClaim(claim_id="CHAT-SCENARIO", policy_id=pid, event=str(facts.get(Slot.EVENT)), amount=Decimal(amount) if amount else None,
                     event_date=started, discharge_date=dates.get("discharge"),
                     treatment_end_date=dates.get("treatment_end"), diagnosis_date=dates.get("diagnosis"), death_date=dates.get("death"))


# --------------------------------------------------------------------------- what-if
# The facts a customer can flip to see how the answer changes. Only controls whose value actually
# changes at least one policy's outcome are offered (verdict sensitivity, the same idea that drives
# the clarifier). Pure solver re-runs on a copy of the facts; the session is never modified.
WHATIF_SLOTS: list[tuple[Slot, str, str, list[Any]]] = [
    (Slot.FACILITY_BPJS_PARTNER, "bool", "Hospital is a BPJS partner", [True, False]),
    (Slot.IS_EMERGENCY, "bool", "Emergency admission", [True, False]),
    (Slot.IS_ACCIDENT, "bool", "Caused by an accident", [True, False]),
    (Slot.WORK_RELATED, "bool", "Happened while working", [True, False]),
    (Slot.LICENSE_VALID, "bool", "Driving licence was valid", [True, False]),
    (Slot.INTOXICATED, "bool", "Under the influence", [True, False]),
    (Slot.EMPLOYMENT_ACTIVE, "bool", "Still employed by the plan sponsor", [True, False]),
    (Slot.VEHICLES_INVOLVED, "choice", "Vehicles involved", [1, 2]),
    (Slot.DAYS_HOSPITALIZED, "int", "Days in hospital", [0, 1, 3, 5, 10, 30]),
]


def _outcomes(session: Any, ctx: Context, facts: ScenarioFacts) -> list[dict[str, Any]]:
    from .. import portfolio

    dates = dict(ctx.event_dates)
    if facts.has(Slot.EVENT):
        dates, _ = derive.derive_event_dates(dates, facts)
        by_policy = _derive(session, ctx.policies, facts, dates, ctx.as_of, ctx.meta, session.diagnosis_code, session.person_id)
    else:
        by_policy = {p.id: facts for p in ctx.policies}
    out = []
    for p in ctx.policies:
        r = portfolio.decide_mapped(p, by_policy[p.id])
        out.append({"policy_id": p.id, "product_name": p.product_name, "verdict": r.verdict.value,
                    "payable": str(r.payable) if r.payable is not None else None, "currency": r.currency or p.currency,
                    "denial_code": r.denial_code, "clarify_slot": r.clarification.slot.value if r.clarification else None})
    return out


def _apply(facts: ScenarioFacts, overrides: dict[str, Any]) -> ScenarioFacts:
    values = dict(facts.values)
    for k, v in overrides.items():
        slot = Slot(k)
        if slot == Slot.VEHICLES_INVOLVED:
            values[Slot.CAUSE] = "ACCIDENT_TRAFFIC"
            values[Slot.IS_ACCIDENT] = True
        if slot == Slot.DAYS_HOSPITALIZED and int(v) > 0 and not values.get(Slot.EVENT):
            values[Slot.EVENT] = "HOSPITALIZATION"
        values[slot] = v
    return ScenarioFacts(values=values, as_of=facts.as_of)


def _coerce(slot: Slot, kind: str, raw: Any) -> Any:
    if kind == "bool":
        if isinstance(raw, bool):
            return raw
        return str(raw).lower() in ("true", "1", "yes")
    return int(raw)


def whatif(session: Any, overrides: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Controls that matter for this account's policies, the current outcome, and the outcome under `overrides`."""
    from ..agent.session import ensure_state

    ensure_state(session)
    try:
        ctx = build_context(session)
    except Exception as e:  # noqa: BLE001
        return unavailable(f"what-if context could not be built: {type(e).__name__}: {str(e)[:120]}")
    if not ctx.policies:
        return unavailable("no policies on this account")
    base_facts = ctx.facts
    if not base_facts.has(Slot.EVENT):
        base_facts = base_facts.bind(Slot.EVENT, "HOSPITALIZATION")  # a what-if needs a situation; inpatient treatment is the common case
    baseline = _outcomes(session, ctx, base_facts)
    key = lambda rows: [(r["verdict"], r["payable"]) for r in rows]  # noqa: E731
    controls = []
    allowed: dict[str, tuple[Slot, str]] = {}
    for slot, kind, label, candidates in WHATIF_SLOTS:
        current = base_facts.values.get(slot)
        seen = {}
        for cand in candidates:
            seen[str(cand)] = key(_outcomes(session, ctx, _apply(base_facts, {slot.value: cand})))
        if len({json.dumps(v) for v in seen.values()}) > 1:
            controls.append({"slot": slot.value, "kind": kind, "label": label, "options": candidates,
                             "current": current if current is not None else None})
            allowed[slot.value] = (slot, kind)
    clean: dict[str, Any] = {}
    for k, v in (overrides or {}).items():
        if k in allowed:
            try:
                clean[k] = _coerce(allowed[k][0], allowed[k][1], v)
            except (TypeError, ValueError):
                continue
    result = _outcomes(session, ctx, _apply(base_facts, clean)) if clean else baseline
    changed = [a["policy_id"] for a, b in zip(baseline, result) if (a["verdict"], a["payable"]) != (b["verdict"], b["payable"])]
    return {"available": True, "controls": controls, "overrides": clean, "baseline": baseline, "result": result, "changed": changed}


def digest(session: Any) -> dict[str, Any]:
    try:
        return {**_tools.get_deadline_digest(session), "available": True}
    except Exception as e:  # noqa: BLE001 - a UI card degrades gracefully rather than breaking the page
        return unavailable(f"digest could not be built: {type(e).__name__}: {str(e)[:120]}")


def timeline(session: Any) -> dict[str, Any]:
    def build() -> dict[str, Any]:
        ctx = build_context(session)
        pay_rows = [_tools.get_payment_status(session, policy_id=p.id) for p in ctx.policies]
        premium_due = {r["policy_id"]: date.fromisoformat(r["unpaid_due_dates"][0]) for r in pay_rows if r.get("unpaid_due_dates")}
        return ctx.candidates(pay_rows=pay_rows, payments=pay_rows, payment_rows=pay_rows, premium_due=premium_due, open_claims=_open_claims(session), session=session)

    return _run("timeline", session, build)


def _single_policy(ctx: Context, policy_id: Optional[str]) -> dict[str, Any]:
    policy = ctx.focus_policy(policy_id)
    if policy is None:
        raise KeyError(policy_id or "no policy")
    facts = ctx.facts_by_policy.get(policy.id, ctx.facts)
    return ctx.candidates(policy=policy, record=policy, policy_id=policy.id, facts=facts, scenario_facts=facts, claim_facts=facts)


def twin(session: Any, claim: Optional[str], policy_id: Optional[str] = None) -> dict[str, Any]:
    def build() -> dict[str, Any]:
        if policy_id and policy_id not in session.owned_policy_ids:
            raise KeyError(policy_id)
        ctx = build_context(session, claim)
        return {**_single_policy(ctx, policy_id), "documents": _uploaded_extracts(session), "extracts": _uploaded_extracts(session)}

    return _run("twin", session, build)


def recourse(session: Any, policy_id: str, claim: Optional[str]) -> dict[str, Any]:
    def build() -> dict[str, Any]:
        if policy_id not in session.owned_policy_ids:
            raise KeyError(policy_id)
        return _single_policy(build_context(session, claim), policy_id)

    return _run("recourse", session, build)


def plans(session: Any, budget: Optional[int], jurisdiction: str) -> dict[str, Any]:
    def build() -> dict[str, Any]:
        from .. import catalogue

        gap = _tools.gap_analysis(session)
        ctx = build_context(session)
        cat = catalogue.catalogue_for(jurisdiction)
        candidate_plans = cat[0] if cat else list(catalogue.build_catalogue().values())
        persons = list(ctx.meta.get("persons", {}).keys()) or [session.user_id]
        return ctx.candidates(gap_report=gap, gap=gap, budget=budget, budget_monthly=budget, budget_per_month=budget, budget_idr_per_month=budget,
                              monthly_budget=budget, jurisdiction=jurisdiction, persons=persons, candidate_plans=candidate_plans,
                              insured=ctx.meta.get("insured") or None, earner=ctx.meta.get("user_id") if len(persons) > 1 else None,
                              currency=cat[2] if cat else "IDR")

    return _run("plans", session, build)
