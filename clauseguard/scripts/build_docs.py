"""Render the submission documents from their Markdown sources to .docx (python-docx).

Sources -> targets (relative to the repository root and its SUBMISSION folder):
  docs/TECHNICAL_DOCUMENTATION.md    -> SUBMISSION/1_Technical_Documentation.docx
  docs/SECURITY_SELF_ASSESSMENT.md   -> SUBMISSION/5_Security_Self_Assessment.docx
  docs/EXECUTION_EVIDENCE.md         -> SUBMISSION/6_Execution_Evidence_Index.docx

Supports headings, paragraphs, bullet and numbered lists, pipe tables, fenced code blocks and inline
`code`, **bold** and *italic*. Run: python scripts/build_docs.py
"""
from __future__ import annotations

import re
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt, RGBColor

ROOT = Path(__file__).resolve().parents[1]
TARGETS = {
    ROOT / "docs" / "TECHNICAL_DOCUMENTATION.md": ROOT.parent / "SUBMISSION" / "1_Technical_Documentation.docx",
    ROOT / "docs" / "SECURITY_SELF_ASSESSMENT.md": ROOT.parent / "SUBMISSION" / "5_Security_Self_Assessment.docx",
    ROOT / "docs" / "EXECUTION_EVIDENCE.md": ROOT.parent / "SUBMISSION" / "6_Execution_Evidence_Index.docx",
}
INLINE = re.compile(r"(\*\*[^*]+\*\*|`[^`]+`|\*[^*]+\*)")


def _runs(par, text: str) -> None:
    for part in INLINE.split(text):
        if not part:
            continue
        if part.startswith("**") and part.endswith("**"):
            par.add_run(part[2:-2]).bold = True
        elif part.startswith("`") and part.endswith("`"):
            r = par.add_run(part[1:-1])
            r.font.name = "Consolas"
            r.font.size = Pt(9.5)
        elif part.startswith("*") and part.endswith("*"):
            par.add_run(part[1:-1]).italic = True
        else:
            par.add_run(part)


def _table(doc, rows: list[list[str]]) -> None:
    t = doc.add_table(rows=len(rows), cols=len(rows[0]))
    t.style = "Table Grid"
    for i, row in enumerate(rows):
        for j, cell in enumerate(row):
            c = t.cell(i, j)
            c.text = ""
            p = c.paragraphs[0]
            _runs(p, cell.strip())
            for r in p.runs:
                r.font.size = Pt(9)
                if i == 0:
                    r.bold = True
    doc.add_paragraph()


def render(src: Path, dst: Path) -> None:
    doc = Document()
    st = doc.styles["Normal"]
    st.font.name = "Calibri"
    st.font.size = Pt(10.5)
    lines = src.read_text(encoding="utf-8").splitlines()
    i, in_code, code, table = 0, False, [], []

    def flush_table() -> None:
        nonlocal table
        if table:
            _table(doc, table)
            table = []

    while i < len(lines):
        ln = lines[i]
        if ln.startswith("```"):
            if in_code:
                p = doc.add_paragraph()
                r = p.add_run("\n".join(code))
                r.font.name = "Consolas"
                r.font.size = Pt(9)
                code, in_code = [], False
            else:
                flush_table()
                in_code = True
            i += 1
            continue
        if in_code:
            code.append(ln)
            i += 1
            continue
        if ln.startswith("|"):
            cells = [c for c in ln.strip().strip("|").split("|")]
            if not all(re.fullmatch(r"\s*:?-{2,}:?\s*", c) for c in cells):
                table.append(cells)
            i += 1
            continue
        flush_table()
        img = re.match(r"^!\[(.*?)\]\((.+?)\)\s*$", ln)
        if img:
            from docx.shared import Inches
            path = (src.parent / img.group(2)).resolve()
            if path.exists():
                doc.add_picture(str(path), width=Inches(6.3))
                doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
                cap = doc.add_paragraph()
                cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
                r = cap.add_run(img.group(1))
                r.italic = True
                r.font.size = Pt(9)
            i += 1
            continue
        m = re.match(r"^(#{1,4})\s+(.*)", ln)
        if m:
            level = len(m.group(1))
            if level == 1:
                h = doc.add_heading(m.group(2).strip(), 0)
                h.alignment = WD_ALIGN_PARAGRAPH.LEFT
            else:
                doc.add_heading(m.group(2).strip(), level - 1)
        elif re.match(r"^\s*[-*]\s+", ln):
            _runs(doc.add_paragraph(style="List Bullet"), re.sub(r"^\s*[-*]\s+", "", ln))
        elif re.match(r"^\s*\d+\.\s+", ln):
            _runs(doc.add_paragraph(style="List Number"), re.sub(r"^\s*\d+\.\s+", "", ln))
        elif ln.strip():
            _runs(doc.add_paragraph(), ln.strip())
        i += 1
    flush_table()
    for p in doc.paragraphs:
        if p.style.name.startswith("Heading"):
            for r in p.runs:
                r.font.color.rgb = RGBColor(0x14, 0x21, 0x3D)
    dst.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(dst))
    print("wrote", dst.name)


if __name__ == "__main__":
    import sys

    if len(sys.argv) == 3:  # python scripts/build_docs.py SRC.md OUT.docx
        render(Path(sys.argv[1]), Path(sys.argv[2]))
    else:
        for s, d in TARGETS.items():
            render(s, d)
