"""Multi-payer claim plan for one hospital stay or accident.

Every policy is evaluated by the solver; the claiming order and the amounts come from the
allocation optimizer (statutory schemes first, then indemnity policies by layer with group
before individual, fixed benefits in parallel). Each payer gets its own package: the documents
of its REQUIRES_DOCUMENT tuples (present / missing), the amount to claim, the expected benefit
and the filing deadline of its filing-deadline tuple (derive.filing_deadline).

The plan is typed state on the session, so "continue" / "lanjutkan" resumes it. Submissions are
one per payer, each a separate tier-2 action with its own server nonce (security.pep.plan_binding).
Once a payer has decided, the next indemnity payer is presented only what is still unpaid
(explanation of benefits) and the expected amounts of the payers after it are recomputed on that
balance. Deterministic; no language model runs here.
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Any, Optional

from pydantic import Field

from .. import portfolio
from ..allocation import SILENT_CODES, BillBreakdown, optimize_allocation
from ..schema import Basis, PolicyRecord, ScenarioFacts, Slot, Strict
from .doclabels import doc_label

INDEMNITY_ROLES = {"STATUTORY", "PRIMARY", "PRO_RATA", "EXCESS"}
DECIDED = {"APPROVED", "PAID", "REJECTED", "SKIPPED", "APPEALED"}
SETTLED = {"APPROVED", "PAID"}
OPEN = {"PLANNED", "AWAITING_CONFIRMATION"}
SETTLEMENT_DOCS = {"COB_LETTER", "COB_LETTER_FIRST_INSURER"}
FACILITY_HELD_DOCS = {"BPJS_CARD_OR_JKN_APP", "ID_COPY", "REFERRAL_LETTER_OR_ER_NOTE", "SEP"}
STATUS_PATTERN = r"^(PLANNED|AWAITING_CONFIRMATION|SUBMITTED|APPROVED|PAID|REJECTED|APPEALED|SKIPPED|NOT_CLAIMABLE|UNCERTAIN)$"
ZERO = Decimal(0)


class PlanStep(Strict):
    n: int
    policy_id: str
    product_name: str
    insurer: str = ""
    role: str = Field(pattern=r"^(STATUTORY|PRIMARY|PRO_RATA|EXCESS|FIXED_BENEFIT|UNCERTAIN|NOT_CLAIMABLE)$")
    basis: str
    status: str = Field(default="PLANNED", pattern=STATUS_PATTERN)
    expected_amount: Optional[Decimal] = None
    claim_amount: Optional[Decimal] = None
    documents_required: list[str] = Field(default_factory=list)
    documents_missing: list[str] = Field(default_factory=list)
    deadline: Optional[date] = None
    late_effect: Optional[str] = None
    deadline_clause: Optional[str] = None
    clause_ids: list[str] = Field(default_factory=list)
    after: list[int] = Field(default_factory=list)
    denial_code: Optional[str] = None
    uncertain_slots: list[str] = Field(default_factory=list)
    estimate_basis: Optional[str] = None
    facility_billed: bool = False
    late: bool = False
    claim_id: Optional[str] = None
    existing_claim_id: Optional[str] = None
    draft_id: Optional[str] = None
    paid_amount: Optional[Decimal] = None
    rejection_code: Optional[str] = None
    decision_source: Optional[str] = None
    filed_on: Optional[date] = None

    @property
    def indemnity(self) -> bool:
        return self.role in INDEMNITY_ROLES or (self.role == "UNCERTAIN" and self.basis == Basis.INDEMNITY.value)


class ClaimPlan(Strict):
    plan_id: str
    person_id: Optional[str] = None
    person_name: Optional[str] = None
    event: str
    admission: Optional[date] = None
    discharge: Optional[date] = None
    facility: Optional[str] = None
    bill_total: Optional[Decimal] = None
    currency: str = "IDR"
    as_of: date
    steps: list[PlanStep] = Field(default_factory=list)
    policies_checked: int = 0
    documents_present: list[str] = Field(default_factory=list)
    incomplete_ok: list[int] = Field(default_factory=list)

    def step(self, n: int) -> Optional[PlanStep]:
        return next((s for s in self.steps if s.n == n), None)

    def by_policy(self, policy_id: str) -> Optional[PlanStep]:
        return next((s for s in self.steps if s.policy_id == policy_id), None)

    @property
    def claimable(self) -> list[PlanStep]:
        return [s for s in self.steps if s.role != "NOT_CLAIMABLE"]


# --------------------------------------------------------------------------- build
def _single_payout(policy: PolicyRecord, facts: ScenarioFacts, facts_by_policy: dict[str, ScenarioFacts], amount: Decimal, as_of: date) -> Decimal:
    """What one indemnity policy pays when `amount` is presented to it alone."""
    if amount <= 0:
        return ZERO
    f = facts.bind(Slot.BILLED_AMOUNT, int(amount))
    res = optimize_allocation([policy], f, BillBreakdown(total=amount, currency=policy.currency), rule_pack="ID", as_of=as_of,
                              facts_by_policy={policy.id: facts_by_policy.get(policy.id, facts).bind(Slot.BILLED_AMOUNT, int(amount))})
    step = next((s for s in res.steps if s.policy_id == policy.id), None)
    return Decimal(step.amount) if step is not None and step.amount is not None else ZERO


def build_plan(policies: list[PolicyRecord], facts: ScenarioFacts, facts_by_policy: dict[str, ScenarioFacts], *, as_of: date,
               person_id: Optional[str] = None, person_name: Optional[str] = None, dates: Optional[dict[str, date]] = None,
               facility: Optional[str] = None, documents_present: Optional[list[str]] = None,
               existing_claims: Optional[list[dict[str, Any]]] = None,
               statutory_estimates: Optional[dict[str, tuple[Decimal, str]]] = None) -> ClaimPlan:
    dates = dates or {}
    by_id = {p.id: p for p in policies}
    currency = policies[0].currency if policies else "IDR"
    bill = BillBreakdown.from_facts(facts, currency=currency)
    res = optimize_allocation(policies, facts, bill, rule_pack="ID", as_of=as_of, facts_by_policy=facts_by_policy)
    paying = {s.policy_id: s for s in res.steps}
    uncertain = {u.policy_id: u for u in res.uncertain}
    excluded = {e.policy_id: e for e in res.excluded}
    steps: list[PlanStep] = []
    indemnity_ns: list[int] = []
    for pid in res.evaluation_order:
        p = by_id[pid]
        fp = facts_by_policy.get(pid, facts)
        deadline, late, tid, _ev = portfolio.compute_deadline(p, fp, as_of)
        common = dict(n=len(steps) + 1, policy_id=pid, product_name=p.product_name, insurer=p.insurer or "", deadline=deadline,
                      late_effect=late, deadline_clause=tid)
        if pid in paying:
            s = paying[pid]
            role = "FIXED_BENEFIT" if s.basis == Basis.FIXED_BENEFIT else s.payer_type
            step = PlanStep(role=role, basis=s.basis.value, expected_amount=s.amount, claim_amount=s.amount if s.basis == Basis.FIXED_BENEFIT else None,
                            documents_required=list(s.documents_required), clause_ids=list(s.clause_ids), **common)
        elif pid in uncertain:
            u = uncertain[pid]
            step = PlanStep(role="UNCERTAIN", basis=u.basis.value, status="UNCERTAIN", expected_amount=u.potential_amount,
                            documents_required=list(u.documents_required), clause_ids=list(u.clause_ids),
                            uncertain_slots=[x.value for x in u.slots], **common)
        elif pid in excluded:
            e = excluded[pid]
            if e.code in SILENT_CODES:
                continue
            step = PlanStep(role="NOT_CLAIMABLE", basis=(e.basis or Basis.INDEMNITY).value, status="NOT_CLAIMABLE", expected_amount=ZERO,
                            denial_code=e.code, clause_ids=list(e.clause_ids), **common)
        else:
            continue
        step.facility_billed = p.product_type == "social_bpjs_kes"
        steps.append(step)
    steps = [x for x in steps if x.role != "NOT_CLAIMABLE"] + [x for x in steps if x.role == "NOT_CLAIMABLE"]
    for i, step in enumerate(steps, 1):
        step.n = i
        if step.indemnity and step.role != "NOT_CLAIMABLE":
            step.after = list(indemnity_ns)
            indemnity_ns.append(step.n)
    plan = ClaimPlan(plan_id=f"PLAN-{uuid.uuid4().hex[:8].upper()}", person_id=person_id, person_name=person_name,
                     event=str(facts.get(Slot.EVENT)) if facts.has(Slot.EVENT) else "HOSPITALIZATION", admission=dates.get("admission") or dates.get("accident"),
                     discharge=dates.get("discharge"), facility=facility, bill_total=bill.total if bill is not None else None, currency=currency,
                     as_of=as_of, steps=steps, policies_checked=len(policies), documents_present=list(documents_present or []))
    for pid, (amount, basis_text) in (statutory_estimates or {}).items():
        s = plan.by_policy(pid)
        if s is not None and s.role == "STATUTORY":
            s.expected_amount = min(amount, plan.bill_total) if plan.bill_total is not None else amount
            s.estimate_basis = basis_text
    _attach_existing(plan, existing_claims or [])
    rebalance(plan, policies, facts, facts_by_policy)
    return plan


def _attach_existing(plan: ClaimPlan, claims: list[dict[str, Any]]) -> None:
    """Claims already on file for this stay: a paid statutory claim, a draft waiting to be filed."""
    anchor = plan.admission
    for c in claims:
        s = plan.by_policy(c.get("policy_id", ""))
        if s is None or s.role == "NOT_CLAIMABLE":
            continue
        start = c.get("admission_date") or c.get("event_date")
        if anchor is None or not start or date.fromisoformat(str(start)) != anchor:
            continue
        status = str(c.get("status") or "").lower()
        if status == "draft":
            s.existing_claim_id = c["id"]
        elif status == "submitted":
            s.status, s.claim_id = "SUBMITTED", c["id"]
            s.filed_on = date.fromisoformat(c["filed_date"]) if c.get("filed_date") else None
        elif status in ("approved", "paid"):
            record_decision(plan, s.n, "PAID" if status == "paid" else "APPROVED", Decimal(str(c.get("paid") or 0)), None, "SANDBOX_INSURER")
            s.claim_id = c["id"]
        elif status == "rejected":
            s.claim_id = c["id"]
            record_decision(plan, s.n, "REJECTED", ZERO, c.get("rejection_code"), "SANDBOX_INSURER")


# --------------------------------------------------------------------------- explanation of benefits
def rebalance(plan: ClaimPlan, policies: list[PolicyRecord], facts: ScenarioFacts, facts_by_policy: dict[str, ScenarioFacts]) -> None:
    """Walk the indemnity payers in order. A decided payer reduces the balance by what it paid; a
    submitted one by what it is expected to pay; an open one is presented the balance and its
    expected benefit is recomputed on it. A payer with nothing left after decided payers is skipped."""
    by_id = {p.id: p for p in policies}
    for s in plan.steps:
        if s.status in OPEN and s.deadline is not None and plan.as_of > s.deadline and s.late_effect in (None, "REJECT"):
            s.status, s.late = "SKIPPED", True
    if plan.bill_total is not None:
        balance = Decimal(plan.bill_total)
        for s in sorted(plan.steps, key=lambda x: x.n):
            if not s.indemnity or s.role == "NOT_CLAIMABLE":
                continue
            prior_decided = all((plan.step(k) is not None and plan.step(k).status in DECIDED) for k in s.after)
            if s.status in SETTLED:
                balance -= Decimal(s.paid_amount or 0)
                continue
            if s.status in ("REJECTED", "APPEALED"):
                continue
            if s.status == "SUBMITTED":
                balance -= Decimal(s.expected_amount or 0)
                continue
            if s.status == "SKIPPED" and s.late:
                continue
            if s.status == "SKIPPED" and balance > 0:
                s.status = "PLANNED"
            if s.status not in OPEN and s.status != "UNCERTAIN":
                continue
            s.claim_amount = max(ZERO, balance)
            if s.role == "STATUTORY" and s.estimate_basis:
                expected = min(Decimal(s.expected_amount or 0), s.claim_amount)
            elif s.policy_id in by_id:
                expected = _single_payout(by_id[s.policy_id], facts, facts_by_policy, s.claim_amount, plan.as_of)
            else:
                expected = Decimal(s.expected_amount or 0)
            s.expected_amount = expected
            if balance <= 0 and prior_decided and s.status in OPEN:
                s.status = "SKIPPED"
            balance -= expected
    _refresh_documents(plan)


def _refresh_documents(plan: ClaimPlan) -> None:
    present = {d.upper() for d in plan.documents_present}
    for s in plan.steps:
        prior_decided = all((plan.step(k) is not None and plan.step(k).status in DECIDED) for k in s.after)
        missing = []
        for d in s.documents_required:
            if d.upper() in present:
                continue
            if d in SETTLEMENT_DOCS:
                continue
            if d in FACILITY_HELD_DOCS and s.facility_billed:
                continue
            missing.append(d)
        s.documents_missing = missing


# --------------------------------------------------------------------------- progress
def next_step(plan: ClaimPlan) -> Optional[PlanStep]:
    """The first open payer whose earlier payers have all decided."""
    for s in sorted(plan.steps, key=lambda x: x.n):
        if s.status != "PLANNED":
            continue
        if any((plan.step(k) is None or plan.step(k).status not in DECIDED) for k in s.after):
            continue
        if s.indemnity and s.claim_amount is not None and s.claim_amount <= 0:
            continue
        return s
    return None


def waiting_on(plan: ClaimPlan) -> list[PlanStep]:
    return [s for s in plan.steps if s.status in ("SUBMITTED", "AWAITING_CONFIRMATION")]


def blocking_question(plan: ClaimPlan) -> Optional[PlanStep]:
    """An indemnity payer whose eligibility turns on an open fact, ahead of open payers."""
    for s in sorted(plan.steps, key=lambda x: x.n):
        if s.status == "UNCERTAIN" and s.indemnity and any(o.status == "PLANNED" and s.n in o.after for o in plan.steps):
            return s
    return None


def is_late(s: PlanStep, as_of: date) -> bool:
    return s.deadline is not None and as_of > s.deadline


def record_submission(plan: ClaimPlan, n: int, claim_id: str, filed_on: date) -> None:
    s = plan.step(n)
    if s is None:
        return
    s.status, s.claim_id, s.filed_on = "SUBMITTED", claim_id, filed_on


def record_decision(plan: ClaimPlan, n: int, status: str, paid: Optional[Decimal], rejection_code: Optional[str], source: str) -> None:
    s = plan.step(n)
    if s is None:
        return
    s.status = status
    s.paid_amount = Decimal(paid) if paid is not None else None
    s.rejection_code = rejection_code
    s.decision_source = source


def totals(plan: ClaimPlan) -> tuple[Decimal, Decimal, Optional[Decimal]]:
    """(expected or paid from indemnity payers, from fixed-benefit payers, out of pocket)."""
    ind = ZERO
    fixed = ZERO
    for s in plan.steps:
        if s.role == "NOT_CLAIMABLE" or s.status in ("SKIPPED", "UNCERTAIN"):
            continue
        amount = (s.paid_amount or ZERO) if s.status in SETTLED | {"REJECTED", "APPEALED"} else s.expected_amount
        if amount is None:
            continue
        if s.role == "FIXED_BENEFIT":
            fixed += Decimal(amount)
        elif s.indemnity:
            ind += Decimal(amount)
    oop = max(ZERO, Decimal(plan.bill_total) - ind) if plan.bill_total is not None else None
    return ind, fixed, oop


def as_payer_steps(plan: ClaimPlan) -> list[portfolio.PayerStep]:
    out = []
    for s in plan.steps:
        status = {"FIXED_BENEFIT": "PARALLEL", "UNCERTAIN": "UNCERTAIN", "NOT_CLAIMABLE": "NOT_CLAIMABLE"}.get(s.role, "PAYER")
        out.append(portfolio.PayerStep(order=s.n, payer_policy_id=s.policy_id, expected_amount=s.expected_amount, basis=Basis(s.basis),
                                       documents=list(s.documents_required), deadline=s.deadline, tuple_ids=list(s.clause_ids), status=status,
                                       denial_code=s.denial_code, currency=plan.currency))
    return out


# --------------------------------------------------------------------------- wording
def _money(v: Optional[Decimal], cur: str = "IDR") -> str:
    return f"{cur} {int(Decimal(v)):,}" if v is not None else "-"


def _L(lang: str, en: str, id_: str) -> str:
    return id_ if lang == "id" else en


ROLE_EN = {"STATUTORY": "statutory payer, first", "PRIMARY": "pays first among private insurers", "PRO_RATA": "shares the bill pro rata",
           "EXCESS": "pays only the remainder (excess clause)", "FIXED_BENEFIT": "fixed benefit, claimed in parallel", "UNCERTAIN": "depends on an open question"}
ROLE_ID = {"STATUTORY": "penjamin wajib, dibayar pertama", "PRIMARY": "penanggung swasta pertama", "PRO_RATA": "berbagi tagihan secara proporsional",
           "EXCESS": "hanya membayar sisa (klausul excess)", "FIXED_BENEFIT": "santunan tetap, diklaim paralel", "UNCERTAIN": "bergantung pada satu pertanyaan"}
CODE_EN = {"NON_PARTNER_FACILITY": "not a BPJS partner facility and not an emergency", "LAPSED": "not in force (premium or contributions unpaid)",
           "PRE_EXISTING": "pre-existing condition exclusion", "WAITING_PERIOD": "still in the waiting period", "NOT_APPLICABLE": "no clause covers this event",
           "SINGLE_VEHICLE": "single-vehicle accident", "NO_VALID_LICENSE": "no valid driving licence", "LATE_FILING": "filed after the deadline",
           "INCOMPLETE_DOCS": "documents incomplete", "LAPSED_BPJS": "membership inactive because contributions are in arrears (it reactivates once they are settled)"}
CODE_ID = {"NON_PARTNER_FACILITY": "bukan faskes mitra BPJS dan bukan kondisi darurat", "LAPSED": "tidak aktif (premi atau iuran belum dibayar)",
           "PRE_EXISTING": "pengecualian kondisi yang sudah ada sebelumnya", "WAITING_PERIOD": "masih dalam masa tunggu", "NOT_APPLICABLE": "tidak ada klausul yang menanggung kejadian ini",
           "SINGLE_VEHICLE": "kecelakaan tunggal", "NO_VALID_LICENSE": "tidak memiliki SIM yang berlaku", "LATE_FILING": "diajukan setelah batas waktu",
           "INCOMPLETE_DOCS": "dokumen belum lengkap", "LAPSED_BPJS": "kepesertaan nonaktif karena menunggak iuran (aktif kembali setelah tunggakan dilunasi)"}
SOURCE_EN = {"SANDBOX_SIMULATED": "simulated insurer decision, sandbox only", "SANDBOX_INSURER": "sandbox insurer record", "USER_REPORTED": "as you reported"}
SOURCE_ID = {"SANDBOX_SIMULATED": "keputusan penanggung simulasi, hanya sandbox", "SANDBOX_INSURER": "catatan penanggung sandbox", "USER_REPORTED": "sesuai laporan Anda"}


def code_text(code: Optional[str], lang: str) -> str:
    table = CODE_ID if lang == "id" else CODE_EN
    return table.get(code or "", (code or "").replace("_", " ").lower())


def _late_text(late: Optional[str], lang: str) -> str:
    if late in (None, "REJECT"):
        return _L(lang, "a late claim is rejected", "klaim yang terlambat ditolak")
    return _L(lang, "the insurer may reject a late claim", "penanggung dapat menolak klaim yang terlambat")


def step_line(plan: ClaimPlan, s: PlanStep, lang: str, detail: bool = True) -> list[str]:
    cur = plan.currency
    role = (ROLE_ID if lang == "id" else ROLE_EN).get(s.role, s.role.lower())
    head = f"{s.n}. {s.product_name} ({s.policy_id}) - {role}"
    if s.status in SETTLED:
        src = (SOURCE_ID if lang == "id" else SOURCE_EN).get(s.decision_source or "", "")
        body = _L(lang, f"PAID {_money(s.paid_amount, cur)}" + (f" ({src})" if src else "") + (f", claim {s.claim_id}" if s.claim_id else ""),
                  f"DIBAYAR {_money(s.paid_amount, cur)}" + (f" ({src})" if src else "") + (f", klaim {s.claim_id}" if s.claim_id else ""))
    elif s.status == "REJECTED":
        body = _L(lang, f"REJECTED ({code_text(s.rejection_code, lang)})" + (f", claim {s.claim_id}" if s.claim_id else ""),
                  f"DITOLAK ({code_text(s.rejection_code, lang)})" + (f", klaim {s.claim_id}" if s.claim_id else ""))
    elif s.status == "APPEALED":
        body = _L(lang, f"rejected, appeal filed (claim {s.claim_id})", f"ditolak, banding sudah diajukan (klaim {s.claim_id})")
    elif s.status == "SUBMITTED":
        body = _L(lang, f"submitted as {s.claim_id} on {s.filed_on.isoformat() if s.filed_on else '-'}, waiting for the insurer's decision; claimed {_money(s.claim_amount, cur)}, expected {_money(s.expected_amount, cur)}",
                  f"sudah diajukan sebagai {s.claim_id} pada {s.filed_on.isoformat() if s.filed_on else '-'}, menunggu keputusan penanggung; diklaim {_money(s.claim_amount, cur)}, perkiraan {_money(s.expected_amount, cur)}")
    elif s.status == "SKIPPED" and s.late:
        left = (plan.as_of - s.deadline).days if s.deadline else 0
        body = _L(lang, f"not filed: the filing deadline {s.deadline.isoformat()} passed {left} days ago and this wording rejects late claims [{s.deadline_clause}]",
                  f"tidak diajukan: batas pengajuan {s.deadline.isoformat()} sudah lewat {left} hari dan ketentuan ini menolak klaim terlambat [{s.deadline_clause}]")
    elif s.status == "SKIPPED":
        body = _L(lang, "nothing left to claim: the earlier payers settled the bill", "tidak ada sisa yang perlu diklaim: penanggung sebelumnya sudah melunasi tagihan")
    elif s.status == "UNCERTAIN":
        slots = ", ".join(x.replace("_", " ") for x in s.uncertain_slots) or "-"
        body = _L(lang, f"eligibility depends on: {slots}", f"kelayakan bergantung pada: {slots}")
    elif s.role == "FIXED_BENEFIT":
        body = _L(lang, f"fixed benefit {_money(s.expected_amount, cur)}, independent of the bill and of the other payers",
                  f"santunan tetap {_money(s.expected_amount, cur)}, tidak bergantung pada tagihan maupun penanggung lain")
    elif s.role == "STATUTORY":
        basis = f" ({s.estimate_basis})" if s.estimate_basis else ""
        body = _L(lang, f"expected {_money(s.expected_amount, cur)}{basis}", f"perkiraan {_money(s.expected_amount, cur)}{basis}")
    else:
        after = ", ".join(str(k) for k in s.after)
        cond = _L(lang, f"after step {after} decides, " if after else "", f"setelah langkah {after} diputus, " if after else "")
        if s.claim_amount is not None and s.claim_amount <= 0:
            body = _L(lang, f"{cond}claim only if a balance remains (none expected now)", f"{cond}diklaim hanya jika masih ada sisa tagihan (saat ini diperkirakan tidak ada)")
        else:
            body = _L(lang, f"{cond}claim the unpaid balance {_money(s.claim_amount, cur)}, expected benefit {_money(s.expected_amount, cur)}",
                      f"{cond}klaim sisa tagihan {_money(s.claim_amount, cur)}, perkiraan manfaat {_money(s.expected_amount, cur)}")
    lines = [f"{head}: {body}."]
    if detail and (s.status in OPEN or s.status == "UNCERTAIN"):
        if s.deadline is not None:
            left = (s.deadline - plan.as_of).days
            when = (_L(lang, f"{left} days left", f"tersisa {left} hari") if left >= 0 else _L(lang, f"passed {-left} days ago", f"sudah lewat {-left} hari"))
            lines.append(_L(lang, f"   Filing deadline {s.deadline.isoformat()} ({when}; {_late_text(s.late_effect, lang)}) [{s.deadline_clause}].",
                            f"   Batas pengajuan {s.deadline.isoformat()} ({when}; {_late_text(s.late_effect, lang)}) [{s.deadline_clause}]."))
        elif s.role != "STATUTORY":
            lines.append(_L(lang, "   No filing deadline is stated in the extracted wording: file as soon as the documents are ready.",
                            "   Ketentuan yang terekstrak tidak menyebut batas pengajuan: ajukan segera setelah dokumen lengkap."))
        if s.documents_required:
            docs = "; ".join(dict.fromkeys(doc_label(d, lang) for d in s.documents_required))
            lines.append(_L(lang, f"   Documents: {docs}.", f"   Dokumen: {docs}."))
            if s.facility_billed:
                lines.append(_L(lang, "   At a partner hospital these are handled at admission: the hospital bills BPJS Kesehatan under the SEP issued then.",
                                "   Di rumah sakit mitra dokumen ini diurus saat masuk: rumah sakit menagih BPJS Kesehatan dengan SEP yang terbit saat itu."))
            elif s.documents_missing:
                miss = "; ".join(dict.fromkeys(doc_label(d, lang) for d in s.documents_missing))
                lines.append(_L(lang, f"   Still missing: {miss}.", f"   Masih kurang: {miss}."))
            else:
                lines.append(_L(lang, "   Documents complete.", "   Dokumen lengkap."))
            if any(d in SETTLEMENT_DOCS for d in s.documents_required) and s.after:
                lines.append(_L(lang, "   The settlement (COB) letter comes with the earlier payer's decision; I attach its result to this claim.",
                                "   Surat penyelesaian (COB) didapat dari keputusan penanggung sebelumnya; hasilnya saya sertakan pada klaim ini."))
    return lines


def render(plan: ClaimPlan, lang: str, detail: Optional[set[int]] = None) -> list[str]:
    """The plan; with `detail` given, deadlines and documents are spelled out only for those steps."""
    cur = plan.currency
    who = plan.person_name or _L(lang, "you", "Anda")
    stay = ""
    if plan.admission and plan.discharge:
        days = (plan.discharge - plan.admission).days + 1
        stay = _L(lang, f", stay {plan.admission.isoformat()} to {plan.discharge.isoformat()} ({days} days)",
                  f", rawat inap {plan.admission.isoformat()} s/d {plan.discharge.isoformat()} ({days} hari)")
    elif plan.discharge:
        stay = _L(lang, f", discharged {plan.discharge.isoformat()}", f", pulang {plan.discharge.isoformat()}")
    at = _L(lang, f" at {plan.facility}", f" di {plan.facility}") if plan.facility else ""
    billed = _L(lang, f", bill {_money(plan.bill_total, cur)}", f", tagihan {_money(plan.bill_total, cur)}") if plan.bill_total is not None else ""
    lines = [_L(lang, f"Claim plan {plan.plan_id} for {who}{stay}{at}{billed}. I checked all {plan.policies_checked} policies that cover {who}.",
                f"Rencana klaim {plan.plan_id} untuk {who}{stay}{at}{billed}. Saya sudah memeriksa {plan.policies_checked} polis yang menanggung {who}.")]
    lines.append(_L(lang, "Claiming order (coordination of benefits, Indonesia: statutory schemes first, then indemnity insurers with group before individual; fixed-benefit plans in parallel):",
                    "Urutan klaim (koordinasi manfaat, Indonesia: penjamin wajib dulu, lalu asuransi indemnitas dengan polis grup sebelum individu; santunan tetap diklaim paralel):"))
    for s in plan.claimable:
        lines += step_line(plan, s, lang, detail=detail is None or s.n in detail)
    skipped = [s for s in plan.steps if s.role == "NOT_CLAIMABLE"]
    if skipped:
        lines.append(_L(lang, "Not claimable for this stay: ", "Tidak bisa diklaim untuk perawatan ini: ")
                     + "; ".join(f"{s.product_name} ({s.policy_id}) - {code_text('LAPSED_BPJS' if s.facility_billed and s.denial_code == 'LAPSED' else s.denial_code, lang)}"
                                 for s in skipped) + ".")
    ind, fixed, oop = totals(plan)
    if plan.bill_total is not None:
        lines.append(_L(lang, f"Expected recovery: {_money(ind, cur)} towards the bill plus {_money(fixed, cur)} in fixed benefits; estimated out of pocket {_money(oop, cur)}.",
                        f"Perkiraan penggantian: {_money(ind, cur)} untuk tagihan ditambah santunan tetap {_money(fixed, cur)}; perkiraan biaya sendiri {_money(oop, cur)}."))
    return lines
