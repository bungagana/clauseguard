"""Run the scripted tasks (data/scripted_tasks/*.yaml) through agent.loop.handle_turn and write
evidence/task_report.md. Pass/fail is decided by code and regex over the structured Reply
fields only; no model judges anything.

Usage:
  python scripts/run_tasks.py                 # real API when GEMINI_API_KEY is set, else mocked
  python scripts/run_tasks.py --no-llm        # deterministic fallbacks only
  python scripts/run_tasks.py --source sandbox  # default: policies from a freshly seeded sandbox DB (--source fixtures is an alias)
  python scripts/run_tasks.py --only T14 A01

Task file format (YAML):
  id, title, persona, as_of (ISO), turns: [str | {user: str, expected: {...}}], expected: {...}
Criteria (all optional, all must hold):
  intent, verdict {policy_id, verdict}, payable {policy_id, amount}, denial_code {policy_id, code},
  deadline (ISO), recommends_plans [catalogue plan ids, in order], not_recommends_plans [ids], recommendation_total_le (IDR/month),
  must_contain [regex], must_not_contain [regex], in_order [regex...],
  expects_clarification_slot, expects_refusal, expects_ticket, no_tool_calls_of_tier_ge (int, counts
  *executed* calls), pep_denied_contains, actions_pending_tool, cob_order [policy ids], cob_status
  {policy_id: status}, max_questions (int), alerts_contain [regex], no_clarification (bool)
A turn string "__CONFIRM__" simulates the UI confirmation click for the first pending action.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import date
from decimal import Decimal
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from clauseguard import config  # noqa: E402
from clauseguard.agent.loop import Reply, confirm_pending, handle_turn  # noqa: E402
from clauseguard.agent.session import Session  # noqa: E402
from clauseguard.agent.tools import PolicySource, ToolRouter  # noqa: E402

TASK_DIR = ROOT / "data" / "scripted_tasks"
REPORT = config.EVIDENCE_DIR / "task_report.md"
RAW = config.EVIDENCE_DIR / "task_runs.jsonl"
# --suite off_script: realistic questions that are not part of T01-T23 / A01-A10 (same criteria language)
SUITES = {"main": (TASK_DIR, REPORT, RAW), "off_script": (TASK_DIR / "off_script", config.EVIDENCE_DIR / "offscript_report.md", config.EVIDENCE_DIR / "offscript_runs.jsonl"),
          "holdout": (TASK_DIR / "off_script_holdout", config.EVIDENCE_DIR / "offscript_holdout_report.md", config.EVIDENCE_DIR / "offscript_holdout_runs.jsonl"),
          "blind": (TASK_DIR / "off_script_blind", config.EVIDENCE_DIR / "offscript_blind_report.md", config.EVIDENCE_DIR / "offscript_blind_runs.jsonl"),
          "blind_llm": (TASK_DIR / "off_script_blind", config.EVIDENCE_DIR / "offscript_blind_llm_report.md", config.EVIDENCE_DIR / "offscript_blind_llm_runs.jsonl"),
          "blind2": (TASK_DIR / "off_script_blind2", config.EVIDENCE_DIR / "offscript_blind2_report.md", config.EVIDENCE_DIR / "offscript_blind2_runs.jsonl"),
          "blind3": (TASK_DIR / "off_script_blind3", config.EVIDENCE_DIR / "offscript_blind3_pre_report.md", config.EVIDENCE_DIR / "offscript_blind3_pre_runs.jsonl"),
          "blind3_post": (TASK_DIR / "off_script_blind3", config.EVIDENCE_DIR / "offscript_blind3_post_report.md", config.EVIDENCE_DIR / "offscript_blind3_post_runs.jsonl")}


# --------------------------------------------------------------------------- criteria
def check(expected: dict, rep: Reply, replies: list[Reply]) -> list[str]:
    """Returns a list of failure messages (empty = pass)."""
    fails: list[str] = []
    text = rep.text
    exp = expected or {}

    if "intent" in exp and rep.intent.value != exp["intent"]:
        fails.append(f"intent {rep.intent.value} != {exp['intent']}")
    if "verdict" in exp:
        want = exp["verdict"]
        v = next((x for x in rep.verdicts if x.policy_id == want["policy_id"]), None)
        if v is None or v.verdict.value != want["verdict"]:
            fails.append(f"verdict {want['policy_id']}: {v.verdict.value if v else None} != {want['verdict']}")
    if "payable" in exp:
        want = exp["payable"]
        v = next((x for x in rep.verdicts if x.policy_id == want["policy_id"]), None)
        got = v.payable if v else None
        if got is None or Decimal(str(got)) != Decimal(str(want["amount"])):
            fails.append(f"payable {want['policy_id']}: {got} != {want['amount']}")
    if "denial_code" in exp:
        want = exp["denial_code"]
        got = rep.denial_codes.get(want["policy_id"])
        if got is None:
            step = next((s for s in rep.cob if s.payer_policy_id == want["policy_id"]), None)
            got = step.denial_code if step else None
        if got != want["code"]:
            fails.append(f"denial_code {want['policy_id']}: {got} != {want['code']}")
    if "deadline" in exp:
        got = rep.deadline.isoformat() if rep.deadline else None
        if got != exp["deadline"]:
            fails.append(f"deadline {got} != {exp['deadline']}")
    for pat in map(str, exp.get("must_contain", [])):
        if not re.search(pat, text, flags=re.I | re.S):
            fails.append(f"must_contain /{pat}/")
    for pat in map(str, exp.get("must_not_contain", [])):
        if re.search(pat, text, flags=re.I | re.S):
            fails.append(f"must_not_contain /{pat}/")
    if "in_order" in exp:
        pos = []
        for pat in exp["in_order"]:
            m = re.search(pat, text, flags=re.I)
            pos.append(m.start() if m else None)
        if any(p is None for p in pos) or pos != sorted(pos):
            fails.append(f"in_order {exp['in_order']} -> {pos}")
    if "expects_clarification_slot" in exp:
        got = rep.clarification.slot.value if rep.clarification else None
        if got != exp["expects_clarification_slot"]:
            fails.append(f"clarification slot {got} != {exp['expects_clarification_slot']}")
    if exp.get("no_clarification") and rep.clarification is not None:
        fails.append(f"unexpected clarification on {rep.clarification.slot.value}")
    if "expects_refusal" in exp and bool(rep.refused) != bool(exp["expects_refusal"]):
        fails.append(f"refused {rep.refused} != {exp['expects_refusal']}")
    if exp.get("expects_ticket") and not rep.escalation_ticket:
        fails.append("no escalation ticket")
    if "no_tool_calls_of_tier_ge" in exp:
        n = exp["no_tool_calls_of_tier_ge"]
        bad = [c for r in replies for c in r.tool_calls if c["allowed"] and c["tier"] >= n]
        if bad:
            fails.append(f"executed tier>={n} calls: {[c['name'] for c in bad]}")
    if "pep_denied_contains" in exp:
        if not any(not c["allowed"] and exp["pep_denied_contains"] in c["reason"] for r in replies for c in r.tool_calls):
            fails.append(f"no PEP denial containing {exp['pep_denied_contains']}")
    if "actions_pending_tool" in exp:
        if not any(a.get("tool") == exp["actions_pending_tool"] for a in rep.actions_pending):
            fails.append(f"no pending action {exp['actions_pending_tool']}")
    if "cob_order" in exp:
        got = [s.payer_policy_id for s in rep.cob if s.payer_policy_id in exp["cob_order"]]
        if got != exp["cob_order"]:
            fails.append(f"cob_order {got} != {exp['cob_order']}")
    for pid, st in exp.get("cob_status", {}).items():
        step = next((s for s in rep.cob if s.payer_policy_id == pid), None)
        if step is None or step.status != st:
            fails.append(f"cob_status {pid}: {step.status if step else None} != {st}")
    if "max_questions" in exp and text.count("?") > exp["max_questions"]:
        fails.append(f"{text.count('?')} questions > {exp['max_questions']}")
    if "recommends_plans" in exp:
        got_plans = [r["plan_id"] for r in rep.recommendations]
        if got_plans != exp["recommends_plans"]:
            fails.append(f"recommended {got_plans} != {exp['recommends_plans']}")
    if exp.get("not_recommends_plans"):
        bad_plans = [r["plan_id"] for r in rep.recommendations if r["plan_id"] in exp["not_recommends_plans"]]
        if bad_plans:
            fails.append(f"recommended excluded plans {bad_plans}")
    if "recommendation_total_le" in exp:
        total = sum(r["monthly_premium_idr"] for r in rep.recommendations)
        if total > exp["recommendation_total_le"]:
            fails.append(f"recommended total {total} > {exp['recommendation_total_le']}")
    for pat in exp.get("alerts_contain", []):
        if not any(re.search(pat, a, flags=re.I) for a in rep.alerts):
            fails.append(f"alerts_contain /{pat}/")
    return fails


# --------------------------------------------------------------------------- runner
SANDBOX_USER = {"rizky": "C-RIZKY", "santoso": "C-BUDI", "dewi": "C-DEWI"}


def setup_sandbox() -> None:
    """Point the sandbox tools at a fresh temporary DB seeded from the single source (seed.py), and give
    this run a private kill-switch flag: evidence/AGENT_HALT belongs to the live backend and any other
    process (pytest, run_adversarial.py KS-01, an operator) that flips it must not pause a task run."""
    import os
    import tempfile

    from clauseguard.sandbox import db as sdb, tools as sb
    from clauseguard.security import kill_switch

    tmp = Path(tempfile.mkdtemp(prefix="cg_tasks_"))
    config.KILL_SWITCH_PATH = tmp / "AGENT_HALT"
    os.environ.pop(kill_switch.ENV_FLAG, None)
    sb.set_connection(sdb.init_db(seed=True, path=tmp / "tasks.sqlite"))


def run_task(task: dict, *, use_llm: bool, source_mode: str) -> dict:
    persona = task["persona"]
    user_id = SANDBOX_USER.get(persona, persona)
    as_of = date.fromisoformat(str(task.get("as_of", "2026-10-11")))
    session = Session(user_id, persona, as_of=as_of)
    router = ToolRouter(PolicySource(mode=source_mode))
    replies: list[Reply] = []
    turn_results: list[dict] = []
    t0 = time.time()
    for i, t in enumerate(task["turns"]):
        text = t["user"] if isinstance(t, dict) else t
        exp = t.get("expected") if isinstance(t, dict) else None
        try:
            rep = confirm_pending(session, router=router, use_llm=use_llm) if text == "__CONFIRM__" else handle_turn(session, text, router=router, use_llm=use_llm)
        except Exception as e:  # noqa: BLE001
            rep = Reply(text=f"EXCEPTION: {type(e).__name__}: {e}", intent="OUT_OF_SCOPE", refused=True, refusal_reason="EXCEPTION")
        replies.append(rep)
        fails = check(exp, rep, replies) if exp else []
        turn_results.append({"turn": i + 1, "user": text, "reply": rep.text, "fails": fails, "intent": rep.intent.value,
                             "verdicts": {v.policy_id: v.verdict.value for v in rep.verdicts}, "clarification": rep.clarification.slot.value if rep.clarification else None,
                             "tool_calls": rep.tool_calls, "actions_pending": [a.get("tool") for a in rep.actions_pending], "refused": rep.refused})
    final_fails = check(task.get("expected"), replies[-1], replies) if task.get("expected") else []
    all_fails = [f"turn {r['turn']}: {x}" for r in turn_results for x in r["fails"]] + [f"final: {x}" for x in final_fails]
    return {"id": task["id"], "title": task.get("title", ""), "persona": persona, "passed": not all_fails, "fails": all_fails,
            "turns": turn_results, "seconds": round(time.time() - t0, 2), "kind": task.get("kind", "functional")}


def load_tasks(only: list[str] | None, task_dir: Path = TASK_DIR) -> list[dict]:
    tasks = []
    for f in sorted(task_dir.glob("*.yaml")):
        t = yaml.safe_load(f.read_text(encoding="utf8"))
        if only and t["id"] not in only:
            continue
        tasks.append(t)
    return tasks


def write_report(results: list[dict], *, use_llm: bool, source_mode: str, report: Path = REPORT, raw: Path = RAW, title: str = "ClauseGuard scripted task report") -> None:
    n = len(results)
    ok = sum(1 for r in results if r["passed"])
    lines = [f"# {title}", "",
             f"Generated {date.today().isoformat()} - LLM: {'real API (' + config.MODEL_FAST + ')' if use_llm else 'mocked / deterministic fallbacks'} - policy source: {source_mode}",
             "", f"**{ok}/{n} tasks passed.** Criteria are evaluated by code and regex on structured Reply fields (verdict, payable, deadline, denial codes, clarification slot, refusal flag, executed tool tiers, COB order); no model judges anything.",
             "", "| id | kind | persona | title | result | failures |", "|---|---|---|---|---|---|"]
    for r in results:
        lines.append(f"| {r['id']} | {r['kind']} | {r['persona']} | {r['title']} | {'PASS' if r['passed'] else 'FAIL'} | {'; '.join(r['fails'])[:300]} |")
    for kind in ("functional", "adversarial", "off_script", "holdout", "blind", "blind2", "blind3", "recommendation", "in_sample_flow"):
        sub = [r for r in results if r["kind"] == kind]
        if sub:
            lines.append(f"\n{kind}: {sum(1 for r in sub if r['passed'])}/{len(sub)} passed")
    lines += ["", "## Failure details", ""]
    any_fail = False
    for r in results:
        if r["passed"]:
            continue
        any_fail = True
        lines.append(f"### {r['id']} - {r['title']}")
        for f in r["fails"]:
            lines.append(f"- {f}")
        for t in r["turns"]:
            lines.append(f"\n**Turn {t['turn']} user:** {t['user']}\n\n**Reply** (intent {t['intent']}, verdicts {t['verdicts']}, clarification {t['clarification']}):\n")
            lines.append("```\n" + t["reply"][:2500] + "\n```")
        lines.append("")
    if not any_fail:
        lines.append("None.")
    lines += ["", "## Transcripts (all tasks)", ""]
    for r in results:
        lines.append(f"### {r['id']} - {r['title']} ({'PASS' if r['passed'] else 'FAIL'})")
        for t in r["turns"]:
            tools = ", ".join(f"{c['name']}{'' if c['allowed'] else ' DENIED:' + c['reason']}" for c in t["tool_calls"]) or "-"
            lines.append(f"\n**User:** {t['user']}\n\n**Tools:** {tools}\n\n```\n{t['reply'][:1800]}\n```")
        lines.append("")
    notes_src = TASK_DIR / ("off_script_holdout" if "holdout" in report.name else ("off_script_blind3" if "blind3" in report.name else "off_script_blind2" if "blind2" in report.name else ("off_script_blind" if "blind" in report.name else "off_script"))) / "NOTES.md"
    if report.name != "task_report.md" and notes_src.exists():  # hand-written reading notes that sit next to the task files
        lines = lines[:2] + [notes_src.read_text(encoding="utf8"), ""] + lines[2:]
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text("\n".join(lines), encoding="utf8")
    with raw.open("w", encoding="utf8") as f:
        for r in results:
            f.write(json.dumps(r, default=str, ensure_ascii=False) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-llm", action="store_true", help="deterministic fallbacks only (no API calls)")
    ap.add_argument("--source", choices=["sandbox", "fixtures", "auto"], default="sandbox",
                    help="policy source; 'fixtures' is kept as an alias of 'sandbox' (there is a single source of truth)")
    ap.add_argument("--suite", choices=sorted(SUITES), default="main")
    ap.add_argument("--only", nargs="*")
    a = ap.parse_args()
    use_llm = not a.no_llm and bool(config.GEMINI_API_KEY)
    if not use_llm:
        from clauseguard import llm

        def _no_llm(*args, **kw):
            raise RuntimeError("LLM disabled for this run")

        llm.generate_json = _no_llm  # every LLM path falls back to its deterministic template
    if a.source == "fixtures":
        a.source = "sandbox"
    setup_sandbox()
    task_dir, report, raw = SUITES[a.suite]
    results = [run_task(t, use_llm=use_llm, source_mode=a.source) for t in load_tasks(a.only, task_dir)]
    write_report(results, use_llm=use_llm, source_mode=a.source, report=report, raw=raw,
                 title={"main": "ClauseGuard scripted task report", "off_script": "ClauseGuard off-script question report", "holdout": "ClauseGuard second off-script batch (a dev set: probed before it was fixed)", "blind": "ClauseGuard blind off-script batch (written and run once, before any fix)", "blind_llm": "ClauseGuard off-script dev set run with the model (the former blind set, seen during this fix pass)", "blind2": "ClauseGuard second blind off-script batch (unseen paraphrases, run once with the model before any fix)",
                        "blind3": "ClauseGuard third blind batch: multi-step claim flows (run once with the model before the flows were built)",
                        "blind3_post": "ClauseGuard third blind batch: single rerun after the flows were built (no longer out-of-sample)"}[a.suite])
    ok = sum(1 for r in results if r["passed"])
    print(f"{ok}/{len(results)} passed -> {report}")
    for r in results:
        print(f"  {r['id']:<4} {'PASS' if r['passed'] else 'FAIL'}  {r['title'][:60]}" + ("" if r["passed"] else "  :: " + "; ".join(r["fails"])[:200]))
    return 0 if ok == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
