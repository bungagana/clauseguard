"""Claim Allocation Optimizer: how much of one bill each policy of a household should be asked
to pay, and in which order, under the coordination rules of a jurisdiction. Pure Python,
deterministic; no language model runs here. Eligibility of every policy comes from `solver.decide`.

Formulation
-----------
The eligible bill B is split into categories c in C (room, surgery, other when the bill is
itemised; a single category "total" otherwise), B = sum_c B_c. For an eligible indemnity
policy i the charges presented to it are y_{i,c} >= 0 with s_i = sum_c y_{i,c}, and the policy
pays

    p_i = g_i(s_i) = min(A_i, s_i - m_i(s_i)),
    m_i(s) = min(K_i, min(s, D_i + F_i) + r_i * max(0, s - D_i - F_i)),

where D_i is the deductible, F_i a flat co-payment, r_i the co-payment rate, K_i the cap on the
member's own cost sharing (a per-admission co-payment cap or an annual out-of-pocket maximum)
and A_i the annual or lifetime cap on what the insurer pays. Inner limits bound what can be
presented: y_{i,c} <= L_{i,c} for separately capped categories (room and board per day x days,
surgery per case) and sum_{c in pool_i} y_{i,c} <= P_i for the per-case pool of the other
categories. g_i is non-decreasing and 1-Lipschitz (0 <= g_i' <= 1).

Coordination is sequential: the payer k-th in line is presented the charges still unpaid after
the payers before it, U_k = B - sum_{j<k} p_j (per category, each earlier payment attributed to
categories pro rata to the charges it was presented), so sum_k p_k <= B holds by construction
(indemnity principle). Fixed-benefit policies are outside the sequence: they pay the amount the
solver computed, independently of B, and stack.

Payer layers come from the rule pack: statutory schemes first, then commercial policies by class
(employer group before individual under the ID pack) and other-insurance kind
primary -> PRO_RATA -> EXCESS. Within a layer of co-primary policies the only free choice is
the claiming order: presenting a payer everything still unpaid is optimal (the total is
non-decreasing in every presented amount because every g_j' <= 1), while the order matters as
soon as a policy has a deductible, a co-payment or a cap. The optimizer therefore evaluates
every order of the layer exactly (at most 6 policies, 720 orders; beyond that a capacity-sorted
heuristic is used and labelled), ties broken toward the pack's preferred order so that the
result is reproducible. The programme is small enough that no linear-programming solver is
needed; the separable case (no deductible, no co-payment, no cost-sharing cap, one pool) has
the order-free optimum min(U, sum_i cap_i).

PRO_RATA policies take a rateable proportion: the unpaid charges are split in proportion to the
policies' limits and each pays its own terms on its share. Two or more EXCESS policies in the
same layer are circular (each is excess over the other); they are resolved the same way and the
result is flagged with their clause ids.

Two baselines are reported: `greedy_total` (claim from the policies in the order they are held,
each paying on what is still unpaid, ignoring the layer rules) and `single_policy_total` (the
best single policy on the whole bill). Because g is 1-Lipschitz, greedy >= single always, and
optimizer >= greedy whenever the holdings order does not breach a coordination rule.
"""
from __future__ import annotations

import itertools
from datetime import date
from decimal import Decimal
from typing import Optional

from pydantic import Field

from .portfolio import (
    ACTIVE_STATUSES,
    cell_basis,
    compute_deadline,
    decide_mapped,
    event_for_policy,
    is_group,
    normalise_denial_code,
    required_documents,
)
from .rulepacks import RulePack, StatutoryRule, get_rule_pack
from .schema import (
    Basis,
    ClauseTuple,
    MissingSlot,
    PolicyRecord,
    Relation,
    ScenarioFacts,
    Slot,
    Strict,
    Verdict,
    VerdictResult,
)
from .solver import eval_condition

ZERO = Decimal(0)
UNIT = Decimal("1")
MAX_ENUMERATED_PAYERS = 6
SILENT_CODES = {"NOT_APPLICABLE", "NOT_SPECIFIED"}


def _q(v: Decimal) -> Decimal:
    """Round down to whole currency units (never pays a fraction more than the programme allows)."""
    return v.quantize(UNIT, rounding="ROUND_DOWN")


def _money(v) -> Decimal:
    return Decimal(str(v)) if v is not None else ZERO


# --------------------------------------------------------------------------- models
class BillBreakdown(Strict):
    """One bill. `total` is required; the itemised parts are optional. Parts that do not add up to
    the total are reconciled: a shortfall is unitemised "other" charges, an excess is scaled down."""

    total: Decimal = Field(ge=0)
    room: Optional[Decimal] = Field(default=None, ge=0)
    surgery: Optional[Decimal] = Field(default=None, ge=0)
    doctor: Optional[Decimal] = Field(default=None, ge=0)
    drugs: Optional[Decimal] = Field(default=None, ge=0)
    other: Optional[Decimal] = Field(default=None, ge=0)
    currency: str = Field(default="IDR", pattern=r"^[A-Z]{3}$")

    def itemised(self) -> bool:
        return any(v is not None for v in (self.room, self.surgery, self.doctor, self.drugs, self.other))

    def categories(self) -> dict[str, Decimal]:
        """Category -> amount. `{"total": T}` when nothing is itemised; room / surgery only when non-zero."""
        if not self.itemised():
            return {"total": _q(self.total)}
        parts = {
            "room": _money(self.room),
            "surgery": _money(self.surgery),
            "other": _money(self.doctor) + _money(self.drugs) + _money(self.other),
        }
        s = sum(parts.values(), ZERO)
        if s < self.total:
            parts["other"] += self.total - s
        elif s > self.total and s > 0:
            scale = self.total / s
            parts = {k: _q(v * scale) for k, v in parts.items()}
            diff = self.total - sum(parts.values(), ZERO)
            parts["other"] += diff
        return {k: _q(v) for k, v in parts.items() if k == "other" or v > 0}

    @classmethod
    def from_facts(cls, facts: ScenarioFacts, breakdown: Optional[dict] = None, currency: str = "IDR") -> Optional["BillBreakdown"]:
        """Build from the BILLED_AMOUNT slot and an optional {room, drugs, doctor, surgery, other} dict."""
        if not facts.has(Slot.BILLED_AMOUNT):
            return None
        b = breakdown or {}
        return cls(total=_money(facts.get(Slot.BILLED_AMOUNT)), room=b.get("room"), surgery=b.get("surgery"),
                   doctor=b.get("doctor"), drugs=b.get("drugs"), other=b.get("other"), currency=currency)


class PolicyTerms(Strict):
    """The typed cost-sharing terms of one policy for one event, derived from COVERS qualifiers."""

    policy_id: str
    clause_ids: list[str] = Field(default_factory=list)
    separate: dict[str, Decimal] = Field(default_factory=dict, description="category -> cap on presented charges")
    pooled: list[str] = Field(default_factory=list, description="categories sharing pool_cap")
    pool_cap: Optional[Decimal] = None
    payment_cap: Optional[Decimal] = None
    deductible: Decimal = ZERO
    flat_copay: Decimal = ZERO
    copay_rate: float = 0.0
    copay_cap: Optional[Decimal] = None
    kind: Optional[str] = Field(default=None, pattern=r"^(EXCESS|PRO_RATA|NONE|STACKABLE)$")
    is_group: bool = False
    notes: list[str] = Field(default_factory=list)

    # -- presentation and payment
    def presentable(self, remainder: dict[str, Decimal]) -> dict[str, Decimal]:
        """Largest charges per category that can be presented out of `remainder`."""
        out: dict[str, Decimal] = {}
        for c, cap in self.separate.items():
            if c in remainder:
                out[c] = min(_money(remainder.get(c)), cap)
        left = self.pool_cap
        for c in self.pooled:
            if c not in remainder:
                continue
            v = _money(remainder.get(c))
            if left is not None:
                v = min(v, left)
                left -= v
            out[c] = v
        return {c: _q(max(ZERO, v)) for c, v in out.items()}

    def member_cost(self, s: Decimal) -> Decimal:
        fixed = self.deductible + self.flat_copay
        m = min(s, fixed) + Decimal(str(self.copay_rate)) / Decimal(100) * max(ZERO, s - fixed)
        if self.copay_cap is not None:
            m = min(m, self.copay_cap)
        return m

    def pay(self, s: Decimal) -> Decimal:
        """g_i(s): what the policy pays when charges s are presented."""
        p = max(ZERO, s - self.member_cost(s))
        if self.payment_cap is not None:
            p = min(p, self.payment_cap)
        return _q(p)

    def capacity(self, remainder: dict[str, Decimal]) -> tuple[Decimal, dict[str, Decimal]]:
        pres = self.presentable(remainder)
        return self.pay(sum(pres.values(), ZERO)), pres

    def limit(self, full: dict[str, Decimal]) -> Decimal:
        """The policy's stated limit for the event (sum of its inner limits), or the charges it can
        be presented out of the whole bill when no inner limit bounds it."""
        if self.pool_cap is None:
            return sum(self.presentable(full).values(), ZERO)
        return sum((v for c, v in self.separate.items() if c in full), ZERO) + self.pool_cap

    def separable(self) -> bool:
        """No deductible, no co-payment and no cost-sharing cap: g_i(s) = min(A_i, s)."""
        return self.deductible == 0 and self.flat_copay == 0 and self.copay_rate == 0


class AllocationStep(Strict):
    """One payer in claiming order. `presented` is what to submit to it per bill category."""

    order: int
    policy_id: str
    payer_type: str = Field(pattern=r"^(STATUTORY|PRIMARY|PRO_RATA|EXCESS|FIXED_BENEFIT)$")
    basis: Basis
    amount: Optional[Decimal] = None
    currency: str = "IDR"
    presented: dict[str, Decimal] = Field(default_factory=dict, description="charges presented per category")
    documents_required: list[str] = Field(default_factory=list)
    filing_deadline: Optional[date] = None
    clause_ids: list[str] = Field(default_factory=list)
    rule_id: Optional[str] = Field(default=None, max_length=80)
    note: Optional[str] = Field(default=None, max_length=400)


class UncertainPolicy(Strict):
    """A policy whose verdict turns on an unbound slot; `potential_amount` is what it could pay once resolved."""

    policy_id: str
    basis: Basis
    slots: list[Slot] = Field(default_factory=list)
    potential_amount: Optional[Decimal] = None
    clause_ids: list[str] = Field(default_factory=list)
    documents_required: list[str] = Field(default_factory=list)
    filing_deadline: Optional[date] = None
    rule_id: Optional[str] = Field(default=None, max_length=80)
    note: Optional[str] = Field(default=None, max_length=400)


class ExcludedPolicy(Strict):
    """A policy that does not pay, with the solver's denial code (or the rule pack's)."""

    policy_id: str
    code: str = Field(max_length=60)
    basis: Optional[Basis] = None
    clause_ids: list[str] = Field(default_factory=list)
    filing_deadline: Optional[date] = None
    rule_id: Optional[str] = Field(default=None, max_length=80)
    note: Optional[str] = Field(default=None, max_length=400)


class AllocationResult(Strict):
    """The plan: payers in order, totals, the two baselines, what is uncertain or excluded, and flags."""

    steps: list[AllocationStep] = Field(default_factory=list)
    total_recovered: Decimal = ZERO
    indemnity_total: Decimal = ZERO
    fixed_benefit_total: Decimal = ZERO
    out_of_pocket: Optional[Decimal] = None
    greedy_total: Optional[Decimal] = None
    single_policy_total: Optional[Decimal] = None
    uncertain: list[UncertainPolicy] = Field(default_factory=list)
    excluded: list[ExcludedPolicy] = Field(default_factory=list)
    circular_excess: bool = False
    circular_clause_ids: list[str] = Field(default_factory=list)
    rule_pack: str = "ID"
    bill_total: Optional[Decimal] = None
    currency: str = "IDR"
    evaluation_order: list[str] = Field(default_factory=list, description="every policy considered, in payer order")
    solver: str = Field(default="none", pattern=r"^(none|exact|order-search|heuristic|mixed)$")
    notes: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------- terms
def _event_tuples(policy: PolicyRecord, event: str, basis: Basis) -> list[ClauseTuple]:
    return [t for t in policy.tuples_by(Relation.COVERS) if t.object == event and cell_basis(t, policy) == basis]


def _other_insurance_kind(policy: PolicyRecord, covers: list[ClauseTuple]) -> Optional[str]:
    for t in covers:
        if t.qualifiers.other_insurance:
            return t.qualifiers.other_insurance
    for t in policy.tuples:
        if t.relation == Relation.DEFINES and t.qualifiers.other_insurance:
            return t.qualifiers.other_insurance
    return None


def policy_terms(policy: PolicyRecord, event: str, facts: ScenarioFacts, categories: list[str]) -> Optional[PolicyTerms]:
    """Derive `PolicyTerms` from the INDEMNITY COVERS tuples of `event` (and the SURGERY tuples when
    the bill itemises surgery). Room and board is capped per day x days hospitalised, surgery per
    case; the other categories share the per-case / flat amount pool; an unitemised bill is capped
    at the sum of the stated inner limits. None when the policy has no indemnity clause for the event."""
    covers = _event_tuples(policy, event, Basis.INDEMNITY)
    if not covers:
        return None
    qs = [t.qualifiers for t in covers]
    clause_ids = [t.id for t in covers]
    notes: list[str] = []
    days = int(facts.get(Slot.DAYS_HOSPITALIZED)) if facts.has(Slot.DAYS_HOSPITALIZED) else None

    per_day = [q for q in qs if q.per_day_limit is not None]
    room_limit: Optional[Decimal] = None
    if per_day:
        room_limit = ZERO
        for q in per_day:
            d = days if days is not None else 0
            if q.deductible_days:
                d = max(0, d - q.deductible_days)
            cap = q.max_days_per_year or q.max_days
            if cap:
                d = min(d, cap)
            room_limit += Decimal(d) * _money(q.per_day_limit)
        if days is None:
            notes.append("days hospitalised unknown: room limit cannot be computed")
    per_case = [q for q in qs if q.per_case_limit is not None]
    flat = [q for q in qs if q.amount is not None and q.per_day_limit is None and q.per_case_limit is None]
    pool_cap: Optional[Decimal] = None
    if per_case or flat:
        pool_cap = sum((_money(q.per_case_limit) for q in per_case), ZERO) + sum((_money(q.amount) for q in flat), ZERO)

    surgery = _event_tuples(policy, "SURGERY", Basis.INDEMNITY) if (event != "SURGERY" and "surgery" in categories) else []
    separate: dict[str, Decimal] = {}
    pooled: list[str] = []
    if categories == ["total"]:
        pooled = ["total"]
        if room_limit is not None or pool_cap is not None:
            pool_cap = (room_limit or ZERO) + (pool_cap or ZERO)
            notes.append(f"inner limits total {int(pool_cap):,} (itemise the bill for a per-category figure)")
        else:
            notes.append("no inner limit stated")
    else:
        if room_limit is not None:
            separate["room"] = room_limit
        else:
            pooled.append("room")
        if surgery:
            separate["surgery"] = sum((_money(t.qualifiers.per_case_limit if t.qualifiers.per_case_limit is not None else t.qualifiers.amount) for t in surgery), ZERO)
            clause_ids += [t.id for t in surgery]
        else:
            pooled.append("surgery")
        pooled.append("other")
        for c, v in separate.items():
            notes.append(f"{c} limit {int(v):,}")
        if pool_cap is not None:
            notes.append(f"{'/'.join(pooled)} limit {int(pool_cap):,}")

    caps = [q.annual_cap for q in qs if q.annual_cap is not None] + [q.lifetime_cap for q in qs if q.lifetime_cap is not None]
    deductible = max([_money(q.deductible_amount) for q in qs] or [ZERO])
    flat_copay = max([_money(q.copay_amount) for q in qs] or [ZERO])
    copay_rate = max([q.copay_pct or 0.0 for q in qs] or [0.0])
    copay_caps = [q.copay_cap for q in qs if q.copay_cap is not None]
    if deductible:
        notes.append(f"deductible {int(deductible):,}")
    if flat_copay:
        notes.append(f"co-payment {int(flat_copay):,} per admission")
    if copay_rate:
        notes.append(f"co-payment {copay_rate:g}%" + (f" (member cost cap {int(min(copay_caps)):,})" if copay_caps else ""))
    return PolicyTerms(
        policy_id=policy.id, clause_ids=list(dict.fromkeys(clause_ids)), separate=separate, pooled=pooled, pool_cap=pool_cap,
        payment_cap=min(caps) if caps else None, deductible=deductible, flat_copay=flat_copay, copay_rate=float(copay_rate),
        copay_cap=min(copay_caps) if copay_caps else None, kind=_other_insurance_kind(policy, covers), is_group=is_group(policy), notes=notes,
    )


# --------------------------------------------------------------------------- layer solvers
Payments = dict[str, tuple[Decimal, dict[str, Decimal]]]


def _sequential(terms: list[PolicyTerms], remainder: dict[str, Decimal]) -> tuple[Payments, dict[str, Decimal]]:
    """Payers in the given order, each presented everything still unpaid. Returns (payments, unpaid)."""
    unpaid = dict(remainder)
    out: Payments = {}
    for t in terms:
        p, pres = t.capacity(unpaid)
        out[t.policy_id] = (p, pres)
        unpaid = _after(unpaid, {t.policy_id: (p, pres)})
    return out, unpaid


def _total(pay: Payments) -> Decimal:
    return sum((p for p, _ in pay.values()), ZERO)


def _solve_layer(terms: list[PolicyTerms], remainder: dict[str, Decimal]) -> tuple[Payments, str]:
    """Best claiming order of one co-primary layer. `terms` is in pack order (the tie-break)."""
    if not terms or sum(remainder.values(), ZERO) <= 0:
        return {t.policy_id: (ZERO, {c: ZERO for c in remainder}) for t in terms}, "none"
    if len(terms) == 1 or all(t.separable() and not t.separate for t in terms):
        # one payer, or order-free: every g_i is min(A_i, s) on a single pool, total = min(U, sum caps)
        return _sequential(terms, remainder)[0], "exact"
    if len(terms) > MAX_ENUMERATED_PAYERS:
        ordered = sorted(terms, key=lambda t: (-t.capacity(remainder)[0], t.policy_id))
        return _sequential(ordered, remainder)[0], "heuristic"
    best: Optional[Payments] = None
    best_total = Decimal(-1)
    for perm in itertools.permutations(terms):
        pay, _ = _sequential(list(perm), remainder)
        total = _total(pay)
        if total > best_total:
            best, best_total = pay, total
    return best or {}, "order-search"


def _pro_rata(terms: list[PolicyTerms], remainder: dict[str, Decimal], full: dict[str, Decimal]) -> Payments:
    """Rateable proportion: the unpaid charges are split between the policies in proportion to their
    limits and each policy pays its own terms on its share (so a deductible applies to the share,
    not to the whole bill). The rounding residue goes to the first policy in pack order."""
    weights = {t.policy_id: t.limit(full) for t in terms}
    w_sum = sum(weights.values(), ZERO)
    n = Decimal(len(terms))
    shares: dict[str, dict[str, Decimal]] = {}
    for c, amount in remainder.items():
        given = ZERO
        for t in terms:
            share = _q(amount * weights[t.policy_id] / w_sum) if w_sum > 0 else _q(amount / n)
            shares.setdefault(t.policy_id, {})[c] = share
            given += share
        if terms and given < amount:
            shares[terms[0].policy_id][c] += amount - given
    out: Payments = {}
    for t in terms:
        pres = t.presentable(shares[t.policy_id])
        out[t.policy_id] = (t.pay(sum(pres.values(), ZERO)), pres)
    return out


def _after(remainder: dict[str, Decimal], payments: Payments) -> dict[str, Decimal]:
    """Remainder after a layer: payments are attributed to categories pro rata to the charges presented."""
    total = sum(remainder.values(), ZERO)
    paid = sum(p for p, _ in payments.values())
    target = max(ZERO, total - paid)
    new = dict(remainder)
    for p, pres in payments.values():
        s = sum(pres.values(), ZERO)
        for c in new:
            w = (pres.get(c, ZERO) / s) if s > 0 else ((remainder[c] / total) if total > 0 else ZERO)
            new[c] = new[c] - _q(p * w)
    new = {c: max(ZERO, v) for c, v in new.items()}
    s_new = sum(new.values(), ZERO)
    if s_new != target:
        if s_new > 0:
            new = {c: _q(v * target / s_new) for c, v in new.items()}
        diff = target - sum(new.values(), ZERO)
        if diff and new:
            c_max = max(new, key=lambda c: (new[c], c))
            new[c_max] = max(ZERO, new[c_max] + diff)
    return new


# --------------------------------------------------------------------------- eligibility
class _Assessed(Strict):
    policy_id: str
    event: Optional[str] = None
    basis: Optional[Basis] = None
    status: str = Field(pattern=r"^(ELIGIBLE|UNCERTAIN|EXCLUDED)$")
    code: Optional[str] = None
    slots: list[Slot] = Field(default_factory=list)
    fired: list[str] = Field(default_factory=list)
    payable: Optional[Decimal] = None
    rule_id: Optional[str] = None
    rule_order: int = 0
    terms: Optional[PolicyTerms] = None
    group: bool = False
    holdings_index: int = 0
    note: Optional[str] = None


def _rule_status(rule: StatutoryRule, facts: ScenarioFacts) -> tuple[str, Optional[Slot]]:
    """SKIP (not in play) / OK / UNCERTAIN (slot) / FAIL for a statutory rule's gate and any_of groups."""
    for c in rule.gate:
        try:
            if not eval_condition(c, facts):
                return "SKIP", None
        except MissingSlot as ms:
            return ("UNCERTAIN", ms.slot) if ms.slot in rule.uncertain_on_unbound else ("SKIP", None)
    if not rule.any_of:
        return "OK", None
    unbound: Optional[Slot] = None
    for group in rule.any_of:
        try:
            if all(eval_condition(c, facts) for c in group):
                return "OK", None
        except MissingSlot as ms:
            if ms.slot in rule.uncertain_on_unbound and unbound is None:
                unbound = ms.slot
    return ("UNCERTAIN", unbound) if unbound is not None else ("FAIL", None)


def _clarify_slots(r: VerdictResult) -> list[Slot]:
    return list(r.missing_slots or ([r.clarification.slot] if r.clarification else []))


def _assess(policy: PolicyRecord, facts: ScenarioFacts, own_facts: ScenarioFacts, pack: RulePack,
            categories: Optional[list[str]], index: int) -> Optional[_Assessed]:
    rule = pack.statutory_rule(policy.product_type)
    rid, rorder = (rule.rule_id, rule.order) if rule else (None, 0)
    base = dict(policy_id=policy.id, rule_id=rid, rule_order=rorder, holdings_index=index, group=is_group(policy))
    if policy.status not in ACTIVE_STATUSES:
        note = rule.excluded_notes.get("LAPSED") if rule else None
        return _Assessed(status="EXCLUDED", code="LAPSED", basis=policy.basis, note=note, **base)
    if not facts.has(Slot.EVENT):
        return _Assessed(status="UNCERTAIN", slots=[Slot.EVENT], basis=policy.basis, **base)
    event = event_for_policy(policy, facts) or str(facts.get(Slot.EVENT))
    ind = _event_tuples(policy, event, Basis.INDEMNITY)
    fixed = _event_tuples(policy, event, Basis.FIXED_BENEFIT)
    if not ind and not fixed:
        return _Assessed(status="EXCLUDED", code="NOT_APPLICABLE", event=event, **base)
    basis = Basis.INDEMNITY if ind else Basis.FIXED_BENEFIT
    terms = policy_terms(policy, event, own_facts, categories) if (basis == Basis.INDEMNITY and categories) else None
    base.update(event=event, basis=basis, terms=terms)
    if rule is not None:
        st, slot = _rule_status(rule, own_facts)
        if st == "SKIP":
            return None
        if st == "UNCERTAIN":
            return _Assessed(status="UNCERTAIN", slots=[slot] if slot else [], fired=[t.id for t in ind or fixed], note=rule.uncertain_note, **base)
        if st == "FAIL":
            return _Assessed(status="EXCLUDED", code=rule.fail_code, fired=[t.id for t in ind or fixed],
                             note=rule.excluded_notes.get(rule.fail_code), **base)
    r = decide_mapped(policy, own_facts)
    if r.verdict == Verdict.COVERED:
        return _Assessed(status="ELIGIBLE", fired=r.fired_tuple_ids, payable=r.payable, **base)
    if r.verdict == Verdict.CLARIFY:
        return _Assessed(status="UNCERTAIN", slots=_clarify_slots(r), fired=r.fired_tuple_ids, note=rule.uncertain_note if rule else None, **base)
    if r.verdict == Verdict.DENIED:
        code = normalise_denial_code(r, policy) or "DENIED"
        return _Assessed(status="EXCLUDED", code=code, fired=r.fired_tuple_ids, note=rule.excluded_notes.get(code) if rule else None, **base)
    code = (rule.not_applicable_code if rule and rule.not_applicable_code else r.verdict.value)
    return _Assessed(status="EXCLUDED", code=code, fired=r.fired_tuple_ids, note=rule.excluded_notes.get(code) if rule else None, **base)


def _layer_key(a: _Assessed, pack: RulePack) -> tuple:
    """(0, rule order) for statutory schemes; (1, class, kind) for commercial indemnity; (2,) for fixed."""
    if a.rule_id:
        return (0, a.rule_order)
    if a.basis == Basis.INDEMNITY:
        cls = (0 if a.group else 1) if pack.group_before_individual else 0
        return (1, cls, pack.kind_rank(a.terms.kind if a.terms else None))
    return (2,)


def _sort_key(a: _Assessed, pack: RulePack, full: Optional[dict[str, Decimal]]) -> tuple:
    key = _layer_key(a, pack)
    if key[0] == 1:
        cap = a.terms.capacity(full)[0] if (a.terms and full) else ZERO
        return key + (-cap, a.policy_id)
    return key + (a.holdings_index,)


# --------------------------------------------------------------------------- main entry
def optimize_allocation(
    policies: list[PolicyRecord],
    facts: ScenarioFacts,
    bill: Optional[BillBreakdown],
    *,
    rule_pack: str | RulePack = "ID",
    as_of: Optional[date] = None,
    facts_by_policy: Optional[dict[str, ScenarioFacts]] = None,
) -> AllocationResult:
    """Allocate `bill` across `policies` for the scenario in `facts` under `rule_pack`.

    `facts_by_policy` supplies policy-relative slots (days since that policy's effective date,
    pre-existing flag) used for eligibility; `facts` carries the shared scenario. With `bill`
    None the plan lists the payers but no amounts (statutory and fixed benefits still carry the
    solver's figures where it computed one).
    """
    pack = get_rule_pack(rule_pack) if isinstance(rule_pack, str) else rule_pack
    as_of = as_of or facts.as_of or date.today()
    fbp = facts_by_policy or {}
    currency = bill.currency if bill else (policies[0].currency if policies else "IDR")
    full = bill.categories() if bill is not None else None
    categories = list(full.keys()) if full else None
    by_id = {p.id: p for p in policies}

    assessed: list[_Assessed] = []
    for i, p in enumerate(policies):
        a = _assess(p, facts, fbp.get(p.id, facts), pack, categories, i)
        if a is not None:
            assessed.append(a)
    assessed.sort(key=lambda a: _sort_key(a, pack, full))
    order = [a.policy_id for a in assessed]

    # ---- layers
    layer_keys: list[tuple] = []
    for a in assessed:
        k = _layer_key(a, pack)
        if k[0] != 2 and k not in layer_keys:
            layer_keys.append(k)
    layer_keys.sort()
    remainder: dict[str, Decimal] = dict(full) if full else {}
    layer_start: dict[tuple, dict[str, Decimal]] = {}
    payments: Payments = {}
    payer_type: dict[str, str] = {}
    solvers: set[str] = set()
    circular_ids: list[str] = []
    circular = False
    for key in layer_keys:
        layer_start[key] = dict(remainder)
        members = [a for a in assessed if a.status == "ELIGIBLE" and a.basis == Basis.INDEMNITY and _layer_key(a, pack) == key]
        if not members or full is None:
            continue
        terms = [a.terms for a in members if a.terms is not None]
        if key[0] == 0:
            pay, used = _solve_layer(terms, remainder)
            ptype = "STATUTORY"
        elif key[2] == 1:
            pay, used, ptype = _pro_rata(terms, remainder, full), "exact", "PRO_RATA"
        elif key[2] == 2:
            ptype = "EXCESS"
            if len(terms) >= 2:
                pay, used = _pro_rata(terms, remainder, full), "exact"
                circular = True
                for t in terms:
                    circular_ids += t.clause_ids
            else:
                pay, used = _sequential(terms, remainder)[0], "exact"
        else:
            pay, used = _solve_layer(terms, remainder)
            ptype = "PRIMARY"
        solvers.add(used)
        payments.update(pay)
        for pid in pay:
            payer_type[pid] = ptype
        remainder = _after(remainder, pay)

    # ---- steps, in the claiming order the layers chose
    # (payers of a layer take the layer's payer slots in the chosen order; other entries keep their slot)
    seq = {pid: i for i, pid in enumerate(payments)}
    reordered: list[_Assessed] = []
    for key in sorted({_layer_key(a, pack) for a in assessed}):
        members = [a for a in assessed if _layer_key(a, pack) == key]
        payers = sorted([a for a in members if a.policy_id in seq], key=lambda a: seq[a.policy_id])
        it = iter(payers)
        reordered += [next(it) if a.policy_id in seq else a for a in members]
    assessed = reordered
    order = [a.policy_id for a in assessed]
    steps: list[AllocationStep] = []
    uncertain: list[UncertainPolicy] = []
    excluded: list[ExcludedPolicy] = []
    indemnity_payers = 0
    for a in assessed:
        p = by_id[a.policy_id]
        deadline = compute_deadline(p, facts, as_of)[0]
        if a.status == "ELIGIBLE":
            if a.basis == Basis.INDEMNITY:
                second = indemnity_payers >= 1
                docs, _ = required_documents(p, facts, second_indemnity_payer=second)
                amt, pres = payments.get(a.policy_id, (None, {}))
                notes = list(a.terms.notes) if a.terms else []
                if full is None:
                    notes.append("bill amount unknown")
                elif amt == 0 and sum(layer_start.get(_layer_key(a, pack), {}).values(), ZERO) == 0:
                    notes.append("nothing left to recover after the earlier payers")
                rule = pack.statutory_rule(p.product_type)
                if rule and rule.payer_note:
                    notes.insert(0, rule.payer_note)
                if second:
                    notes.append("second indemnity payer: legalised copies and the first payer's settlement letter")
                steps.append(AllocationStep(order=len(steps) + 1, policy_id=a.policy_id, payer_type=payer_type.get(a.policy_id, "STATUTORY" if a.rule_id else "PRIMARY"),
                                            basis=Basis.INDEMNITY, amount=amt, currency=currency, presented=pres, documents_required=docs,
                                            filing_deadline=deadline, clause_ids=(a.terms.clause_ids if a.terms else a.fired) or a.fired,
                                            rule_id=a.rule_id, note="; ".join(notes)[:400] or None))
                indemnity_payers += 1
            else:
                docs, _ = required_documents(p, facts)
                steps.append(AllocationStep(order=len(steps) + 1, policy_id=a.policy_id, payer_type="FIXED_BENEFIT", basis=Basis.FIXED_BENEFIT,
                                            amount=a.payable, currency=currency, documents_required=docs, filing_deadline=deadline, clause_ids=a.fired,
                                            note="fixed benefit: claim in parallel with its own form and copies; stacks with indemnity recovery"))
        elif a.status == "UNCERTAIN":
            potential: Optional[Decimal] = None
            if a.basis == Basis.INDEMNITY and a.terms is not None and full is not None:
                start = layer_start.get(_layer_key(a, pack), remainder)
                potential = a.terms.capacity(start)[0]
            docs, _ = required_documents(p, facts, second_indemnity_payer=(a.basis == Basis.INDEMNITY and indemnity_payers >= 1)) if a.event else ([], [])
            note = a.note or ("payable only if the open question resolves in your favour; amount shown is the remainder it could cover" if a.basis == Basis.INDEMNITY else None)
            uncertain.append(UncertainPolicy(policy_id=a.policy_id, basis=a.basis or Basis.INDEMNITY, slots=a.slots, potential_amount=potential,
                                             clause_ids=(a.terms.clause_ids if a.terms else a.fired) or a.fired, documents_required=docs,
                                             filing_deadline=deadline, rule_id=a.rule_id, note=note))
        else:
            excluded.append(ExcludedPolicy(policy_id=a.policy_id, code=a.code or "EXCLUDED", basis=a.basis, clause_ids=a.fired,
                                           filing_deadline=deadline, rule_id=a.rule_id, note=a.note))

    # ---- totals and baselines
    indemnity_total = sum((s.amount for s in steps if s.basis == Basis.INDEMNITY and s.amount is not None), ZERO)
    fixed_total = sum((s.amount for s in steps if s.basis == Basis.FIXED_BENEFIT and s.amount is not None), ZERO)
    greedy: Optional[Decimal] = None
    single: Optional[Decimal] = None
    if full is not None:
        elig = sorted([a for a in assessed if a.status == "ELIGIBLE" and a.basis == Basis.INDEMNITY and a.terms is not None], key=lambda a: a.holdings_index)
        greedy = _total(_sequential([a.terms for a in elig], full)[0]) + fixed_total
        singles = [a.terms.capacity(full)[0] for a in elig] + [s.amount for s in steps if s.basis == Basis.FIXED_BENEFIT and s.amount is not None]
        single = max(singles) if singles else ZERO
    solver = "none" if not solvers else (next(iter(solvers)) if len(solvers) == 1 else "mixed")
    return AllocationResult(
        steps=steps, total_recovered=indemnity_total + fixed_total, indemnity_total=indemnity_total, fixed_benefit_total=fixed_total,
        out_of_pocket=(max(ZERO, bill.total - indemnity_total) if bill is not None else None), greedy_total=greedy, single_policy_total=single,
        uncertain=uncertain, excluded=excluded, circular_excess=circular, circular_clause_ids=list(dict.fromkeys(circular_ids)),
        rule_pack=pack.code, bill_total=bill.total if bill is not None else None, currency=currency, evaluation_order=order, solver=solver,
        notes=(["greedy_total ignores the coordination rules (naive claiming order); it can exceed the rule-bound optimum only by breaching a rule"]
               if greedy is not None and greedy > indemnity_total + fixed_total else []),
    )
