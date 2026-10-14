"""Agent turns for the multi-payer claim plan, its continuation, appeals and the deadline digest.

Every turn here goes through the same PEP-checked router as the rest of the loop: the plan is the
T1 tool `claim_plan`, decisions are read with the T0 tool `get_claim_status`, each payer's
submission is a T2 `submit_claim` prepared as a pending action with its own draft (and therefore
its own nonce once the user clicks Confirm), an appeal is drafted with the T1 tool `draft_appeal`
and filed with the T2 tool `file_appeal`. Every step is audited (CLAIM_PLAN / APPEAL events).
Replies here are deterministic templates in the user's language; the model never words a plan.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any, Callable, Optional

from .. import portfolio
from ..schema import ClarificationRequest, PolicyRecord, ScenarioFacts, Slot, SourceTier, Verdict
from . import appeal as appeal_mod
from . import claim_plan as cp
from . import digest as digest_mod
from .doclabels import doc_label
from .session import register_value
from .tools import _jsonable, audit

CONTINUE_RE = re.compile(
    r"^\W*(continue|go on|proceed|next|carry on|resume|lanjut\w*|teruskan|selanjutnya)\b"
    r"|\b(continue|resume|lanjutkan|teruskan)\b.{0,20}\b(plan|claims?|klaim|rencana)\b|\bwhat'?s next\b|\bnext step\b"
    r"|\b(any|ada) (news|update|kabar)\b|\bstatus (of )?(my |the )?(plan|claims?)\b|\b(decision|keputusan)\b.{0,20}\b(came|arrived|is in|in|sudah|ada|keluar)\b", re.I)
DECISION_PAID_RE = re.compile(r"\b(paid|approved|settled|reimbursed|transferred|dibayar|disetujui|cair|sudah cair|lunas)\b", re.I)
DECISION_REJECTED_RE = re.compile(r"\b(rejected|denied|declined|refused|ditolak)\b", re.I)
FIRST_PERSON_RE = re.compile(r"\b(i was|i am|i'm|i got|i've been|i went|i had|me\b|saya (baru |sudah |kemarin )?(keluar|dirawat|pulang|opname|kecelakaan|masuk|sakit)|aku)", re.I)
PAYER_WORDS = {
    "social_bpjs_kes": r"\bbpjs\b|\bjkn\b", "group_health": r"\b(group|company|employer|office|kantor|grup)\b", "health_indemnity": r"\b(individual|mandiri|sari'?s plan|individu)\b",
    "hospital_cash": r"\b(hospital cash|santunan harian|rider|hcp)\b", "jasa_raharja": r"\bjasa raharja\b", "pa": r"\b(personal accident|\bpa\b)\b",
    "platform_accident": r"\bplatform\b",
}


@dataclass
class Ctx:
    session: Any
    router: Any
    call: Callable[..., Any]
    finish: Callable[..., Any]
    policies: list[PolicyRecord]
    facts_by_policy: dict[str, ScenarioFacts]
    documents_present: list[str]
    meta: dict
    user_text: str
    lang: str
    eff_dates: dict[str, date]
    focus_types: set
    use_llm: bool = False
    doc_sourced: bool = False
    lead: list[str] = field(default_factory=list)


def _L(ctx_or_lang: Any, en: str, id_: str) -> str:
    lang = ctx_or_lang if isinstance(ctx_or_lang, str) else ctx_or_lang.lang
    return id_ if lang == "id" else en


def _money(v: Optional[Decimal], cur: str = "IDR") -> str:
    return f"{cur} {int(Decimal(v)):,}" if v is not None else "-"


def _audit(ctx: Ctx, event: str, **fields: Any) -> None:
    audit(ctx.session, event, **fields)


def holder_key(meta: dict) -> Optional[str]:
    persons = list((meta.get("persons") or {}).keys())
    return persons[0] if persons else None


def customer_id(person: Optional[str]) -> Optional[str]:
    return f"C-{person.upper()}" if person else None


# --------------------------------------------------------------------------- facts the plan needs
def _plan_policies(ctx: Ctx) -> list[PolicyRecord]:
    person = ctx.session.person_id
    insured = ctx.meta.get("insured", {})
    out = [p for p in ctx.policies if not person or person in insured.get(p.id, [person])]
    if ctx.focus_types:
        focused = [p for p in out if p.product_type in ctx.focus_types]
        if focused:
            return focused
    return out


def _missing_facts(ctx: Ctx) -> tuple[list[tuple[str, str, str]], bool]:
    """([(slot, english, indonesian)], whether a plan can already be built)."""
    s = ctx.session
    f = s.facts
    persons = ctx.meta.get("persons") or {}
    out: list[tuple[str, str, str]] = []
    critical = False
    if not f.has(Slot.EVENT):
        out.append(("event", "what happened (a hospital stay, an accident, a diagnosis)", "apa yang terjadi (rawat inap, kecelakaan, diagnosis)"))
        critical = True
    if len(persons) > 1 and not s.person_id:
        names = ", ".join(v.split()[0] for v in persons.values())
        out.append(("person", f"who was treated ({names})", f"siapa yang dirawat ({names})"))
        critical = True
    if not f.has(Slot.CAUSE):
        out.append((Slot.CAUSE.value, "the cause or diagnosis (an illness, or an accident)", "penyebab atau diagnosis (sakit, atau kecelakaan)"))
        critical = True
    d = ctx.eff_dates
    if not any(k in d for k in ("admission", "accident")):
        known = _L(ctx, f" (discharge {d['discharge'].isoformat()} noted)", f" (tanggal pulang {d['discharge'].isoformat()} sudah dicatat)") if "discharge" in d else ""
        out.append((Slot.DAYS_HOSPITALIZED.value, f"the admission date or how many days the stay lasted{known}", f"tanggal masuk atau berapa hari dirawat{known}"))
        critical = critical or "discharge" not in d
    elif "discharge" not in d and f.has(Slot.EVENT) and f.get(Slot.EVENT) == "HOSPITALIZATION":
        out.append(("discharge", "the discharge date", "tanggal pulang"))
    plan_pols = _plan_policies(ctx) if not critical else ctx.policies
    if not f.has(Slot.FACILITY_BPJS_PARTNER) and any(p.product_type == "social_bpjs_kes" for p in plan_pols):
        out.append((Slot.FACILITY_BPJS_PARTNER.value, "the name of the hospital", "nama rumah sakit"))
    if not f.has(Slot.BILLED_AMOUNT) and any(p.basis.value == "INDEMNITY" or p.product_type in ("group_health", "health_indemnity") for p in plan_pols):
        out.append((Slot.BILLED_AMOUNT.value, "the total bill", "total tagihan"))
    return out, not critical


def _question(ctx: Ctx, missing: list[tuple[str, str, str]], *, building: bool) -> tuple[str, Optional[ClarificationRequest]]:
    items = [(id_ if ctx.lang == "id" else en) for _s, en, id_ in missing]
    if not items:
        return "", None
    lead = (_L(ctx, "To complete the plan I still need: ", "Untuk melengkapi rencana saya masih perlu: ") if building
            else _L(ctx, "I will check every policy on your account and prepare one claim per insurer in the right order. First I need: ",
                    "Saya akan memeriksa semua polis di akun Anda dan menyiapkan satu klaim per penanggung sesuai urutan. Sebelumnya saya perlu: "))
    text = lead + "; ".join(f"({i}) {x}" for i, x in enumerate(items, 1)) + "?"
    slot = next((Slot(sl) for sl, _e, _i in missing if sl in {x.value for x in Slot}), None)
    return text, ClarificationRequest(slot=slot, verdict_by_value={}) if slot is not None else None


# --------------------------------------------------------------------------- plan turns
def plan_facts(ctx: Ctx) -> ScenarioFacts:
    """The scenario with the stay length the dates imply (derived here, never stored as if stated)."""
    f = ctx.session.facts
    d = ctx.eff_dates
    if not f.has(Slot.DAYS_HOSPITALIZED) and "admission" in d and "discharge" in d:
        from .derive import stay_days

        f = f.bind(Slot.DAYS_HOSPITALIZED, stay_days(d["admission"], d["discharge"]))
    return f


def _verdicts(ctx: Ctx, plan: cp.ClaimPlan) -> list:
    by_id = {p.id: p for p in ctx.policies}
    out = []
    for s in plan.steps:
        p = by_id.get(s.policy_id)
        f = ctx.facts_by_policy.get(s.policy_id)
        if p is None or f is None or not f.has(Slot.EVENT):
            continue
        r = portfolio.decide_mapped(p, f)
        if r.verdict in (Verdict.COVERED, Verdict.DENIED, Verdict.CLARIFY):
            out.append(r)
    return out


def _build(ctx: Ctx) -> Optional[cp.ClaimPlan]:
    s = ctx.session
    persons = ctx.meta.get("persons") or {}
    dates = dict(ctx.eff_dates)
    if "admission" not in dates and "accident" in dates:
        dates["admission"] = dates["accident"]
    pols = _plan_policies(ctx)
    f = plan_facts(ctx)
    d, plan = ctx.call("claim_plan", {"claim_facts": _jsonable(f)}, policies=pols, facts=f, facts_by_policy=ctx.facts_by_policy,
                       dates=dates, person_id=s.person_id, person_name=persons.get(s.person_id) if s.person_id else None,
                       facility=getattr(s, "facility_name", None), documents_present=list(ctx.documents_present), diagnosis=s.diagnosis_code)
    if not d.allow:
        return None
    _audit(ctx, "CLAIM_PLAN", kind="CREATED", plan_id=plan.plan_id, steps=[(x.n, x.policy_id, x.role, x.status) for x in plan.steps])
    return plan


def _refresh_plan_inputs(ctx: Ctx, plan: cp.ClaimPlan) -> None:
    plan.documents_present = list(dict.fromkeys(list(plan.documents_present) + list(ctx.documents_present)))
    cp.rebalance(plan, ctx.policies, plan_facts(ctx), ctx.facts_by_policy)


def start_plan(ctx: Ctx, change_note: Optional[str] = None) -> Any:
    s = ctx.session
    if not s.person_id and FIRST_PERSON_RE.search(ctx.user_text):
        s.person_id = holder_key(ctx.meta)
    if not s.person_id and len(ctx.meta.get("persons") or {}) == 1:
        s.person_id = holder_key(ctx.meta)
    missing, buildable = _missing_facts(ctx)
    if not buildable:
        q, clar = _question(ctx, missing, building=False)
        _audit(ctx, "CLAIM_PLAN", kind="INTAKE", missing=[m[0] for m in missing])
        return ctx.finish("\n".join(ctx.lead + [q]), clarification=clar, _no_compose=True)
    old = s.claim_plan
    if old is not None and any(x.status in ("SUBMITTED", "PAID", "APPROVED", "REJECTED", "APPEALED") for x in old.steps) and old.admission == (ctx.eff_dates.get("admission") or ctx.eff_dates.get("accident")):
        _refresh_plan_inputs(ctx, old)
        return progress(ctx, old)
    plan = _build(ctx)
    if plan is None:
        return ctx.finish(_L(ctx, "I cannot build the claim plan in this session (safety limit reached). Nothing was submitted.",
                             "Rencana klaim tidak bisa dibuat di sesi ini (batas keamanan tercapai). Tidak ada yang diajukan."), refused=True, refusal_reason="PLAN_DENIED", _no_compose=True)
    s.claim_plan = plan
    if change_note:
        ctx.lead.append(change_note)
    if ctx.focus_types and len(plan.steps) < len([p for p in ctx.policies if not portfolio.is_statutory(p)]):
        ctx.lead.append(_L(ctx, "You asked about one type of cover, so the plan covers only that policy; say 'all my insurers' to include the others.",
                           "Anda menanyakan satu jenis pertanggungan, jadi rencana ini hanya untuk polis itu; ketik 'semua asuransi' untuk menyertakan yang lain."))
    q, clar = _question(ctx, missing, building=True)
    return progress(ctx, plan, question=q, clarification=clar, full=True)


def _reset_unconfirmed(ctx: Ctx, plan: cp.ClaimPlan) -> None:
    for x in plan.steps:
        if x.status == "AWAITING_CONFIRMATION":
            x.status = "PLANNED"
            x.draft_id = None
    ctx.session.pending_actions = [p for p in ctx.session.pending_actions if not p.get("plan_id")]


def _prepare(ctx: Ctx, plan: cp.ClaimPlan, step: cp.PlanStep) -> tuple[Optional[dict], str]:
    from .loop import _pending

    s = ctx.session
    p = next((x for x in ctx.policies if x.id == step.policy_id), None)
    if p is None:
        return None, "NO_POLICY"
    f = ctx.facts_by_policy.get(p.id, s.facts)
    d, draft = ctx.call("draft_claim", {"policy_id": p.id, "claim_facts": _jsonable(f), "document_handles": list(getattr(s, "doc_uploads", []) or [])}, facts=f, readiness=None, policy=p)
    if not d.allow:
        return None, d.reason
    claim_amount = step.claim_amount if step.claim_amount is not None else step.expected_amount
    draft.update({
        "plan_id": plan.plan_id, "plan_step": step.n, "amount": str(step.expected_amount) if step.expected_amount is not None else None,
        "expected_amount": str(step.expected_amount) if step.expected_amount is not None else None,
        "claim_amount": str(claim_amount) if claim_amount is not None else None, "deadline": step.deadline.isoformat() if step.deadline else None,
        "admission": plan.admission.isoformat() if plan.admission else None, "discharge": plan.discharge.isoformat() if plan.discharge else None,
        "diagnosis": s.diagnosis_code, "insured_customer_id": customer_id(plan.person_id), "claim_id": step.existing_claim_id,
        "missing_documents": [doc_label(x, ctx.lang) for x in step.documents_missing],
    })
    from . import claim_form

    claim_form.attach(draft, policy=p, session=s, meta=ctx.meta, documents_present=ctx.documents_present, lang=ctx.lang, use_llm=ctx.use_llm)
    label = SourceTier.USER_UPLOAD if ctx.doc_sourced else SourceTier.TOOL
    handle = register_value(s, draft, "ClaimDraft", label, draft["draft_id"])
    step.status, step.draft_id = "AWAITING_CONFIRMATION", draft["draft_id"]
    total = len(plan.claimable)
    missing_text = ", ".join(doc_label(x, ctx.lang) for x in step.documents_missing) or _L(ctx, "none", "tidak ada")
    summary = _L(ctx,
                 f"Plan {plan.plan_id}, step {step.n} of {total}: submit to {step.product_name} ({step.policy_id}) only - claim {_money(claim_amount, plan.currency)}, "
                 f"expected {_money(step.expected_amount, plan.currency)}, deadline {step.deadline.isoformat() if step.deadline else 'not stated'}, "
                 f"missing documents: {missing_text}",
                 f"Rencana {plan.plan_id}, langkah {step.n} dari {total}: ajukan ke {step.product_name} ({step.policy_id}) saja - klaim {_money(claim_amount, plan.currency)}, "
                 f"perkiraan {_money(step.expected_amount, plan.currency)}, batas waktu {step.deadline.isoformat() if step.deadline else 'tidak disebutkan'}, "
                 f"dokumen yang kurang: {missing_text}")
    extra = {"plan_id": plan.plan_id, "plan_step": step.n, "policy_id": step.policy_id, "draft_id": draft["draft_id"], "draft_label": label.value}
    if step.documents_missing:
        extra.update({"incomplete": True, "requires_acknowledgement": True, "missing_documents": [doc_label(x, ctx.lang) for x in step.documents_missing]})
    pending = _pending(s, "submit_claim", {"draft_handle": handle}, summary, **extra)
    _audit(ctx, "CLAIM_PLAN", kind="STEP_READY", plan_id=plan.plan_id, step=step.n, policy_id=step.policy_id, claim_amount=str(claim_amount), draft_id=draft["draft_id"])
    return pending, "OK"


def progress(ctx: Ctx, plan: cp.ClaimPlan, *, question: str = "", clarification: Optional[ClarificationRequest] = None, full: bool = False) -> Any:
    s = ctx.session
    _reset_unconfirmed(ctx, plan)
    cp.rebalance(plan, ctx.policies, plan_facts(ctx), ctx.facts_by_policy)
    upcoming = cp.next_step(plan)
    lines = list(ctx.lead) + cp.render(plan, ctx.lang, detail=None if full else ({upcoming.n} if upcoming else set()))
    pending: list[dict] = []
    nxt = cp.next_step(plan)
    blocker = cp.blocking_question(plan)
    waiting = [x for x in plan.steps if x.status == "SUBMITTED"]
    late_skipped: list[cp.PlanStep] = []
    while nxt is not None and cp.is_late(nxt, plan.as_of) and nxt.late_effect in (None, "REJECT"):
        late_skipped.append(nxt)
        nxt.status = "SKIPPED"
        nxt = cp.next_step(plan)
    for x in late_skipped:
        lines.append(_L(ctx, f"Step {x.n} ({x.policy_id}) is not prepared: its filing deadline {x.deadline.isoformat()} has passed and this wording rejects late claims [{x.deadline_clause}].",
                        f"Langkah {x.n} ({x.policy_id}) tidak disiapkan: batas pengajuan {x.deadline.isoformat()} sudah lewat dan ketentuan ini menolak klaim terlambat [{x.deadline_clause}]."))
    if nxt is not None and nxt.indemnity and plan.bill_total is None:
        lines.append(_L(ctx, f"Next is step {nxt.n} ({nxt.product_name}, {nxt.policy_id}), but its claim amount depends on the bill: tell me the total bill and I will prepare it.",
                        f"Berikutnya langkah {nxt.n} ({nxt.product_name}, {nxt.policy_id}), tetapi jumlah klaimnya bergantung pada tagihan: sebutkan total tagihan dan saya siapkan."))
        nxt = None
    elif nxt is not None and nxt.documents_missing and nxt.n not in plan.incomplete_ok:
        miss = "; ".join(doc_label(x, ctx.lang) for x in nxt.documents_missing)
        lines.append(_L(ctx, f"Next is step {nxt.n} ({nxt.product_name}, {nxt.policy_id}). I have not prepared it because these documents are still missing: {miss}. "
                             "Tell me when you have them (or attach them), or say 'submit anyway' to file it incomplete with a separate acknowledgement. Nothing has been sent.",
                        f"Berikutnya langkah {nxt.n} ({nxt.product_name}, {nxt.policy_id}). Belum saya siapkan karena dokumen ini masih kurang: {miss}. "
                        "Beri tahu saya jika sudah lengkap (atau lampirkan), atau ketik 'ajukan saja' untuk mengajukan meski belum lengkap dengan persetujuan terpisah. Belum ada yang terkirim."))
        nxt = None
    if nxt is not None:
        pa, reason = _prepare(ctx, plan, nxt)
        if pa is None:
            lines.append(_L(ctx, f"I could not prepare step {nxt.n} in this session ({reason}). Nothing was sent.", f"Langkah {nxt.n} tidak bisa disiapkan di sesi ini ({reason}). Tidak ada yang terkirim."))
        else:
            pending = [pa]
            lines.append(_L(ctx, f"Next: step {nxt.n}, {nxt.product_name} ({nxt.policy_id}). The submission is prepared but NOT sent. Press Confirm for this payer only: each insurer gets its "
                                 "own submission with its own one-time confirmation, one confirmation never covers more than one insurer, and typing 'confirm' in chat is not enough.",
                            f"Berikutnya: langkah {nxt.n}, {nxt.product_name} ({nxt.policy_id}). Pengajuannya sudah disiapkan tetapi BELUM dikirim. Tekan Konfirmasi untuk penanggung ini saja: "
                            "setiap penanggung punya pengajuan dan konfirmasi sekali pakai sendiri, satu konfirmasi tidak pernah berlaku untuk lebih dari satu penanggung, dan mengetik 'konfirmasi' di chat tidak cukup."))
    elif waiting:
        names = ", ".join(f"step {x.n} {x.policy_id} ({x.claim_id})" for x in waiting)
        names_id = ", ".join(f"langkah {x.n} {x.policy_id} ({x.claim_id})" for x in waiting)
        lines.append(_L(ctx, f"Waiting for the insurer's decision on {names}. Say 'continue' when it arrives and I will check it and carry the unpaid balance to the next payer.",
                        f"Menunggu keputusan penanggung untuk {names_id}. Ketik 'lanjutkan' jika keputusannya sudah ada; saya cek dan sisa tagihan saya teruskan ke penanggung berikutnya."))
    elif blocker is not None and not question:
        slot = (blocker.uncertain_slots or ["fact"])[0]
        c = ClarificationRequest(slot=Slot(slot), verdict_by_value={}) if slot in {x.value for x in Slot} else None
        from .clarifier import SLOT_QUESTIONS

        q = SLOT_QUESTIONS.get(Slot(slot)) if c else None
        lines.append(_L(ctx, f"Before the later payers can be prepared, step {blocker.n} ({blocker.policy_id}) needs one fact: ", f"Sebelum penanggung berikutnya disiapkan, langkah {blocker.n} ({blocker.policy_id}) perlu satu fakta: ")
                     + (q or slot.replace("_", " ")))
        clarification = clarification or c
    elif not any(x.status in cp.OPEN or x.status == "UNCERTAIN" for x in plan.steps):
        ind, fixed, oop = cp.totals(plan)
        appealed = [x for x in plan.steps if x.status == "APPEALED"]
        if appealed:
            lines.append(_L(ctx, "Appeal pending: " + ", ".join(f"step {x.n} {x.policy_id} (claim {x.claim_id})" for x in appealed) + "; its amount is not counted below until the insurer answers.",
                            "Banding masih diproses: " + ", ".join(f"langkah {x.n} {x.policy_id} (klaim {x.claim_id})" for x in appealed) + "; jumlahnya belum dihitung di bawah sampai penanggung menjawab."))
        lines.append(_L(ctx, f"Every payer in the plan has been filed or settled. Recovered or expected: {_money(ind, plan.currency)} towards the bill plus {_money(fixed, plan.currency)} in fixed benefits"
                             + (f"; out of pocket {_money(oop, plan.currency)}." if oop is not None else "."),
                        f"Semua penanggung dalam rencana sudah diajukan atau diselesaikan. Diterima atau diperkirakan: {_money(ind, plan.currency)} untuk tagihan ditambah santunan tetap {_money(fixed, plan.currency)}"
                        + (f"; biaya sendiri {_money(oop, plan.currency)}." if oop is not None else ".")))
    if question:
        lines.append(question)
    lines.append(_L(ctx, "Indicative only, based on the wording in your documents; each insurer makes its own claim decision and the policy wording prevails.",
                    "Bersifat indikatif, berdasarkan ketentuan di dokumen Anda; setiap penanggung memutuskan klaimnya sendiri dan ketentuan polis yang berlaku."))
    nxt_due = min((x.deadline for x in plan.steps if x.deadline and x.status in cp.OPEN), default=None)
    return ctx.finish("\n".join(lines), actions_pending=pending, cob=cp.as_payer_steps(plan), verdicts=_verdicts(ctx, plan), clarification=clarification,
                      deadline=nxt_due, _no_compose=True)


def after_submission(ctx: Ctx, pa: dict, res: dict) -> Any:
    s = ctx.session
    plan = s.claim_plan
    step = plan.step(int(pa.get("plan_step"))) if plan is not None else None
    if step is None:
        return None
    filed = date.fromisoformat(res["submitted_on"]) if res.get("submitted_on") else s.as_of
    cp.record_submission(plan, step.n, res.get("id"), filed)
    _audit(ctx, "CLAIM_PLAN", kind="SUBMITTED", plan_id=plan.plan_id, step=step.n, policy_id=step.policy_id, claim_id=res.get("id"))
    ctx.lead.append(_L(ctx, f"Step {step.n} submitted: your claim to {step.product_name} ({step.policy_id}) is filed in the sandbox insurer system as {res.get('id')} "
                            f"for {_money(step.claim_amount if step.claim_amount is not None else step.expected_amount, plan.currency)} (no real insurer received it).",
                       f"Langkah {step.n} terkirim: klaim ke {step.product_name} ({step.policy_id}) tercatat di sistem penanggung sandbox sebagai {res.get('id')} "
                       f"sebesar {_money(step.claim_amount if step.claim_amount is not None else step.expected_amount, plan.currency)} (tidak dikirim ke penanggung sungguhan)."))
    return progress(ctx, plan)


# --------------------------------------------------------------------------- continuation
def _payer_mentioned(plan: cp.ClaimPlan, policies: dict[str, PolicyRecord], text: str) -> Optional[cp.PlanStep]:
    for x in plan.steps:
        if x.policy_id.lower() in text.lower():
            return x
    for x in plan.steps:
        p = policies.get(x.policy_id)
        pat = PAYER_WORDS.get(p.product_type) if p else None
        if pat and re.search(pat, text, flags=re.I):
            return x
    return None


def _user_reported(ctx: Ctx, plan: cp.ClaimPlan) -> list[str]:
    from .facts_fallback import _money as parse_money

    text = ctx.user_text
    paid = DECISION_PAID_RE.search(text)
    rejected = DECISION_REJECTED_RE.search(text)
    if not paid and not rejected:
        return []
    waiting = [x for x in plan.steps if x.status == "SUBMITTED"]
    target = _payer_mentioned(plan, {p.id: p for p in ctx.policies}, text)
    if target is None or target.status != "SUBMITTED":
        target = waiting[0] if len(waiting) == 1 else None
    if target is None:
        return []
    if rejected and not paid:
        code = appeal_mod.reason_from_text(text) or "NOT_SPECIFIED"
        cp.record_decision(plan, target.n, "REJECTED", Decimal(0), code, "USER_REPORTED")
    else:
        amount = parse_money(text)
        if amount is None:
            return [_L(ctx, f"How much did {target.product_name} ({target.policy_id}) pay? I need the amount on its settlement letter to work out the balance for the next payer.",
                        f"Berapa yang dibayar {target.product_name} ({target.policy_id})? Saya perlu jumlah di surat penyelesaiannya untuk menghitung sisa bagi penanggung berikutnya.")]
        cp.record_decision(plan, target.n, "PAID", Decimal(amount), None, "USER_REPORTED")
    _audit(ctx, "CLAIM_PLAN", kind="DECISION", plan_id=plan.plan_id, step=target.n, status=target.status, paid=str(target.paid_amount), source="USER_REPORTED")
    return []


def _fetch_decisions(ctx: Ctx, plan: cp.ClaimPlan) -> list[cp.PlanStep]:
    changed = []
    for x in [y for y in plan.steps if y.status == "SUBMITTED" and y.claim_id]:
        d, rows = ctx.call("get_claim_status", {"claim_id": x.claim_id})
        row = next((r for r in (rows or []) if r.get("id") == x.claim_id), None) if d.allow else None
        if row is None:
            continue
        st = str(row.get("status") or "").lower()
        payers = " ".join(str(pm.get("payer") or "") for pm in row.get("payments") or [])
        source = "SANDBOX_SIMULATED" if "SANDBOX_SIMULATED" in payers else "SANDBOX_INSURER"
        if st in ("approved", "paid"):
            cp.record_decision(plan, x.n, "PAID" if st == "paid" else "APPROVED", Decimal(str(row.get("paid") or 0)), None, source)
        elif st == "rejected":
            cp.record_decision(plan, x.n, "REJECTED", Decimal(0), row.get("rejection_code"), source)
        elif st == "appealed":
            x.status = "APPEALED"
        else:
            continue
        changed.append(x)
        _audit(ctx, "CLAIM_PLAN", kind="DECISION", plan_id=plan.plan_id, step=x.n, policy_id=x.policy_id, status=x.status, paid=str(x.paid_amount), source=x.decision_source)
    return changed


def continue_plan(ctx: Ctx) -> Any:
    s = ctx.session
    plan: cp.ClaimPlan = s.claim_plan
    before = {x.n: x.status for x in plan.steps}
    changed = _fetch_decisions(ctx, plan)
    ask = _user_reported(ctx, plan)
    if ask:
        return ctx.finish("\n".join(ask), _no_compose=True)
    changed = changed or [x for x in plan.steps if before.get(x.n) != x.status]
    _refresh_plan_inputs(ctx, plan)
    for x in changed:
        src = (cp.SOURCE_ID if ctx.lang == "id" else cp.SOURCE_EN).get(x.decision_source or "", "")
        if x.status in cp.SETTLED:
            ctx.lead.append(_L(ctx, f"Decision received: step {x.n}, {x.product_name} ({x.policy_id}) paid {_money(x.paid_amount, plan.currency)} on claim {x.claim_id} ({src}).",
                               f"Keputusan diterima: langkah {x.n}, {x.product_name} ({x.policy_id}) membayar {_money(x.paid_amount, plan.currency)} untuk klaim {x.claim_id} ({src})."))
        elif x.status == "REJECTED":
            ctx.lead.append(_L(ctx, f"Decision received: step {x.n}, {x.product_name} ({x.policy_id}) REJECTED claim {x.claim_id} ({cp.code_text(x.rejection_code, ctx.lang)}; {src}).",
                               f"Keputusan diterima: langkah {x.n}, {x.product_name} ({x.policy_id}) MENOLAK klaim {x.claim_id} ({cp.code_text(x.rejection_code, ctx.lang)}; {src})."))
    settled_now = [x for x in changed if x.indemnity and x.status in cp.SETTLED | {"REJECTED"}]
    if settled_now and plan.bill_total is not None:
        paid = sum((Decimal(y.paid_amount or 0) for y in plan.steps if y.indemnity and y.status in cp.SETTLED), Decimal(0))
        balance = max(Decimal(0), Decimal(plan.bill_total) - paid)
        nxt = next((y for y in sorted(plan.steps, key=lambda z: z.n) if y.indemnity and y.status in cp.OPEN and y.n > settled_now[-1].n), None)
        if balance > 0 and nxt is not None:
            ctx.lead.append(_L(ctx, f"Explanation of benefits: {_money(paid, plan.currency)} of the {_money(plan.bill_total, plan.currency)} bill is paid; the unpaid {_money(balance, plan.currency)} goes to step {nxt.n}, {nxt.product_name} ({nxt.policy_id}).",
                               f"Rincian manfaat: {_money(paid, plan.currency)} dari tagihan {_money(plan.bill_total, plan.currency)} sudah dibayar; sisa {_money(balance, plan.currency)} diteruskan ke langkah {nxt.n}, {nxt.product_name} ({nxt.policy_id})."))
        elif balance <= 0:
            ctx.lead.append(_L(ctx, "The bill is fully paid by the earlier payers: there is nothing left to claim from the later indemnity insurers.",
                               "Tagihan sudah lunas dibayar penanggung sebelumnya: tidak ada sisa yang perlu diklaim ke penanggung indemnitas berikutnya."))
    rejected = next((x for x in changed if x.status == "REJECTED"), None)
    if rejected is not None:
        return appeal_for_step(ctx, plan, rejected)
    still = [x for x in plan.steps if x.status == "SUBMITTED"]
    if not changed and still:
        ctx.lead.append(_L(ctx, "No decision yet on " + ", ".join(f"step {x.n} ({x.policy_id}, claim {x.claim_id})" for x in still) + ".",
                           "Belum ada keputusan untuk " + ", ".join(f"langkah {x.n} ({x.policy_id}, klaim {x.claim_id})" for x in still) + "."))
    return progress(ctx, plan)


# --------------------------------------------------------------------------- appeals
def _draft_case(ctx: Ctx, policy: PolicyRecord, build: Callable[[], appeal_mod.AppealCase]) -> Optional[appeal_mod.AppealCase]:
    d, case = ctx.call("draft_appeal", {"policy_id": policy.id}, build=build)
    if not d.allow:
        return None
    return case


def _appeal_reply(ctx: Ctx, case: appeal_mod.AppealCase, plan: Optional[cp.ClaimPlan] = None) -> Any:
    from .loop import _pending

    s = ctx.session
    lines = list(ctx.lead) + appeal_mod.summary_lines(case, ctx.lang)
    _audit(ctx, "APPEAL", kind="ANALYSED", case_id=case.case_id, policy_id=case.policy_id, claim_id=case.claim_id, outcome=case.outcome, code=case.rejection_code)
    pending: list[dict] = []
    if case.outcome == "NEEDS_FACTS":
        need = ", ".join(x.replace("_", " ") for x in case.needs) or _L(ctx, "the event date", "tanggal kejadian")
        lines.append(_L(ctx, f"To check the rejection I need: {need}.", f"Untuk memeriksa penolakan ini saya perlu: {need}."))
        slot = next((Slot(x) for x in case.needs if x in {y.value for y in Slot}), None)
        return ctx.finish("\n".join(lines), clarification=ClarificationRequest(slot=slot, verdict_by_value={}) if slot else None, _no_compose=True)
    if case.outcome == "NO_LEGITIMATE_FIX":
        lines += appeal_mod.no_fix_lines(case, ctx.lang)
        s.appeal_case = None
        if plan is not None:
            ctx.lead = lines + [_L(ctx, "The plan continues with the other payers.", "Rencana dilanjutkan dengan penanggung lainnya.")]
            return progress(ctx, plan)
        return ctx.finish("\n".join(lines), _no_compose=True, denial_codes={case.policy_id: case.rejection_code})
    claimant = (ctx.meta.get("name") or "").strip() or _L(ctx, "The policyholder", "Pemegang polis")
    letter, worded, violations = appeal_mod.compose_letter(case, ctx.lang, claimant, use_llm=ctx.use_llm)
    if violations:
        _audit(ctx, "COMPOSER_REJECTED", violations=violations[:10], scope="appeal_letter")
    appeal_value = {"created_by": "draft_appeal", "case_id": case.case_id, "policy_id": case.policy_id, "claim_id": case.claim_id, "letter": letter,
                    "clause_ids": [g.clause_id for g in case.grounds if g.clause_id], "outcome": case.outcome, "recorded_facts": case.recorded_facts,
                    "plan_id": plan.plan_id if plan is not None else None}
    handle = register_value(s, appeal_value, "AppealDraft", SourceTier.TOOL, case.case_id)
    s.appeal_case = case
    summary = (f"File the appeal for claim {case.claim_id or '(no sandbox claim id)'} with {case.insurer or case.policy_id} ({case.policy_id}); "
               f"grounds: {', '.join(g.code for g in case.grounds)}; letter shown in chat")
    pending = [_pending(s, "file_appeal", {"appeal_handle": handle}, summary, case_id=case.case_id, policy_id=case.policy_id, claim_id=case.claim_id)]
    lines.append(_L(ctx, "A legitimate appeal is possible. Draft letter (the facts are exactly those on record; nothing about what happened is changed):",
                    "Banding yang sah bisa diajukan. Draf surat (faktanya persis seperti yang tercatat; tidak ada fakta kejadian yang diubah):"))
    lines += ["---", letter, "---"]
    lines.append(_L(ctx, "Filing the appeal is a tier-2 action: press Confirm to file it with the insurer (sandbox). Nothing has been sent yet.",
                    "Pengajuan banding adalah tindakan tingkat 2: tekan Konfirmasi untuk mengajukannya ke penanggung (sandbox). Belum ada yang terkirim."))
    lines.append(appeal_mod.COMPLAINT_ROUTE_ID if ctx.lang == "id" else appeal_mod.COMPLAINT_ROUTE_EN)
    _audit(ctx, "APPEAL", kind="DRAFTED", case_id=case.case_id, worded_by_model=worded)
    return ctx.finish("\n".join(lines), actions_pending=pending, denial_codes={case.policy_id: case.rejection_code}, _no_compose=True)


def appeal_for_step(ctx: Ctx, plan: cp.ClaimPlan, step: cp.PlanStep) -> Any:
    policy = next(p for p in ctx.policies if p.id == step.policy_id)
    dates = {k: v for k, v in (("admission", plan.admission), ("discharge", plan.discharge), ("treatment_end", plan.discharge)) if v}
    for k in ("accident", "event"):
        if k in ctx.eff_dates:
            dates[k] = ctx.eff_dates[k]
    f = ctx.facts_by_policy.get(policy.id, ctx.session.facts)

    def build() -> appeal_mod.AppealCase:
        return appeal_mod.analyse(policy, f, as_of=ctx.session.as_of, rejection_code=step.rejection_code, rejection_source=step.decision_source or "SANDBOX_INSURER",
                                  claim_id=step.claim_id, filed_on=step.filed_on, dates=dates, others=ctx.policies, facts_by_policy=ctx.facts_by_policy,
                                  documents_present=plan.documents_present, claimed_amount=step.claim_amount)

    case = _draft_case(ctx, policy, build)
    if case is None:
        return progress(ctx, plan)
    return _appeal_reply(ctx, case, plan)


def _claim_dates(row: dict) -> dict[str, date]:
    out = {}
    for k, col in (("admission", "admission_date"), ("discharge", "discharge_date"), ("accident", "accident"), ("admission", "admission"), ("discharge", "discharge")):
        v = row.get(col)
        if v and k not in out:
            out[k] = date.fromisoformat(str(v))
    if "discharge" in out:
        out["treatment_end"] = out["discharge"]
    return out


def appeal_turn(ctx: Ctx) -> Any:
    """The user reports (or asks about) a rejected claim."""
    from .facts_fallback import derive_for_policy

    s = ctx.session
    plan = s.claim_plan
    if plan is not None:
        rej = next((x for x in plan.steps if x.status == "REJECTED"), None)
        if rej is not None:
            return appeal_for_step(ctx, plan, rej)
    by_id = {p.id: p for p in ctx.policies}
    claims = ctx.router._sandbox_claims(s)
    rejected = [c for c in claims if str(c.get("status")) == "rejected" and c.get("policy_id") in by_id]
    if ctx.focus_types:
        rejected = [c for c in rejected if by_id[c["policy_id"]].product_type in ctx.focus_types] or []
    code = appeal_mod.reason_from_text(ctx.user_text)
    if rejected:
        row = rejected[-1]
        policy = by_id[row["policy_id"]]
        dates = _claim_dates(row)
        facts = ctx.facts_by_policy.get(policy.id, s.facts)
        if not facts.has(Slot.EVENT):
            from ..sandbox.insurer_sim import _facts as claim_facts

            base, dates = claim_facts(row, Decimal(row.get("claim_amount") or 0))
            facts = derive_for_policy(base, policy, dates=dates, as_of=s.as_of)
        filed = date.fromisoformat(row["filed_date"]) if row.get("filed_date") else None

        def build() -> appeal_mod.AppealCase:
            return appeal_mod.analyse(policy, facts, as_of=s.as_of, rejection_code=row.get("rejection_code") or code, rejection_source="SANDBOX_INSURER",
                                      claim_id=row["id"], filed_on=filed, dates=dates, others=ctx.policies, facts_by_policy=ctx.facts_by_policy,
                                      documents_present=ctx.documents_present, claimed_amount=Decimal(row["claim_amount"]) if row.get("claim_amount") else None)
    else:
        policy = next((p for p in ctx.policies if p.product_type in ctx.focus_types), None) if ctx.focus_types else None
        if policy is None:
            covered = [p for p in ctx.policies if not portfolio.is_statutory(p)]
            if len(covered) == 1:
                policy = covered[0]
        if policy is None:
            names = "; ".join(f"{p.product_name} ({p.id})" for p in ctx.policies if not portfolio.is_statutory(p))
            return ctx.finish(_L(ctx, f"Which policy rejected the claim, and for what reason? Your policies: {names}.",
                                 f"Polis mana yang menolak klaim, dan apa alasannya? Polis Anda: {names}."), _no_compose=True)
        dates = {k: v for k, v in ctx.eff_dates.items() if not (k == "event" and v == s.as_of)}
        source = "record"
        facts = ctx.facts_by_policy.get(policy.id, s.facts)
        if not dates:
            on_file = next((c for c in ctx.meta.get("claims", []) if (not s.person_id or c.get("person") in (None, s.person_id))), None)
            if on_file is not None:
                dates = _claim_dates(on_file)
                source = "on_file"
                values = {Slot.EVENT: on_file.get("event", "HOSPITALIZATION")}
                if on_file.get("cause"):
                    values[Slot.CAUSE] = on_file["cause"]
                    values[Slot.IS_ACCIDENT] = str(on_file["cause"]).startswith("ACCIDENT")
                for k, v in s.facts.values.items():
                    values.setdefault(k, v)
                base = ScenarioFacts(values=values, as_of=s.as_of)
                facts = derive_for_policy(base, policy, dates=dates, as_of=s.as_of, payment=ctx.meta.get("payments", {}).get(policy.id))
                fbp = {p.id: derive_for_policy(base, p, dates=dates, as_of=s.as_of, payment=ctx.meta.get("payments", {}).get(p.id)) for p in ctx.policies}
                ctx.facts_by_policy = {**ctx.facts_by_policy, **fbp}

        def build() -> appeal_mod.AppealCase:
            return appeal_mod.analyse(policy, facts, as_of=s.as_of, rejection_code=code, rejection_source="USER_REPORTED", claim_id=None, filed_on=None,
                                      dates=dates, others=ctx.policies, facts_by_policy=ctx.facts_by_policy, documents_present=ctx.documents_present,
                                      dates_source=source)
    case = _draft_case(ctx, policy, build)
    if case is None:
        return ctx.finish(_L(ctx, "I cannot analyse the rejection in this session (safety limit reached).", "Penolakan ini tidak bisa dianalisis di sesi ini (batas keamanan tercapai)."),
                          refused=True, refusal_reason="APPEAL_DENIED", _no_compose=True)
    return _appeal_reply(ctx, case)


def appeal_filed(ctx: Ctx, pa: dict, res: dict) -> Any:
    s = ctx.session
    case = s.appeal_case
    _audit(ctx, "APPEAL", kind="FILED", appeal_id=res.get("appeal_id"), claim_id=res.get("claim_id"), policy_id=res.get("policy_id"))
    s.appeal_case = None
    ctx.lead.append(_L(ctx, f"Appeal filed: {res.get('appeal_id')} for claim {res.get('claim_id') or '-'} with {case.insurer if case else res.get('policy_id')} (sandbox; no real insurer received it). "
                            "The insurer reviews it and answers in writing; if you disagree with that answer, the complaint route above applies.",
                       f"Banding diajukan: {res.get('appeal_id')} untuk klaim {res.get('claim_id') or '-'} ke {case.insurer if case else res.get('policy_id')} (sandbox; tidak dikirim ke penanggung sungguhan). "
                       "Penanggung meninjau dan menjawab tertulis; jika Anda tidak setuju dengan jawabannya, jalur pengaduan di atas berlaku."))
    plan = s.claim_plan
    if plan is not None:
        step = next((x for x in plan.steps if x.claim_id and x.claim_id == res.get("claim_id")), None)
        if step is not None:
            step.status = "APPEALED"
        return progress(ctx, plan)
    return ctx.finish("\n".join(ctx.lead), _no_compose=True)


# --------------------------------------------------------------------------- digest
def digest_turn(ctx: Ctx) -> Any:
    s = ctx.session
    extra = []
    plan = s.claim_plan
    if plan is not None:
        from ..timeline import OpenClaim

        for x in plan.steps:
            if x.status in cp.OPEN and x.deadline is not None:
                extra.append(OpenClaim(claim_id=x.existing_claim_id or f"{plan.plan_id}-{x.n}", policy_id=x.policy_id, event=plan.event,
                                       amount=x.expected_amount, event_date=plan.admission, discharge_date=plan.discharge))
    d, items = ctx.call("get_deadline_digest", {}, extra_claims=extra)
    if not d.allow:
        return ctx.finish(_L(ctx, "I cannot read your deadlines in this session.", "Tenggat Anda tidak bisa dibaca di sesi ini."), refused=True, refusal_reason=d.reason, _no_compose=True)
    items = items or []
    seen: set = set()
    unique = []
    for it in items:
        key = (it.policy_id, it.kind, it.date)
        if key not in seen:
            seen.add(key)
            unique.append(it)
    _audit(ctx, "DIGEST", items=len(unique), kinds=sorted({i.kind for i in unique}))
    lines = digest_mod.render(unique, ctx.lang)
    alerts = [f"{i.policy_id}:{i.kind}:{i.date.isoformat()}" for i in unique]
    first_deadline = next((i.date for i in unique if i.kind == "FILING_DEADLINE" and i.days_left >= 0), None)
    return ctx.finish("\n".join(lines), alerts=alerts, deadline=first_deadline, _no_compose=True)
