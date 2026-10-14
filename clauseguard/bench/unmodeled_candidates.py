"""Cluster the free-text labels of UNMODELED_RULE tuples across extracted policies: promotion candidates for new closed relations.

Promotion stays manual: a candidate is promoted only after review, with solver semantics and tests.
Usage: python -m bench.unmodeled_candidates [--dir data/extracted] [--min 2]
"""
from __future__ import annotations

import argparse
import re
from collections import defaultdict
from pathlib import Path

from clauseguard import config
from clauseguard.schema import PolicyRecord, Relation

_STOP = {"the", "a", "an", "of", "on", "to", "and", "or", "in", "for", "rule", "clause", "provision"}


def key(label: str) -> str:
    toks = [t[:6] for t in re.findall(r"[a-z]+", label.lower()) if t not in _STOP]
    return " ".join(sorted(set(toks)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=str(config.DATA_DIR / "extracted"))
    ap.add_argument("--min", type=int, default=2)
    a = ap.parse_args()
    groups: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
    for p in sorted(Path(a.dir).glob("*.json")):
        if p.name.endswith(".meta.json"):
            continue
        try:
            rec = PolicyRecord.model_validate_json(p.read_text(encoding="utf8"))
        except Exception:  # noqa: BLE001
            continue
        for t in rec.tuples:
            if t.relation == Relation.UNMODELED_RULE:
                groups[key(t.qualifiers.proposed_label or t.object)].append((rec.id, t.qualifiers.proposed_label or t.object, t.evidence.text[:100]))
    print(f"{sum(len(v) for v in groups.values())} unmodeled rules, {len(groups)} label clusters, in {len({x[0] for v in groups.values() for x in v})} policies")
    for k, v in sorted(groups.items(), key=lambda kv: -len({x[0] for x in kv[1]})):
        pols = sorted({x[0] for x in v})
        if len(pols) >= a.min:
            print(f"- {v[0][1]!r}: {len(v)} rules in {len(pols)} policies {pols}\n    e.g. {v[0][2]!r}")


if __name__ == "__main__":
    main()
