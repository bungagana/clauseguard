"""Simulated insurer decisions, for sandbox claims only.

A real insurer decides a claim in its own systems. The sandbox has no such counterpart, so a
multi-payer claim could never move past its first payer in a demo. This module stands in for the
insurer's claims desk and is labelled as such everywhere: each decision it writes is tagged
SIMULATED in the audit log and on the payment record, it only touches claims filed through the
assistant in the sandbox database (created_via = 'assistant', status 'submitted' or 'appealed'),
and it is reachable only from the back office (admin token) or from a sandbox-only endpoint scoped
to the session's own claims. It is not in the tool registry: the agent cannot call it.

The adjudication is deterministic. BPJS Kesehatan pays the INA-CBG package for the member's class
when the sandbox tariff table lists one for the diagnosis (mock values), otherwise the presented
amount; an indemnity insurer pays what its own terms give on the amount presented to it (inner
limits, co-payment and caps, as in the allocation optimizer); a fixed-benefit insurer pays the
solver's amount. A solver denial becomes a rejection carrying the denial code.
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Any, Optional

from ..schema import Basis, ScenarioFacts, Slot, Verdict
from . import seed as _seed
from . import tools as _tools

SIMULATED = "SIMULATED insurer decision (sandbox only)"
CBG_BY_DIAGNOSIS = {
    "DENGUE": "A-4-13-I", "A90": "A-4-13-I", "A91": "A-4-13-II", "TYPHOID": "A-4-14-I", "A01": "A-4-14-I",
    "ASTHMA": "E-4-10-I", "J45": "E-4-10-I", "FRACTURE": "W-1-20-I", "S82": "W-1-20-I",
}
_CAUSE = {"illness": "ILLNESS", "accident": "ACCIDENT", "accident_traffic": "ACCIDENT_TRAFFIC", "accident_traffic_multi": "ACCIDENT_TRAFFIC", "accident_work": "ACCIDENT_WORK"}


class NotSimulable(PermissionError):
    pass


def cbg_for(diagnosis: Optional[str]) -> Optional[str]:
    if not diagnosis:
        return None
    d = str(diagnosis).upper()
    return CBG_BY_DIAGNOSIS.get(d) or CBG_BY_DIAGNOSIS.get(d.split(".")[0])


def package_tariff(diagnosis: Optional[str], bpjs_class: Optional[int]) -> Optional[tuple[Decimal, str]]:
    """(amount, basis) of the mock INA-CBG package for this diagnosis and class, if the table has one."""
    code = cbg_for(diagnosis)
    if code is None or bpjs_class is None:
        return None
    row = next((t for t in _seed.TARIFFS if t[0] == code and int(t[1]) == int(bpjs_class)), None)
    if row is None:
        return None
    return Decimal(row[2]), f"INA-CBG {code} class {int(bpjs_class)}, sandbox mock tariff"


def _facts(row: dict[str, Any], presented: Decimal) -> tuple[ScenarioFacts, dict[str, date]]:
    values: dict[Slot, Any] = {Slot.EVENT: row.get("event_type") or "HOSPITALIZATION", Slot.BILLED_AMOUNT: int(presented)}
    cause = _CAUSE.get(str(row.get("cause") or "").lower(), str(row.get("cause")).upper() if row.get("cause") else None)
    if cause:
        values[Slot.CAUSE] = cause
        values[Slot.IS_ACCIDENT] = cause.startswith("ACCIDENT")
    if row.get("facility_is_bpjs_partner") is not None:
        values[Slot.FACILITY_BPJS_PARTNER] = bool(row["facility_is_bpjs_partner"])
    if row.get("is_emergency") is not None:
        values[Slot.IS_EMERGENCY] = bool(row["is_emergency"])
    dates: dict[str, date] = {}
    for key, col in (("admission", "admission_date"), ("discharge", "discharge_date")):
        if row.get(col):
            dates[key] = date.fromisoformat(row[col])
    if "admission" in dates and "discharge" in dates:
        values[Slot.DAYS_HOSPITALIZED] = (dates["discharge"] - dates["admission"]).days + 1
    return ScenarioFacts(values=values), dates


def adjudicate(row: dict[str, Any], today: date) -> tuple[str, Decimal, Optional[str]]:
    """(status, paid amount, rejection code) the simulated claims desk arrives at."""
    from .. import portfolio
    from ..agent.facts_fallback import derive_for_policy
    from ..allocation import _event_tuples, policy_terms

    rec = _tools.record_for(row["policy_id"])
    presented = Decimal(row.get("claim_amount") if row.get("claim_amount") is not None else (row.get("billed_amount") or 0))
    facts, dates = _facts(row, presented)
    if rec.product_type == "social_bpjs_kes":
        if not facts.values.get(Slot.FACILITY_BPJS_PARTNER) and not facts.values.get(Slot.IS_EMERGENCY):
            return "rejected", Decimal(0), "NON_PARTNER_FACILITY"
        cust = _tools._rows("SELECT bpjs_kes_class FROM customers WHERE id=?", row.get("customer_id"))
        t = package_tariff(row.get("diagnosis_icd"), cust[0]["bpjs_kes_class"] if cust else None)
        return "approved", (min(t[0], presented) if t else presented), None
    from .persona_policies import PERSONA_BY_USER, PERSONA_META

    meta = PERSONA_META.get(PERSONA_BY_USER.get(str(row.get("customer_id")), ""), {})
    filed = date.fromisoformat(row["filed_date"]) if row.get("filed_date") else today
    person = str(row.get("customer_id") or "").replace("C-", "").lower()
    conditions = {k: date.fromisoformat(v) for k, v in meta.get("conditions", {}).get(person, {}).items()}
    f = derive_for_policy(facts, rec, dates=dates, as_of=filed, diagnosis=row.get("diagnosis_icd"), diagnosis_dates=conditions,
                          payment=meta.get("payments", {}).get(rec.id), employment_active=meta.get("employment_active"))
    deadline, late_effect, _tid, _ev = portfolio.compute_deadline(rec, f, filed)
    if deadline is not None and filed > deadline and late_effect in (None, "REJECT"):
        return "rejected", Decimal(0), "LATE_FILING"
    r = portfolio.decide_mapped(rec, f)
    if r.verdict == Verdict.DENIED:
        return "rejected", Decimal(0), portfolio.normalise_denial_code(r, rec) or "DENIED"
    if r.verdict != Verdict.COVERED:
        return "submitted", Decimal(0), None
    event = portfolio.event_for_policy(rec, f) or str(f.get(Slot.EVENT))
    if _event_tuples(rec, event, Basis.INDEMNITY):
        terms = policy_terms(rec, event, f, ["total"])
        paid = terms.capacity({"total": presented})[0] if terms is not None else min(Decimal(r.payable or presented), presented)
        return "approved", Decimal(paid), None
    return "approved", Decimal(r.payable or 0), None


def _write(claim_id: str, row: dict[str, Any], status: str, paid: Decimal, code: Optional[str], today: date, source: str) -> dict[str, Any]:
    from ..security import audit

    c = _tools.conn()
    c.execute("UPDATE claims SET status=?, rejection_code=? WHERE id=?", (status, code, claim_id))
    payment_id: Optional[str] = None
    if status in ("approved", "paid") and paid > 0:
        rec = _tools.record_for(row["policy_id"])
        payment_id = f"CP-{uuid.uuid4().hex[:8].upper()}"
        c.execute("INSERT INTO claim_payments VALUES (?,?,?,?,?)", (payment_id, claim_id, f"{rec.insurer} [{source}]", int(paid), today.isoformat()))
    c.commit()
    _tools._mirror("claim", claim_id)
    if payment_id:
        _tools._mirror("payment", payment_id)
    audit.append({"event_type": "INSURER_DECISION", "user_id": "sandbox-insurer", "decision": status, "doc_id": claim_id,
                  "reason": f"{source}: claim {claim_id} {status} paid={int(paid)} code={code or '-'}"})
    return {"claim_id": claim_id, "status": status, "paid_amount": int(paid), "rejection_code": code, "source": source}


def simulate_decision(claim_id: str, *, decision: str = "auto", amount: Optional[int] = None, rejection_code: Optional[str] = None,
                      today: Optional[date] = None) -> dict[str, Any]:
    """Decide one sandbox claim filed through the assistant. `decision` is auto | approved | rejected."""
    rows = _tools._rows("SELECT * FROM claims WHERE id=?", claim_id)
    if not rows:
        raise KeyError(claim_id)
    row = rows[0]
    if row.get("created_via") != "assistant" or row.get("status") not in ("submitted", "appealed"):
        raise NotSimulable("only undecided claims filed through the assistant in the sandbox can be decided by the simulator")
    today = today or date.today()
    if decision == "rejected":
        status, paid, code = "rejected", Decimal(0), rejection_code or "NOT_SPECIFIED"
    elif decision == "approved" and amount is not None:
        status, paid, code = "approved", Decimal(amount), None
    else:
        status, paid, code = adjudicate(row, today)
        if status == "submitted":
            return {"claim_id": claim_id, "status": "submitted", "paid_amount": 0, "rejection_code": None, "source": "SANDBOX_SIMULATED",
                    "note": "the simulated claims desk needs more information before it can decide"}
    return _write(claim_id, row, status, paid, code, today, "SANDBOX_SIMULATED")


def record_human_decision(claim_id: str, decision: str, amount: Optional[int], rejection_code: Optional[str], today: Optional[date] = None) -> dict[str, Any]:
    """A back-office officer's decision, with the paid amount when there is one (the explanation of benefits)."""
    rows = _tools._rows("SELECT * FROM claims WHERE id=?", claim_id)
    if not rows:
        raise KeyError(claim_id)
    status = decision
    paid = Decimal(amount or 0) if decision in ("approved", "paid") else Decimal(0)
    return _write(claim_id, rows[0], status, paid, rejection_code if decision == "rejected" else None, today or date.today(), "BACKOFFICE")
