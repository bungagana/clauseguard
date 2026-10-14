"""Run the policy extractor over the benchmark contracts and the real RIPLAY PDFs.

Writes data/extracted/<policy_id>.json (PolicyRecord.model_dump_json) plus
data/extracted/<policy_id>.meta.json (outline sections + dropped rows) and prints tuple
counts per document.

Held-out discipline: the extraction prompts in clauseguard/extractor/policy_extractor.py
were developed and tuned ONLY on contract_1_term_life.txt and contract_7_term_with_riders.txt.
All other contracts and every PDF were run blind; their outputs were not used to change
prompts or normalisation rules.

Usage:
    python scripts/extract_all.py                 # everything
    python scripts/extract_all.py C1 C7 SOMPO-HCP # subset
    python scripts/extract_all.py --no-pdf        # benchmark only
    python scripts/extract_all.py --force         # re-extract even if data/extracted/<id>.json exists
"""
from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from clauseguard.extractor import policy_extractor as pe  # noqa: E402
from clauseguard.schema import SourceTier  # noqa: E402

BENCH_DIR = ROOT / "data" / "policies" / "benchmark"
REAL_DIR = ROOT / "data" / "policies" / "real"
OUT_DIR = ROOT / "data" / "extracted"

# benchmark ids C1..C10 follow contract_N
BENCHMARK: dict[str, str] = {
    "C1": "contract_1_term_life.txt",
    "C2": "contract_2_whole_life.txt",
    "C3": "contract_3_universal_life.txt",
    "C4": "contract_4_variable_universal.txt",
    "C5": "contract_5_final_expense.txt",
    "C6": "contract_6_group_term.txt",
    "C7": "contract_7_term_with_riders.txt",
    "C8": "contract_8_joint_survivorship.txt",
    "C9": "contract_9_return_of_premium.txt",
    "C10": "contract_10_indexed_universal.txt",
}
REAL: dict[str, tuple[str, str]] = {  # id -> (file, product_hint)
    "SOMPO-HCP": ("roojai_hcp_en.pdf", "hospital_cash"),
    "ASTRA-HCP": ("astra_hcp.pdf", "hospital_cash"),
    "ASTRA-FLEXI-LIFE": ("astra_flexi_life.pdf", "term_life"),
    "CHUBB-MY-PA": ("chubb_my_pa.pdf", "personal_accident"),
    "CHUBB-VHIS-STD": ("chubb_vhis_std.pdf", "medical"),
    "GE-SG-PA": ("ge_pa.pdf", "personal_accident"),
}


def run_one(policy_id: str, path: Path, product_hint: str | None = None, force: bool = False) -> int:
    t0 = time.time()
    out = OUT_DIR / f"{policy_id}.json"
    if out.exists() and not force:
        from clauseguard.schema import PolicyRecord

        rec = PolicyRecord.model_validate_json(out.read_text(encoding="utf8"))
        print(f"{policy_id:16s} {path.name:32s} tuples={len(rec.tuples):3d} (cached on disk; --force to redo) coverage={rec.extraction_coverage:.2f}")
        return len(rec.tuples)
    meta_path = OUT_DIR / f"{policy_id}.meta.json"
    if force and meta_path.exists():
        try:  # reuse the model that produced the cached responses for this document
            pe.prefer_model(json.loads(meta_path.read_text(encoding="utf8")).get("model"))
        except Exception:  # noqa: BLE001
            pass
    rec = pe.extract_policy(path, policy_id=policy_id, doc_id=path.name, source_tier=SourceTier.POLICY_DOC_UNVERIFIED, product_hint=product_hint)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / f"{policy_id}.json").write_text(rec.model_dump_json(indent=1), encoding="utf8")
    meta = pe._LAST_META.get(policy_id, {})
    (OUT_DIR / f"{policy_id}.meta.json").write_text(json.dumps(meta, indent=1, default=str), encoding="utf8")
    by_rel: dict[str, int] = {}
    for t in rec.tuples:
        by_rel[t.relation.value] = by_rel.get(t.relation.value, 0) + 1
    print(
        f"{policy_id:16s} {path.name:32s} tuples={len(rec.tuples):3d} dropped={len(meta.get('dropped', [])):2d} "
        f"coverage={rec.extraction_coverage:.2f} riders={len(rec.riders)} lang={rec.tuples[0].language if rec.tuples else '-'} "
        f"{time.time()-t0:5.1f}s  {dict(sorted(by_rel.items()))}"
    )
    return len(rec.tuples)


def main(argv: list[str]) -> None:
    logging.basicConfig(level=logging.WARNING)
    logging.getLogger("clauseguard").setLevel(logging.INFO)
    want = [a for a in argv if not a.startswith("--")]
    no_pdf = "--no-pdf" in argv
    force = "--force" in argv
    total = 0
    for pid, fname in BENCHMARK.items():
        if want and pid not in want:
            continue
        try:
            total += run_one(pid, BENCH_DIR / fname, force=force)
        except Exception as e:  # noqa: BLE001
            print(f"{pid:16s} FAILED: {str(e)[:300]}")
    if not no_pdf:
        for pid, (fname, hint) in REAL.items():
            if want and pid not in want:
                continue
            try:
                total += run_one(pid, REAL_DIR / fname, hint, force=force)
            except Exception as e:  # noqa: BLE001 - keep going, report at the end
                print(f"{pid:16s} FAILED: {str(e)[:300]}")
    print(f"total tuples: {total}")


if __name__ == "__main__":
    main(sys.argv[1:])
