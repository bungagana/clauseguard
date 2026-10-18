"""Indonesian versions of the submission documents, for the team's own reading.

The official package is English (competition rule). This script translates the Markdown sources
with the project's model wrapper, section by section, keeping Markdown structure, code, tables,
numbers, file paths and product names unchanged, then renders the same .docx/.pptx with the
existing builders into ../SUBMISSION-ID/.

Usage: python scripts/translate_docs.py [--only README,VIDEO,DECK,TECH,SEC,EVID]
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from clauseguard import config, llm  # noqa: E402
TOP = ROOT.parent
OUT_DIR = TOP / "SUBMISSION-ID"
ID_DOCS = ROOT / "docs" / "id"

SYSTEM = (
    "You translate technical documentation from English to formal Indonesian (bahasa Indonesia baku) for an engineering "
    "and insurance audience. Keep every Markdown structure exactly: headings, bullet markers, numbered lists, tables (same "
    "columns and rows), fenced code blocks, inline code, links and image paths. Do not translate anything inside code "
    "spans or code blocks, file paths, command lines, identifiers, product names (ClauseGuard, Sompo, BPJS Kesehatan, "
    "Gemini, Vercel, Supabase), policy ids (HCP-SOMPO-01), claim ids, dataset names, or the words 'Line:', 'Image:', "
    "'Image2:', 'Chart:', 'Notes:' at the start of a line. Keep numbers, units, percentages and dates as they are. Keep "
    "established English technical terms where Indonesian practice keeps them (benchmark, audit log, endpoint, "
    "sandbox, deadline may be 'tenggat'). Translate meaning faithfully; do not add, omit or soften claims."
)


class _T(BaseModel):
    text: str = Field(description="the translated Markdown, same structure")


def translate_md(src: Path, dst: Path, max_chars: int = 7000) -> None:
    md = src.read_text(encoding="utf-8")
    # split on level-2 headings so each call sees one section; the preamble stays with the first
    parts = re.split(r"(?m)^(?=## )", md)
    chunks, buf = [], ""
    for p in parts:
        if len(buf) + len(p) > max_chars and buf:
            chunks.append(buf)
            buf = p
        else:
            buf += p
    if buf:
        chunks.append(buf)
    out = []
    for i, ch in enumerate(chunks, 1):
        raw = llm.generate_json(f"Translate this Markdown to Indonesian.\n\n<markdown>\n{ch}\n</markdown>", schema=_T, system=SYSTEM,
                                model=config.MODEL_FAST, max_output_tokens=8192)
        text = _T.model_validate(raw).text
        if ch.count("```") != text.count("```") or abs(ch.count("|") - text.count("|")) > 4:
            print(f"  warning: structure drift in chunk {i} of {src.name}", file=sys.stderr)
        out.append(text if text.endswith("\n") else text + "\n")
        print(f"  {src.name}: chunk {i}/{len(chunks)}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text("".join(out), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="README,VIDEO,DECK,TECH,SEC,EVID")
    only = set(ap.parse_args().only.split(","))
    OUT_DIR.mkdir(exist_ok=True)
    (OUT_DIR / "evidence").mkdir(exist_ok=True)
    jobs = {
        "README": (TOP / "SUBMISSION" / "README.md", OUT_DIR / "README.md"),
        "VIDEO": (TOP / "SUBMISSION" / "3_Video_Script.md", OUT_DIR / "3_Naskah_Video.md"),
        "DECK": (ROOT / "docs" / "DECK.md", ID_DOCS / "DECK.md"),
        "TECH": (ROOT / "docs" / "TECHNICAL_DOCUMENTATION.md", ID_DOCS / "TECHNICAL_DOCUMENTATION.md"),
        "SEC": (ROOT / "docs" / "SECURITY_SELF_ASSESSMENT.md", ID_DOCS / "SECURITY_SELF_ASSESSMENT.md"),
        "EVID": (ROOT / "docs" / "EXECUTION_EVIDENCE.md", ID_DOCS / "EXECUTION_EVIDENCE.md"),
    }
    for key, (src, dst) in jobs.items():
        if key in only:
            print("translating", src.name)
            translate_md(src, dst)
    render = {
        "TECH": (ID_DOCS / "TECHNICAL_DOCUMENTATION.md", OUT_DIR / "1_Dokumentasi_Teknis.docx"),
        "SEC": (ID_DOCS / "SECURITY_SELF_ASSESSMENT.md", OUT_DIR / "5_Penilaian_Keamanan_Mandiri.docx"),
        "EVID": (ID_DOCS / "EXECUTION_EVIDENCE.md", OUT_DIR / "6_Indeks_Bukti_Eksekusi.docx"),
    }
    for key, (src, dst) in render.items():
        if key in only and src.exists():
            subprocess.run([sys.executable, str(ROOT / "scripts" / "build_docs.py"), str(src), str(dst)], check=True)
    if "DECK" in only and (ID_DOCS / "DECK.md").exists():
        subprocess.run([sys.executable, str(ROOT / "docs" / "deck" / "build_deck.py"), str(ID_DOCS / "DECK.md"), str(OUT_DIR / "2_Deck_Presentasi.pptx")], check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
