"""Recourse and adjudication-twin evaluation.

Part A - scripted tasks. Every DENIED verdict produced while replaying the 33 scripted tasks
(data/scripted_tasks/T*.yaml, A*.yaml) through the agent loop with the language model off is
handed to `recourse.find_recourse` with the persona's full portfolio; the report counts how many
denials have a legitimate recourse and what it is.

Part B - real disputes. When data/real/fos_decisions.jsonl exists (UK Financial Ombudsman
decisions, downloaded separately), each decision that quotes a clause type the solver models
(waiting period, pre-existing condition, late notification, exclusion) is counted, and each
decision with a hand-written entry in bench/fos_mapping.json is replayed through the twin on the
closest sandbox policy; the report says whether the twin's top ground matches the ground the
ombudsman discussed. The file is loaded lazily and the section is skipped when it is missing.

Output: evidence/recourse_report.md (with provenance and limits) and evidence/recourse_eval.json.

Usage: python -m bench.recourse_eval
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any, Optional

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from clauseguard import config  # noqa: E402
from clauseguard.agent.facts_fallback import derive_for_policy  # noqa: E402
from clauseguard.agent.loop import confirm_pending, handle_turn  # noqa: E402
from clauseguard.recourse import RecourseResult, find_recourse  # noqa: E402
from clauseguard.sandbox.persona_policies import PERSONA_META, policies_for_persona  # noqa: E402
from clauseguard.schema import PolicyRecord, ScenarioFacts, Slot, Verdict  # noqa: E402
from clauseguard.twin import adjudicate_like_insurer  # noqa: E402

from .agent_harness import disable_llm, new_session  # noqa: E402

TASK_DIR = config.DATA_DIR / "scripted_tasks"
FOS_PATH = config.DATA_DIR / "real" / "fos_decisions.jsonl"
MAPPING_PATH = Path(__file__).with_name("fos_mapping.json")
REPORT = config.EVIDENCE_DIR / "recourse_report.md"
RAW = config.EVIDENCE_DIR / "recourse_eval.json"

#: Clause types the solver models, with the phrases an ombudsman decision uses for them.
CLAUSE_PATTERNS: dict[str, re.Pattern[str]] = {
    "waiting_period": re.compile(r"\b(waiting|qualifying|deferred) period\b", re.I),
    "pre_existing": re.compile(r"\bpre-?existing\b", re.I),
    "late_notification": re.compile(r"\b(late notification|notified? (us|the insurer) (late|out of time)|time limit for (notifying|making) (a )?claim|out of time)\b", re.I),
    "exclusion": re.compile(r"\b(exclusion|excluded under|not covered under the terms)\b", re.I),
}
CLAUSE_TO_CODES: dict[str, set[str]] = {
    "waiting_period": {"WAITING_PERIOD", "SPECIFIED_DISEASE_WAITING", "SURVIVAL_PERIOD"},
    "pre_existing": {"PRE_EXISTING"},
    "late_notification": {"LATE_FILING", "LATE_FILING_DISCRETIONARY"},
    "exclusion": set(),  # any EXCLUSION_* / cause code
}


# --------------------------------------------------------------------------- part A
def load_tasks() -> list[dict]:
    out = []
    for p in sorted(TASK_DIR.glob("*.yaml")):
        out.append(yaml.safe_load(p.read_text(encoding="utf8")))
    return out


def _facts_for_policies(session, policies: list[PolicyRecord], meta: dict) -> dict[str, ScenarioFacts]:
    """The same policy-relative derivation the agent loop uses before it calls the solver."""
    person = session.person_id or session.user_id
    conditions = {k: date.fromisoformat(v) for k, v in meta.get("conditions", {}).get(person, {}).items()}
    out: dict[str, ScenarioFacts] = {}
    for p in policies:
        out[p.id] = derive_for_policy(session.facts, p, dates=session.event_dates, as_of=session.as_of, diagnosis=session.diagnosis_code,
                                      diagnosis_dates=conditions, effective_override=session.effective_override,
                                      payment=meta.get("payments", {}).get(p.id), employment_active=meta.get("employment_active"))
        if p.product_type == "social_bpjs_kes" and not session.facts.has(Slot.PREMIUM_STATUS):
            out[p.id] = out[p.id].bind(Slot.PREMIUM_STATUS, "PAID" if p.status == "active" else "LAPSED")
    return out


def _summarise(r: RecourseResult) -> dict:
    best = r.best()
    return {
        "baseline": r.baseline_verdict.value, "denial_code": r.baseline_denial_code, "has_recourse": r.has_recourse,
        "n_options": len(r.options), "searched": r.searched,
        "best_kinds": [a.kind.value for a in best.actions] if best else [],
        "all_options": [" + ".join(a.kind.value + (f"({a.other_policy_id})" if a.other_policy_id else "") for a in o.actions) for o in r.options],
        "best_cost": best.cost.model_dump() if best else None,
        "best": best.description if best else None,
        "blocked_by_immutable": [s.value for s in r.blocked_by_immutable], "notes": r.notes,
    }


def run_tasks() -> dict:
    disable_llm()
    tasks = load_tasks()
    denials: list[dict] = []
    n_turns = 0
    for task in tasks:
        persona = task["persona"]
        as_of = date.fromisoformat(str(task.get("as_of", "2026-10-11")))
        session, router = new_session(persona, as_of)
        policies = policies_for_persona(persona)
        meta = PERSONA_META[persona]
        for i, turn in enumerate(task.get("turns", []), start=1):
            text = turn["user"] if isinstance(turn, dict) else str(turn)
            try:
                rep = confirm_pending(session, router=router) if text == "__CONFIRM__" else handle_turn(session, text, router=router, use_llm=False)
            except Exception as e:  # noqa: BLE001 - a crashing turn is reported, not hidden
                denials.append({"task": task["id"], "turn": i, "error": f"{type(e).__name__}: {e}"})
                continue
            n_turns += 1
            denied = [v for v in rep.verdicts if v.verdict == Verdict.DENIED]
            if not denied:
                continue
            fbp = _facts_for_policies(session, policies, meta)
            for v in denied:
                pol = next((p for p in policies if p.id == v.policy_id), None)
                if pol is None:
                    continue
                r = find_recourse(pol, fbp[pol.id], as_of=as_of, portfolio=policies, facts_by_policy=fbp)
                denials.append({"task": task["id"], "title": task.get("title"), "turn": i, "persona": persona, "policy_id": pol.id,
                                "agent_denial_code": rep.denial_codes.get(pol.id), **_summarise(r)})
    ok = [d for d in denials if "error" not in d]
    kinds = Counter(k for d in ok if d["has_recourse"] for k in d["best_kinds"])
    return {"n_tasks": len(tasks), "n_turns": n_turns, "n_denials": len(ok), "n_with_recourse": sum(d["has_recourse"] for d in ok),
            "by_code": dict(Counter(d["denial_code"] for d in ok)), "by_best_kind": dict(kinds), "denials": denials}


# --------------------------------------------------------------------------- part B
def _get(d: dict, *keys: str, default: Any = None) -> Any:
    for k in keys:
        if k in d and d[k] not in (None, ""):
            return d[k]
    return default


def load_fos() -> Optional[list[dict]]:
    if not FOS_PATH.exists():
        return None
    rows = []
    with FOS_PATH.open(encoding="utf8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def classify(text: str) -> list[str]:
    return [k for k, pat in CLAUSE_PATTERNS.items() if pat.search(text or "")]


def run_fos() -> dict:
    rows = load_fos()
    if rows is None:
        return {"available": False, "path": str(FOS_PATH), "n_decisions": 0, "n_modelled": 0, "by_clause_type": {}, "n_mapped": 0, "matches": []}
    mapping = json.loads(MAPPING_PATH.read_text(encoding="utf8")).get("mappings", []) if MAPPING_PATH.exists() else []
    by_type: Counter = Counter()
    modelled = 0
    ids_with_type: dict[str, list[str]] = {}
    for r in rows:
        text = " ".join(str(_get(r, k, default="")) for k in ("text", "body", "decision_text", "summary", "title"))
        types = classify(text)
        if types:
            modelled += 1
            by_type.update(types)
            ids_with_type[str(_get(r, "id", "decision_id", "reference", "drn", default=""))] = types
    results = []
    for m in mapping:
        persona = m["persona"]
        policies = policies_for_persona(persona)
        pol = next((p for p in policies if p.id == m["policy_id"]), None)
        if pol is None:
            results.append({"decision_id": m.get("decision_id"), "error": f"unknown policy {m.get('policy_id')}"})
            continue
        facts = ScenarioFacts(values={Slot(k): v for k, v in m.get("facts", {}).items()}, as_of=date.fromisoformat(m.get("as_of", "2026-10-11")))
        as_of = facts.as_of or date(2026, 10, 11)
        rep = adjudicate_like_insurer(pol, facts, [], as_of=as_of, documents_present=m.get("documents_present", []), portfolio=policies)
        top = rep.top_ground
        expected = m["ground_code"]
        codes = [g.code for g in rep.grounds]
        results.append({"decision_id": m.get("decision_id"), "clause_type": m.get("clause_type"), "expected": expected,
                        "twin_top": top.code if top else None, "twin_grounds": codes, "top_matches": bool(top and top.code == expected),
                        "any_matches": expected in codes, "in_corpus_types": ids_with_type.get(str(m.get("decision_id")), []),
                        "readiness_score": rep.readiness_score, "after_fix_score": rep.after_fix_score, "note": m.get("note")})
    return {"available": True, "path": str(FOS_PATH), "n_decisions": len(rows), "n_modelled": modelled, "by_clause_type": dict(by_type),
            "n_mapped": len(mapping), "matches": results}


# --------------------------------------------------------------------------- report
def _pct(n: int, d: int) -> str:
    return f"{n}/{d} ({100.0 * n / d:.0f}%)" if d else "0/0"


def write_report(a: dict, b: dict) -> str:
    L: list[str] = []
    L.append("# Recourse and adjudication-twin evaluation")
    L.append("")
    L.append("## Provenance")
    L.append("")
    L.append(f"- Generated by `python -m bench.recourse_eval` on {date.today().isoformat()}; deterministic (language model disabled, rule planner and rule fact binder only).")
    L.append("- Policies: the hand-verified sandbox records in `clauseguard/sandbox/persona_policies.py` (tier POLICY_DOC_VERIFIED); four are modelled on real public wordings (Sompo/Roojai HCP, Astra HCP rider, Astra Flexi Life, Chubb MY PA), the rest are mock wordings written for the sandbox.")
    L.append(f"- Part A replays the {a['n_tasks']} scripted tasks in `data/scripted_tasks/` ({a['n_turns']} turns) through `agent.loop.handle_turn`; every DENIED verdict is passed to `recourse.find_recourse` (breadth-first, at most 2 legitimate actions, Pareto-minimal by (days, money, effort)) with the persona's whole portfolio.")
    L.append("- Part B reads `data/real/fos_decisions.jsonl` when present and `bench/fos_mapping.json` (manual mapping).")
    L.append("- Raw results: `evidence/recourse_eval.json`.")
    L.append("")
    L.append("## Part A: recourse on the scripted tasks")
    L.append("")
    ok = [d for d in a["denials"] if "error" not in d]
    errs = [d for d in a["denials"] if "error" in d]
    L.append(f"DENIED verdicts seen: {a['n_denials']}; with a legitimate recourse: {_pct(a['n_with_recourse'], a['n_denials'])}.")
    if errs:
        L.append(f"Turns that raised an exception: {len(errs)} (listed in the raw file).")
    L.append("")
    L.append("| task | turn | policy | denial code | recourse | best action | cost (days, money, effort) | all Pareto options | blocked by |")
    L.append("|---|---|---|---|---|---|---|---|---|")
    for d in ok:
        cost = d["best_cost"]
        cost_s = f"({cost['days']}, {cost['money']}, {cost['effort']})" if cost else ""
        best = (d["best"] or "").replace("|", "/")
        L.append(f"| {d['task']} | {d['turn']} | {d['policy_id']} | {d['denial_code']} | {'yes' if d['has_recourse'] else 'no'} | {best} | {cost_s} | {'; '.join(d['all_options'])} | {', '.join(d['blocked_by_immutable'])} |")
    L.append("")
    L.append("Denial codes: " + ", ".join(f"{k} x{v}" for k, v in sorted(a["by_code"].items(), key=lambda kv: (-kv[1], str(kv[0])))) + ".")
    L.append("Best-option action kinds: " + (", ".join(f"{k} x{v}" for k, v in sorted(a["by_best_kind"].items())) or "none") + ".")
    L.append("")
    L.append("Reading the table: `WAIT` options give the calendar date from which a *new* admission is outside the waiting period or window; they never move the date of the admission that was denied. `CLAIM_OTHER_POLICY` means another policy of the same person covers the same facts. A denial that depends only on immutable facts (cause, survival days, licence, employment) correctly has no recourse on that policy.")
    L.append("")
    L.append("## Part B: real disputes (UK Financial Ombudsman decisions)")
    L.append("")
    if not b["available"]:
        L.append("`data/real/fos_decisions.jsonl` is not present, so this section is skipped. The loader, the clause-type classifier and the mapping replay are implemented and run as soon as the file exists; `bench/fos_mapping.json` holds the (currently empty) manual mapping table and its schema.")
    else:
        L.append(f"Decisions loaded: {b['n_decisions']}; decisions quoting a clause type the solver models: {b['n_modelled']} "
                 + "(" + ", ".join(f"{k}: {v}" for k, v in sorted(b["by_clause_type"].items())) + ").")
        L.append(f"Decisions with a manual mapping: {b['n_mapped']}.")
        ms = [m for m in b["matches"] if "error" not in m]
        if ms:
            top = sum(m["top_matches"] for m in ms)
            anym = sum(m["any_matches"] for m in ms)
            L.append(f"Twin top ground matches the ombudsman's ground: {_pct(top, len(ms))}; ground present anywhere in the twin's list: {_pct(anym, len(ms))}.")
            L.append("")
            L.append("| decision | clause type | ombudsman ground | twin top ground | all twin grounds | match |")
            L.append("|---|---|---|---|---|---|")
            for m in ms:
                L.append(f"| {m['decision_id']} | {m['clause_type']} | {m['expected']} | {m['twin_top']} | {', '.join(m['twin_grounds'])} | {'yes' if m['top_matches'] else 'no'} |")
        for m in b["matches"]:
            if "error" in m:
                L.append(f"- {m['decision_id']}: {m['error']}")
    L.append("")
    L.append("## Limits")
    L.append("")
    L.append("- The FOS mapping is manual: a human reads each decision, picks the closest sandbox policy and writes the facts; the twin is then judged against that reading, not against the decision text itself. A different reader could map a decision differently.")
    L.append("- Sample size: Part A has " + str(a["n_denials"]) + " denials from 33 scripted conversations over three personas and eleven policies; Part B has " + str(b.get("n_mapped", 0)) + " mapped decisions. Neither supports a rate with a useful confidence interval; the numbers describe this corpus only.")
    L.append("- UK decisions concern UK products and law; the sandbox policies are Indonesian and Malaysian wordings. Only the clause *type* (waiting period, pre-existing, late notification, exclusion) carries over, not the amounts, periods or the regulator's reasonableness test.")
    L.append("- Recourse costs are ordinal (money and effort 0..3) from a small table, not quotes; the time component is exact calendar arithmetic from the policy's dates.")
    L.append("- The twin lists grounds by isolating each clause under the frozen solver; a ground the solver cannot express (for example a reasonableness or disclosure argument) is not listed.")
    L.append("")
    return "\n".join(L)


def main() -> int:
    a = run_tasks()
    b = run_fos()
    RAW.write_text(json.dumps({"tasks": a, "fos": b}, indent=2, default=str), encoding="utf8")
    REPORT.write_text(write_report(a, b), encoding="utf8")
    print(f"denials {a['n_denials']}, with recourse {a['n_with_recourse']}; fos available={b['available']} mapped={b['n_mapped']}")
    print(f"wrote {REPORT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
