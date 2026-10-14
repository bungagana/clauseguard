"""Entitlement timeline: every dated event in a household's policies and open claims, with the
money that turns on it. Pure Python, deterministic; built only from typed qualifiers.

Formulation
-----------
For each policy p with anchor dates (effective e_p, issue i_p, reinstatement r_p, expiry x_p)
and each HAS_PERIOD tuple t with a window (n, unit, from), the event date is

    d(t) = anchor(from) + n units,   anchor(EFFECTIVE) = e_p, anchor(ISSUE) = i_p,
                                     anchor(REINSTATEMENT) = r_p (else e_p)

and kind(t) maps the period kind: WAITING -> WAITING_ENDS, WAITING_SPECIFIED ->
SPECIFIED_WAITING_ENDS, CONTESTABILITY -> CONTESTABILITY_ENDS. A policy in grace with a known
premium due date u_p yields GRACE_ENDS at u_p + grace days (from its GRACE tuple, else
`grace_days`); its expiry date yields POLICY_EXPIRES. For each open claim c on policy p with a
FILING_DEADLINE tuple (k days from anchor a) the event is FILING_DEADLINE at date(a) + k, and
a SURVIVAL tuple on a critical-illness claim yields SURVIVAL_PERIOD_ENDS at diagnosis + n.

money_at_risk is the claim amount for FILING_DEADLINE and SURVIVAL_PERIOD_ENDS, and the cover
at stake (sum assured, else the largest annual limit or benefit amount of the policy) for
GRACE_ENDS and POLICY_EXPIRES. days_left = d - as_of (negative when the date has passed).
Events dated before `as_of` are dropped except GRACE_ENDS and FILING_DEADLINE, whose passing is
itself the risk. The list is sorted by date, then policy id, then kind.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from pydantic import Field

from .agent.derive import filing_deadline, survival_end
from .portfolio import ACTIVE_STATUSES, add_months, exclusion_window_end, filing_deadline_tuple
from .schema import ClauseTuple, EventCode, PeriodKind, PolicyRecord, Relation, Strict, TimeUnit, WindowFrom

KINDS = ("WAITING_ENDS", "SPECIFIED_WAITING_ENDS", "GRACE_ENDS", "FILING_DEADLINE", "SURVIVAL_PERIOD_ENDS", "POLICY_EXPIRES", "CONTESTABILITY_ENDS")
PERIOD_TO_KIND = {
    PeriodKind.WAITING: "WAITING_ENDS",
    PeriodKind.WAITING_SPECIFIED: "SPECIFIED_WAITING_ENDS",
    PeriodKind.CONTESTABILITY: "CONTESTABILITY_ENDS",
}
PAST_KINDS_KEPT = {"GRACE_ENDS", "FILING_DEADLINE"}
CI_EVENTS = {EventCode.CRITICAL_ILLNESS.value, EventCode.TERMINAL_ILLNESS.value}


class OpenClaim(Strict):
    """A claim not yet filed. Dates are the claim's own anchors; `amount` is what the claim is worth
    (the solver's payable, or the indemnity amount expected from this policy)."""

    claim_id: str = Field(max_length=40)
    policy_id: str = Field(max_length=40)
    event: str = Field(max_length=40)
    amount: Optional[Decimal] = None
    event_date: Optional[date] = None
    discharge_date: Optional[date] = None
    treatment_end_date: Optional[date] = None
    diagnosis_date: Optional[date] = None
    death_date: Optional[date] = None


class TimelineEvent(Strict):
    date: date
    policy_id: str
    kind: str = Field(pattern="^(" + "|".join(KINDS) + ")$")
    money_at_risk: Optional[Decimal] = None
    days_left: int
    clause_id: Optional[str] = None
    claim_id: Optional[str] = None
    message: str = Field(max_length=300)


# --------------------------------------------------------------------------- helpers
def _fmt(v: Decimal, cur: str) -> str:
    return f"{cur} {int(v):,}"


def cover_at_stake(policy: PolicyRecord) -> Optional[Decimal]:
    """Sum assured, else the largest annual limit / lifetime cap / benefit amount / per-day x days
    among the COVERS tuples (what lapses with the policy)."""
    best: Optional[Decimal] = None
    for t in policy.tuples_by(Relation.COVERS):
        q = t.qualifiers
        cands: list[Decimal] = []
        for v in (q.annual_cap, q.lifetime_cap, q.amount, q.per_case_limit):
            if v is not None:
                cands.append(Decimal(v))
        if q.per_day_limit is not None and (q.max_days_per_year or q.max_days):
            cands.append(Decimal(q.per_day_limit) * (q.max_days_per_year or q.max_days))
        if q.per_week_amount is not None and q.max_weeks:
            cands.append(Decimal(q.per_week_amount) * q.max_weeks)
        if q.pct_of_sum_assured is not None and policy.sum_assured is not None:
            cands.append(policy.sum_assured * Decimal(str(q.pct_of_sum_assured)) / Decimal(100))
        for c in cands:
            if best is None or c > best:
                best = c
    if best is None and policy.sum_assured is not None:
        return policy.sum_assured
    return best.quantize(Decimal("1")) if best is not None else None


def _window_end(policy: PolicyRecord, t: ClauseTuple) -> Optional[date]:
    q = t.qualifiers
    if q.period_kind == PeriodKind.WAITING or t.object == PeriodKind.WAITING.value:
        anchor = policy.reinstatement_date if (q.window_from == WindowFrom.REINSTATEMENT and policy.reinstatement_date) else (policy.effective_date or policy.issue_date)
        if anchor is None:
            return None
        if q.waiting_days is not None:
            return anchor + timedelta(days=int(q.waiting_days))
        if q.window_len is None:
            return None
        unit = q.window_unit or TimeUnit.DAYS
        n = int(q.window_len)
        return add_months(anchor, n) if unit == TimeUnit.MONTHS else (anchor + timedelta(days=n) if unit == TimeUnit.DAYS else date(anchor.year + n, anchor.month, anchor.day))
    return exclusion_window_end(policy, t)


def _period_kind(t: ClauseTuple) -> Optional[PeriodKind]:
    if t.qualifiers.period_kind is not None:
        return t.qualifiers.period_kind
    try:
        return PeriodKind(t.object)
    except ValueError:
        return None


def _grace_days(policy: PolicyRecord) -> tuple[Optional[int], Optional[str]]:
    for t in policy.tuples_by(Relation.HAS_PERIOD):
        if _period_kind(t) == PeriodKind.GRACE:
            q = t.qualifiers
            if q.window_len is not None and q.window_unit in (None, TimeUnit.DAYS):
                return int(q.window_len), t.id
            return policy.grace_days, t.id
    return policy.grace_days, None


def _claim_anchor(anchor: WindowFrom, claim: OpenClaim) -> Optional[date]:
    if anchor in (WindowFrom.DISCHARGE,):
        return claim.discharge_date or claim.treatment_end_date
    if anchor == WindowFrom.TREATMENT_END:
        return claim.treatment_end_date or claim.discharge_date
    if anchor in (WindowFrom.EVENT, WindowFrom.ACCIDENT):
        return claim.event_date or claim.discharge_date
    if anchor == WindowFrom.DEATH:
        return claim.death_date or claim.event_date
    if anchor == WindowFrom.DIAGNOSIS:
        return claim.diagnosis_date or claim.event_date
    return None


# --------------------------------------------------------------------------- main entry
def build_timeline(
    policies: list[PolicyRecord],
    open_claims: list[OpenClaim],
    as_of: date,
    *,
    premium_due: Optional[dict[str, date]] = None,
) -> list[TimelineEvent]:
    """Dated entitlement events for `policies` and `open_claims`, sorted by date (see module doc).
    `premium_due` maps policy id -> the unpaid premium's due date (needed for GRACE_ENDS; the
    policy record itself carries no due date)."""
    premium_due = premium_due or {}
    events: list[TimelineEvent] = []

    def add(d: date, policy: PolicyRecord, kind: str, money: Optional[Decimal], clause_id: Optional[str], message: str, claim_id: Optional[str] = None) -> None:
        left = (d - as_of).days
        if left < 0 and kind not in PAST_KINDS_KEPT:
            return
        events.append(TimelineEvent(date=d, policy_id=policy.id, kind=kind, money_at_risk=money, days_left=left, clause_id=clause_id,
                                    claim_id=claim_id, message=message[:300]))

    for p in policies:
        cur = p.currency
        stake = cover_at_stake(p)
        for t in p.tuples_by(Relation.HAS_PERIOD):
            kind = PERIOD_TO_KIND.get(_period_kind(t))
            if kind is None:
                continue
            d = _window_end(p, t)
            if d is None:
                continue
            if kind == "WAITING_ENDS":
                msg = f"{p.id}: general waiting period ends; illness claims become eligible"
            elif kind == "SPECIFIED_WAITING_ENDS":
                n = len(t.qualifiers.diseases)
                msg = f"{p.id}: waiting period for {n} specified diseases ends" if n else f"{p.id}: specified-disease waiting period ends"
            else:
                msg = f"{p.id}: contestability period ends; the insurer can no longer void the policy for misstatement"
            add(d, p, kind, None, t.id, msg)
        if p.status == "grace":
            days, tid = _grace_days(p)
            due = premium_due.get(p.id)
            if days is not None and due is not None:
                d = due + timedelta(days=int(days))
                money = stake
                tail = f"; {_fmt(money, cur)} of cover lapses" if money is not None else ""
                msg = (f"{p.id}: grace period ends; pay the premium due {due.isoformat()} before this date{tail}" if d >= as_of
                       else f"{p.id}: grace period ended on {d.isoformat()}; the policy lapses unless the premium due {due.isoformat()} is paid now{tail}")
                add(d, p, "GRACE_ENDS", money, tid, msg)
        if p.expiry_date is not None and p.status in ACTIVE_STATUSES:
            add(p.expiry_date, p, "POLICY_EXPIRES", stake, None, f"{p.id}: policy period ends; renew to keep cover" + (f" of {_fmt(stake, cur)}" if stake is not None else ""))

    by_id = {p.id: p for p in policies}
    for c in open_claims:
        p = by_id.get(c.policy_id)
        if p is None:
            continue
        cur = p.currency
        t = filing_deadline_tuple(p)
        if t is not None:
            q = t.qualifiers
            days = q.deadline_days if q.deadline_days is not None else (q.window_len if q.window_unit in (None, TimeUnit.DAYS) else None)
            anchor = _claim_anchor(q.from_event or q.window_from or WindowFrom.DISCHARGE, c)
            if days is not None and anchor is not None:
                d = filing_deadline(anchor, int(days))
                effect = "the claim is rejected" if q.late_effect in (None, "REJECT") else "acceptance is at the insurer's discretion"
                amt = f" ({_fmt(c.amount, cur)} at risk)" if c.amount is not None else ""
                add(d, p, "FILING_DEADLINE", c.amount, t.id, f"{p.id}: file claim {c.claim_id} by this date, after it {effect}{amt}", c.claim_id)
        if c.event in CI_EVENTS and c.diagnosis_date is not None:
            for s in p.tuples_by(Relation.HAS_PERIOD):
                if _period_kind(s) == PeriodKind.SURVIVAL and s.qualifiers.window_len is not None:
                    n = int(s.qualifiers.window_len)
                    unit = s.qualifiers.window_unit or TimeUnit.DAYS
                    d = add_months(c.diagnosis_date, n) if unit == TimeUnit.MONTHS else survival_end(c.diagnosis_date, n)
                    add(d, p, "SURVIVAL_PERIOD_ENDS", c.amount, s.id, f"{p.id}: survival period for claim {c.claim_id} ends; the benefit is payable from this date", c.claim_id)
    events.sort(key=lambda e: (e.date, e.policy_id, e.kind, e.claim_id or ""))
    return events
