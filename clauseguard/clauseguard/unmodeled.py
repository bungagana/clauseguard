"""Deterministic relevance of UNMODELED_RULE tuples to a scenario.

An UNMODELED_RULE is a rule the extractor found but the closed relations cannot express. It never
decides a verdict; when it plausibly governs the scenario's event the solver marks the result uncertain.
"""
from __future__ import annotations

import re

from .schema import ClauseTuple, PolicyRecord, Relation, ScenarioFacts, Slot

EVENT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "DEATH": ("death", "dies", "died", "deceased", "death benefit"),
    "ACCIDENTAL_DEATH": ("accident", "death"),
    "SUICIDE": ("suicid",),
    "POLICY_LOAN": ("loan", "borrow"),
    "SURRENDER": ("surrender", "cash value", "cash surrender"),
    "PARTIAL_WITHDRAWAL": ("withdraw",),
    "CONVERSION": ("convert", "conversion"),
    "REINSTATEMENT": ("reinstat", "revive"),
    "FREE_LOOK": ("free look", "free-look", "right to examine", "cancel"),
    "LAPSE": ("lapse", "grace", "nonforfeiture", "non-forfeiture", "extended term", "paid-up", "paid up"),
    "TERMINAL_ILLNESS": ("terminal", "accelerat"),
    "CHRONIC_ILLNESS": ("chronic", "accelerat"),
    "PREMIUM_WAIVER": ("waiv", "disab"),
    "RETURN_OF_PREMIUM": ("return of premium", "refund"),
    "CHILD_DEATH": ("child",),
    "JOINT_DEATH": ("joint", "survivor", "both insured"),
    "JOINT_FIRST_DEATH": ("joint", "first death", "first insured"),
    "GROUP_TERMINATION": ("terminat", "employ"),
}


def _keywords(event: str) -> tuple[str, ...]:
    return EVENT_KEYWORDS.get(event) or tuple(w.lower() for w in re.split(r"[_\s]+", event) if len(w) > 3)


def relevant_unmodeled(policy: PolicyRecord, facts: ScenarioFacts) -> list[ClauseTuple]:
    if not facts.has(Slot.EVENT):
        return []
    event = str(facts.get(Slot.EVENT))
    kws = _keywords(event)
    if not kws:
        return []
    granting_heads = {t.head for t in policy.tuples if t.relation in (Relation.COVERS, Relation.PERMITS) and t.object == event}
    heads = {policy.id} | granting_heads
    out = []
    for t in policy.tuples:
        if t.relation != Relation.UNMODELED_RULE or t.head not in heads:
            continue
        hay = f"{t.object} {t.qualifiers.proposed_label or ''} {t.evidence.text}".lower().replace("_", " ")
        if any(k in hay for k in kws):
            out.append(t)
    return out
