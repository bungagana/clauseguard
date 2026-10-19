"""Render the submission documents from their Markdown sources to .docx (python-docx).

Sources -> targets (relative to the repository root and its SUBMISSION folder):
  docs/TECHNICAL_DOCUMENTATION.md    -> SUBMISSION/1_Technical_Documentation.docx
  docs/SECURITY_SELF_ASSESSMENT.md   -> SUBMISSION/5_Security_Self_Assessment.docx
  docs/EXECUTION_EVIDENCE.md         -> SUBMISSION/6_Execution_Evidence_Index.docx

Supports headings, paragraphs, bullet and numbered lists, pipe tables, fenced code blocks, images
(`![caption|width_in](path)`) and inline `code`, **bold** and *italic*. All text is black. Tables get
proportional column widths, a shaded repeating header row and centred short columns. A4 pages with a
footer carrying the document title and page numbers.
Run: python scripts/build_docs.py  or  python scripts/build_docs.py SRC.md OUT.docx
"""
from __future__ import annotations

import os
import re
from pathlib import Path

from docx import Document
from docx.enum.section import WD_ORIENT
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

ROOT = Path(__file__).resolve().parents[1]
TARGETS = {
    ROOT / "docs" / "TECHNICAL_DOCUMENTATION.md": ROOT.parent / "SUBMISSION" / "1_Technical_Documentation.docx",
    ROOT / "docs" / "SECURITY_SELF_ASSESSMENT.md": ROOT.parent / "SUBMISSION" / "5_Security_Self_Assessment.docx",
    ROOT / "docs" / "EXECUTION_EVIDENCE.md": ROOT.parent / "SUBMISSION" / "6_Execution_Evidence_Index.docx",
}
INLINE = re.compile(r"(\*\*[^*]+\*\*|`[^`]+`|\*[^*]+\*)")
BLACK = RGBColor(0, 0, 0)
FONT = "Calibri"
MONO = "Consolas"
PAGE_W, MARGIN = 8.27, 0.9  # A4 portrait, inches
USABLE_W = PAGE_W - 2 * MARGIN


def _font(obj, name=FONT, size=None, bold=None, italic=None) -> None:
    """Set a run's or style's font, always black, and drop theme fonts that would override the name."""
    f = obj.font
    f.name = name
    f.color.rgb = BLACK
    if size:
        f.size = Pt(size)
    if bold is not None:
        f.bold = bold
    if italic is not None:
        f.italic = italic
    rpr = obj._r.get_or_add_rPr() if hasattr(obj, "_r") else obj.element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.append(rfonts)
    for attr in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
        rfonts.set(qn(attr), name)
    for attr in ("w:asciiTheme", "w:hAnsiTheme", "w:cstheme", "w:eastAsiaTheme"):
        if rfonts.get(qn(attr)) is not None:
            del rfonts.attrib[qn(attr)]


def _runs(par, text: str, size: float | None = None, bold: bool | None = None) -> None:
    for part in INLINE.split(text):
        if not part:
            continue
        if part.startswith("**") and part.endswith("**"):
            _font(par.add_run(part[2:-2]), size=size, bold=True)
        elif part.startswith("`") and part.endswith("`"):
            _font(par.add_run(part[1:-1]), name=MONO, size=(size or 10.5) - 1, bold=bold)
        elif part.startswith("*") and part.endswith("*"):
            _font(par.add_run(part[1:-1]), size=size, italic=True, bold=bold)
        else:
            _font(par.add_run(part), size=size, bold=bold)


def _spacing(par, before=0, after=6, line=1.12, keep_next=False) -> None:
    pf = par.paragraph_format
    pf.space_before, pf.space_after, pf.line_spacing = Pt(before), Pt(after), line
    pf.keep_with_next = keep_next


def _shade(cell, fill: str) -> None:
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)
    cell._tc.get_or_add_tcPr().append(shd)


def _table_format(table, color="7F7F7F", size=4) -> None:
    tblpr = table._tbl.tblPr
    borders = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = OxmlElement(f"w:{edge}")
        el.set(qn("w:val"), "single")
        el.set(qn("w:sz"), str(size))
        el.set(qn("w:space"), "0")
        el.set(qn("w:color"), color)
        borders.append(el)
    tblpr.append(borders)
    layout = OxmlElement("w:tblLayout")
    layout.set(qn("w:type"), "fixed")
    tblpr.append(layout)
    mar = OxmlElement("w:tblCellMar")
    for edge, w in (("top", 45), ("left", 85), ("bottom", 45), ("right", 85)):
        el = OxmlElement(f"w:{edge}")
        el.set(qn("w:w"), str(w))
        el.set(qn("w:type"), "dxa")
        mar.append(el)
    tblpr.append(mar)


def _plain(text: str) -> str:
    return re.sub(r"[*`]", "", text)


def _col_widths(rows: list[list[str]]) -> list[float]:
    """Proportional widths with a floor per column so that its longest word never breaks mid-word."""
    n = len(rows[0])
    weights, floors = [], []
    for j in range(n):
        lens = [len(_plain(r[j])) for r in rows]
        weights.append(min(max(0.5 * (sum(lens) / len(lens)) + 0.5 * min(max(lens), 90), 6.0), 70.0))
        longest_word = max((len(w) for r in rows for w in _plain(r[j]).split()), default=1)
        floors.append(max(0.4, 0.22 + 0.068 * min(longest_word, 18)))
    total = sum(weights)
    widths = [max(USABLE_W * w / total, f) for w, f in zip(weights, floors)]
    excess = sum(widths) - USABLE_W
    if excess > 0:
        room = [max(w - f, 0.0) for w, f in zip(widths, floors)]
        widths = [w - excess * r / sum(room) if sum(room) else w for w, r in zip(widths, room)]
    return widths


def _table(doc, rows: list[list[str]]) -> None:
    n = len(rows[0])
    rows = [(r + [""] * n)[:n] for r in rows]
    t = doc.add_table(rows=len(rows), cols=n)
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    t.autofit = False
    _table_format(t)
    widths = _col_widths(rows)
    short = [max(len(_plain(r[j].strip())) for r in rows) <= 14 for j in range(n)]
    for i, row in enumerate(rows):
        trpr = t.rows[i]._tr.get_or_add_trPr()
        trpr.append(OxmlElement("w:cantSplit"))
        if i == 0:
            trpr.append(OxmlElement("w:tblHeader"))
        for j, text in enumerate(row):
            c = t.cell(i, j)
            c.width = Inches(widths[j])
            c.text = ""
            p = c.paragraphs[0]
            _spacing(p, 0, 0, 1.05, keep_next=(i == 0 or len(rows) <= 9) and i < len(rows) - 1)
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER if short[j] else WD_ALIGN_PARAGRAPH.LEFT
            _runs(p, text.strip(), size=9, bold=True if i == 0 else None)
            if i == 0:
                _shade(c, "D9D9D9")
    for j, col in enumerate(t.columns):
        col.width = Inches(widths[j])
    _spacing(doc.add_paragraph(), 0, 4)


def _field(par, instr: str) -> None:
    for kind in ("begin", instr, "end"):
        r = par.add_run()
        _font(r, size=8.5)
        if kind in ("begin", "end"):
            fc = OxmlElement("w:fldChar")
            fc.set(qn("w:fldCharType"), kind)
            r._r.append(fc)
        else:
            it = OxmlElement("w:instrText")
            it.set(qn("xml:space"), "preserve")
            it.text = kind
            r._r.append(it)


def _setup(doc, title: str) -> None:
    sec = doc.sections[0]
    sec.orientation = WD_ORIENT.PORTRAIT
    sec.page_width, sec.page_height = Inches(PAGE_W), Inches(11.69)
    sec.left_margin = sec.right_margin = Inches(MARGIN)
    sec.top_margin, sec.bottom_margin = Inches(0.9), Inches(0.85)
    _font(doc.styles["Normal"], size=10.5)
    for name, size in (("Heading 1", 14), ("Heading 2", 12), ("Heading 3", 11)):
        st = doc.styles[name]
        _font(st, size=size, bold=True)
        st.paragraph_format.space_before = Pt(16 if name == "Heading 1" else 10)
        st.paragraph_format.space_after = Pt(5)
        st.paragraph_format.keep_with_next = True
    foot = sec.footer.paragraphs[0]
    foot.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _font(foot.add_run(f"{title}  ·  Page "), size=8.5)
    _field(foot, "PAGE")
    _font(foot.add_run(" of "), size=8.5)
    _field(foot, "NUMPAGES")


def render(src: Path, dst: Path) -> None:
    text = src.read_text(encoding="utf-8")
    # The admin token for judges never lives in the repository: set JUDGE_ADMIN_TOKEN when building the file to send.
    token = os.environ.get("JUDGE_ADMIN_TOKEN", "").strip()
    text = text.replace("{{ADMIN_TOKEN}}", token or "(given in the registration form)")
    lines = text.splitlines()
    first = next((ln for ln in lines if ln.startswith("# ")), "# Document")
    doc = Document()
    _setup(doc, first[2:].strip())
    i, in_code, code, table, num = 0, False, [], [], 0

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
                _spacing(p, 2, 8, 1.0)
                p.paragraph_format.left_indent = Inches(0.1)
                _font(p.add_run("\n".join(code)), name=MONO, size=8.5)
                shd = OxmlElement("w:shd")
                shd.set(qn("w:val"), "clear")
                shd.set(qn("w:color"), "auto")
                shd.set(qn("w:fill"), "F2F2F2")
                p._p.get_or_add_pPr().append(shd)
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
            cells = ln.strip().strip("|").split("|")
            if not all(re.fullmatch(r"\s*:?-{2,}:?\s*", c) for c in cells):
                table.append(cells)
            i += 1
            continue
        flush_table()
        img = re.match(r"^!\[(.*?)\]\((.+?)\)\s*$", ln)
        if img:
            path = (src.parent / img.group(2)).resolve()
            if path.exists():
                cap_text, _, w = img.group(1).partition("|")
                doc.add_picture(str(path), width=Inches(min(float(w) if w.strip() else USABLE_W, USABLE_W)))
                pic = doc.paragraphs[-1]
                pic.alignment = WD_ALIGN_PARAGRAPH.CENTER
                _spacing(pic, 4, 2, 1.0, keep_next=True)
                cap = doc.add_paragraph()
                cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
                _spacing(cap, 0, 10)
                _font(cap.add_run(cap_text), size=9, italic=True)
            i += 1
            continue
        m = re.match(r"^(#{1,4})\s+(.*)", ln)
        if m:
            num = 0
            level = len(m.group(1))
            if level == 1:
                p = doc.add_paragraph()
                _spacing(p, 0, 2, 1.0)
                _font(p.add_run(m.group(2).strip()), size=20, bold=True)
            else:
                doc.add_heading(m.group(2).strip(), level - 1)
            i += 1
            continue
        bullet = re.match(r"^\s*[-*]\s+(.*)", ln)
        numbered = re.match(r"^\s*(\d+)\.\s+(.*)", ln)
        if bullet or numbered:
            if bullet:
                label, body, num = "•", bullet.group(1), 0
            else:
                num += 1
                label, body = f"{num}.", numbered.group(2)
            p = doc.add_paragraph()
            _spacing(p, 0, 3)
            p.paragraph_format.left_indent = Inches(0.3)
            p.paragraph_format.first_line_indent = Inches(-0.25)
            p.paragraph_format.tab_stops.add_tab_stop(Inches(0.3))
            p.alignment = WD_ALIGN_PARAGRAPH.LEFT
            _runs(p, f"{label}\t{body}")
        elif ln.strip():
            num = 0
            s = ln.strip()
            p = doc.add_paragraph()
            if re.match(r"^\*\*(Table|Tabel) \d+\.", s):
                _spacing(p, 8, 3, 1.0, keep_next=True)
                p.alignment = WD_ALIGN_PARAGRAPH.LEFT
                _runs(p, s, size=10)
            else:
                _spacing(p, 0, 6)
                p.alignment = WD_ALIGN_PARAGRAPH.LEFT if len(s) < 90 else WD_ALIGN_PARAGRAPH.JUSTIFY
                _runs(p, s)
        else:
            num = 0
        i += 1
    flush_table()
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
