"""Diagnosis-line -> ICD-10 category evaluation: retrieval ablation on a development and a held-out set.

Two team-authored sets (neither is a public clinical benchmark; no public Indonesian
discharge-summary benchmark with ICD-10 labels exists):

  development  data/benchmark/icd_eval.jsonl          76 lines, seen while the pipeline was built
  held-out     data/benchmark/icd_eval_heldout.jsonl  85 lines, written and frozen before any
               retrieval ablation was run; the primary evidence

Retrieval configurations over the same normalised terms and the same selection step:

  bm25            BM25 over the English terms (the previous default)
  <b>:emb         dense similarity only (English terms and raw text, rank-fused)
  <b>:hybrid      reciprocal-rank fusion (k=60) of BM25 and the dense rankings

with <b> in {gemini (gemini-embedding-001 API), e5onnx (multilingual-e5-small int8, local CPU)}.

Per set and configuration: retrieval recall@5/10/20 over category rankings, category accuracy of
the full pipeline, undetermined rate and FALSE-CODE rate (a category outside the gold set, or any
category on a gold-undetermined line), all with Wilson 95% intervals; exact McNemar tests against
BM25 on the same lines; latency and model calls per line. The alias dictionary row is the offline
fallback path.

Usage: python -m bench.icd_eval [--configs bm25,gemini:hybrid,...] [--offline] [--timing-lines N]
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
import time
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any, Optional, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from clauseguard import config, icd10_coder, icd10_embed, icd10_lookup, llm  # noqa: E402

BENCH = config.DATA_DIR / "benchmark"
SETS = {"development": BENCH / "icd_eval.jsonl", "heldout": BENCH / "icd_eval_heldout.jsonl"}
REPORT = config.EVIDENCE_DIR / "icd_report.md"
RESULTS = config.EVIDENCE_DIR / "icd_results.jsonl"
ALL_CONFIGS = ["bm25", "gemini:emb", "gemini:hybrid", "e5onnx:emb", "e5onnx:hybrid"]
COST_ORDER = ["e5onnx:hybrid", "gemini:hybrid", "bm25"]
PREVIOUS = {"n": 76, "accuracy": "92.2%", "false_code": "3.9%", "recall": "96.9%"}


# --------------------------------------------------------------------------- statistics
def wilson(k: int, n: int, z: float = 1.959964) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion."""
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, centre - half), min(1.0, centre + half))


def binom_two_sided(b: int, c: int) -> float:
    """Exact two-sided McNemar p-value from the discordant counts (binomial, p = 0.5)."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def mcnemar(a_ok: Sequence[bool], b_ok: Sequence[bool]) -> dict[str, Any]:
    """Paired comparison of two systems on the same lines; b_only = system B right and A wrong."""
    a_only = sum(1 for x, y in zip(a_ok, b_ok) if x and not y)
    b_only = sum(1 for x, y in zip(a_ok, b_ok) if y and not x)
    return {"a_only": a_only, "b_only": b_only, "p": binom_two_sided(a_only, b_only)}


def fmt_ci(k: int, n: int) -> str:
    if n == 0:
        return "n/a"
    lo, hi = wilson(k, n)
    return f"{100 * k / n:.1f}% ({k}/{n}) [{100 * lo:.1f}, {100 * hi:.1f}]"


# --------------------------------------------------------------------------- data + running
def load_set(path: Path) -> list[dict]:
    rows = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    for r in rows:
        assert r["gold"] is None or (isinstance(r["gold"], list) and r["gold"]), r
    return rows


def run_line(text: str, terms: list[str], how: str, retriever: str) -> dict[str, Any]:
    t0 = time.perf_counter()
    try:
        cands, used, ranked = icd10_coder._retrieve(terms, icd10_coder.TOP_K_CATEGORIES, icd10_coder.TOP_K_FULL_CODES, text, retriever)
        t_retr = time.perf_counter() - t0
        res = icd10_coder.select(text, terms, cands)
    except icd10_coder.CoderUnavailable as e:
        return {"ran": False, "category": None, "error": str(e)[:200], "retriever": retriever}
    return {
        "ran": True, "category": res.category, "code": res.code, "confidence": res.confidence, "matched_phrase": res.matched_phrase,
        "reject_reason": res.reject_reason, "retriever_used": used, "ranked": ranked[:20], "candidates": [c.code for c in cands],
        "retrieval_seconds_cached_queries": round(t_retr, 4),
    }


def hit_at(r: dict, pred: dict, k: int) -> bool:
    return any(g in pred["ranked"][:k] for g in r["gold"])


def line_ok(r: dict, pred: dict) -> bool:
    return pred["category"] in r["gold"] if r["gold"] else pred["category"] is None


def is_false(r: dict, pred: dict) -> bool:
    return pred["category"] is not None and (not r["gold"] or pred["category"] not in r["gold"])


def metrics(rows: list[dict], preds: list[dict]) -> dict[str, Any]:
    coded = [(r, p) for r, p in zip(rows, preds) if r["gold"]]
    n = len(rows)
    out = {
        "n": n, "n_coded": len(coded), "n_null": n - len(coded),
        "correct": sum(1 for r, p in coded if p["category"] in r["gold"]),
        "undetermined": sum(1 for p in preds if p["category"] is None),
        "false_code": sum(1 for r, p in zip(rows, preds) if is_false(r, p)),
        "false_on_null": sum(1 for r, p in zip(rows, preds) if not r["gold"] and p["category"] is not None),
    }
    for k in (5, 10, 15, 20):
        out[f"recall@{k}"] = sum(1 for r, p in coded if hit_at(r, p, k))
    return out


def timing_pass(configs: list[str], rows: list[dict], norm: dict[str, tuple[list[str], str]], n_lines: int) -> dict[str, dict]:
    """Retrieval latency with the query-vector cache off (embedding cost included)."""
    out: dict[str, dict] = {}
    icd10_embed.QUERY_CACHE_ENABLED = False
    try:
        for cfg in configs:
            ts = []
            for r in rows[:n_lines]:
                terms, _ = norm[r["text"]]
                t0 = time.perf_counter()
                try:
                    icd10_coder._retrieve(terms, 15, 5, r["text"], cfg)
                except Exception as e:  # noqa: BLE001
                    out[cfg] = {"error": str(e)[:100]}
                    break
                ts.append(time.perf_counter() - t0)
            else:
                out[cfg] = {"median_ms": 1000 * statistics.median(ts), "p95_ms": 1000 * sorted(ts)[max(0, int(0.95 * len(ts)) - 1)], "n": len(ts)}
    finally:
        icd10_embed.QUERY_CACHE_ENABLED = True
    return out


def index_status(name: str) -> Optional[str]:
    cl = icd10_coder.code_list()
    docs = icd10_embed.category_documents(cl.codes, cl.category_label)
    idx = icd10_embed.load_index(icd10_embed.get_backend(name), docs)
    return None if idx is None else f"{len(idx.ids)} categories x {idx.matrix.shape[1]} dims"


# --------------------------------------------------------------------------- main
def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--configs", default=",".join(ALL_CONFIGS))
    ap.add_argument("--offline", action="store_true", help="alias dictionary only")
    ap.add_argument("--timing-lines", type=int, default=20)
    args = ap.parse_args(argv)

    sets = {k: load_set(p) for k, p in SETS.items()}
    configs = [c.strip() for c in args.configs.split(",") if c.strip()]
    available = ["bm25"]
    skipped: dict[str, str] = {}
    for c in configs:
        if c == "bm25":
            continue
        b = c.split(":")[0]
        status = index_status(b)
        if status is None:
            skipped[c] = f"no cached category embeddings for {b}"
        else:
            available.append(c)
    configs = [c for c in configs if c == "bm25" or c in available]

    results: list[dict] = []
    preds: dict[str, dict[str, list[dict]]] = {s: {c: [] for c in configs} for s in sets}
    alias_preds: dict[str, list[dict]] = {s: [] for s in sets}
    norm: dict[str, tuple[list[str], str]] = {}
    llm_before = dict(llm.STATS)
    t_start = time.perf_counter()
    n_lines_total = 0
    for sname, rows in sets.items():
        for r in rows:
            code = icd10_lookup.lookup(r["text"])
            alias = {"category": code[:3] if code else None}
            alias_preds[sname].append(alias)
            rec = {"set": sname, **r, "alias": alias, "configs": {}}
            if not args.offline:
                if r["text"] not in norm:
                    norm[r["text"]] = icd10_coder.normalise(r["text"])
                terms, how = norm[r["text"]]
                rec["normalised_terms"], rec["normalisation"] = terms[:12], how
                for c in configs:
                    p = run_line(r["text"], terms, how, c)
                    if not p["ran"]:
                        p.update(category=None, ranked=[], candidates=[])
                    preds[sname][c].append(p)
                    rec["configs"][c] = p
                n_lines_total += 1
                print(f"{r['id']} gold={r['gold']} " + " ".join(f"{c}={rec['configs'][c]['category']}" for c in configs), flush=True)
            results.append(rec)
    wall = time.perf_counter() - t_start
    llm_delta = {k: llm.STATS[k] - llm_before[k] for k in llm.STATS}

    RESULTS.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in results) + "\n", encoding="utf-8")
    if args.offline:
        print("wrote", RESULTS)
        return 0

    timing = timing_pass(configs, sets["heldout"], norm, args.timing_lines)
    write_report(sets, configs, preds, alias_preds, skipped, timing, llm_delta, wall, n_lines_total)
    print("wrote", REPORT, RESULTS)
    return 0


def paired(sets: dict, preds: dict, cfg: str, base: str, which: Sequence[str], fn) -> dict[str, Any]:
    a, b = [], []
    for s in which:
        for r, pa, pb in zip(sets[s], preds[s][base], preds[s][cfg]):
            x, y = fn(r, pa), fn(r, pb)
            if x is not None and y is not None:
                a.append(x)
                b.append(y)
    return mcnemar(a, b)


def write_report(sets, configs, preds, alias_preds, skipped, timing, llm_delta, wall, n_lines) -> None:
    M = {s: {c: metrics(sets[s], preds[s][c]) for c in configs} for s in sets}
    L: list[str] = []
    w = L.append
    w("# Diagnosis line to ICD-10 category: retrieval ablation and evaluation")
    w("")
    w(f"Date: {date.today().isoformat()}. Selection/normalisation model: `{config.MODEL_FAST}` (temperature 0, schema-constrained, disk-cached). "
      f"Gemini embedding model: `{icd10_embed.GEMINI_MODEL}` ({icd10_embed.GEMINI_DIM} dims, RETRIEVAL_DOCUMENT / RETRIEVAL_QUERY). "
      f"Local embedding model: `{icd10_embed.E5_NAME}` (intfloat/multilingual-e5-small, int8 ONNX export, onnxruntime + tokenizers on CPU, no PyTorch).")
    w("")
    bad = sum(1 for s in sets for c in configs for p in preds[s][c] if not p.get("ran", True))
    if bad:
        w(f"**INVALID RUN: {bad} line-configuration evaluations could not run the language model (quota or outage); the figures below are not usable.**")
        w("")
    w("## Data and what this evidence is")
    w("")
    w("Both sets are **team-authored and team-labelled**. They are not a public clinical benchmark, and no public Indonesian "
      "discharge-summary benchmark with ICD-10 labels exists (real discharge summaries carry patient data). Gold labels are ICD-10-CM "
      "3-character categories; where a label is arguable, the line lists more than one accepted category and carries a `note`.")
    w("")
    for s, rows in sets.items():
        nn = sum(1 for r in rows if not r["gold"])
        multi = sum(1 for r in rows if r["gold"] and len(r["gold"]) > 1)
        w(f"- **{s}** (`{SETS[s].relative_to(config.DATA_DIR.parent)}`): {len(rows)} lines, {nn} gold-undetermined, {multi} with more than one accepted category."
          + (" Seen while the pipeline and its synonym tables were built: its BM25 numbers are optimistic." if s == "development" else
             " Written and frozen before any retrieval ablation was run; the primary evidence."))
    w("")
    w("Code list: ICD-10-CM FY2027 descriptions (CMS/CDC-NCHS, public domain), `data/real/icd10cm_codes.txt`. Each category is embedded as its "
      "official label plus up to 6 distinct member-code descriptions, once, and cached under `data/cache/` (rebuild: `python scripts/fetch_real_data.py --only e5onnx,icdembed`).")
    w("")
    w("Configurations: **bm25** = BM25 over the English terms (previous default); **emb** = dense similarity only (English terms and raw diagnosis text, "
      "two rankings fused by RRF); **hybrid** = RRF (k=60) of BM25 with both dense rankings. Normalisation and selection prompts, guards and thresholds are identical "
      "in every configuration; only the candidate list changes. Candidate list = top 15 categories + 5 full codes. For `emb`/`hybrid` the 5 full codes are "
      "BM25 full codes restricted to the fused categories (for `bm25` unrestricted, as before). Recall is measured on category rankings only.")
    if skipped:
        w("")
        w("Not run: " + "; ".join(f"`{k}` ({v})" for k, v in skipped.items()) + ".")
    w("")
    for s in sets:
        m0 = M[s]["bm25"]
        w(f"## Results: {s} set (n={m0['n']}, gold-coded {m0['n_coded']}, gold-undetermined {m0['n_null']})")
        w("")
        w("Proportions with Wilson 95% intervals. Accuracy and recall are over gold-coded lines; undetermined and false-code rates over all lines.")
        w("")
        w("| config | recall@5 | recall@10 | recall@20 | category accuracy | undetermined | **false-code** |")
        w("|---|---|---|---|---|---|---|")
        for c in configs:
            m = M[s][c]
            w(f"| {c} | " + " | ".join([fmt_ci(m["recall@5"], m["n_coded"]), fmt_ci(m["recall@10"], m["n_coded"]), fmt_ci(m["recall@20"], m["n_coded"]),
                                       fmt_ci(m["correct"], m["n_coded"]), fmt_ci(m["undetermined"], m["n"]), f"**{fmt_ci(m['false_code'], m['n'])}**"]) + " |")
        w("")
        w("Exact McNemar against `bm25` on the same lines (discordant counts: lines only the other configuration gets right / lines only bm25 gets right; two-sided exact binomial p):")
        w("")
        w("| config | line correct (gold-coded: in gold; gold-undetermined: left undetermined) | false-code (lower is better; counts = only-other-is-false / only-bm25-is-false) | recall@10 hit |")
        w("|---|---|---|---|")
        for c in configs:
            if c == "bm25":
                continue
            ok = paired(sets, preds, c, "bm25", [s], line_ok)
            fc = paired(sets, preds, c, "bm25", [s], lambda r, p: not is_false(r, p))
            rc = paired(sets, preds, c, "bm25", [s], lambda r, p: hit_at(r, p, 10) if r["gold"] else None)
            w(f"| {c} | {ok['b_only']} / {ok['a_only']}, p={ok['p']:.3f} | {fc['a_only']} / {fc['b_only']}, p={fc['p']:.3f} | {rc['b_only']} / {rc['a_only']}, p={rc['p']:.3f} |")
        w("")
    w("## Pooled (development + held-out), for power only")
    w("")
    w("| config | recall@10 | category accuracy | false-code |")
    w("|---|---|---|---|")
    for c in configs:
        a, b = M["development"][c], M["heldout"][c]
        w(f"| {c} | {fmt_ci(a['recall@10'] + b['recall@10'], a['n_coded'] + b['n_coded'])} | {fmt_ci(a['correct'] + b['correct'], a['n_coded'] + b['n_coded'])} | {fmt_ci(a['false_code'] + b['false_code'], a['n'] + b['n'])} |")
    w("")
    w("| config | line correct vs bm25 (b/c, p) | false-code vs bm25 (b/c, p) |")
    w("|---|---|---|")
    both = list(sets)
    for c in configs:
        if c == "bm25":
            continue
        ok = paired(sets, preds, c, "bm25", both, line_ok)
        fc = paired(sets, preds, c, "bm25", both, lambda r, p: not is_false(r, p))
        w(f"| {c} | {ok['b_only']} / {ok['a_only']}, p={ok['p']:.3f} | {fc['a_only']} / {fc['b_only']}, p={fc['p']:.3f} |")
    w("")
    w("## Previous version (BM25 only, before this change, development set)")
    w("")
    w(f"Category accuracy {PREVIOUS['accuracy']}, false-code rate {PREVIOUS['false_code']}, retrieval recall@k (k = 15 categories + 5 codes) {PREVIOUS['recall']}, n={PREVIOUS['n']}. "
      "Failures included retrieval misses (Graves E05, head injury S06). The `bm25` row on the development set above is the same pipeline re-run with the current evaluation code.")
    w("")
    w("## Alias dictionary (offline fallback path)")
    w("")
    w("| set | category accuracy | false-code |")
    w("|---|---|---|")
    for s, rows in sets.items():
        pa = alias_preds[s]
        coded = [(r, p) for r, p in zip(rows, pa) if r["gold"]]
        cor = sum(1 for r, p in coded if p["category"] in r["gold"])
        fc = sum(1 for r, p in zip(rows, pa) if p["category"] is not None and (not r["gold"] or p["category"] not in r["gold"]))
        w(f"| {s} | {fmt_ci(cor, len(coded))} | {fmt_ci(fc, len(rows))} |")
    w("")
    w("## Latency and model calls")
    w("")
    w("Retrieval latency per diagnosis line, query-vector cache disabled, first %d held-out lines (includes the embedding API round-trip or local ONNX inference and ranking; excludes the two language-model calls):" % next(iter(timing.values()), {}).get("n", 0))
    w("")
    w("| config | median ms | p95 ms |")
    w("|---|---|---|")
    for c in configs:
        t = timing.get(c, {})
        w(f"| {c} | " + (f"{t['median_ms']:.1f} | {t['p95_ms']:.1f} |" if "median_ms" in t else f"n/a ({t.get('error', '')}) | |"))
    w("")
    w("Model calls per diagnosis line: normalisation 1 + selection 1 language-model call in every configuration; `gemini:*` adds 1 embedding API call (English terms and raw text sent as one batch); `e5onnx:*` adds 0 network calls and `bm25` adds 0. "
      f"In this evaluation run (all configurations, {n_lines} distinct line-evaluations, wall time {wall:.0f}s) the language-model client recorded {llm_delta['live_calls']} live generation calls and {llm_delta['cache_hits']} disk-cache hits; "
      "repeated candidate lists across configurations are answered from the cache, so per-line wall time in this run understates a cold single-line request.")
    w("")
    w("Model sizes: e5 int8 ONNX 118 MB on disk + 17 MB tokenizer (not in the backend image unless fetched; optional packages `onnxruntime`, `tokenizers`); Gemini embeddings need no local model; cached category vectors are ~2.7 MB (e5, 384 dims) or ~6 MB (Gemini, 768 dims).")
    w("")
    w("## Default retrieval rule")
    w("")
    h = {c: M["heldout"][c] for c in configs}
    best = max(configs, key=lambda c: (h[c]["recall@10"], -h[c]["false_code"]))
    w(f"Rule: choose the cheapest configuration (local e5, then Gemini, then BM25 as the order of preference) that is not significantly worse (exact McNemar p<0.05 against the best) than the best held-out configuration on both false-code and recall@10. "
      f"Best held-out configuration by recall@10 then false-code: `{best}`.")
    w("")
    chosen = None
    rows_rule = []
    for c in COST_ORDER:
        if c not in configs:
            continue
        fc = paired(sets, preds, c, best, ["heldout"], lambda r, p: not is_false(r, p)) if c != best else {"p": 1.0, "a_only": 0, "b_only": 0}
        rc = paired(sets, preds, c, best, ["heldout"], lambda r, p: hit_at(r, p, 10) if r["gold"] else None) if c != best else {"p": 1.0, "a_only": 0, "b_only": 0}
        ok = fc["p"] >= 0.05 or fc["a_only"] <= fc["b_only"]
        ok = ok and (rc["p"] >= 0.05 or rc["a_only"] <= rc["b_only"])
        rows_rule.append((c, fc, rc, ok))
        if ok and chosen is None:
            chosen = c
    w("| config | false-code vs best (p; only-this-is-better / only-best-is-better) | recall@10 vs best (p) | acceptable |")
    w("|---|---|---|---|")
    for c, fc, rc, ok in rows_rule:
        w(f"| {c} | p={fc['p']:.3f} ({fc['b_only']}/{fc['a_only']}) | p={rc['p']:.3f} ({rc['b_only']}/{rc['a_only']}) | {'yes' if ok else 'no'} |")
    w("")
    w(f"Rule outcome: `{chosen}`.")
    w("")
    w("A \"not significantly worse\" test at this sample size has little power: with 85 held-out lines a difference of a few lines cannot be distinguished from noise, "
      "so the rule favours the cheapest configuration by construction. The honest reading is the table above: the point estimates and intervals, not the rule outcome, carry the evidence.")
    w("")
    w("## Errors (held-out set)")
    w("")
    for c in configs:
        bad = [(r, p) for r, p in zip(sets["heldout"], preds["heldout"][c]) if is_false(r, p)]
        miss = [(r, p) for r, p in zip(sets["heldout"], preds["heldout"][c]) if r["gold"] and p["category"] is None]
        w(f"**{c}** false codes ({len(bad)}):")
        w("")
        for r, p in bad:
            w(f"- {r['id']} `{r['text']}` gold {r['gold']} -> {p['code']} (phrase {p.get('matched_phrase')!r}, confidence {p.get('confidence')})")
        if not bad:
            w("- none")
        w("")
        w(f"gold-coded lines left undetermined ({len(miss)}): " + ("; ".join(f"{r['id']} {r['gold']} ({p.get('reject_reason')}, gold in top-15: {hit_at(r, p, 15)})" for r, p in miss) or "none"))
        w("")
    w("## Limits")
    w("")
    w("- Small, team-written sets; the confidence intervals above are wide. They support a functional check and a rough ranking, not a clinical coding benchmark.")
    w("- The development set was used while the pipeline was built, so BM25 is tuned toward it; embedding configurations were not tuned on either set (no hyper-parameters were fitted; RRF k=60 and the category text recipe were fixed before any run).")
    w("- Gold labels are 3-character categories; sub-category correctness is not scored because coverage clauses are written at category or range level.")
    w("- ICD-10-CM (US clinical modification) is used because it is the only official ICD-10 code list published as a public-domain text file; its 3-character categories coincide with WHO ICD-10 for the conditions here, except that ICD-10-CM has no A16 (respiratory TB is A15).")
    w("- The held-out set was written by the same team that wrote the development set and the synonym tables, so style leakage is possible. Selection and normalisation are large-language-model calls and can change across model versions; results are disk-cached for this run.")
    w("- INA-CBG tariff grouping is not implemented; this evaluation covers diagnosis-to-category resolution only.")
    w("")
    REPORT.write_text("\n".join(L), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
