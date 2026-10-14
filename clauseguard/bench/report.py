"""Render evidence/bench_report.md from evidence/bench_*.jsonl. Usage: python -m bench.report"""
from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path

from clauseguard import config

from .metrics import accuracy, load, mcnemar, summarize

SYSTEM_ORDER = ["b0", "b0cw", "b4", "b4oracle"]
SYSTEM_DESC = {
    "b0": "whole contract + scenario, schema JSON (extract model, T=0)",
    "b0cw": "B0 + explicit closed-world instruction",
    "b4": "extracted typed tuples + deterministic solver (LLM binds facts only)",
    "b4oracle": "ABox oracle tuples + deterministic solver (LLM binds facts only)",
}


def pct(x: float) -> str:
    return "n/a" if x != x else f"{100 * x:.1f}"


def render(evidence_dir: Path) -> str:
    data = {s: load(evidence_dir / f"bench_{s}.jsonl") for s in SYSTEM_ORDER}
    data = {s: r for s, r in data.items() if r}
    summ = {s: summarize(r) for s, r in data.items()}
    L = []
    L.append("# ClauseGuard benchmark report\n")
    L.append("Benchmark: Mridul, Kapa & Seneviratne (2026), 58 scenarios x 10 synthetic US life-insurance contracts, labels {COVERED, DENIED, NOT_APPLICABLE}. "
             "Ground truth is clause-traced. All conditions: Gemini API, temperature 0, schema-constrained JSON, disk-cached. "
             "The paper's own LLM baselines were run through web chat; ours are API + schema, so B0 is expected to score higher than the paper's reported numbers.\n")
    L.append("## Overall (all scenarios the condition was run on)\n")
    L.append("| system | contracts | n | accuracy | 95% CI (bootstrap over scenarios) | macro-F1 | NA->DENIED | evidence hit (n) | evidence hit, correct only (n) | fallback | clarify-resolved |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|")
    for s, m in summ.items():
        lo, hi = m["ci95"]
        L.append(f"| {s} | {','.join(m['contracts'])} | {m['n']} | {pct(m['accuracy'])} | [{pct(lo)}, {pct(hi)}] | {pct(m['macro_f1'])} | {pct(m['na_to_denied'])} | "
                 f"{pct(m['evidence_hit'])} ({m['evidence_n']}) | {pct(m['evidence_hit_correct_only'])} ({m['evidence_n_correct']}) | {m['fallback_n']} | {m['clarify_resolved_n']} |")
    L.append("")
    for s, m in summ.items():
        L.append(f"- **{s}**: {SYSTEM_DESC.get(s, '')}")
    L.append("")

    # ---- paired comparison on the common subset
    common = None
    for s, recs in data.items():
        keys = {(r["scenario_id"], r["contract_id"]) for r in recs}
        common = keys if common is None else common & keys
    if common and len(data) > 1:
        L.append(f"## Paired comparison on the common subset ({len(common)} items, {len({k[0] for k in common})} scenarios x {sorted({k[1] for k in common}, key=lambda c: int(c[1:]))})\n")
        L.append("| system | accuracy | macro-F1 | NA->DENIED | evidence hit | in-scope acc (n) | out-of-scope acc (n) |")
        L.append("|---|---|---|---|---|---|---|")
        for s, recs in data.items():
            sub = [r for r in recs if (r["scenario_id"], r["contract_id"]) in common]
            m = summarize(sub)
            ins = f"{pct(m['in_scope']['acc'])} ({m['in_scope']['n']})" if m.get("in_scope") else "-"
            outs = f"{pct(m['out_scope']['acc'])} ({m['out_scope']['n']})" if m.get("out_scope") else "-"
            L.append(f"| {s} | {pct(m['accuracy'])} | {pct(m['macro_f1'])} | {pct(m['na_to_denied'])} | {pct(m['evidence_hit'])} | {ins} | {outs} |")
        L.append("")
        if "b0cw" in data:
            L.append("### McNemar vs B0CW (paired, exact binomial on discordant pairs)\n")
            L.append("| system | pairs | system right / B0CW wrong | system wrong / B0CW right | p (exact) |")
            L.append("|---|---|---|---|---|")
            for s, recs in data.items():
                if s == "b0cw":
                    continue
                mc = mcnemar(recs, data["b0cw"])
                L.append(f"| {s} | {mc['n_pairs']} | {mc['b01']} | {mc['b10']} | {mc['p_exact']:.3f} |")
            L.append("")

    # ---- scope breakdown for B4 conditions (the solver-scope subset is the honest headline for B4)
    for s in ("b4oracle", "b4"):
        if s not in summ:
            continue
        m = summ[s]
        L.append(f"## {s}: solver-scope subset vs. B0CW fallback\n")
        if m.get("in_scope"):
            L.append(f"- In solver scope (coverage / exclusion / period / rider / termination / permitted action): n={m['in_scope']['n']}, accuracy {pct(m['in_scope']['acc'])}, macro-F1 {pct(m['in_scope']['macro_f1'])}, NA->DENIED {pct(m['in_scope']['na_to_denied'])}")
        if m.get("out_scope"):
            L.append(f"- Out of scope (answered by B0CW fallback, flagged): n={m['out_scope']['n']}, accuracy {pct(m['out_scope']['acc'])}")
        L.append("")
        L.append("Per-scenario accuracy (in-scope scenarios below 100% are listed with the failure reason in bench/README.md):\n")
        L.append("| scenario | category | scope | acc |")
        L.append("|---|---|---|---|")
        recs = data[s]
        scope_of = {r["scenario_id"]: r.get("in_scope") for r in recs}
        for sid, ps in m["per_scenario"].items():
            L.append(f"| {sid} | {ps['category']} | {'solver' if scope_of.get(sid) else 'fallback'} | {pct(ps['acc'])} |")
        L.append("")

    # ---- residual b4oracle errors that are ground-truth inconsistencies
    if "b4oracle" in data:
        L.append("## B4-oracle residual errors: ground-truth inconsistencies\n")
        L.append("The oracle condition feeds the benchmark's own ABox into the solver, so its residual errors isolate label noise. Each row quotes the scenario text and the labels the ground truth gives to the *same* contract under the same facts.\n")
        L.append("| scenario | text (abridged) | contracts wrong | ground truth | conflicting ground truth |")
        L.append("|---|---|---|---|---|")
        from .data import scenario_by_id
        wrong = defaultdict(list)
        for r in data["b4oracle"]:
            if r.get("in_scope") and r["pred"] != r["gt"]:
                wrong[r["scenario_id"]].append(r["contract_id"])
        rows = [
            ("SCEN-046", "SCEN-035", "C1", "same wording ('accidental death benefit claim'), same contracts: 046 = COVERED, 035 = NOT_APPLICABLE"),
            ("SCEN-057", "SCEN-025", "C1", "material misrepresentation inside the 2-year contestability window: 057 (23 months) = COVERED / NOT_APPLICABLE, 025 (18 months) = DENIED on all 10"),
            ("SCEN-018", "SCEN-001", "C8", "single death on the second-to-die policy: 018/019/037 = COVERED, 001/004/005 = DENIED, 011 = NOT_APPLICABLE"),
            ("SCEN-011", "SCEN-001", "C8", "as above"),
            ("SCEN-008", "SCEN-008", "C10", "`lapseAutoPaysSurrenderValue` is true for C3 (COVERED) and C10 (NOT_APPLICABLE) in the ABox"),
        ]
        for sid, other, cid, note in rows:
            if sid not in wrong:
                continue
            scn, oth = scenario_by_id(sid), scenario_by_id(other)
            gt = scn["gt"].get(cid, {}).get("status", "?")
            ogt = oth["gt"].get(cid, {}).get("status", "?")
            txt = scn["scenario_description"].replace("|", "/")[:160]
            L.append(f"| {sid} | {txt} | {', '.join(wrong[sid])} | {cid}: {gt} | {other} {cid}: {ogt} - {note} |")
        abox_gap = [(sid, cids) for sid, cids in wrong.items() if sid in ("SCEN-012", "SCEN-021", "SCEN-054")]
        if abox_gap:
            L.append("")
            L.append("ABox gaps (clause exists in the contract text but not in the ground-truth ABox): " + "; ".join(f"{sid} {','.join(c)}" for sid, c in abox_gap) + " (C5 loans, C9 early-surrender schedule, C5 graded accidental carve-out).")
        L.append("")

    # ---- confusion matrices
    L.append("## Confusion matrices (rows = ground truth, columns = prediction)\n")
    for s, m in summ.items():
        L.append(f"**{s}**\n")
        L.append("| gt \\ pred | COVERED | DENIED | NOT_APPLICABLE |")
        L.append("|---|---|---|---|")
        for g, row in m["confusion"].items():
            L.append(f"| {g} | {row['COVERED']} | {row['DENIED']} | {row['NOT_APPLICABLE']} |")
        L.append("")

    # ---- per-category for all systems on the common subset
    if common:
        cats = sorted({r["category"] for recs in data.values() for r in recs if (r["scenario_id"], r["contract_id"]) in common})
        L.append("## Per-category accuracy (common subset)\n")
        L.append("| category | " + " | ".join(data) + " |")
        L.append("|---|" + "---|" * len(data))
        for c in cats:
            row = []
            for s, recs in data.items():
                sub = [r for r in recs if r["category"] == c and (r["scenario_id"], r["contract_id"]) in common]
                row.append(pct(accuracy(sub)) if sub else "-")
            L.append(f"| {c} | " + " | ".join(row) + " |")
        L.append("")
    L.append("## Per-contract accuracy\n")
    L.append("| contract | " + " | ".join(data) + " |")
    L.append("|---|" + "---|" * len(data))
    for cid in [f"C{i}" for i in range(1, 11)]:
        row = [pct(summ[s]["per_contract"][cid]["acc"]) if cid in summ[s]["per_contract"] else "-" for s in data]
        L.append(f"| {cid} | " + " | ".join(row) + " |")
    L.append("")
    L.append("Evidence hit = predicted section matches the ground-truth section, or >= 40% token overlap between the predicted excerpt and the ground-truth quote; "
             "computed only where the ground truth cites a clause. NOT_SPECIFIED is scored as NOT_APPLICABLE. "
             "Bootstrap CI resamples scenarios (each a cluster of contracts), not labels. McNemar uses the exact binomial test on discordant pairs.\n")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--evidence", default=str(config.EVIDENCE_DIR))
    ap.add_argument("--out", default=str(config.EVIDENCE_DIR / "bench_report.md"))
    args = ap.parse_args()
    md = render(Path(args.evidence))
    Path(args.out).write_text(md, encoding="utf8")
    print(md)


if __name__ == "__main__":
    main()
