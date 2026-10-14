"""Build ClauseGuard_deck.pptx from docs/DECK.md (python-pptx).

Usage: python docs/deck/build_deck.py
"""
import re
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.util import Inches, Pt

HERE = Path(__file__).resolve().parent
SRC = HERE.parent / "DECK.md"
OUT = HERE / "ClauseGuard_deck.pptx"

ACCENT = RGBColor(0x0B, 0x6E, 0x6E)
INK = RGBColor(0x1F, 0x29, 0x33)
MUTED = RGBColor(0x5B, 0x67, 0x72)
LIGHT = RGBColor(0xE8, 0xF1, 0xF1)
FONT = "Calibri"


def parse(md: str):
    slides = []
    for block in re.split(r"^## Slide \d+: ", md, flags=re.M)[1:]:
        title, _, rest = block.partition("\n")
        body, _, notes = rest.partition("Notes:")
        bullets = [ln[2:].strip() for ln in body.splitlines() if ln.startswith("- ")]
        slides.append({"title": title.strip(), "bullets": bullets, "notes": notes.strip()})
    return slides


def run(p, text, size, color=INK, bold=False):
    r = p.add_run()
    r.text = text
    r.font.size = Pt(size)
    r.font.name = FONT
    r.font.bold = bold
    r.font.color.rgb = color
    return r


def box(slide, x, y, w, h, fill=None, line=None):
    shp = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, x, y, w, h)
    if fill is None:
        shp.fill.background()
    else:
        shp.fill.solid()
        shp.fill.fore_color.rgb = fill
    if line is None:
        shp.line.fill.background()
    else:
        shp.line.color.rgb = line
        shp.line.width = Pt(1.25)
    shp.shadow.inherit = False
    return shp


def flow(slide, labels, y):
    n = len(labels)
    gap = Inches(0.25)
    total_w = Inches(12.1)
    w = int((total_w - gap * (n - 1)) / n)
    x = Inches(0.6)
    for i, lab in enumerate(labels):
        shp = box(slide, x, y, w, Inches(1.0), fill=LIGHT, line=ACCENT)
        tf = shp.text_frame
        tf.word_wrap = True
        tf.vertical_anchor = MSO_ANCHOR.MIDDLE
        p = tf.paragraphs[0]
        p.alignment = PP_ALIGN.CENTER
        run(p, lab, 13, INK, True)
        if i < n - 1:
            ar = slide.shapes.add_shape(MSO_SHAPE.RIGHT_ARROW, x + w + Inches(0.02), y + Inches(0.35), gap - Inches(0.04), Inches(0.3))
            ar.fill.solid()
            ar.fill.fore_color.rgb = ACCENT
            ar.line.fill.background()
        x += w + gap


def build():
    slides = parse(SRC.read_text(encoding="utf8"))
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
    blank = prs.slide_layouts[6]
    for i, s in enumerate(slides, 1):
        sl = prs.slides.add_slide(blank)
        if i == 1:
            box(sl, 0, 0, Inches(0.5), Inches(7.5), fill=ACCENT)
            tb = sl.shapes.add_textbox(Inches(1.2), Inches(2.0), Inches(11), Inches(1.4)).text_frame
            run(tb.paragraphs[0], s["title"], 54, ACCENT, True)
            tb = sl.shapes.add_textbox(Inches(1.2), Inches(3.3), Inches(11), Inches(3.5)).text_frame
            tb.word_wrap = True
            for j, b in enumerate(s["bullets"]):
                p = tb.paragraphs[0] if j == 0 else tb.add_paragraph()
                run(p, b, 26 if j == 0 else 20, INK if j == 0 else MUTED, j == 0)
                p.space_after = Pt(10)
        else:
            box(sl, 0, 0, Inches(0.25), Inches(7.5), fill=ACCENT)
            tf = sl.shapes.add_textbox(Inches(0.7), Inches(0.4), Inches(12), Inches(1.0)).text_frame
            tf.word_wrap = True
            run(tf.paragraphs[0], s["title"], 36, ACCENT, True)
            top = Inches(1.5)
            if i == 4:
                flow(sl, ["PDF policy", "Quarantined extractor", "Typed clause store", "Deterministic solver", "Cited reply"], Inches(1.5))
                top = Inches(2.9)
            n = len(s["bullets"])
            size = 22 if n <= 4 else 19 if n <= 5 else 17
            tb = sl.shapes.add_textbox(Inches(0.7), top, Inches(12), Inches(7.0) - top).text_frame
            tb.word_wrap = True
            for j, b in enumerate(s["bullets"]):
                p = tb.paragraphs[0] if j == 0 else tb.add_paragraph()
                run(p, "■  ", size - 6, ACCENT, True)
                run(p, b, size)
                p.space_after = Pt(12)
            ft = sl.shapes.add_textbox(Inches(0.7), Inches(7.0), Inches(12), Inches(0.35)).text_frame
            run(ft.paragraphs[0], f"ClauseGuard  |  FinTechathon 2026, Topic D  |  {i}/10", 11, MUTED)
        sl.notes_slide.notes_text_frame.text = s["notes"]
    prs.save(OUT)
    words = [len(s["notes"].split()) for s in slides]
    print("saved", OUT, "slides", len(slides), "note words", words, "total", sum(words))


if __name__ == "__main__":
    build()
