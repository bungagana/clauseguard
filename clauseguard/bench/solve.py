"""Solver adapter for the benchmark: event-scoped view of a PolicyRecord + CLARIFY resolution.

The frozen solver (clauseguard/solver.py) has three gaps the oracle mapping exposes; the
adapter closes them *outside* the solver so the solver itself stays untouched:
  1. PERMITS is never consulted by `solver.run` (it only looks at COVERS). For action events
     (POLICY_LOAN, SURRENDER, CONVERSION, FREE_LOOK, ...) PERMITS tuples are presented to the
     solver as COVERS tuples (same id, same evidence).
  2. CONDITIONED_ON tuples are applied to every event. They are filtered to the ones whose
     object is the event being evaluated (or a COVERS tuple id for that event).
  3. Rider-scoped EXCLUDES / HAS_PERIOD / TERMINATES_IF tuples apply to every event while
     the rider is attached; they are filtered to events the rider itself covers. Policy-level
     TERMINATES_IF applies to benefit events only (a termination clause does not deny the
     question "what happens on termination").
  4. HAS_PERIOD SUICIDE is kept for DEATH/SUICIDE only (otherwise it disables the closed-world
     shortcut for every event); GRACE / CONTESTABILITY periods are kept for benefit events only
     (an overdue premium does not deny the question "can I reinstate / what happens on lapse").
Recommended solver changes are listed in bench/README.md.
"""
from __future__ import annotations

from collections import Counter
from typing import Optional

from clauseguard.schema import PolicyRecord, Relation, ScenarioFacts, Slot, Verdict, VerdictResult
from clauseguard.solver import decide

ACTION_EVENTS = {"POLICY_LOAN", "SURRENDER", "PARTIAL_WITHDRAWAL", "CONVERSION", "REINSTATEMENT", "FREE_LOOK",
                 "LAPSE", "GROUP_TERMINATION", "GUARANTEED_INSURABILITY"}
# trace results whose tuple was examined and did not block: cited as supporting evidence
SUPPORTING_RESULTS = {"PASSED", "OUTSIDE_WINDOW", "IN_GRACE", "WAITING_EXEMPT", "CONDITION_NOT_MET", "OVERRIDES", "CANDIDATE"}
BENEFIT_EVENTS = {"DEATH", "ACCIDENTAL_DEATH", "SUICIDE", "CHILD_DEATH", "JOINT_DEATH", "JOINT_FIRST_DEATH",
                  "TERMINAL_ILLNESS", "CHRONIC_ILLNESS", "CRITICAL_ILLNESS", "PREMIUM_WAIVER", "RETURN_OF_PREMIUM",
                  "HOSPITALIZATION", "SURGERY", "ICU", "OUTPATIENT", "TPD", "TEMPORARY_DISABILITY", "DENTAL",
                  "ACCIDENT_MEDICAL", "PREGNANCY"}


def solver_view(policy: PolicyRecord, event: str) -> PolicyRecord:
    rider_events: dict[str, set[str]] = {}
    for t in policy.tuples:
        if t.head != policy.id and t.relation in (Relation.COVERS, Relation.PERMITS):
            rider_events.setdefault(t.head, set()).add(t.object)
    cover_ids_for_event = {t.id for t in policy.tuples if t.relation in (Relation.COVERS, Relation.PERMITS) and t.object == event}
    keep = []
    for t in policy.tuples:
        rider_scoped = t.head != policy.id
        if t.relation == Relation.PERMITS:
            keep.append(t.model_copy(update={"relation": Relation.COVERS}))
        elif t.relation == Relation.CONDITIONED_ON:
            if t.object == event or t.object in cover_ids_for_event:
                keep.append(t)
        elif t.relation in (Relation.EXCLUDES, Relation.HAS_PERIOD) and rider_scoped:
            if event in rider_events.get(t.head, set()):
                keep.append(t)
        elif t.relation == Relation.EXCLUDES and not rider_scoped and event not in BENEFIT_EVENTS and t.object != event:
            continue  # cause-based exclusions govern benefits, not actions (a loan is not denied by a war clause)
        elif t.relation == Relation.HAS_PERIOD and t.object == "SUICIDE":
            # a suicide clause governs death only; keeping it for other events defeats the
            # solver's closed-world shortcut and lets unrelated periods (grace) deny them
            if event in ("DEATH", "SUICIDE"):
                keep.append(t)
        elif t.relation == Relation.HAS_PERIOD and t.object in ("GRACE", "CONTESTABILITY"):
            # premium/contestability status can deny a benefit; it does not answer an action
            # question such as "what happens on lapse" or "can I reinstate"
            if event in BENEFIT_EVENTS:
                keep.append(t)
        elif t.relation == Relation.TERMINATES_IF:
            if rider_scoped:
                if event in rider_events.get(t.head, set()):
                    keep.append(t)
            elif event in BENEFIT_EVENTS:
                keep.append(t)
        else:
            keep.append(t)
    return policy.model_copy(update={"tuples": keep})


def resolve_clarify(r: VerdictResult) -> tuple[Verdict, dict]:
    """Benchmark has no user to ask: take the majority verdict over the slot's domain (flagged)."""
    flags: dict = {"clarify_slot": r.clarification.slot.value if r.clarification else None}
    vbv = r.clarification.verdict_by_value if r.clarification else {}
    if not vbv:
        flags["clarify_unresolved"] = True
        return Verdict.NOT_APPLICABLE, flags
    counts = Counter(vbv.values())
    top = counts.most_common()
    verdict = top[0][0]
    flags["clarify_majority"] = {k: v.value for k, v in vbv.items()}
    if len(top) > 1 and top[0][1] == top[1][1]:
        flags["clarify_tie"] = True
        verdict = next(iter(vbv.values()))  # deterministic: first domain value
    return verdict, flags


def decide_bench(policy: PolicyRecord, facts: ScenarioFacts) -> tuple[VerdictResult, Verdict, dict]:
    """Returns (raw solver result, resolved verdict, flags)."""
    event = str(facts.values.get(Slot.EVENT, ""))
    flags: dict = {}
    view = solver_view(policy, event)
    r = decide(view, facts)
    if r.uncertain:
        flags["uncertain_unmodeled"] = r.unmodeled_clause_ids
    idx = {t.id: t for t in policy.tuples}
    low = [i for i in r.fired_tuple_ids if i in idx and idx[i].confidence < 0.7]
    if low:
        flags["low_confidence_decisive"] = low
    verdict = r.verdict
    if verdict == Verdict.CLARIFY:
        verdict, flags = resolve_clarify(r)
    if verdict == Verdict.NOT_SPECIFIED:
        flags["not_specified"] = True
        verdict = Verdict.NOT_APPLICABLE
    return r, verdict, flags


def evidence_of(policy: PolicyRecord, r: VerdictResult) -> tuple[Optional[str], str]:
    """(section of the deciding tuple, concatenated evidence text of all fired tuples)."""
    idx = policy.tuple_index()
    fired = [idx[t] for t in r.fired_tuple_ids if t in idx]
    checked = [idx[s.tuple_id] for s in r.trace if s.tuple_id in idx and s.result in SUPPORTING_RESULTS and s.tuple_id not in r.fired_tuple_ids]
    if not fired and not checked:
        return None, ""
    deciding = fired[-1] if fired else checked[0]
    parts = [f"[{t.evidence.section or '-'}] {t.evidence.text}" for t in fired + checked]
    return deciding.evidence.section, " | ".join(dict.fromkeys(parts))
