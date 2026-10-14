"""LLM calls and token cost per chat turn, versus a whole-policy long-context baseline.

The scripted tasks (T01-T23, A01-A10) are replayed turn by turn with the LLM paths ENABLED but in
replay-only mode (`CG_LLM_REPLAY_ONLY=1`): `llm.generate_json` is never allowed to reach the network,
and a call-hook records every call the agent loop *attempts* (which module, prompt / system / schema
size, whether the answer was in the disk cache). When the cache has no answer the loop falls back to its
deterministic path, exactly as it does when the API is unavailable, so the count is the number of calls
the loop issues per turn, independent of quota.

Token estimates: tokens = characters / 4. Output tokens use fixed per-purpose assumptions (the schemas
cap them): planner 40, fact binder 150, explanation 180, clarification 40.

Baseline ("whole-policy long context"): one call per turn whose prompt holds the full text of every
policy the user holds (the extracted source text of the public PDF where one exists under `CG_POLICY_TEXT_DIR`,
otherwise the sandbox wording) plus the question; 250 output tokens.

Output: evidence/cost_report.md (+ .json)
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import statistics
import sys
import tempfile
from collections import Counter
from datetime import date
from pathlib import Path

os.environ["CG_LLM_REPLAY_ONLY"] = "1"
os.environ.setdefault("CG_AUDIT_PATH", str(Path(tempfile.mkdtemp(prefix="cg_audit_")) / "audit.jsonl"))
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from clauseguard import config, llm  # noqa: E402
from clauseguard.agent.loop import Reply, confirm_pending, handle_turn  # noqa: E402
from clauseguard.agent.session import Session  # noqa: E402
from clauseguard.agent.tools import PolicySource, ToolRouter  # noqa: E402

OUT_TOKENS = {"_LLMPlan": 40, "FactSheet": 150, "_LLMExplanation": 180, "_LLMQuestion": 40, "_LLMComposed": 250}
PURPOSE = {"_LLMPlan": "intent planner", "FactSheet": "fact binder", "_LLMExplanation": "explainer wording", "_LLMQuestion": "clarifier wording",
           "_LLMComposed": "reply composer"}
BASELINE_OUT = 250
BASELINE_SYSTEM_CHARS = 400
DOCS = Path(os.environ.get("CG_POLICY_TEXT_DIR", ROOT / "data" / "policies" / "real_text"))  # optional plain-text copies of data/policies/real/*.pdf
SOURCE_DOC = {"HCP-SOMPO-01": "roojai_hcp_en.txt", "TL-ASTRA-07": "astra_flexi_life.txt", "HCP-RIDER-B": "astra_hcp.txt", "PA-CHUBB-03": "chubb_my_pa.txt"}


def _load_run_tasks():
    spec = importlib.util.spec_from_file_location("run_tasks_cost", ROOT / "scripts" / "run_tasks.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["run_tasks_cost"] = mod
    spec.loader.exec_module(mod)
    return mod


def baseline_policy_chars(policies) -> tuple[int, int]:
    """(chars of source documents where available else sandbox wording, chars of sandbox wording only)."""
    full = wording = 0
    for p in policies:
        w = sum(len(t.evidence.text) for t in p.tuples)
        wording += w
        f = DOCS / SOURCE_DOC.get(p.id, "")
        full += len(f.read_text(encoding="utf8", errors="ignore")) if p.id in SOURCE_DOC and f.exists() else w
    return full, wording


def tokens_in(c: dict) -> float:
    return (c["prompt_chars"] + c["system_chars"] + c["schema_chars"]) / 4


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(config.EVIDENCE_DIR / "cost_report.md"))
    ap.add_argument("--notes", default="")
    a = ap.parse_args()
    rt = _load_run_tasks()
    rt.setup_sandbox()
    calls: list[dict] = []
    llm.set_call_hook(calls.append)
    rows = []
    for task in rt.load_tasks(None, rt.TASK_DIR):
        persona = task["persona"]
        user = rt.SANDBOX_USER.get(persona, persona)
        s = Session(user, persona, as_of=date.fromisoformat(str(task.get("as_of", "2026-10-11"))))
        router = ToolRouter(PolicySource(mode="sandbox"))
        for i, t in enumerate(task["turns"]):
            text = t["user"] if isinstance(t, dict) else t
            calls.clear()
            try:
                rep: Reply = confirm_pending(s, router=router, use_llm=True) if text == "__CONFIRM__" else handle_turn(s, text, router=router, use_llm=True)
            except Exception as e:  # noqa: BLE001
                rep = Reply(text=f"EXCEPTION {e}", intent="OUT_OF_SCOPE", refused=True)
            mine = list(calls)
            pol = router.source.policies_for(s)
            full, wording = baseline_policy_chars(pol)
            q = len(text)
            t_in = sum(tokens_in(c) for c in mine)
            t_out = sum(OUT_TOKENS.get(c["schema"], 100) for c in mine)
            rows.append({
                "task": task["id"], "turn": i + 1, "user": text[:80], "intent": rep.intent.value, "refused": bool(rep.refused), "n_calls": len(mine),
                "by_purpose": dict(Counter(PURPOSE.get(c["schema"], c["schema"]) for c in mine)), "cache_answers": sum(1 for c in mine if c["cached"]),
                "tokens_in": round(t_in), "tokens_out": t_out, "tokens_total": round(t_in + t_out),
                "baseline_tokens_full_docs": round((full + q + BASELINE_SYSTEM_CHARS) / 4 + BASELINE_OUT),
                "baseline_tokens_wording_only": round((wording + q + BASELINE_SYSTEM_CHARS) / 4 + BASELINE_OUT),
            })
    llm.set_call_hook(None)
    def summarise(rs: list[dict]) -> dict:
        n = [r["n_calls"] for r in rs]
        tot = [r["tokens_total"] for r in rs]
        b_full = [r["baseline_tokens_full_docs"] for r in rs]
        b_word = [r["baseline_tokens_wording_only"] for r in rs]
        with_llm = [r for r in rs if r["n_calls"] > 0]
        purpose = Counter()
        for r in rs:
            purpose.update(r["by_purpose"])
        return {
            "turns": len(rs), "tasks": len({r["task"] for r in rs}),
            "calls_per_turn_mean": round(statistics.mean(n), 2), "calls_per_turn_max": max(n), "calls_per_turn_median": statistics.median(n),
            "turns_with_zero_calls": sum(1 for x in n if x == 0), "turns_with_zero_calls_pct": round(100 * sum(1 for x in n if x == 0) / len(n)),
            "tokens_per_turn_mean": round(statistics.mean(tot)), "tokens_per_turn_max": max(tot),
            "tokens_per_llm_turn_mean": round(statistics.mean(r["tokens_total"] for r in with_llm)) if with_llm else 0,
            "baseline_full_docs_mean": round(statistics.mean(b_full)), "baseline_full_docs_max": max(b_full),
            "baseline_wording_mean": round(statistics.mean(b_word)), "baseline_wording_max": max(b_word),
            "ratio_vs_full_docs": round(statistics.mean(tot) / statistics.mean(b_full), 3), "ratio_vs_wording": round(statistics.mean(tot) / statistics.mean(b_word), 3),
            "calls_by_purpose": dict(purpose), "cache_answers": sum(r["cache_answers"] for r in rs), "calls_total": sum(n),
        }

    summary = summarise(rows)
    functional = summarise([r for r in rows if r["task"].startswith("T")])
    top = sorted(rows, key=lambda r: -r["n_calls"])[:4]
    purpose_total = Counter(summary["calls_by_purpose"])
    L = ["# Token and call cost report", "",
         f"Generated {date.today().isoformat()}. `python bench/cost_eval.py` reproduces this file with no API calls (`CG_LLM_REPLAY_ONLY=1`). "
         f"Scope: {summary['turns']} chat turns of the {summary['tasks']} scripted tasks (T01-T23 functional incl. plan recommendation, A01-A10 adversarial), run with the LLM paths enabled. "
         "The loop's call-hook records every LLM call the loop *attempts*; with no cached answer it falls back to its deterministic path, so these are the calls per turn the design issues, independent of API quota.", "",
         "## LLM calls per chat turn", "",
         "| measure | value |", "|---|---|",
         f"| mean calls per turn | **{summary['calls_per_turn_mean']}** |", f"| median | {summary['calls_per_turn_median']} |", f"| max | **{summary['calls_per_turn_max']}** |",
         f"| turns with zero LLM calls | {summary['turns_with_zero_calls']} of {summary['turns']} ({summary['turns_with_zero_calls_pct']}%) - refusals, T2/T3 actions, hard guardrails, glossary and status lookups |",
         f"| calls by purpose (total {summary['calls_total']}) | " + ", ".join(f"{k}: {v}" for k, v in sorted(purpose_total.items())) + " |",
         f"| of which already in the disk cache | {summary['cache_answers']} |", "",
         "Purposes: the planner refines the intent only for benign intents (never for safety-relevant ones, which the rules decide before any model is consulted); "
         "the fact binder runs only when a scenario is expected; the explainer words one verdict per decided policy and falls back to a template if its quote is not verbatim; "
         "the clarifier words at most one question per turn. **With no key, no quota or `--no-llm` every one of these calls is skipped and the answer is the deterministic template: 0 calls.**", "",
         f"Functional tasks only (T01-T23, excluding A09's 50 repeated refusal turns, which pull the all-task mean down): {functional['turns']} turns, mean **{functional['calls_per_turn_mean']}** calls per turn, median {functional['calls_per_turn_median']}, max {functional['calls_per_turn_max']}, "
         f"{functional['turns_with_zero_calls']} turns with zero calls; mean {functional['tokens_per_turn_mean']:,} tokens per turn (max {functional['tokens_per_turn_max']:,}) against {functional['baseline_full_docs_mean']:,} for the full-document baseline "
         f"({100 * functional['ratio_vs_full_docs']:.1f}%) and {functional['baseline_wording_mean']:,} for the wording-only baseline ({100 * functional['ratio_vs_wording']:.1f}%).", "",
         "Turns with the most calls: " + "; ".join(f"{r['task']} turn {r['turn']} ({r['n_calls']} calls: {', '.join(f'{k} x{v}' for k, v in r['by_purpose'].items())})" for r in top) + ".", "",
         "## Estimated tokens per turn", "",
         "tokens = characters / 4 over prompt + system prompt + response schema; output tokens: planner 40, fact binder 150, explanation 180, clarification 40 (assumptions, the schemas cap them).", "",
         "| | mean per turn | max |", "|---|---|---|",
         f"| ClauseGuard (calls issued) | **{summary['tokens_per_turn_mean']:,}** | {summary['tokens_per_turn_max']:,} |",
         f"| ClauseGuard, only turns that call a model | {summary['tokens_per_llm_turn_mean']:,} | |",
         f"| baseline: all of the user's policy documents in context (1 call) | {summary['baseline_full_docs_mean']:,} | {summary['baseline_full_docs_max']:,} |",
         f"| baseline: sandbox wording of the user's policies only (1 call) | {summary['baseline_wording_mean']:,} | {summary['baseline_wording_max']:,} |", "",
         f"On the functional tasks ClauseGuard issues **{100 * functional['ratio_vs_full_docs']:.0f}%** of the full-document baseline's tokens per turn and **{100 * functional['ratio_vs_wording']:.0f}%** of the wording-only baseline's "
         f"(over all {summary['turns']} turns, including the zero-call refusal turns: {100 * summary['ratio_vs_full_docs']:.0f}% and {100 * summary['ratio_vs_wording']:.0f}%). "
         "The saving comes from the architecture: the model never reads a policy. It sees the user's sentence (fact binder), a verdict that the solver already computed plus one clause (explainer), or one slot name (clarifier). "
         "The baseline must resend every policy every turn, and its answer still has to be trusted instead of verified.", "",
         "Caveats: (1) the baseline is a rough size model (one call, no retrieval, no history); a retrieval-augmented baseline would sit between the two; "
         "(2) the mock policies in the sandbox are short, so the full-document baseline is dominated by the four real policy documents (Roojai/Sompo, Astra Flexi Life, Astra HCP, Chubb PA); against the short mock wording alone the saving is only about a quarter, because the explainer sends one clause per decided policy; "
         "(3) output-token figures are assumptions, input-token figures are measured prompt sizes / 4; (4) ClauseGuard also has one-off extraction cost per policy document (not a per-turn cost, cached on disk).", "",
         "## Per turn", "", "| task | turn | intent | calls | purposes | tokens (ours) | tokens (baseline, full docs) |", "|---|---|---|---|---|---|---|"]
    for r in rows:
        L.append(f"| {r['task']} | {r['turn']} | {r['intent']}{' (refused)' if r['refused'] else ''} | {r['n_calls']} | {', '.join(f'{k} x{v}' for k, v in r['by_purpose'].items()) or '-'} | {r['tokens_total']:,} | {r['baseline_tokens_full_docs']:,} |")
    if a.notes and Path(a.notes).exists():
        L += ["", Path(a.notes).read_text(encoding="utf8")]
    Path(a.out).write_text("\n".join(L), encoding="utf8")
    Path(a.out).with_suffix(".json").write_text(json.dumps({"summary": summary, "functional": functional, "rows": rows}, indent=1), encoding="utf8")
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
