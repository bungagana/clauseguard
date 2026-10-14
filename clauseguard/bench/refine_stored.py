"""Apply the refinement stages to already-extracted records, reusing their first-pass tuples.

verify  deterministic evidence verification (no model call)
recall  rule-cue sentences not contained in any tuple's evidence go through one model call per chunk

Usage: python -m bench.refine_stored --tag recall --contracts C1,C2 [--no-recall] [--src data/extracted] [--model M]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from types import SimpleNamespace

from clauseguard import config
from clauseguard.extractor import policy_extractor as pe
from clauseguard.extractor import refine
from clauseguard.schema import PolicyRecord

from .data import contract_text


def refine_record(rec: PolicyRecord, text: str, meta: dict, *, recall: bool) -> tuple[PolicyRecord, dict]:
    salvaged: list = []
    first = rec.tuples[0] if rec.tuples else None
    sctx = pe._Ctx(rec.id, rec.doc_id, first.source_tier if first else None, first.language if first else "en", text)
    sctx.n = max([int(t.id.rsplit("-t", 1)[-1]) for t in rec.tuples] + [0])
    for d in meta.get("dropped", []):
        if not any(k in d.get("error", "") for k in ("is not an EventCode", "is not a permitted action", "is not a termination code")) or d.get("pass") == "recall":
            continue
        try:
            row = pe.ExtractedTuple.model_validate(d["row"])
            t = pe._convert_one(row, [sctx.next_id()], 0, sctx, {r.id for r in rec.riders}, {})
        except Exception:  # noqa: BLE001
            continue
        if t is not None:
            salvaged.append(t)
    tuples, log = refine.verify_tuples(list(rec.tuples) + salvaged, pe.window_from_text)
    info = {"verify_actions": len(log), "salvaged_rows": len(salvaged), "recall_sentences": 0, "added": 0}
    if recall:
        outline = SimpleNamespace(
            glossary=[SimpleNamespace(term=g.get("term", ""), definition=g.get("definition", "")) for g in meta.get("glossary", [])],
            riders=[SimpleNamespace(id=r.id, name=r.rider_type) for r in rec.riders],
        )
        first = tuples[0] if tuples else None
        ctx = pe._Ctx(rec.id, rec.doc_id, first.source_tier if first else rec.tuples[0].source_tier, first.language if first else "en", text)
        ctx.n = max([int(t.id.rsplit("-t", 1)[-1]) for t in tuples] + [0])
        before = len(tuples)
        tuples = pe._recall_pass(tuples, text, outline, ctx, {r.id for r in rec.riders}, {})
        tuples, more = refine.verify_tuples(pe._dedupe(tuples), pe.window_from_text)
        log += more
        info.update(recall_sentences=ctx.recall_sentences, added=len(tuples) - before, dropped=ctx.dropped)
    return rec.model_copy(update={"tuples": tuples}), {"refine_log": log, **info}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", required=True)
    ap.add_argument("--contracts", required=True)
    ap.add_argument("--no-recall", action="store_true")
    ap.add_argument("--src", default=str(config.DATA_DIR / "extracted"))
    ap.add_argument("--model", default=None, help="put this model first in the chain")
    a = ap.parse_args()
    if a.model:
        pe.MODEL_CHAIN.insert(0, a.model)
    out = config.DATA_DIR / "extracted_variants" / a.tag
    out.mkdir(parents=True, exist_ok=True)
    src = Path(a.src)
    for cid in [c.strip().upper() for c in a.contracts.split(",") if c.strip()]:
        rec = PolicyRecord.model_validate_json((src / f"{cid}.json").read_text(encoding="utf8"))
        mp = src / f"{cid}.meta.json"
        meta = json.loads(mp.read_text(encoding="utf8")) if mp.exists() else {}
        new, info = refine_record(rec, contract_text(cid), meta, recall=not a.no_recall)
        (out / f"{cid}.json").write_text(new.model_dump_json(indent=1), encoding="utf8")
        (out / f"{cid}.meta.json").write_text(json.dumps(info, indent=1, default=str), encoding="utf8")
        print(f"{cid}: tuples {len(rec.tuples)} -> {len(new.tuples)}; verify actions {info['verify_actions']}; recall sentences {info['recall_sentences']}; added {info['added']}")


if __name__ == "__main__":
    main()
