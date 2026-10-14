"""Counterfactual recourse over the constraint program.

Given a policy P, bound facts f and the solver's verdict V(f) = DENIED (or NOT_APPLICABLE),
find the smallest sets of *legitimate* fact changes A = {a_1, ..., a_k}, k <= max_changes,
such that V(f after A) = COVERED, and return the Pareto-minimal ones under the cost vector

    c(A) = sum_i c(a_i) = (days, money, effort)        (componentwise, all >= 0)

An option A dominates B when c(A) <= c(B) in every component and c(A) != c(B); only
non-dominated options are returned. The search is breadth-first over the action set
(single actions first, then pairs); a set that already flips the verdict is never
extended, because every strict superset costs at least as much.

Legitimate actions are things the claimant can really do:

* wait until a date (the time slots ``days_since_effective`` / ``months_since_issue`` /
  ``months_since_reinstatement`` advance; the earliest date that flips the verdict is reported)
* provide documents (``documents_present``)
* choose a partner / network facility for a *future* admission
* obtain an emergency classification, only when the facts do not already state otherwise
* settle premium arrears while still inside the grace period (``premium_status`` -> PAID)
* attach a rider for future cover (``rider_attached``)
* claim under another policy of the same portfolio

Nothing about what happened may change. ``IMMUTABLE_SLOTS`` lists the slots that describe the
event itself (cause, dates of a past event, diagnosis, occupation, licence, intoxication, ...);
``MISREPRESENTATION_GUARD`` adds the slots whose value may only be *bound* when unknown, never
flipped once stated. ``guard_change`` enforces both, and every action passes through it.
Deterministic; no language model runs here.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from enum import Enum
from itertools import combinations
from typing import Optional

from pydantic import Field

from .portfolio import (
    ACTIVE_STATUSES,
    add_months,
    decide_mapped,
    required_documents,
    with_policy_defaults,
)
from .schema import (
    SLOT_DOMAINS,
    PeriodKind,
    PolicyRecord,
    Relation,
    Scalar,
    ScenarioFacts,
    Slot,
    Strict,
    TimeUnit,
    Verdict,
    VerdictResult,
    WindowFrom,
)
from .solver import CAUSE_LIKE_OBJECTS

# --------------------------------------------------------------------------- immutability
#: Slots that describe what happened. A recourse never changes them.
IMMUTABLE_SLOTS: frozenset[Slot] = frozenset({
    Slot.EVENT, Slot.CAUSE, Slot.IS_ACCIDENT,
    Slot.DAYS_SINCE_DIAGNOSIS, Slot.DAYS_SINCE_EVENT, Slot.DAYS_SINCE_DISCHARGE,
    Slot.DAYS_SINCE_TREATMENT_END, Slot.DAYS_SINCE_DEATH, Slot.DAYS_OVERDUE,
    Slot.AGE, Slot.AGE_AT_ISSUE, Slot.PLAN, Slot.POLICY_YEAR,
    Slot.DIAGNOSIS_BEFORE_EFFECTIVE, Slot.DISEASE_IN_SPECIFIED_LIST, Slot.SURVIVAL_DAYS,
    Slot.EMPLOYMENT_ACTIVE, Slot.WORK_RELATED, Slot.VEHICLES_INVOLVED, Slot.LICENSE_VALID,
    Slot.OCCUPATION_CLASS, Slot.INTOXICATED, Slot.PILOT_ROLE, Slot.MILITARY_SERVICE,
    Slot.DAYS_HOSPITALIZED, Slot.DAYS_ICU, Slot.BILLED_AMOUNT, Slot.MISREPRESENTATION,
    Slot.LOAN_BALANCE, Slot.CASH_VALUE, Slot.PARTIES_BOTH_DEAD,
})

#: Slots that may be bound only while unknown (a true classification can be obtained; a stated
#: value is never flipped). Together with IMMUTABLE_SLOTS this is the misrepresentation guard.
MISREPRESENTATION_GUARD: frozenset[Slot] = frozenset({Slot.IS_EMERGENCY}) | IMMUTABLE_SLOTS

#: Slots that advance with calendar time (an action of kind WAIT moves them forward only).
TIME_SLOTS: tuple[Slot, ...] = (Slot.DAYS_SINCE_EFFECTIVE, Slot.MONTHS_SINCE_ISSUE, Slot.MONTHS_SINCE_REINSTATEMENT)


class ActionKind(str, Enum):
    WAIT = "WAIT"
    PROVIDE_DOCUMENTS = "PROVIDE_DOCUMENTS"
    CHOOSE_PARTNER_FACILITY = "CHOOSE_PARTNER_FACILITY"
    CHOOSE_NETWORK_FACILITY = "CHOOSE_NETWORK_FACILITY"
    OBTAIN_EMERGENCY_CLASSIFICATION = "OBTAIN_EMERGENCY_CLASSIFICATION"
    SETTLE_ARREARS = "SETTLE_ARREARS"
    ATTACH_RIDER = "ATTACH_RIDER"
    CLAIM_OTHER_POLICY = "CLAIM_OTHER_POLICY"


class ActionCost(Strict):
    """Cost of one action. ``days`` is calendar time until the action takes effect; ``money`` is
    an ordinal 0..3 (0 none, 1 a fee or copy charge, 2 arrears, 3 a new premium); ``effort`` is
    an ordinal 0..3 (forms and visits)."""

    days: int = Field(ge=0, default=0)
    money: int = Field(ge=0, le=3, default=0)
    effort: int = Field(ge=0, le=3, default=0)

    def __add__(self, other: "ActionCost") -> "ActionCost":
        return ActionCost(days=self.days + other.days, money=min(3, self.money + other.money), effort=min(3, self.effort + other.effort))

    def as_tuple(self) -> tuple[int, int, int]:
        return (self.days, self.money, self.effort)


#: Base cost per action kind (time is added per action from the date arithmetic).
COST_TABLE: dict[ActionKind, ActionCost] = {
    ActionKind.WAIT: ActionCost(days=0, money=0, effort=0),
    ActionKind.PROVIDE_DOCUMENTS: ActionCost(days=3, money=1, effort=1),
    ActionKind.CHOOSE_PARTNER_FACILITY: ActionCost(days=0, money=0, effort=2),
    ActionKind.CHOOSE_NETWORK_FACILITY: ActionCost(days=0, money=0, effort=2),
    ActionKind.OBTAIN_EMERGENCY_CLASSIFICATION: ActionCost(days=2, money=0, effort=1),
    ActionKind.SETTLE_ARREARS: ActionCost(days=1, money=2, effort=1),
    ActionKind.ATTACH_RIDER: ActionCost(days=0, money=3, effort=2),
    ActionKind.CLAIM_OTHER_POLICY: ActionCost(days=0, money=0, effort=1),
}


class FactChange(Strict):
    slot: Slot
    from_value: Scalar = None
    to_value: Scalar = None


class RecourseAction(Strict):
    kind: ActionKind
    changes: list[FactChange] = Field(default_factory=list)
    description: str = Field(max_length=300)
    cost: ActionCost = Field(default_factory=ActionCost)
    earliest_date: Optional[date] = None
    deadline: Optional[date] = None
    documents: list[str] = Field(default_factory=list)
    other_policy_id: Optional[str] = None


class RecourseOption(Strict):
    policy_id: str
    actions: list[RecourseAction]
    verdict: Verdict
    payable: Optional[Decimal] = None
    currency: Optional[str] = None
    clause_ids: list[str] = Field(default_factory=list)
    cost: ActionCost
    description: str = Field(max_length=600)

    @property
    def n_changes(self) -> int:
        return len(self.actions)


class RecourseResult(Strict):
    policy_id: str
    baseline_verdict: Verdict
    baseline_denial_code: Optional[str] = None
    options: list[RecourseOption] = Field(default_factory=list)
    blocked_by_immutable: list[Slot] = Field(default_factory=list, description="slots the denial depends on that no legitimate action may change")
    notes: list[str] = Field(default_factory=list)
    searched: int = 0

    @property
    def has_recourse(self) -> bool:
        return bool(self.options)

    def best(self) -> Optional[RecourseOption]:
        """Lowest (days, money, effort, number of actions); None if no option."""
        if not self.options:
            return None
        return min(self.options, key=lambda o: o.cost.as_tuple() + (len(o.actions),))


class GuardViolation(ValueError):
    """Raised when a proposed change touches a slot the guard protects."""


def guard_change(change: FactChange, facts: ScenarioFacts) -> None:
    """Reject a change that would misrepresent what happened.

    * an IMMUTABLE slot is never changed;
    * a slot in MISREPRESENTATION_GUARD that is already bound is never flipped;
    * a TIME slot may only move forward (waiting), never backward.
    """
    if change.slot in IMMUTABLE_SLOTS:
        raise GuardViolation(f"{change.slot.value} describes what happened and cannot be changed")
    if change.slot in MISREPRESENTATION_GUARD and facts.has(change.slot) and facts.get(change.slot) != change.to_value:
        raise GuardViolation(f"{change.slot.value} is stated as {facts.get(change.slot)!r}; a recourse never contradicts a stated fact")
    if change.slot in TIME_SLOTS and facts.has(change.slot):
        try:
            if float(change.to_value) < float(facts.get(change.slot)):  # type: ignore[arg-type]
                raise GuardViolation(f"{change.slot.value} can only advance")
        except (TypeError, ValueError):
            raise GuardViolation(f"{change.slot.value} must be numeric")


def apply_action(facts: ScenarioFacts, action: RecourseAction) -> ScenarioFacts:
    """Facts after the action; every change passes the guard."""
    f = facts
    for ch in action.changes:
        guard_change(ch, facts)
        f = f.bind(ch.slot, ch.to_value)
    return f


# --------------------------------------------------------------------------- date helpers
def _fmt_money(v: Optional[Decimal], cur: Optional[str]) -> str:
    if v is None:
        return "amount per the benefit schedule"
    return f"{cur or 'IDR'} {int(Decimal(v)):,}"


def _time_thresholds(policy: PolicyRecord, slot: Slot, *, bound: bool) -> list[int]:
    """Candidate values of a time slot at which a window or waiting period ends, read from the
    policy's typed qualifiers; when the slot is bound the slot's default domain is added so a
    window expressed in another unit is still probed. Sorted, de-duplicated."""
    vals: set[int] = set(int(v) for v in SLOT_DOMAINS.get(slot, []) if isinstance(v, (int, float))) if bound else set()
    for t in policy.tuples:
        q = t.qualifiers
        if t.relation == Relation.HAS_PERIOD and (q.period_kind == PeriodKind.WAITING or t.object == PeriodKind.WAITING.value):
            wd = q.waiting_days if q.waiting_days is not None else q.window_len
            if wd is not None and slot == Slot.DAYS_SINCE_EFFECTIVE:
                vals.add(int(wd))
        if q.window_len is None:
            continue
        unit = q.window_unit or TimeUnit.MONTHS
        anchor = q.window_from or WindowFrom.ISSUE
        n = int(q.window_len)
        if anchor in (WindowFrom.ISSUE, WindowFrom.EFFECTIVE, WindowFrom.RIDER_START):
            if unit == TimeUnit.DAYS and slot == Slot.DAYS_SINCE_EFFECTIVE:
                vals.add(n)
            elif unit == TimeUnit.MONTHS and slot == Slot.MONTHS_SINCE_ISSUE:
                vals.add(n)
            elif unit == TimeUnit.YEARS and slot == Slot.MONTHS_SINCE_ISSUE:
                vals.add(n * 12)
        elif anchor == WindowFrom.REINSTATEMENT and slot == Slot.MONTHS_SINCE_REINSTATEMENT:
            vals.add(n if unit == TimeUnit.MONTHS else (n * 12 if unit == TimeUnit.YEARS else -(-n // 30)))
    return sorted(vals)


def _date_when(policy: PolicyRecord, slot: Slot, current: Optional[float], target: int, as_of: date) -> date:
    """Calendar date at which `slot` reaches `target`, anchored on the policy's own dates when
    known, otherwise on `as_of` plus the remaining distance."""
    if slot == Slot.DAYS_SINCE_EFFECTIVE:
        if policy.effective_date:
            return policy.effective_date + timedelta(days=target)
        return as_of + timedelta(days=max(0, target - int(current or 0)))
    if slot == Slot.MONTHS_SINCE_ISSUE:
        anchor = policy.issue_date or policy.effective_date
        if anchor:
            return add_months(anchor, target)
        return add_months(as_of, max(0, target - int(current or 0)))
    anchor = policy.reinstatement_date
    if anchor:
        return add_months(anchor, target)
    return add_months(as_of, max(0, target - int(current or 0)))


# --------------------------------------------------------------------------- action generators
def _wait_actions(policy: PolicyRecord, facts: ScenarioFacts, as_of: date) -> list[RecourseAction]:
    """One WAIT action per (time slot, threshold) strictly beyond the current value."""
    out: list[RecourseAction] = []
    for slot in TIME_SLOTS:
        current = float(facts.get(slot)) if facts.has(slot) else None
        if slot == Slot.MONTHS_SINCE_REINSTATEMENT and not facts.has(slot):
            continue
        for target in _time_thresholds(policy, slot, bound=current is not None):
            if current is not None and target <= current:
                continue
            when = _date_when(policy, slot, current, target, as_of)
            unit = "days" if slot == Slot.DAYS_SINCE_EFFECTIVE else "months"
            if when <= as_of:
                # the window has already closed in calendar time: the facts describe an event inside it
                desc = f"The {target}-{unit[:-1]} waiting period or window ended on {when.isoformat()}; a new admission or event on or after today ({as_of.isoformat()}) is outside it."
                when = as_of
            else:
                desc = f"Wait until {when.isoformat()} ({target} {unit} from the policy's start): an admission or event on or after that date is outside this waiting period or window."
            changes = [FactChange(slot=slot, from_value=facts.values.get(slot), to_value=target)]
            # keep the paired time slots coherent (days <-> months of the same anchor)
            if slot == Slot.DAYS_SINCE_EFFECTIVE and facts.has(Slot.MONTHS_SINCE_ISSUE):
                m = max(int(facts.get(Slot.MONTHS_SINCE_ISSUE)), target // 30)  # type: ignore[arg-type]
                changes.append(FactChange(slot=Slot.MONTHS_SINCE_ISSUE, from_value=facts.get(Slot.MONTHS_SINCE_ISSUE), to_value=m))
            if slot == Slot.MONTHS_SINCE_ISSUE and facts.has(Slot.DAYS_SINCE_EFFECTIVE):
                d = max(int(facts.get(Slot.DAYS_SINCE_EFFECTIVE)), target * 30)  # type: ignore[arg-type]
                changes.append(FactChange(slot=Slot.DAYS_SINCE_EFFECTIVE, from_value=facts.get(Slot.DAYS_SINCE_EFFECTIVE), to_value=d))
            out.append(RecourseAction(
                kind=ActionKind.WAIT, changes=changes, earliest_date=when,
                cost=COST_TABLE[ActionKind.WAIT] + ActionCost(days=max(0, (when - as_of).days)), description=desc,
            ))
    return out


def _facility_actions(policy: PolicyRecord, facts: ScenarioFacts) -> list[RecourseAction]:
    out: list[RecourseAction] = []
    used = {c.slot for t in policy.tuples for c in t.qualifiers.applies_if}
    for slot, kind, label in ((Slot.FACILITY_BPJS_PARTNER, ActionKind.CHOOSE_PARTNER_FACILITY, "BPJS partner facility"),
                              (Slot.FACILITY_IN_NETWORK, ActionKind.CHOOSE_NETWORK_FACILITY, "network facility")):
        if slot not in used:
            continue
        if facts.has(slot) and bool(facts.get(slot)):
            continue
        out.append(RecourseAction(
            kind=kind, changes=[FactChange(slot=slot, from_value=facts.values.get(slot), to_value=True)],
            cost=COST_TABLE[kind],
            description=f"For a future admission choose a {label} (or arrange a transfer once stable); the past admission's facility cannot be changed.",
        ))
    return out


def _emergency_action(policy: PolicyRecord, facts: ScenarioFacts) -> list[RecourseAction]:
    """Only when the facts do not state whether the admission was an emergency."""
    if facts.has(Slot.IS_EMERGENCY):
        return []
    touches = any(c.slot == Slot.IS_EMERGENCY for t in policy.tuples for c in t.qualifiers.applies_if) or any(
        (t.qualifiers.period_kind == PeriodKind.WAITING or t.object == PeriodKind.WAITING.value) for t in policy.tuples_by(Relation.HAS_PERIOD))
    if not touches:
        return []
    return [RecourseAction(
        kind=ActionKind.OBTAIN_EMERGENCY_CLASSIFICATION,
        changes=[FactChange(slot=Slot.IS_EMERGENCY, from_value=None, to_value=True)],
        cost=COST_TABLE[ActionKind.OBTAIN_EMERGENCY_CLASSIFICATION],
        description="If, and only if, the admission was in fact an emergency, obtain the emergency-unit note or doctor's classification stating so.",
    )]


def _arrears_action(policy: PolicyRecord, facts: ScenarioFacts, as_of: date) -> list[RecourseAction]:
    status = facts.get(Slot.PREMIUM_STATUS) if facts.has(Slot.PREMIUM_STATUS) else None
    if status == "PAID":
        return []
    grace = None
    for t in policy.tuples_by(Relation.HAS_PERIOD):
        if t.qualifiers.period_kind == PeriodKind.GRACE or t.object == PeriodKind.GRACE.value:
            grace = t.qualifiers.window_len
    grace = grace if grace is not None else policy.grace_days
    overdue = int(facts.get(Slot.DAYS_OVERDUE)) if facts.has(Slot.DAYS_OVERDUE) else None  # type: ignore[arg-type]
    statutory = policy.product_type == "social_bpjs_kes"
    deadline: Optional[date] = None
    if grace is not None and overdue is not None:
        if overdue > int(grace) and not statutory:
            return []  # grace period already ended: reinstatement is an underwriting decision, not a fact change
        deadline = as_of + timedelta(days=int(grace) - overdue)
    elif status == "LAPSED" and not statutory:
        return []
    changes = [FactChange(slot=Slot.PREMIUM_STATUS, from_value=status, to_value="PAID")]
    if facts.has(Slot.IN_FORCE) and not bool(facts.get(Slot.IN_FORCE)):
        changes.append(FactChange(slot=Slot.IN_FORCE, from_value=False, to_value=True))
    if statutory:
        desc = "Settle the outstanding contributions to reactivate the membership; cover resumes for admissions after reactivation (a reactivation service fee may apply)."
    else:
        desc = f"Pay the arrears before the grace period ends on {deadline.isoformat()}: the policy stays in force and the claim is assessed normally." if deadline else "Pay the arrears while the policy is still inside its grace period."
    return [RecourseAction(kind=ActionKind.SETTLE_ARREARS, changes=changes, cost=COST_TABLE[ActionKind.SETTLE_ARREARS], deadline=deadline, description=desc)]


def _rider_action(policy: PolicyRecord, facts: ScenarioFacts) -> list[RecourseAction]:
    rider_heads = {t.head for t in policy.tuples if t.head != policy.id}
    if not rider_heads and not policy.riders:
        return []
    if facts.has(Slot.RIDER_ATTACHED) and bool(facts.get(Slot.RIDER_ATTACHED)):
        return []
    if not facts.has(Slot.RIDER_ATTACHED) and all(r.attached for r in policy.riders) and policy.riders:
        return []
    return [RecourseAction(
        kind=ActionKind.ATTACH_RIDER, changes=[FactChange(slot=Slot.RIDER_ATTACHED, from_value=facts.values.get(Slot.RIDER_ATTACHED), to_value=True)],
        cost=COST_TABLE[ActionKind.ATTACH_RIDER],
        description="Attach the rider for future cover (its own waiting period will run from the rider start date); it cannot cover an event that already happened.",
    )]


def candidate_actions(policy: PolicyRecord, facts: ScenarioFacts, as_of: date) -> list[RecourseAction]:
    """All single legitimate actions for this policy and these facts (every change guarded)."""
    acts = _wait_actions(policy, facts, as_of) + _facility_actions(policy, facts) + _emergency_action(policy, facts) \
        + _arrears_action(policy, facts, as_of) + _rider_action(policy, facts)
    ok: list[RecourseAction] = []
    for a in acts:
        try:
            for ch in a.changes:
                guard_change(ch, facts)
        except GuardViolation:
            continue
        ok.append(a)
    return ok


def document_recourse(policy: PolicyRecord, facts: ScenarioFacts, documents_present: list[str]) -> Optional[RecourseAction]:
    """PROVIDE_DOCUMENTS action listing the required documents not yet present; None if complete."""
    docs, _ = required_documents(policy, facts)
    present = {d.strip().upper() for d in documents_present}
    missing = [d for d in docs if d.upper() not in present]
    if not missing:
        return None
    return RecourseAction(
        kind=ActionKind.PROVIDE_DOCUMENTS, changes=[], documents=missing, cost=COST_TABLE[ActionKind.PROVIDE_DOCUMENTS],
        description="Provide the missing documents: " + ", ".join(d.replace("_", " ").lower() for d in missing) + ".",
    )


# --------------------------------------------------------------------------- search
def _pareto(options: list[RecourseOption]) -> list[RecourseOption]:
    keep: list[RecourseOption] = []
    for o in options:
        co = o.cost.as_tuple() + (len(o.actions),)
        dominated = False
        for p in options:
            if p is o:
                continue
            cp = p.cost.as_tuple() + (len(p.actions),)
            if all(a <= b for a, b in zip(cp, co)) and cp != co:
                dominated = True
                break
        if not dominated and not any(k.cost == o.cost and [a.description for a in k.actions] == [a.description for a in o.actions] for k in keep):
            keep.append(o)
    return sorted(keep, key=lambda o: o.cost.as_tuple() + (len(o.actions),))


def _option(policy: PolicyRecord, actions: list[RecourseAction], r: VerdictResult) -> RecourseOption:
    cost = ActionCost()
    for a in actions:
        cost = cost + a.cost
    desc = " Then ".join(a.description for a in actions) if len(actions) > 1 else actions[0].description
    desc += f" Result: {r.verdict.value}, {_fmt_money(r.payable, r.currency)} (clauses {', '.join(r.fired_tuple_ids) or 'n/a'})."
    return RecourseOption(policy_id=policy.id, actions=actions, verdict=r.verdict, payable=r.payable, currency=r.currency,
                          clause_ids=list(r.fired_tuple_ids), cost=cost, description=desc[:600])


def _dependency_slots(policy: PolicyRecord, baseline: VerdictResult) -> set[Slot]:
    """Slots the fired denial tuples condition on (for the blocked_by_immutable report)."""
    idx = policy.tuple_index()
    slots: set[Slot] = set()
    for tid in baseline.fired_tuple_ids:
        t = idx.get(tid)
        if t is None:
            continue
        slots |= {c.slot for c in t.qualifiers.applies_if}
        if t.relation == Relation.EXCLUDES:
            slots.add(Slot.CAUSE if t.object in CAUSE_LIKE_OBJECTS else Slot.EVENT)
            for ex in policy.tuples_by(Relation.EXCEPTS):
                if ex.object == t.id:
                    slots |= {c.slot for c in ex.qualifiers.applies_if}
        kind = t.qualifiers.period_kind
        if kind == PeriodKind.SURVIVAL:
            slots.add(Slot.SURVIVAL_DAYS)
        if kind == PeriodKind.WAITING_SPECIFIED:
            slots.add(Slot.DISEASE_IN_SPECIFIED_LIST)
        if kind == PeriodKind.CONTESTABILITY:
            slots.add(Slot.MISREPRESENTATION)
    return slots


def find_recourse(
    policy: PolicyRecord,
    facts: ScenarioFacts,
    *,
    as_of: date,
    max_changes: int = 2,
    portfolio: Optional[list[PolicyRecord]] = None,
    facts_by_policy: Optional[dict[str, ScenarioFacts]] = None,
) -> RecourseResult:
    """Pareto-minimal sets of at most `max_changes` legitimate actions that turn the verdict
    into COVERED. `portfolio` (other policies of the same person) adds CLAIM_OTHER_POLICY
    options evaluated on `facts_by_policy[other.id]` when given, else on `facts`."""
    facts = with_policy_defaults(policy, facts)
    baseline = decide_mapped(policy, facts)
    res = RecourseResult(policy_id=policy.id, baseline_verdict=baseline.verdict, baseline_denial_code=baseline.denial_code)
    if baseline.verdict == Verdict.COVERED:
        res.notes.append("already covered; no recourse needed")
        return res
    if baseline.verdict in (Verdict.CLARIFY, Verdict.NOT_SPECIFIED):
        res.notes.append(f"verdict is {baseline.verdict.value}: bind the open facts before searching for recourse")
        return res

    actions = candidate_actions(policy, facts, as_of)
    found: list[RecourseOption] = []
    searched = 0
    successful: list[frozenset[int]] = []
    # smallest WAIT threshold per time slot that flipped the verdict on its own: a longer wait on
    # the same slot is dominated (same or later date, same other actions)
    wait_floor: dict[Slot, int] = {}

    def _wait_dominated(a: RecourseAction) -> bool:
        if a.kind != ActionKind.WAIT:
            return False
        ch = a.changes[0]
        return ch.slot in wait_floor and int(ch.to_value) > wait_floor[ch.slot]  # type: ignore[arg-type]

    for k in range(1, max(1, max_changes) + 1):
        for combo in combinations(range(len(actions)), k):
            key = frozenset(combo)
            if any(s <= key for s in successful):
                continue  # a superset of a flipping set is dominated
            chosen = [actions[i] for i in combo]
            if any(_wait_dominated(a) for a in chosen):
                continue
            slots_touched = [ch.slot for a in chosen for ch in a.changes]
            if len(slots_touched) != len(set(slots_touched)):
                continue  # two actions on the same slot are not one coherent plan
            f = facts
            try:
                for a in chosen:
                    f = apply_action(f, a)
            except GuardViolation:
                continue
            searched += 1
            r = decide_mapped(policy, f)
            if r.verdict == Verdict.COVERED:
                successful.append(key)
                found.append(_option(policy, chosen, r))
                if k == 1 and chosen[0].kind == ActionKind.WAIT:
                    ch = chosen[0].changes[0]
                    wait_floor[ch.slot] = min(wait_floor.get(ch.slot, int(ch.to_value)), int(ch.to_value))  # type: ignore[arg-type]
    res.searched = searched

    if portfolio:
        for other in portfolio:
            if other.id == policy.id or other.status not in ACTIVE_STATUSES:
                continue
            of = (facts_by_policy or {}).get(other.id, facts)
            of = with_policy_defaults(other, of)
            try:
                r = decide_mapped(other, of)
            except Exception:  # noqa: BLE001 - a malformed other policy must not hide this policy's recourse
                continue
            if r.verdict == Verdict.COVERED:
                a = RecourseAction(kind=ActionKind.CLAIM_OTHER_POLICY, cost=COST_TABLE[ActionKind.CLAIM_OTHER_POLICY], other_policy_id=other.id,
                                   description=f"Claim the same event under {other.id} ({other.product_name}), which covers it on the stated facts.")
                opt = _option(other, [a], r)
                found.append(opt.model_copy(update={"policy_id": policy.id}))

    # two Pareto fronts: actions on this policy, and claiming elsewhere. A cheaper alternative
    # policy must not hide a legitimate recourse on the policy that was denied.
    on_policy = [o for o in found if not any(a.kind == ActionKind.CLAIM_OTHER_POLICY for a in o.actions)]
    elsewhere = [o for o in found if any(a.kind == ActionKind.CLAIM_OTHER_POLICY for a in o.actions)]
    res.options = _pareto(on_policy) + _pareto(elsewhere)
    deps = _dependency_slots(policy, baseline)
    res.blocked_by_immutable = sorted((s for s in deps if s in IMMUTABLE_SLOTS), key=lambda s: s.value)
    if not res.options:
        if res.blocked_by_immutable:
            res.notes.append("the denial depends only on facts about what happened (" + ", ".join(s.value for s in res.blocked_by_immutable) + "); no legitimate change of circumstances flips it")
        else:
            res.notes.append("no set of up to %d legitimate actions flips the verdict" % max_changes)
    return res


__all__ = [
    "ActionCost", "ActionKind", "COST_TABLE", "FactChange", "GuardViolation", "IMMUTABLE_SLOTS", "MISREPRESENTATION_GUARD",
    "RecourseAction", "RecourseOption", "RecourseResult", "TIME_SLOTS", "apply_action", "candidate_actions", "document_recourse",
    "find_recourse", "guard_change",
]
