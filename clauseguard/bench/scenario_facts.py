"""Scenario description -> ScenarioFacts via bind_facts (cached) + hand overrides + bench presumptions.

Three layers, all recorded per scenario for transparency:
  1. `bind_facts` (fast model fills the closed FactSheet; code derives slots)  -> tier LLM
  2. bench/scenario_overrides.json  "slots": hand corrections of (1)             -> tier USER
  3. BENCH_PRESUMPTIONS: closed-world defaults the benchmark's own ground truth assumes
     (policy in force, premiums paid, no misrepresentation, employee still employed, ...)
     applied ONLY to slots still unbound after (1)+(2), and only for in-scope scenarios.
`in_solver_scope` (from the overrides file, default by category keyword) marks scenarios
whose question is a coverage / exclusion / period / rider / termination / permitted-action
question. Out-of-scope scenarios (cash-value projections, dividend options, settlement
options, claim payment speed, estate planning, underwriting, crediting mechanics) are
answered by the B0CW fallback and flagged.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from clauseguard.agent.facts import DEATH_EVENTS, bind_facts
from clauseguard.schema import ScenarioFacts, Slot

from .data import scenarios

OVERRIDES_PATH = Path(__file__).with_name("scenario_overrides.json")
AS_OF = date(2026, 10, 11)

# Closed-world presumptions shared with the benchmark's ground truth (applied only if unbound).
BENCH_PRESUMPTIONS: dict[Slot, Any] = {
    Slot.IN_FORCE: True,
    Slot.PREMIUM_STATUS: "PAID",
    Slot.MISREPRESENTATION: False,
    Slot.INTOXICATED: False,
    Slot.EMPLOYMENT_ACTIVE: True,
    Slot.MILITARY_SERVICE: False,
    Slot.DOCUMENTS_PRESENT: True,
}
# Only for death-type events: an unstated cause is recorded as UNKNOWN (no exclusion-triggering cause).
DEATH_PRESUMPTIONS: dict[Slot, Any] = {Slot.CAUSE: "UNKNOWN", Slot.PARTIES_BOTH_DEAD: False}

OUT_OF_SCOPE_KEYWORDS = ("DIVIDEND", "SETTLEMENT", "PAYMENT_SPEED", "ESTATE", "CASH_VALUE", "PROJECTION", "CREDITING",
                         "CAP_RATE", "PREMIUM_LOAD", "INVESTMENT_RISK", "UNDERWRITING", "FLEXIBLE_PREMIUM", "DEPLETION",
                         "NO_LAPSE", "ASSIGNMENT", "SPLIT", "GUARANTEE_PERIOD", "SALARY", "LATE_ENTRANT", "MISSTATEMENT",
                         "INCREASING_DEATH_BENEFIT", "GUARANTEED_INSURABILITY", "NON_FORFEITURE", "LOAN_AT_FIRST_DEATH")


def load_overrides() -> dict[str, dict]:
    if OVERRIDES_PATH.exists():
        return json.loads(OVERRIDES_PATH.read_text(encoding="utf8"))
    return {}


def default_in_scope(category: str) -> bool:
    return not any(k in category for k in OUT_OF_SCOPE_KEYWORDS)


def in_scope(sid: str, category: str, overrides: dict[str, dict] | None = None) -> bool:
    ov = (overrides or load_overrides()).get(sid, {})
    if "in_solver_scope" in ov:
        return bool(ov["in_solver_scope"])
    return default_in_scope(category)


def facts_for(scn: dict, *, overrides: dict[str, dict] | None = None, apply_presumptions: bool = True) -> dict:
    """Returns {facts: ScenarioFacts, llm: {...}, overrides: {...}, presumed: [...], in_scope: bool}."""
    overrides = overrides if overrides is not None else load_overrides()
    sid = scn["scenario_id"]
    f = bind_facts(scn["scenario_description"], policies=[], as_of=AS_OF)
    llm_values = dict(f.values)
    ov = overrides.get(sid, {})
    values = dict(f.values)
    for k, v in ov.get("slots", {}).items():
        values[Slot(k)] = v
    for k in ov.get("unbind", []):
        values.pop(Slot(k), None)
    scope = in_scope(sid, scn["category"], overrides)
    presumed: list[str] = []
    if apply_presumptions and scope:
        pres = dict(BENCH_PRESUMPTIONS)
        if str(values.get(Slot.EVENT, "")) in DEATH_EVENTS:
            pres.update(DEATH_PRESUMPTIONS)
        for slot, v in pres.items():
            if slot not in values:
                values[slot] = v
                presumed.append(slot.value)
    return {"facts": ScenarioFacts(values=values, as_of=AS_OF), "llm": {k.value: v for k, v in llm_values.items()},
            "overrides": ov.get("slots", {}), "presumed": presumed, "in_scope": scope, "note": ov.get("note")}


def main():
    overrides = load_overrides()
    for scn in scenarios():
        r = facts_for(scn, overrides=overrides)
        tag = "IN " if r["in_scope"] else "OUT"
        print(f"{scn['scenario_id']} [{tag}] {scn['category']}")
        print("   llm:", r["llm"])
        if r["overrides"]:
            print("   override:", r["overrides"], "|", r["note"] or "")
        if r["presumed"]:
            print("   presumed:", r["presumed"])


if __name__ == "__main__":
    main()
