"""Build the sanitized source-code zip for the competition submission.

Excludes secrets, caches, scratch logs, third-party documents and datasets, and scans the
result for API-key patterns. Usage: python scripts/make_submission_zip.py OUT.zip
"""
from __future__ import annotations

import fnmatch
import os
import re
import sys
import zipfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT.parent / "SUBMISSION" / "4_Source_Code_ClauseGuard.zip"

EXCL_DIRS = {".git", "__pycache__", ".pytest_cache", ".venv", "node_modules", "cache", "uploads", "archive", "tmp", "_downloads"}
EXCL_PREFIX = (
    "data/policies", "data/benchmark", "data/extracted", "docs/deck",
    "data/real/raw", "data/real/riplay", "data/real/insuranceqa_questions.jsonl",
)
EXCL_FILES = {".env", "sandbox.sqlite", "audit_log.jsonl", "make_submission_zip.py"}
EXCL_PAT = ["*.lock", "*.pyc", "*.sqlite-*", "bench_b*.jsonl", "adversarial_results.json", "clarify_report.json",
            "paraphrase_report.json", "_adv_audit*", "*.err"]
ENV_EXAMPLE = ("# Copy to .env and fill in. Never commit .env.\nGEMINI_API_KEY=your_key_here\n"
               "CG_MODEL_EXTRACT=gemini-3.6-flash\nCG_MODEL_FAST=gemini-3.5-flash-lite\nCG_MODEL_EMBED=gemini-embedding-001\n"
               "# Set to 1 to run without any model calls (deterministic fallbacks)\nCG_OFFLINE=0\n")
BAD = re.compile(r"AIzaSy[0-9A-Za-z_\-]{20,}|AQ\.Ab8R[0-9A-Za-z_\-]+")  # API-key shapes

OUT.parent.mkdir(parents=True, exist_ok=True)
n = 0
with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
    for dp, dn, fn in os.walk(ROOT):
        dn[:] = [d for d in dn if d not in EXCL_DIRS and (Path(dp) / d).relative_to(ROOT).as_posix() not in EXCL_PREFIX]
        for f in fn:
            if f in EXCL_FILES or any(fnmatch.fnmatch(f, p) for p in EXCL_PAT):
                continue
            fp = Path(dp) / f
            rel = fp.relative_to(ROOT).as_posix()
            if f == ".env.example":
                z.writestr("clauseguard/.env.example", ENV_EXAMPLE)
            else:
                z.write(fp, "clauseguard/" + rel)
            n += 1
    bd = ROOT / "docs" / "deck" / "build_deck.py"
    if bd.exists():
        z.write(bd, "clauseguard/docs/deck/build_deck.py")
        n += 1

hits = []
with zipfile.ZipFile(OUT) as z:
    for name in z.namelist():
        if name.endswith((".pdf", ".pptx", ".png", ".sqlite", ".docx")):
            continue
        text = z.read(name).decode("utf8", "ignore")
        hits += [(name, m.group(0)[:30]) for m in BAD.finditer(text)]
print(f"files: {n}, size KB: {OUT.stat().st_size // 1024}, secret hits: {len(hits)}")
for name, cnt in Counter(h[0] for h in hits).most_common(15):
    print("  ", cnt, name)
sys.exit(1 if hits else 0)
