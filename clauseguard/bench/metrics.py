"""Benchmark metrics over evidence/bench_<system>.jsonl records.

accuracy, macro-F1 over {COVERED, DENIED, NOT_APPLICABLE} (NOT_SPECIFIED -> NOT_APPLICABLE),
NA->DENIED rate, evidence hit rate (section match or >= 40% token overlap with the ground-truth
source), in-scope / out-of-scope breakdown, per-category accuracy, bootstrap 95% CI over
*scenarios* (not labels), McNemar test against a reference system on paired items.
"""
from __future__ import annotations

import json
import math
import random
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable, Optional

from .data import LABELS, quoted_text, section_keys

_STOP = set("the a an of to and or in on for is are be will we you this that any as by with if at from not no it its".split())


def norm_label(x: Optional[str]) -> str:
    x = (x or "").upper()
    if x in ("NOT_SPECIFIED", "CLARIFY", ""):
        return "NOT_APPLICABLE"
    return x


def load(path: Path) -> list[dict]:
    recs = []
    if not path.exists():
        return recs
    for line in path.read_text(encoding="utf8").splitlines():
        if line.strip():
            r = json.loads(line)
            r["pred"] = norm_label(r.get("pred"))
            r["gt"] = norm_label(r.get("gt"))
            recs.append(r)
    return recs


def _tokens(s: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", (s or "").lower()) if t not in _STOP and len(t) > 1}


def evidence_hit(rec: dict) -> Optional[bool]:
    """None when the ground truth has no citable source (e.g. 'contract is silent')."""
    src = rec.get("gt_source") or ""
    gt_secs = section_keys(src)
    gt_quote = quoted_text(src)
    if rec["gt"] == "NOT_APPLICABLE" and not gt_secs:
        return None
    if not gt_secs and len(_tokens(gt_quote)) < 4:
        return None
    pred_secs = section_keys(rec.get("evidence_section") or "") | section_keys(rec.get("evidence_text") or "")
    if gt_secs and pred_secs & gt_secs:
        return True
    a, b = _tokens(rec.get("evidence_text") or ""), _tokens(gt_quote)
    if a and b:
        overlap = len(a & b) / len(b)
        if overlap >= 0.4:
            return True
    return False


def accuracy(recs: Iterable[dict]) -> float:
    recs = list(recs)
    return sum(r["pred"] == r["gt"] for r in recs) / len(recs) if recs else float("nan")


def macro_f1(recs: Iterable[dict]) -> float:
    recs = list(recs)
    f1s = []
    for lab in LABELS:
        tp = sum(r["pred"] == lab and r["gt"] == lab for r in recs)
        fp = sum(r["pred"] == lab and r["gt"] != lab for r in recs)
        fn = sum(r["pred"] != lab and r["gt"] == lab for r in recs)
        if tp + fp + fn == 0:
            continue
        p = tp / (tp + fp) if tp + fp else 0.0
        rc = tp / (tp + fn) if tp + fn else 0.0
        f1s.append(2 * p * rc / (p + rc) if p + rc else 0.0)
    return sum(f1s) / len(f1s) if f1s else float("nan")


def na_to_denied(recs: Iterable[dict]) -> float:
    na = [r for r in recs if r["gt"] == "NOT_APPLICABLE"]
    return sum(r["pred"] == "DENIED" for r in na) / len(na) if na else float("nan")


def evidence_hit_rate(recs: Iterable[dict], only_correct: bool = False, governed_only: bool = True) -> tuple[float, int]:
    """Share of items whose cited evidence matches the ground-truth clause. By default only items whose
    ground truth is COVERED/DENIED (a clause governs); a NOT_APPLICABLE verdict cites absence."""
    hits, n = 0, 0
    for r in recs:
        if only_correct and r["pred"] != r["gt"]:
            continue
        if governed_only and r["gt"] == "NOT_APPLICABLE":
            continue
        h = evidence_hit(r)
        if h is None:
            continue
        n += 1
        hits += int(h)
    return (hits / n if n else float("nan")), n


def confusion(recs: Iterable[dict]) -> dict[str, dict[str, int]]:
    m: dict[str, dict[str, int]] = {g: {p: 0 for p in LABELS} for g in LABELS}
    for r in recs:
        m[r["gt"]][r["pred"]] += 1
    return m


def bootstrap_ci(recs: list[dict], stat=accuracy, n_boot: int = 2000, seed: int = 0) -> tuple[float, float]:
    """Resample scenarios (clusters of 10 contracts) with replacement."""
    by_s: dict[str, list[dict]] = defaultdict(list)
    for r in recs:
        by_s[r["scenario_id"]].append(r)
    sids = sorted(by_s)
    if not sids:
        return float("nan"), float("nan")
    rng = random.Random(seed)
    vals = []
    for _ in range(n_boot):
        sample = [x for _ in sids for x in by_s[rng.choice(sids)]]
        vals.append(stat(sample))
    vals.sort()
    return vals[int(0.025 * n_boot)], vals[int(0.975 * n_boot) - 1]


def mcnemar(a: list[dict], b: list[dict]) -> dict:
    """Paired on (scenario_id, contract_id). b01 = a right & b wrong, b10 = a wrong & b right."""
    ia = {(r["scenario_id"], r["contract_id"]): r for r in a}
    ib = {(r["scenario_id"], r["contract_id"]): r for r in b}
    keys = sorted(set(ia) & set(ib))
    b01 = sum(ia[k]["pred"] == ia[k]["gt"] and ib[k]["pred"] != ib[k]["gt"] for k in keys)
    b10 = sum(ia[k]["pred"] != ia[k]["gt"] and ib[k]["pred"] == ib[k]["gt"] for k in keys)
    n = b01 + b10
    if n == 0:
        return {"n_pairs": len(keys), "b01": b01, "b10": b10, "p_exact": 1.0, "chi2": 0.0}
    k = min(b01, b10)
    p = sum(math.comb(n, i) for i in range(0, k + 1)) / 2 ** n * 2
    p = min(1.0, p)
    chi2 = (abs(b01 - b10) - 1) ** 2 / n
    return {"n_pairs": len(keys), "b01": b01, "b10": b10, "p_exact": p, "chi2": chi2,
            "acc_a": accuracy([ia[k] for k in keys]), "acc_b": accuracy([ib[k] for k in keys])}


def summarize(recs: list[dict]) -> dict:
    if not recs:
        return {"n": 0}
    lo, hi = bootstrap_ci(recs)
    eh, en = evidence_hit_rate(recs)
    ehc, enc = evidence_hit_rate(recs, only_correct=True)
    in_scope = [r for r in recs if r.get("in_scope") is True]
    out_scope = [r for r in recs if r.get("in_scope") is False]
    fallback = [r for r in recs if r.get("fallback")]
    clar = [r for r in recs if (r.get("flags") or {}).get("clarify_slot")]
    per_cat = {}
    for cat, grp in sorted(_group(recs, "category").items()):
        per_cat[cat] = {"n": len(grp), "acc": accuracy(grp)}
    per_scn = {}
    for sid, grp in sorted(_group(recs, "scenario_id").items(), key=lambda kv: int(kv[0].split("-")[1])):
        per_scn[sid] = {"n": len(grp), "acc": accuracy(grp), "category": grp[0]["category"]}
    per_contract = {cid: {"n": len(grp), "acc": accuracy(grp)} for cid, grp in sorted(_group(recs, "contract_id").items(), key=lambda kv: int(kv[0][1:]))}
    return {
        "n": len(recs), "n_scenarios": len({r["scenario_id"] for r in recs}), "contracts": sorted({r["contract_id"] for r in recs}, key=lambda c: int(c[1:])),
        "accuracy": accuracy(recs), "ci95": (lo, hi), "macro_f1": macro_f1(recs), "na_to_denied": na_to_denied(recs),
        "evidence_hit": eh, "evidence_n": en, "evidence_hit_correct_only": ehc, "evidence_n_correct": enc,
        "confusion": confusion(recs), "pred_dist": dict(Counter(r["pred"] for r in recs)), "gt_dist": dict(Counter(r["gt"] for r in recs)),
        "in_scope": {"n": len(in_scope), "acc": accuracy(in_scope), "macro_f1": macro_f1(in_scope), "na_to_denied": na_to_denied(in_scope)} if in_scope else None,
        "out_scope": {"n": len(out_scope), "acc": accuracy(out_scope), "macro_f1": macro_f1(out_scope)} if out_scope else None,
        "fallback_n": len(fallback), "clarify_resolved_n": len(clar),
        "per_category": per_cat, "per_scenario": per_scn, "per_contract": per_contract,
    }


def _group(recs: list[dict], key: str) -> dict[str, list[dict]]:
    g: dict[str, list[dict]] = defaultdict(list)
    for r in recs:
        g[r.get(key) or "?"].append(r)
    return g
