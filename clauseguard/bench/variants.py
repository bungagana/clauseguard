"""Re-extract benchmark contracts with a chosen refinement setting into data/extracted_variants/<tag>/.

--cache-only makes any prompt that is not already in the disk cache fail instead of calling the model, so
deterministic stages (verification) can be evaluated without spending quota.

Usage: python -m bench.variants --tag verify --contracts C1,C2 [--no-recall] [--no-refine] [--cache-only]
Then:  CG_BENCH_EXTRACTED_DIR=data/extracted_variants/<tag> python -m bench.run_bench --system b4 --contracts C1,C2 \
         --skip-fallback --out evidence/bench_b4_<tag>.jsonl
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from clauseguard import config, llm
from clauseguard.extractor import policy_extractor as pe
from clauseguard.schema import SourceTier

from .data import CONTRACT_DIR


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", required=True)
    ap.add_argument("--contracts", required=True)
    ap.add_argument("--no-refine", action="store_true")
    ap.add_argument("--no-recall", action="store_true")
    ap.add_argument("--cache-only", action="store_true")
    ap.add_argument("--model", default=None, help="start the model chain here")
    a = ap.parse_args()
    out = config.DATA_DIR / "extracted_variants" / a.tag
    out.mkdir(parents=True, exist_ok=True)
    if a.cache_only:
        def _miss(*args, **kw):
            raise RuntimeError("cache miss (cache-only)")
        llm.generate_json = _miss
    if a.model:
        pe.MODEL_CHAIN.insert(0, a.model)
    for cid in [c.strip().upper() for c in a.contracts.split(",") if c.strip()]:
        n = int(cid[1:])
        path = sorted(CONTRACT_DIR.glob(f"contract_{n}_*.txt"))[0]
        meta_old = config.DATA_DIR / "extracted" / f"{cid}.meta.json"
        if meta_old.exists() and not a.model:
            pe.prefer_model(json.loads(meta_old.read_text(encoding="utf8")).get("model"))
        t0 = time.time()
        rec = pe.extract_policy(path, policy_id=cid, doc_id=path.name, source_tier=SourceTier.POLICY_DOC_UNVERIFIED,
                                refine=not a.no_refine, recall=not a.no_recall)
        (out / f"{cid}.json").write_text(rec.model_dump_json(indent=1), encoding="utf8")
        (out / f"{cid}.meta.json").write_text(json.dumps(pe._LAST_META.get(cid, {}), indent=1, default=str), encoding="utf8")
        print(f"{cid} tuples={len(rec.tuples)} refine_log={len(pe._LAST_META[cid]['refine_log'])} recall_sentences={pe._LAST_META[cid]['recall_sentences']} {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
