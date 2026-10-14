"""Split-aware evaluation per evidence/bench_protocol.md: Wilson CIs, paired exact McNemar vs the long-context baseline.

Usage: python -m bench.protocol_eval [--b4 evidence/bench_b4.jsonl] [--base evidence/bench_b0cw.jsonl]
       [--sets dev,analysis,heldout] [--scope solver|all]
"""
from __future__ import annotations

import argparse
import json
from math import comb, sqrt
from pathlib import Path

from clauseguard import config

SPLITS = {"dev": ["C1", "C7"], "analysis": ["C2", "C3", "C4"], "heldout": ["C5", "C6", "C8", "C9", "C10"]}


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def mcnemar_exact(b: int, c: int) -> float:
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    p = 2 * sum(comb(n, i) for i in range(k + 1)) / 2 ** n
    return min(1.0, p)


def load(path: Path) -> dict[tuple[str, str], dict]:
    out = {}
    if path.exists():
        for line in path.read_text(encoding="utf8").splitlines():
            if line.strip():
                r = json.loads(line)
                out[(r["scenario_id"], r["contract_id"])] = r
    return out


def ok(r: dict) -> bool:
    return str(r.get("pred", "")).upper() == str(r.get("gt", "")).upper()


def fmt(k: int, n: int) -> str:
    lo, hi = wilson(k, n)
    return f"{100 * k / n:.1f} [{100 * lo:.1f}, {100 * hi:.1f}] ({k}/{n})" if n else "n/a"


def compare(sys_recs: dict, base: dict, contracts: list[str], scope: str) -> dict:
    keys = [k for k in sys_recs if k[1] in contracts and (scope == "all" or sys_recs[k].get("in_scope", True))]
    n = len(keys)
    ks = sum(ok(sys_recs[k]) for k in keys)
    paired = [k for k in keys if k in base]
    b = sum(ok(sys_recs[k]) and not ok(base[k]) for k in paired)
    c = sum((not ok(sys_recs[k])) and ok(base[k]) for k in paired)
    kp = sum(ok(sys_recs[k]) for k in paired)
    kb = sum(ok(base[k]) for k in paired)
    return {"n": n, "sys": fmt(ks, n), "n_paired": len(paired), "sys_paired": fmt(kp, len(paired)), "base_paired": fmt(kb, len(paired)),
            "sys_only": b, "base_only": c, "p": mcnemar_exact(b, c)}


def table(sys_recs: dict, base: dict, sets: list[str], scope: str) -> str:
    rows = ["| set | contracts | n (system) | system acc [Wilson 95%] | paired n | system acc, paired | baseline acc, paired | sys right/base wrong | sys wrong/base right | McNemar p |",
            "|---|---|---|---|---|---|---|---|---|---|"]
    groups = [(s, SPLITS[s]) for s in sets] + [("overall", sum((SPLITS[s] for s in sets), []))]
    for name, cs in groups:
        r = compare(sys_recs, base, cs, scope)
        rows.append(f"| {name} | {','.join(cs)} | {r['n']} | {r['sys']} | {r['n_paired']} | {r['sys_paired']} | {r['base_paired']} | {r['sys_only']} | {r['base_only']} | {r['p']:.3f} |")
    return "\n".join(rows)


def abstains(r: dict) -> bool:
    f = r.get("flags") or {}
    return bool(f.get("uncertain_unmodeled") or f.get("low_confidence_decisive") or f.get("clarify_unresolved") or f.get("clarify_majority") or f.get("not_specified"))


def risk_coverage(sys_recs: dict, base: dict, contracts: list[str]) -> dict:
    keys = [k for k in sys_recs if k[1] in contracts and sys_recs[k].get("in_scope", True)]
    ans = [k for k in keys if not abstains(sys_recs[k])]
    pk = [k for k in ans if k in base]
    return {"n": len(keys), "answered": len(ans), "coverage": len(ans) / len(keys) if keys else 0.0,
            "acc_answered": fmt(sum(ok(sys_recs[k]) for k in ans), len(ans)), "acc_abstained_items": fmt(sum(ok(sys_recs[k]) for k in keys if k not in set(ans)), len(keys) - len(ans)),
            "paired_answered": len(pk), "sys_on_paired": fmt(sum(ok(sys_recs[k]) for k in pk), len(pk)), "base_on_paired": fmt(sum(ok(base[k]) for k in pk), len(pk))}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--b4", default=str(config.EVIDENCE_DIR / "bench_b4.jsonl"))
    ap.add_argument("--base", default=str(config.EVIDENCE_DIR / "bench_b0cw.jsonl"))
    ap.add_argument("--sets", default="dev,analysis,heldout")
    ap.add_argument("--scope", default="solver", choices=["solver", "all"])
    ap.add_argument("--risk", action="store_true")
    a = ap.parse_args()
    sysr, base = load(Path(a.b4)), load(Path(a.base))
    print(table(sysr, base, a.sets.split(","), a.scope))
    if a.risk:
        for name in a.sets.split(","):
            print(name, risk_coverage(sysr, base, SPLITS[name]))


if __name__ == "__main__":
    main()
