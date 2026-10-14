"""Benchmark data loaders: contracts, scenarios with ground truth, oracle / extracted policies."""
from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Optional

from clauseguard import config
from clauseguard.schema import PolicyRecord

BENCH_DIR = config.DATA_DIR / "benchmark"
CONTRACT_DIR = BENCH_DIR / "contracts"
SCENARIO_DIR = BENCH_DIR / "scenarios"
ORACLE_DIR = BENCH_DIR / "oracle"
EXTRACTED_DIR = Path(os.environ["CG_BENCH_EXTRACTED_DIR"]) if os.environ.get("CG_BENCH_EXTRACTED_DIR") else config.DATA_DIR / "extracted"
CONTRACT_IDS = [f"C{i}" for i in range(1, 11)]
LABELS = ("COVERED", "DENIED", "NOT_APPLICABLE")


@lru_cache(maxsize=None)
def contract_text(cid: str) -> str:
    n = int(cid[1:])
    paths = sorted(CONTRACT_DIR.glob(f"contract_{n}_*.txt"))
    if not paths:
        raise FileNotFoundError(f"no contract text for {cid} in {CONTRACT_DIR}")
    return paths[0].read_text(encoding="utf8", errors="replace")


@lru_cache(maxsize=None)
def scenarios() -> list[dict]:
    """All 58 scenarios with per-contract ground truth: [{scenario_id, category, scenario_description, gt: {cid: {status, source, details}}}]."""
    out = []
    for f in sorted(SCENARIO_DIR.glob("*.json")):
        for s in json.loads(f.read_text(encoding="utf8")):
            gt = {r["contract_id"]: {"status": r["status"], "source": r.get("source", ""), "details": r.get("details", "")}
                  for r in s.get("contract_responses", [])}
            out.append({"scenario_id": s["scenario_id"], "category": s.get("category", ""),
                        "scenario_description": s["scenario_description"], "gt": gt})
    out.sort(key=lambda s: int(s["scenario_id"].split("-")[1]))
    return out


def scenario_by_id(sid: str) -> dict:
    return next(s for s in scenarios() if s["scenario_id"] == sid)


def load_policy_dir(d: Path) -> dict[str, PolicyRecord]:
    """Load PolicyRecord JSON files named C1.json .. C10.json (or contract_1_*.json)."""
    out: dict[str, PolicyRecord] = {}
    if not d.exists():
        return out
    for p in sorted(d.glob("*.json")):
        m = re.match(r"^(C\d+)\.json$", p.name) or re.match(r"^contract_(\d+)_", p.name)
        if not m:
            continue
        cid = m.group(1) if m.group(1).startswith("C") else f"C{m.group(1)}"
        try:
            rec = PolicyRecord.model_validate_json(p.read_text(encoding="utf8"))
        except Exception as e:  # noqa: BLE001
            print(f"[bench] skipping {p.name}: {str(e)[:120]}")
            continue
        out[cid] = rec
    return out


def oracle_policies() -> dict[str, PolicyRecord]:
    return load_policy_dir(ORACLE_DIR)


def extracted_policies() -> dict[str, PolicyRecord]:
    return load_policy_dir(EXTRACTED_DIR)


_SECTION_RE = re.compile(r"(?:Section|Article|§)\s*([IVX]+|\d+)(?:\.(\d+))?(?:\s*\(([a-z])\))?", re.I)


def section_keys(text: Optional[str]) -> set[str]:
    """Normalise 'Section 5.1, 9.3' / 'Article VII.1' / '4.6 GRACE' into keys like '5.1', '5', 'VII.1'."""
    if not text:
        return set()
    keys: set[str] = set()
    for m in _SECTION_RE.finditer(text):
        top = m.group(1).upper()
        keys.add(top)
        if m.group(2):
            keys.add(f"{top}.{m.group(2)}")
        # 'Section 5.1, 9.3' -> also catch the trailing list
        tail = text[m.end(): m.end() + 40]
        for extra in re.findall(r",\s*([IVX]+|\d+(?:\.\d+)?)(?![\w])", tail):
            keys.add(extra.upper())
            keys.add(extra.split(".")[0].upper())
    for m in re.finditer(r"(?<![\w.])(\d{1,2}\.\d{1,2})(?![\d.])", text):
        keys.add(m.group(1))
        keys.add(m.group(1).split(".")[0])
    return keys


def quoted_text(source: str) -> str:
    """Ground-truth 'source' usually looks like: Section 5.1: 'quoted clause ...'. Return the quoted part (or all)."""
    m = re.search(r"['\"‘“](.+?)['\"’”]\s*$", source.strip(), re.S)
    if m and len(m.group(1)) > 20:
        return m.group(1)
    parts = source.split(":", 1)
    return parts[1].strip() if len(parts) == 2 and len(parts[1]) > 20 else source
