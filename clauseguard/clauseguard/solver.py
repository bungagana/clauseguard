"""Deterministic coverage solver. The LLM never runs here.

verdict(policy, facts):
  1. candidates = COVERS tuples for the event whose applies_if hold
  2. closed world: no candidate and no governing EXCLUDES/PERIOD/TERMINATES -> NOT_APPLICABLE
     (NOT_SPECIFIED if the document's extraction coverage is low)
  3. any EXCLUDES on event/cause whose window & conditions hold and is not EXCEPTED -> DENIED
  4. any unmet CONDITIONED_ON / HAS_PERIOD (waiting, grace, survival, contestability) -> DENIED
  5. TERMINATES_IF holds -> DENIED
  6. else COVERED (+ payable from PAYS / limits)
Precedence: exception > exclusion > condition > coverage; rider tuples scope to the rider.

Clarification by verdict sensitivity: if evaluation touches an unbound slot, re-run over
that slot's domain; if the verdict is invariant, proceed; if it changes, return CLARIFY
naming exactly that slot and the verdict under each value.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from .schema import (
    SLOT_DOMAINS,
    TIER_RANK,
    ClarificationRequest,
    ClauseTuple,
    Condition,
    EventCode,
    MissingSlot,
    Op,
    PeriodKind,
    PolicyRecord,
    Qualifiers,
    Relation,
    ScenarioFacts,
    Slot,
    TimeUnit,
    TraceStep,
    Verdict,
    VerdictResult,
    WindowFrom,
)

from .unmodeled import relevant_unmodeled  # noqa: E402

NOT_SPECIFIED_COVERAGE_THRESHOLD = 0.6

# Policy actions (not benefits): governed by PERMITS tuples, not by benefit periods.
ACTION_EVENTS = {
    EventCode.POLICY_LOAN.value,
    EventCode.SURRENDER.value,
    EventCode.PARTIAL_WITHDRAWAL.value,
    EventCode.CONVERSION.value,
    EventCode.REINSTATEMENT.value,
    EventCode.FREE_LOOK.value,
}

# Causes that count as "accident" for waiting-period exemptions etc.
ACCIDENT_CAUSES = {"ACCIDENT", "ACCIDENT_TRAFFIC", "ACCIDENT_WORK", "ACCIDENT_OTHER"}

# Events that an EXCLUDES tuple on a *cause* can block (cause-based exclusions apply to any benefit).
CAUSE_LIKE_OBJECTS = {
    EventCode.SUICIDE.value,
    EventCode.WAR.value,
    EventCode.AVIATION.value,
    EventCode.INTOXICATION.value,
    EventCode.HAZARDOUS_ACTIVITY.value,
    EventCode.CRIMINAL_ACT.value,
    EventCode.NO_VALID_LICENSE.value,
    EventCode.COMMERCIAL_MOTORCYCLING.value,
    EventCode.PRE_EXISTING_CONDITION.value,
    EventCode.SPECIFIED_DISEASE.value,
    EventCode.MISREPRESENTATION.value,
}


# --------------------------------------------------------------------------- condition logic
def eval_condition(c: Condition, facts: ScenarioFacts) -> bool:
    v = facts.get(c.slot)  # raises MissingSlot
    if c.op == Op.IS_TRUE:
        return bool(v)
    if c.op == Op.IS_FALSE:
        return not bool(v)
    if c.op == Op.IN:
        return v in (c.value or [])
    if c.op == Op.NOT_IN:
        return v not in (c.value or [])
    if c.op == Op.EQ:
        return v == c.value
    if c.op == Op.NE:
        return v != c.value
    try:
        a, b = float(v), float(c.value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return False
    return {Op.LT: a < b, Op.LE: a <= b, Op.GT: a > b, Op.GE: a >= b}[c.op]


def all_hold(conds: list[Condition], facts: ScenarioFacts) -> bool:
    """A conjunction with one definitely false member is false whatever the unbound members are."""
    unknown: Optional[MissingSlot] = None
    for c in conds:
        try:
            if not eval_condition(c, facts):
                return False
        except MissingSlot as e:
            unknown = unknown or e
    if unknown is not None:
        raise unknown
    return True


def _elapsed_for(q: Qualifiers, facts: ScenarioFacts) -> Optional[float]:
    """Elapsed time in the window's unit, for the window's anchor. None if no window."""
    if q.window_len is None:
        return None
    anchor = q.window_from or WindowFrom.ISSUE
    unit = q.window_unit or TimeUnit.MONTHS
    if anchor in (WindowFrom.ISSUE, WindowFrom.EFFECTIVE):
        if unit == TimeUnit.DAYS:
            return float(facts.get(Slot.DAYS_SINCE_EFFECTIVE))
        m = float(facts.get(Slot.MONTHS_SINCE_ISSUE))
        return m / 12 if unit == TimeUnit.YEARS else m
    if anchor == WindowFrom.REINSTATEMENT:
        slot = Slot.MONTHS_SINCE_REINSTATEMENT if facts.has(Slot.MONTHS_SINCE_REINSTATEMENT) else Slot.MONTHS_SINCE_ISSUE
        m = float(facts.get(slot))
        if unit == TimeUnit.DAYS:
            return m * 30.4
        return m / 12 if unit == TimeUnit.YEARS else m
    mapping = {
        WindowFrom.DIAGNOSIS: Slot.DAYS_SINCE_DIAGNOSIS,
        WindowFrom.EVENT: Slot.DAYS_SINCE_EVENT,
        WindowFrom.ACCIDENT: Slot.DAYS_SINCE_EVENT,
        WindowFrom.DISCHARGE: Slot.DAYS_SINCE_DISCHARGE,
        WindowFrom.TREATMENT_END: Slot.DAYS_SINCE_TREATMENT_END,
        WindowFrom.DEATH: Slot.DAYS_SINCE_DEATH,
        WindowFrom.PREMIUM_DUE: Slot.DAYS_OVERDUE,
        WindowFrom.RIDER_START: Slot.MONTHS_SINCE_ISSUE,
    }
    d = float(facts.get(mapping[anchor]))
    if unit == TimeUnit.DAYS:
        return d
    return d / 30.4 if unit == TimeUnit.MONTHS else d / 365.0


def window_active(q: Qualifiers, facts: ScenarioFacts) -> bool:
    """True if the scenario falls *inside* the tuple's time window (e.g. within 24 months)."""
    e = _elapsed_for(q, facts)
    if e is None:
        return True  # no window -> always applies
    return e < float(q.window_len)  # strictly inside; boundary day counts as outside


def _event_matches(obj: str, facts: ScenarioFacts) -> bool:
    ev = facts.get(Slot.EVENT)
    return obj == ev


def _cause_matches(obj: str, facts: ScenarioFacts) -> bool:
    if not facts.has(Slot.CAUSE):
        raise MissingSlot(Slot.CAUSE)
    return obj == facts.get(Slot.CAUSE)


def _icd10_in_entry(code: str, entry: str) -> bool:
    """`entry` is either one code ("I21", "N18.5") or a chapter range ("C00-C97")."""
    chapter, numeric = code[0], code[1:]
    if "-" in entry:
        lo, hi = entry.split("-", 1)
        if chapter != lo[0] or chapter != hi[0]:
            return False
        try:
            return float(lo[1:]) <= float(numeric) <= float(hi[1:])
        except ValueError:
            return False
    return code == entry or code.startswith(entry + ".") or (entry[0] == chapter and "." not in entry and numeric.split(".")[0] == entry[1:])


def icd10_covered(code: str, entries: list[str]) -> bool:
    """True if `code` (e.g. "C50.9", "C50.911", "C50911") falls within any covered code or range in `entries`."""
    c = code.strip().upper()
    if len(c) > 3 and "." not in c:
        c = f"{c[:3]}.{c[3:]}"
    return any(_icd10_in_entry(c, e.strip().upper()) for e in entries)


# --------------------------------------------------------------------------- core
class _Eval:
    def __init__(self, policy: PolicyRecord, facts: ScenarioFacts):
        self.p = policy
        self.f = facts
        self.idx = policy.tuple_index()
        self.ordered = list(policy.tuples)
        self.lenient = False
        self.trace: list[TraceStep] = []
        self.fired: list[str] = []

    def t(self, rule: str, result: str, tid: Optional[str] = None, detail: Optional[str] = None):
        self.trace.append(TraceStep(rule=rule, tuple_id=tid, result=result, detail=detail))

    def excepted(self, excl: ClauseTuple) -> bool:
        for ex in self.p.tuples_by(Relation.EXCEPTS):
            if ex.object == excl.id and all_hold(ex.qualifiers.applies_if, self.f):
                self.t("exception", "OVERRIDES", ex.id, f"exception to {excl.id} holds")
                self.fired.append(ex.id)
                return True
        return False

    def active_riders(self) -> set[str]:
        return {r.id for r in self.p.riders if r.attached}

    def scoped_in(self, tup: ClauseTuple) -> bool:
        """Rider tuples only apply if the rider is attached (RIDER_ATTACHED slot overrides)."""
        if tup.head == self.p.id:
            return True
        if self.f.has(Slot.RIDER_ATTACHED):
            return bool(self.f.get(Slot.RIDER_ATTACHED))
        return tup.head in self.active_riders()

    def run(self) -> VerdictResult:
        event = self.f.get(Slot.EVENT)
        is_action = event in ACTION_EVENTS
        # COVERS (benefits) and PERMITS (policy actions: loan, surrender, conversion...) are both "grants".
        grants = [c for c in self.ordered if c.relation in (Relation.COVERS, Relation.PERMITS) and c.object == event and self.scoped_in(c)]
        diagnosed_code = self.f.get(Slot.DIAGNOSIS_ICD10) if self.f.has(Slot.DIAGNOSIS_ICD10) else None
        candidates = []
        skipped: set[str] = set()
        while True:
            current = None
            candidates.clear()
            try:
                for c in grants:
                    if c.id in skipped:
                        continue
                    current = c
                    if not all_hold(c.qualifiers.applies_if, self.f):
                        self.t("cover", "CONDITION_FAILED", c.id)
                        continue
                    if diagnosed_code and c.qualifiers.icd10_codes and not icd10_covered(str(diagnosed_code), c.qualifiers.icd10_codes):
                        self.t("cover", "ICD10_NOT_LISTED", c.id, f"{diagnosed_code} not in {c.qualifiers.icd10_codes}")
                        continue
                    candidates.append(c)
                    self.t("cover", "CANDIDATE", c.id)
                break
            except MissingSlot:
                if not self.lenient or current is None:
                    raise
                skipped.add(current.id)

        # Scope: base-policy tuples always; rider tuples only if that rider grants this event.
        scope_heads = {self.p.id} | {c.head for c in candidates}

        def in_scope(tup: ClauseTuple) -> bool:
            return tup.head in scope_heads

        exclusions = [x for x in self.ordered if x.relation == Relation.EXCLUDES and in_scope(x)]
        governing_excl = []
        for x in exclusions:
            if x.object == event or (x.object in CAUSE_LIKE_OBJECTS and self.f.has(Slot.CAUSE) and x.object == self.f.get(Slot.CAUSE)):
                governing_excl.append(x)
            elif x.object in CAUSE_LIKE_OBJECTS and not self.f.has(Slot.CAUSE) and candidates and not is_action and not self.lenient:
                # cause-based exclusion might apply to this benefit; we need the cause to decide
                raise MissingSlot(Slot.CAUSE)

        cand_ids = {c.id for c in candidates}
        periods = [pr for pr in self.ordered if pr.relation == Relation.HAS_PERIOD and in_scope(pr)]
        terminations = [tm for tm in self.ordered if tm.relation == Relation.TERMINATES_IF and in_scope(tm)]
        # CONDITIONED_ON scoping: a condition keyed to a *different* grant event (e.g. loan
        # minimum years) must not govern this event; conditions keyed by a condition code
        # (PREMIUM_PAID, NO_VALID_LICENSE...), by this event, by a candidate id or by ANY apply.
        other_grant_events = {
            g.object for g in self.p.tuples if g.relation in (Relation.COVERS, Relation.PERMITS) and g.object != event
        } | (ACTION_EVENTS - {event})
        conditions = [
            c for c in self.ordered if c.relation == Relation.CONDITIONED_ON
            if in_scope(c) and (c.object == event or c.object in cand_ids or c.object in ("ANY", "*") or c.object not in other_grant_events)
        ]

        # ---- closed world: nothing grants and nothing explicitly excludes this event
        if not candidates and not governing_excl:
            if self.p.extraction_coverage < NOT_SPECIFIED_COVERAGE_THRESHOLD:
                self.t("closed_world", "NOT_SPECIFIED", detail="document is a summary or extraction incomplete")
                return self._result(Verdict.NOT_SPECIFIED)
            self.t("closed_world", "NOT_APPLICABLE", detail=f"no clause governs event {event}")
            return self._result(Verdict.NOT_APPLICABLE)

        if is_action:
            # Policy actions are governed by their PERMITS conditions and explicit exclusions only;
            # benefit periods (waiting, grace, survival, suicide, contestability) do not apply.
            periods = [pr for pr in periods if (pr.qualifiers.period_kind or pr.object) == PeriodKind.FREE_LOOK.value]

        # ---- exclusions (exception > exclusion)
        skipped: set[str] = set()
        while True:
            current = None
            try:
                for x in governing_excl:
                    if x.id in skipped:
                        continue
                    current = x
                    q = x.qualifiers
                    if not all_hold(q.applies_if, self.f):
                        self.t("exclusion", "CONDITION_NOT_MET", x.id)
                        continue
                    if not window_active(q, self.f):
                        self.t("exclusion", "OUTSIDE_WINDOW", x.id, f"window {q.window_len} {q.window_unit} from {q.window_from}")
                        continue
                    if self.excepted(x):
                        continue
                    self.fired.append(x.id)
                    self.t("exclusion", "DENIED", x.id)
                    # suicide-type exclusions may still return premiums: encode via benefit_type
                    code = f"EXCLUSION_{x.object}"
                    return self._result(Verdict.DENIED, denial_code=code, benefit_type=q.benefit_type)
                break
            except MissingSlot:
                if not self.lenient or current is None:
                    raise
                skipped.add(current.id)

        # ---- periods
        skipped: set[str] = set()
        while True:
            current = None
            try:
                for pr in periods:
                    if pr.id in skipped:
                        continue
                    current = pr
                    q = pr.qualifiers
                    kind = q.period_kind or PeriodKind(pr.object) if pr.object in PeriodKind.__members__ else q.period_kind
                    if kind is None:
                        continue
                    if q.applies_if and not all_hold(q.applies_if, self.f):
                        self.t("period", "CONDITION_NOT_MET", pr.id)
                        continue
                    if kind == PeriodKind.WAITING:
                        exempt = self.f.has(Slot.IS_ACCIDENT) and bool(self.f.get(Slot.IS_ACCIDENT)) or (
                            self.f.has(Slot.IS_EMERGENCY) and bool(self.f.get(Slot.IS_EMERGENCY))
                        )
                        if exempt and (q.unless_clause_ids or True):
                            self.t("period", "WAITING_EXEMPT", pr.id, "accident/emergency exemption")
                            continue
                        days = float(self.f.get(Slot.DAYS_SINCE_EFFECTIVE))
                        wd = q.waiting_days if q.waiting_days is not None else (q.window_len or 0)
                        if days < wd:
                            self.fired.append(pr.id)
                            self.t("period", "DENIED", pr.id, f"day {int(days)} < waiting {wd}")
                            return self._result(Verdict.DENIED, denial_code="WAITING_PERIOD")
                        self.t("period", "PASSED", pr.id)
                    elif kind == PeriodKind.WAITING_SPECIFIED:
                        if self.f.has(Slot.DISEASE_IN_SPECIFIED_LIST) and self.f.get(Slot.DISEASE_IN_SPECIFIED_LIST):
                            if not window_active(q, self.f):
                                self.t("period", "PASSED", pr.id)
                                continue
                            self.fired.append(pr.id)
                            self.t("period", "DENIED", pr.id, "specified disease inside waiting window")
                            return self._result(Verdict.DENIED, denial_code="SPECIFIED_DISEASE_WAITING")
                        elif not self.f.has(Slot.DISEASE_IN_SPECIFIED_LIST) and event in (EventCode.HOSPITALIZATION.value, EventCode.SURGERY.value):
                            raise MissingSlot(Slot.DISEASE_IN_SPECIFIED_LIST)
                    elif kind == PeriodKind.GRACE:
                        if self.f.has(Slot.PREMIUM_STATUS) and self.f.get(Slot.PREMIUM_STATUS) in ("OVERDUE", "LAPSED"):
                            overdue = float(self.f.get(Slot.DAYS_OVERDUE))
                            grace = float(q.window_len or self.p.grace_days or 0)
                            if overdue > grace:
                                self.fired.append(pr.id)
                                self.t("period", "DENIED", pr.id, f"{int(overdue)} days overdue > grace {int(grace)}")
                                return self._result(Verdict.DENIED, denial_code="LAPSED")
                            self.t("period", "IN_GRACE", pr.id)
                    elif kind == PeriodKind.SURVIVAL:
                        if event in (EventCode.CRITICAL_ILLNESS.value, EventCode.TERMINAL_ILLNESS.value):
                            sd = float(self.f.get(Slot.SURVIVAL_DAYS))
                            need = float(q.window_len or 0)
                            if sd < need:
                                self.fired.append(pr.id)
                                self.t("period", "DENIED", pr.id, f"survival {int(sd)} < {int(need)} days")
                                return self._result(Verdict.DENIED, denial_code="SURVIVAL_PERIOD")
                    elif kind == PeriodKind.CONTESTABILITY:
                        if self.f.has(Slot.MISREPRESENTATION) and self.f.get(Slot.MISREPRESENTATION) and window_active(q, self.f):
                            self.fired.append(pr.id)
                            self.t("period", "DENIED", pr.id, "material misrepresentation within contestability period")
                            return self._result(Verdict.DENIED, denial_code="CONTESTABILITY")
                    elif kind == PeriodKind.SUICIDE:
                        if event in (EventCode.DEATH.value, EventCode.SUICIDE.value):
                            cause = self.f.get(Slot.CAUSE)
                            if cause == "SUICIDE" and window_active(q, self.f):
                                self.fired.append(pr.id)
                                self.t("period", "DENIED", pr.id, "suicide inside exclusion window")
                                return self._result(Verdict.DENIED, denial_code="SUICIDE_PERIOD", benefit_type=q.benefit_type)
                    elif kind == PeriodKind.FILING_DEADLINE:
                        pass  # evaluated by claims readiness, not coverage
                break
            except MissingSlot:
                if not self.lenient or current is None:
                    raise
                skipped.add(current.id)

        # ---- conditions
        skipped: set[str] = set()
        while True:
            current = None
            try:
                for c in conditions:
                    if c.id in skipped:
                        continue
                    current = c
                    if not all_hold(c.qualifiers.applies_if, self.f):
                        self.fired.append(c.id)
                        self.t("condition", "DENIED", c.id)
                        return self._result(Verdict.DENIED, denial_code="CONDITION_NOT_MET")
                break
            except MissingSlot:
                if not self.lenient or current is None:
                    raise
                skipped.add(current.id)

        # ---- terminations
        skipped: set[str] = set()
        while True:
            current = None
            try:
                for term in terminations:
                    if term.id in skipped:
                        continue
                    current = term
                    q = term.qualifiers
                    if q.applies_if and all_hold(q.applies_if, self.f):
                        self.fired.append(term.id)
                        self.t("termination", "DENIED", term.id)
                        return self._result(Verdict.DENIED, denial_code=f"TERMINATED_{term.object}")
                break
            except MissingSlot:
                if not self.lenient or current is None:
                    raise
                skipped.add(current.id)

        if not candidates:
            # only exclusions/periods governed but none fired, and nothing covers -> not applicable
            self.t("closed_world", "NOT_APPLICABLE", detail="no coverage clause for this event")
            return self._result(Verdict.NOT_APPLICABLE)

        best = candidates[0]
        self.fired.append(best.id)
        self.t("cover", "COVERED", best.id)
        payable, cur = self._payable(best)
        return self._result(Verdict.COVERED, payable=payable, currency=cur)

    def _payable(self, cover: ClauseTuple) -> tuple[Optional[Decimal], Optional[str]]:
        q = cover.qualifiers
        cur = q.currency or self.p.currency
        if q.per_day_limit is not None and self.f.has(Slot.DAYS_HOSPITALIZED):
            days = int(self.f.get(Slot.DAYS_HOSPITALIZED))
            if q.deductible_days:
                days = max(0, days - q.deductible_days)
            cap = q.max_days_per_year or q.max_days
            if cap:
                days = min(days, cap)
            return Decimal(days) * q.per_day_limit, cur
        if q.amount is not None:
            return q.amount, cur
        if q.pct_of_sum_assured is not None and self.p.sum_assured is not None:
            return (self.p.sum_assured * Decimal(str(q.pct_of_sum_assured)) / Decimal(100)).quantize(Decimal("1")), cur
        if q.per_case_limit is not None and self.f.has(Slot.BILLED_AMOUNT):
            billed = Decimal(str(self.f.get(Slot.BILLED_AMOUNT)))
            if q.deductible_amount:
                billed = max(Decimal(0), billed - q.deductible_amount)
            if q.copay_pct:
                copay = billed * Decimal(str(q.copay_pct)) / Decimal(100)
                if q.copay_cap:
                    copay = min(copay, q.copay_cap)
                billed -= copay
            return min(billed, q.per_case_limit), cur
        return None, cur

    def _result(self, verdict: Verdict, *, payable=None, currency=None, denial_code=None, benefit_type=None) -> VerdictResult:
        tiers = [self.idx[t].source_tier for t in self.fired if t in self.idx]
        min_tier = min(tiers, key=lambda s: TIER_RANK[s]) if tiers else None
        if verdict == Verdict.DENIED and benefit_type == "RETURN_PREMIUMS":
            self.t("benefit", "RETURN_PREMIUMS", detail="liability limited to premiums paid")
        return VerdictResult(
            policy_id=self.p.id,
            verdict=verdict,
            fired_tuple_ids=list(dict.fromkeys(self.fired)),
            payable=payable,
            currency=currency,
            trace=self.trace,
            denial_code=denial_code,
            min_source_tier=min_tier,
        )


def _definite_denial(policy: PolicyRecord, facts: ScenarioFacts) -> Optional[VerdictResult]:
    """A denial that holds whatever the unbound slots turn out to be: checks that need an unbound slot are skipped."""
    ev = _Eval(policy, facts)
    ev.lenient = True
    try:
        r = ev.run()
    except MissingSlot:
        return None
    return r if r.verdict == Verdict.DENIED else None


def evaluate(policy: PolicyRecord, facts: ScenarioFacts) -> VerdictResult:
    """Raises MissingSlot if an unbound slot is needed. Use `decide` for clarification handling."""
    return _Eval(policy, facts).run()


def _decide(policy: PolicyRecord, facts: ScenarioFacts, *, max_depth: int = 3) -> VerdictResult:
    """Evaluate with verdict-sensitivity clarification.

    If an unbound slot is touched, try every value in its domain. If all values give the
    same verdict, the slot is irrelevant: return that verdict (binding nothing). If the
    verdict differs, return CLARIFY for exactly that slot.
    """
    try:
        return evaluate(policy, facts)
    except MissingSlot as ms:
        denial = _definite_denial(policy, facts)
        if denial is not None:
            return denial
        slot = ms.slot
        domain = SLOT_DOMAINS.get(slot)
        if not domain or max_depth == 0:
            r = VerdictResult(policy_id=policy.id, verdict=Verdict.CLARIFY, missing_slots=[slot])
            r.clarification = ClarificationRequest(slot=slot, verdict_by_value={})
            return r
        outcomes: dict[str, Verdict] = {}
        sub: dict[str, VerdictResult] = {}
        for v in domain:
            r = _decide(policy, facts.bind(slot, v), max_depth=max_depth - 1)
            outcomes[str(v)] = r.verdict
            sub[str(v)] = r
        distinct = set(outcomes.values())
        if len(distinct) == 1 and Verdict.CLARIFY not in distinct:
            r = next(iter(sub.values()))
            r.trace.insert(0, TraceStep(rule="sensitivity", result="INVARIANT", detail=f"{slot.value} does not change the verdict"))
            return r
        if distinct == {Verdict.CLARIFY}:
            # nested missing slot dominates; surface the first nested clarification
            return next(iter(sub.values()))
        r = VerdictResult(policy_id=policy.id, verdict=Verdict.CLARIFY, missing_slots=[slot])
        why = None
        for sr in sub.values():
            if sr.fired_tuple_ids:
                why = sr.fired_tuple_ids[0]
                break
        r.clarification = ClarificationRequest(slot=slot, verdict_by_value={k: v for k, v in outcomes.items() if v != Verdict.CLARIFY}, why_tuple_id=why)
        summary = ", ".join(f"{k}->{v.value}" for k, v in outcomes.items())
        r.trace.append(TraceStep(rule="sensitivity", result="CLARIFY", detail=(f"{slot.value} changes the verdict: {summary}")[:300]))
        return r


def decide(policy: PolicyRecord, facts: ScenarioFacts, *, max_depth: int = 3) -> VerdictResult:
    """`_decide` plus the UNMODELED_RULE guard: a plausibly relevant unmodeled clause marks the result uncertain; it never changes the verdict."""
    r = _decide(policy, facts, max_depth=max_depth)
    if any(t.relation == Relation.UNMODELED_RULE for t in policy.tuples) and r.verdict in (Verdict.COVERED, Verdict.DENIED, Verdict.NOT_APPLICABLE):
        hits = relevant_unmodeled(policy, facts)
        if hits:
            r.uncertain = True
            r.unmodeled_clause_ids = [t.id for t in hits]
            r.trace.append(TraceStep(rule="unmodeled", result="UNCERTAIN", tuple_id=hits[0].id,
                                     detail=f"uncertain: unmodeled clause {', '.join(t.id for t in hits)}"[:300]))
    return r


def decide_portfolio(policies: list[PolicyRecord], facts: ScenarioFacts) -> list[VerdictResult]:
    return [decide(p, facts) for p in policies]
