"""Second pass for docs/id/*.md: retranslate any section the first pass left in English.

Resumable: each section is written as soon as it is translated, successful calls are cached by the
model wrapper, and a model outage leaves the section for the next run instead of aborting.
Usage: python scripts/translate_fix.py [--build]
"""
from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from clauseguard import config, llm  # noqa: E402

spec = importlib.util.spec_from_file_location("td", ROOT / "scripts" / "translate_docs.py")
td = importlib.util.module_from_spec(spec)
spec.loader.exec_module(td)

EN = re.compile(r"\b(the|and|of|with|is|are|this|that|for)\b", re.I)
ID = re.compile(r"\b(dan|yang|dengan|untuk|dari|ini|adalah|tidak|pada)\b", re.I)
MODELS = [config.MODEL_FAST, "gemini-3.1-flash-lite", "gemini-2.5-flash-lite", config.MODEL_EXTRACT]
DOCS = ["TECHNICAL_DOCUMENTATION", "SECURITY_SELF_ASSESSMENT", "EXECUTION_EVIDENCE", "DECK"]
RENDER = {"TECHNICAL_DOCUMENTATION": "1_Dokumentasi_Teknis.docx", "SECURITY_SELF_ASSESSMENT": "5_Penilaian_Keamanan_Mandiri.docx",
          "EXECUTION_EVIDENCE": "6_Indeks_Bukti_Eksekusi.docx"}


def looks_english(t: str) -> bool:
    prose = re.sub(r"`[^`]*`|```.*?```", "", t, flags=re.S)
    e, i = len(EN.findall(prose)), len(ID.findall(prose))
    return e > i * 2 and e > 3


def translate(part: str) -> str | None:
    for model in MODELS:
        try:
            raw = llm.generate_json(f"Translate this Markdown to Indonesian.\n\n<markdown>\n{part}\n</markdown>", schema=td._T, system=td.SYSTEM,
                                    model=model, max_output_tokens=8192)
            t = td._T.model_validate(raw).text
            if not looks_english(t):
                return t if t.endswith("\n") else t + "\n"
        except Exception as e:  # noqa: BLE001 - outage: try the next model, then give up on this section for now
            print(f"    {model}: {str(e)[:60]}")
    return None


def main() -> int:
    left = 0
    for name in DOCS:
        p = ROOT / "docs" / "id" / f"{name}.md"
        parts = re.split(r"(?m)^(?=#{1,3} )", p.read_text(encoding="utf-8"))
        for idx, part in enumerate(parts):
            if not looks_english(part):
                continue
            head = part.splitlines()[0][:60]
            t = translate(part)
            if t is None:
                print(f"{name}: {head!r} -> left in English for now")
                left += 1
                continue
            parts[idx] = t
            p.write_text("".join(parts), encoding="utf-8")
            print(f"{name}: {head!r} -> ok")
    print("sections still in English:", left)
    if "--build" in sys.argv:
        for src, dst in RENDER.items():
            subprocess.run([sys.executable, str(ROOT / "scripts" / "build_docs.py"), str(ROOT / "docs" / "id" / f"{src}.md"), str(ROOT.parent / "SUBMISSION-ID" / dst)], check=True)
        subprocess.run([sys.executable, str(ROOT / "docs" / "deck" / "build_deck.py"), str(ROOT / "docs" / "id" / "DECK.md"), str(ROOT.parent / "SUBMISSION-ID" / "2_Deck_Presentasi.pptx")], check=True)
    return 0 if left == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
