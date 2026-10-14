"""Tool implementations, bound to the registry specs in `clauseguard.security.registry`.

Every function takes `session` first (server-side identity: `session.user_id`); the
remaining keyword arguments are the PEP-bound values (handles already resolved). No tool
ever reads a user id from its arguments, and no tool here can approve/deny/pay anything.

T0 read own data      T1 compute/draft (no side effect)      T2 create records (nonce-gated by PEP)
T3 create_account_change_request -> ticket only; the account value is hashed, never stored raw.

T1 functions that need `clauseguard.portfolio` import it lazily and raise
NotImplementedError("portfolio pending") until it lands.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Optional

from ..schema import PolicyRecord, Relation, ScenarioFacts, Slot, VerdictResult
from ..security import registry
from ..solver import decide
from . import db as _db
from . import seed as _seed

_conn: Optional[sqlite3.Connection] = None


def conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = _db.init_db(seed=True)
    return _conn


def _mirror(kind: str, row_id: str) -> None:
    try:
        from ..storage import mirror

        fn = {"claim": mirror.mirror_claim, "ticket": mirror.mirror_ticket, "payment": mirror.mirror_payment}[kind]
        fn(conn(), row_id)
    except Exception:
        pass


def set_connection(c: Optional[sqlite3.Connection]) -> None:
    """Tests inject a temporary database here."""
    global _conn
    _conn = c


def _rows(sql: str, *params: Any) -> list[dict[str, Any]]:
    return [dict(r) for r in conn().execute(sql, params).fetchall()]


def household_ids(user_id: str) -> list[str]:
    r = conn().execute("SELECT household_id FROM customers WHERE id=?", (user_id,)).fetchone()
    if r is None:
        return [user_id]
    return [x["id"] for x in conn().execute("SELECT id FROM customers WHERE household_id=?", (r["household_id"],)).fetchall()]


def owned_policy_rows(user_id: str) -> list[dict[str, Any]]:
    ids = household_ids(user_id)
    q = ",".join("?" * len(ids))
    return _rows(f"SELECT * FROM policies WHERE customer_id IN ({q}) OR customer_id IS NULL ORDER BY id", *ids)


def owned_policy_ids(user_id: str) -> set[str]:
    return {r["id"] for r in owned_policy_rows(user_id)}


def owned_record_ids(user_id: str) -> set[str]:
    return {r["record_id"] for r in owned_policy_rows(user_id)}


def owned_claim_ids(user_id: str) -> set[str]:
    ids = household_ids(user_id)
    q = ",".join("?" * len(ids))
    return {r["id"] for r in _rows(f"SELECT id FROM claims WHERE customer_id IN ({q})", *ids)}


def all_policy_ids() -> set[str]:
    return {r["id"] for r in _rows("SELECT id FROM policies")} | {r["record_id"] for r in _rows("SELECT record_id FROM policies")}


_records_cache: Optional[dict[str, PolicyRecord]] = None


def records() -> dict[str, PolicyRecord]:
    global _records_cache
    if _records_cache is None:
        _records_cache = _seed.load_policy_files()
    return _records_cache


def record_for(policy_id: str) -> PolicyRecord:
    row = conn().execute("SELECT record_id FROM policies WHERE id=?", (policy_id,)).fetchone()
    rid = row["record_id"] if row else policy_id
    return records()[rid]


def row_record(row: dict[str, Any]) -> PolicyRecord:
    """Record of one policy row: shared wording (BPJS-KES) is instantiated per member with the row's id and status."""
    from .persona_policies import holding_record

    rec = records()[row["record_id"]]
    return holding_record(rec, row["id"], row["status"])


def user_records(user_id: str) -> list[PolicyRecord]:
    return [row_record(r) for r in owned_policy_rows(user_id)]


def _facts(obj: Any) -> ScenarioFacts:
    if isinstance(obj, ScenarioFacts):
        return obj
    if not isinstance(obj, dict):
        raise ValueError("scenario facts must be a dict of slot -> value")
    values = {Slot(k) if not isinstance(k, Slot) else k: v for k, v in (obj.get("values", obj)).items() if k != "as_of"}
    as_of = obj.get("as_of") if isinstance(obj.get("as_of"), (date, type(None))) else None
    return ScenarioFacts(values=values, as_of=as_of)


def _dump(v: Any) -> Any:
    if hasattr(v, "model_dump"):
        return json.loads(v.model_dump_json())
    if isinstance(v, Decimal):
        return str(v)
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    if isinstance(v, list):
        return [_dump(x) for x in v]
    if isinstance(v, dict):
        return {k: _dump(x) for k, x in v.items()}
    return v


# ------------------------------------------------------------------ T0
def get_my_policies(session, **_: Any) -> dict[str, Any]:
    rows = owned_policy_rows(session.user_id)
    for r in rows:
        r.pop("document_id", None)
    return {"user_id": session.user_id, "policies": rows}


def get_policy_clause(session, policy_id: str, tuple_id: str, **_: Any) -> dict[str, Any]:
    rec = record_for(policy_id)
    t = rec.tuple_index().get(tuple_id)
    if t is None:
        return {"policy_id": policy_id, "tuple_id": tuple_id, "found": False}
    d = _dump(t)
    d["evidence"]["display_only"] = True  # strings from documents never reach the planner
    return {"policy_id": policy_id, "tuple_id": tuple_id, "found": True, "tuple": d}


def get_claim_status(session, claim_id: str, **_: Any) -> dict[str, Any]:
    rows = _rows("SELECT id, policy_id, event_type, event_date, status, rejection_code, filed_date, deadline_date, claim_amount, billed_amount FROM claims WHERE id=?", claim_id)
    if not rows:
        return {"claim_id": claim_id, "found": False}
    payments = _rows("SELECT payer, amount, paid_date FROM claim_payments WHERE claim_id=?", claim_id)
    return {"claim_id": claim_id, "found": True, "claim": rows[0], "payments": payments}


def get_payment_status(session, policy_id: str, **_: Any) -> dict[str, Any]:
    pol = _rows("SELECT id, status, grace_days, premium_idr, premium_frequency FROM policies WHERE id=?", policy_id)
    if not pol:
        return {"policy_id": policy_id, "found": False}
    pays = _rows("SELECT due_date, paid_date, amount FROM payments WHERE policy_id=? ORDER BY due_date", policy_id)
    today = date.today()
    unpaid = [p for p in pays if p["paid_date"] is None and date.fromisoformat(p["due_date"]) <= today]
    days_overdue = (today - date.fromisoformat(unpaid[0]["due_date"])).days if unpaid else 0
    grace = pol[0]["grace_days"] or 0
    premium_status = "PAID" if not unpaid else ("OVERDUE" if days_overdue <= grace else "LAPSED")
    return {"policy_id": policy_id, "found": True, "status": pol[0]["status"], "premium_status": premium_status, "days_overdue": days_overdue,
            "grace_days": grace, "unpaid_due_dates": [p["due_date"] for p in unpaid], "payments": pays, "as_of": today.isoformat()}


def get_deadline_digest(session, **_: Any) -> dict[str, Any]:
    from ..agent.digest import digest_for_user

    return {"items": _dump(digest_for_user(session.user_id, getattr(session, "persona", None), date.today()))}


# ------------------------------------------------------------------ T1
def _portfolio():
    try:
        from .. import portfolio  # type: ignore
    except ImportError as e:  # portfolio module not importable
        raise NotImplementedError("portfolio pending") from e
    return portfolio


def check_coverage(session, scenario_facts: Any, **_: Any) -> dict[str, Any]:
    facts = _facts(scenario_facts)
    out = []
    for rec in user_records(session.user_id):
        r: VerdictResult = decide(rec, facts)
        out.append(_dump(r))
    return {"facts": _dump(facts), "verdicts": out}


def gap_analysis(session, **_: Any) -> dict[str, Any]:
    pf = _portfolio()
    from ..schema import EventCode

    persons = household_ids(session.user_id)
    recs = []
    for r in owned_policy_rows(session.user_id):  # status as of today: a premium past its grace period means the policy is lapsed (same rule as the agent's gap tool and /policies)
        rec = row_record(r)
        if r["status"] != "active" and get_payment_status(session, policy_id=r["id"]).get("premium_status") == "LAPSED":
            rec = rec.model_copy(update={"status": "lapsed"})
        recs.append(rec)
    perils = [EventCode.HOSPITALIZATION, EventCode.SURGERY, EventCode.ICU, EventCode.DEATH, EventCode.ACCIDENTAL_DEATH, EventCode.TPD, EventCode.CRITICAL_ILLNESS, EventCode.TEMPORARY_DISABILITY, EventCode.ACCIDENT_MEDICAL]
    insured: dict[str, list[str]] = {}
    for c in _rows("SELECT policy_id, insured_person_id FROM coverages WHERE insured_person_id IS NOT NULL"):
        insured.setdefault(c["policy_id"], [])
        if c["insured_person_id"] not in insured[c["policy_id"]]:
            insured[c["policy_id"]].append(c["insured_person_id"])  # policies without person-level rows (BPJS, Jasa Raharja) cover the whole household
    return _dump(pf.gap_overlap(recs, persons, perils, insured={k: v for k, v in insured.items() if k in {x.id for x in recs}}))


def claim_readiness(session, policy_id: str, claim_facts: Any, **_: Any) -> dict[str, Any]:
    pf = _portfolio()
    facts = _facts(claim_facts)
    docs = facts.values.get(Slot.DOCUMENTS_PRESENT) or []
    rep = pf.claim_readiness(record_for(policy_id), facts, list(docs) if isinstance(docs, (list, tuple)) else [], facts.as_of or date.today())
    return _dump(rep)


def cob_plan(session, claim_facts: Any, **_: Any) -> dict[str, Any]:
    pf = _portfolio()
    return {"steps": _dump(pf.cob_plan(user_records(session.user_id), _facts(claim_facts)))}


def estimate_payout(session, policy_id: str, claim_facts: Any, **_: Any) -> dict[str, Any]:
    r = decide(record_for(policy_id), _facts(claim_facts))
    return {"policy_id": policy_id, "verdict": r.verdict.value, "payable": _dump(r.payable), "currency": r.currency, "fired_tuple_ids": r.fired_tuple_ids}


def policy_limit(rec: PolicyRecord, event: Any) -> Optional[int]:
    """Maximum the policy can pay for this event (used by PEP R5 as the per-claim ceiling)."""
    best: Optional[Decimal] = None
    for t in rec.tuples_by(Relation.COVERS):
        if t.object != event:
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
        if q.pct_of_sum_assured is not None and rec.sum_assured is not None:
            cands.append(rec.sum_assured * Decimal(str(q.pct_of_sum_assured)) / Decimal(100))
        if cands:
            m = max(cands)
            best = m if best is None else max(best, m)
    return int(best) if best is not None else None


def draft_claim(session, policy_id: str, claim_facts: Any, document_handles: Optional[list[str]] = None, **_: Any) -> dict[str, Any]:
    """A draft is pure data; nothing is written. submit_claim needs the registry handle of this dict."""
    facts = _facts(claim_facts)
    rec = record_for(policy_id)
    r = decide(rec, facts)
    limit = policy_limit(rec, facts.values.get(Slot.EVENT))
    req = [t.qualifiers.document_codes for t in rec.tuples_by(Relation.REQUIRES_DOCUMENT) if t.object == facts.values.get(Slot.EVENT)]
    required = sorted({c for codes in req for c in codes})
    return {
        "draft_id": f"DRAFT-{uuid.uuid4().hex[:8]}",
        "policy_id": policy_id,
        "event": facts.values.get(Slot.EVENT),
        "verdict": r.verdict.value,
        "amount": _dump(r.payable),
        "currency": r.currency or rec.currency,
        "policy_limit": limit,
        "fired_tuple_ids": r.fired_tuple_ids,
        "required_documents": required,
        "document_handles": list(document_handles or []),
        "facts": _dump(facts),
        "created_by": "draft_claim",
    }


def extract_document(session, doc_handle: Any, **_: Any) -> dict[str, Any]:
    try:
        from ..extractor.claim_doc import extract_claim_document  # type: ignore
    except ImportError as e:
        raise NotImplementedError("extractor pending") from e
    path = doc_handle["path"] if isinstance(doc_handle, dict) else str(doc_handle)
    name = conn().execute("SELECT name FROM customers WHERE id=?", (session.user_id,)).fetchone()
    return _dump(extract_claim_document(path, policyholder_name=name["name"] if name else ""))


# ------------------------------------------------------------------ T2 (PEP has already verified the nonce)
def _form_record(d: dict[str, Any]) -> dict[str, Any]:
    """The claim form as the insurer receives it: typed fields only, never free text from the chat."""
    facts = d.get("facts", {}).get("values", {})
    return {
        "policy_id": d.get("policy_id"), "event": d.get("event"), "admission_date": d.get("admission"), "discharge_date": d.get("discharge"),
        "diagnosis": d.get("diagnosis"), "cause": facts.get("cause"), "days_hospitalized": facts.get("days_hospitalized"),
        "billed_amount": facts.get("billed_amount"), "claimed_amount": d.get("claim_amount", d.get("amount")), "currency": d.get("currency"),
        "facility_bpjs_partner": facts.get("facility_bpjs_partner"), "is_emergency": facts.get("is_emergency"),
        "required_documents": d.get("required_documents", []), "documents_attached": len(d.get("document_handles", [])),
        "missing_documents_acknowledged": d.get("missing_documents", []), "clauses_relied_on": d.get("fired_tuple_ids", []),
        "prepared_by": "ClauseGuard assistant", "confirmed_by_customer": True,
        # the insurer's own form layout (from its policy clauses), already filled from the typed values above
        "form_title": d.get("form_title"), "form_layout_source": d.get("form_layout_source"), "sections": d.get("form_sections") or [],
    }


def submit_claim(session, draft_handle: Any, **_: Any) -> dict[str, Any]:
    d = draft_handle if isinstance(draft_handle, dict) else {}
    if d.get("created_by") != "draft_claim":
        raise ValueError("submit_claim needs a draft produced by draft_claim")
    facts = d.get("facts", {}).get("values", {})
    today = date.today()
    deadline = d.get("deadline")
    if not deadline:
        rule = _rows("SELECT docs_within_days FROM claim_rules WHERE policy_id=?", d["policy_id"])
        deadline = (today + timedelta(days=rule[0]["docs_within_days"])).isoformat() if rule and rule[0]["docs_within_days"] else None
    household = set(household_ids(session.user_id))
    customer = d.get("insured_customer_id") if d.get("insured_customer_id") in household else session.user_id
    presented = d.get("claim_amount") if d.get("claim_amount") is not None else d.get("amount")
    presented = int(Decimal(str(presented))) if presented is not None else None
    partner = facts.get("facility_bpjs_partner")
    existing = d.get("claim_id")
    if existing:
        row = _rows("SELECT customer_id, status, policy_id FROM claims WHERE id=?", existing)
        if not row or row[0]["customer_id"] not in household or row[0]["status"] != "draft" or row[0]["policy_id"] != d["policy_id"]:
            raise ValueError("the claim on file is not an open draft of this policy on this account")
        conn().execute("UPDATE claims SET status='submitted', filed_date=?, claim_amount=COALESCE(?, claim_amount), deadline_date=COALESCE(?, deadline_date), created_via='assistant', form_json=? WHERE id=?",
                       (today.isoformat(), presented, deadline, json.dumps(_form_record(d), default=str), existing))
        claim_id = existing
    else:
        claim_id = f"CL-{uuid.uuid4().hex[:8].upper()}"
        conn().execute(
            "INSERT INTO claims(id,policy_id,customer_id,event_type,event_date,admission_date,discharge_date,diagnosis_icd,cause,facility_is_bpjs_partner,is_emergency,"
            "billed_amount,claim_amount,status,filed_date,deadline_date,created_via,form_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (claim_id, d["policy_id"], customer, d.get("event"), d.get("admission") or today.isoformat(), d.get("admission"), d.get("discharge"), d.get("diagnosis"),
             str(facts.get("cause") or "").lower() or None, None if partner is None else int(bool(partner)),
             None if facts.get("is_emergency") is None else int(bool(facts.get("is_emergency"))), facts.get("billed_amount"), presented,
             "submitted", today.isoformat(), deadline, "assistant", json.dumps(_form_record(d), default=str)),
        )
    for h in d.get("document_handles", []):
        # the customer's upload is filed under the claim so the insurer's desk can open it; the handle resolves
        # to a DocRef whose type came from the quarantined extractor (invoice, discharge summary, ...), never the chat
        reg = getattr(session, "registry", None)
        tv = reg.resolve(h) if reg is not None else None
        ref = tv.value if tv is not None and isinstance(tv.value, dict) else (h if isinstance(h, dict) else {"path": str(h)})
        path = Path(str(ref.get("path") or "")).name
        dtype = ref.get("type") or "attachment"
        conn().execute("INSERT INTO documents(id,claim_id,type,file_path,taint_label,uploaded_by,uploaded_at) VALUES (?,?,?,?,?,?,?)",
                       (f"DOC-{uuid.uuid4().hex[:8]}", claim_id, str(dtype).lower(), str(path), "untrusted", session.user_id, datetime.now(timezone.utc).isoformat()))
    conn().commit()
    _mirror("claim", claim_id)
    try:
        session.owned_claim_ids.add(claim_id)
    except AttributeError:
        pass
    return {"claim_id": claim_id, "status": "submitted", "deadline_date": deadline, "created_via": "assistant", "filed_date": today.isoformat()}


def claim_plan(session, claim_facts: Any, **_: Any) -> dict[str, Any]:
    from ..agent.claim_plan import build_plan

    facts = _facts(claim_facts)
    recs = user_records(session.user_id)
    return _dump(build_plan(recs, facts, {r.id: facts for r in recs}, as_of=facts.as_of or date.today()))


def draft_appeal(session, policy_id: str, claim_id: Optional[str] = None, **_: Any) -> dict[str, Any]:
    from ..agent.appeal import case_from_claim_row

    row = _rows("SELECT * FROM claims WHERE id=?", claim_id)[0] if claim_id else None
    return _dump(case_from_claim_row(record_for(policy_id), row, date.today()))


def file_appeal(session, appeal_handle: Any, **_: Any) -> dict[str, Any]:
    a = appeal_handle if isinstance(appeal_handle, dict) else {}
    if a.get("created_by") != "draft_appeal":
        raise ValueError("file_appeal needs an appeal produced by draft_appeal")
    aid = f"APL-{uuid.uuid4().hex[:8].upper()}"
    letter = str(a.get("letter") or "")
    conn().execute("INSERT INTO tickets(id,customer_id,type,status,created_at,payload_hash,requested_via,note,session_id) VALUES (?,?,?,?,?,?,?,?,?)",
                   (aid, session.user_id, "APPEAL", "FILED", datetime.now(timezone.utc).isoformat(), hashlib.sha256(letter.encode()).hexdigest(),
                    "AI ASSISTANT", f"claim={a.get('claim_id') or '-'} policy={a.get('policy_id')} grounds={','.join(a.get('clause_ids') or [])}"[:300],
                    getattr(session, "session_id", None)))
    cid = a.get("claim_id")
    if cid:
        conn().execute("UPDATE claims SET status='appealed' WHERE id=? AND status='rejected'", (cid,))
    conn().commit()
    _mirror("ticket", aid)
    if cid:
        _mirror("claim", cid)
    return {"appeal_id": aid, "claim_id": cid, "policy_id": a.get("policy_id"), "status": "FILED"}


def attach_document(session, claim_id: str, doc_handle: Any, **_: Any) -> dict[str, Any]:
    path = doc_handle["path"] if isinstance(doc_handle, dict) else str(doc_handle)
    doc_id = f"DOC-{uuid.uuid4().hex[:8]}"
    conn().execute("INSERT INTO documents(id,claim_id,type,file_path,taint_label,uploaded_by,uploaded_at) VALUES (?,?,?,?,?,?,?)",
                   (doc_id, claim_id, "attachment", path, "untrusted", session.user_id, datetime.now(timezone.utc).isoformat()))
    conn().commit()
    return {"document_id": doc_id, "claim_id": claim_id}


def schedule_callback(session, slot: Any, **_: Any) -> dict[str, Any]:
    tid = f"TK-{uuid.uuid4().hex[:8].upper()}"
    conn().execute("INSERT INTO tickets(id,customer_id,type,status,created_at,payload_hash,requested_via,note,session_id) VALUES (?,?,?,?,?,?,?,?,?)",
                   (tid, session.user_id, "CALLBACK", "OPEN", datetime.now(timezone.utc).isoformat(), hashlib.sha256(str(slot).encode()).hexdigest(),
                    "AI ASSISTANT", f"slot={slot}", getattr(session, "session_id", None)))
    conn().commit()
    _mirror("ticket", tid)
    return {"ticket_id": tid, "type": "CALLBACK", "slot": str(slot)}


# ------------------------------------------------------------------ T3 (ticket only)
def create_account_change_request(session, form_handle: Any, **_: Any) -> dict[str, Any]:
    """Opens a ticket. The new account/beneficiary value is hashed; a human verifies out-of-band."""
    payload = json.dumps(form_handle, sort_keys=True, default=str)
    tid = f"TK-{uuid.uuid4().hex[:8].upper()}"
    conn().execute("INSERT INTO tickets(id,customer_id,type,status,created_at,payload_hash,requested_via,note,session_id) VALUES (?,?,?,?,?,?,?,?,?)",
                   (tid, session.user_id, "ACCOUNT_CHANGE", "PENDING_OUT_OF_BAND_VERIFICATION", datetime.now(timezone.utc).isoformat(),
                    hashlib.sha256(payload.encode()).hexdigest(), "REQUESTED VIA AI ASSISTANT", "requires OTP / branch verification; no change applied", getattr(session, "session_id", None)))
    conn().commit()
    _mirror("ticket", tid)
    return {"ticket_id": tid, "type": "ACCOUNT_CHANGE", "status": "PENDING_OUT_OF_BAND_VERIFICATION", "note": "No account data was changed. A human verification step is required."}


def t3_tickets_last_24h(user_id: str) -> int:
    since = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    r = conn().execute("SELECT COUNT(*) FROM tickets WHERE customer_id=? AND type='ACCOUNT_CHANGE' AND created_at>=?", (user_id, since)).fetchone()
    return int(r[0])


# ------------------------------------------------------------------ bind to registry
for _name, _fn in {
    "get_my_policies": get_my_policies, "get_policy_clause": get_policy_clause, "get_claim_status": get_claim_status, "get_payment_status": get_payment_status,
    "get_deadline_digest": get_deadline_digest,
    "check_coverage": check_coverage, "gap_analysis": gap_analysis, "claim_readiness": claim_readiness, "cob_plan": cob_plan,
    "draft_claim": draft_claim, "estimate_payout": estimate_payout, "extract_document": extract_document,
    "submit_claim": submit_claim, "attach_document": attach_document, "schedule_callback": schedule_callback,
    "claim_plan": claim_plan, "draft_appeal": draft_appeal, "file_appeal": file_appeal,
    "create_account_change_request": create_account_change_request,
}.items():
    registry.bind(_name, _fn)


def run_tool(name: str, session, bound_args: dict[str, Any]) -> Any:
    """Execute an already-PEP-approved call. `bound_args` is Decision.bound_args."""
    spec = registry.REGISTRY[name]
    if spec.fn is None:
        raise RuntimeError(f"tool {name} has no implementation bound")
    args = {k: v for k, v in bound_args.items() if k != "user_id"}
    return spec.fn(session, **args)
