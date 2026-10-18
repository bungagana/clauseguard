"""Build ClauseGuard_deck.pptx from docs/DECK.md.

One idea per slide: a title, one sentence, one or two pictures or a chart, at most three short bullets,
and spoken notes of at most 60 words. Usage: python docs/deck/build_deck.py
"""
from __future__ import annotations

import re
from pathlib import Path

from PIL import Image
from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LABEL_POSITION
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN
from pptx.util import Emu, Inches, Pt

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]  # LOMBA-CHINA/
SRC = HERE.parent / "DECK.md"
OUT = HERE / "ClauseGuard_deck.pptx"

NAVY = RGBColor(0x14, 0x21, 0x3D)
BLUE = RGBColor(0x1E, 0x40, 0xAF)
INK = RGBColor(0x1F, 0x29, 0x33)
MUTED = RGBColor(0x5B, 0x67, 0x72)
LIGHT = RGBColor(0xEE, 0xF2, 0xFF)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
FONT = "Calibri"
W, H = Inches(13.333), Inches(7.5)
MARGIN = Inches(0.7)
MAX_NOTE_WORDS = 72

BENCH = [("Gemini 3", 65.2, 26.6), ("ChatGPT 5.3", 72.9, 6.7), ("Claude Sonnet 4.6", 87.8, 2.4), ("ClauseGuard", 84.6, 1.4)]
SERIES = {"en": ("Accuracy (%)", "Fabricated denials (%)"), "id": ("Akurasi (%)", "Penolakan yang dikarang (%)")}
LANG = "en"


def parse(md: str) -> list[dict]:
    slides = []
    for block in re.split(r"^## Slide \d+: ", md, flags=re.M)[1:]:
        title, _, rest = block.partition("\n")
        body, _, notes = rest.partition("Notes:")
        s = {"title": title.strip(), "line": "", "images": [], "chart": None, "bullets": [], "notes": " ".join(notes.split())}
        for ln in body.splitlines():
            if ln.startswith("Line:"):
                s["line"] = ln[5:].strip()
            elif ln.startswith(("Image:", "Image2:")):
                s["images"].append(REPO / ln.split(":", 1)[1].strip())
            elif ln.startswith("Chart:"):
                s["chart"] = ln[6:].strip()
            elif ln.startswith("- "):
                s["bullets"].append(ln[2:].strip())
        if len(s["notes"].split()) > MAX_NOTE_WORDS:
            raise SystemExit(f"slide '{s['title']}': notes exceed {MAX_NOTE_WORDS} words")
        if len(s["bullets"]) > 4:
            raise SystemExit(f"slide '{s['title']}': more than four bullets")
        slides.append(s)
    return slides


def text(slide, x, y, w, h, s, size, color=INK, bold=False, align=PP_ALIGN.LEFT):
    tb = slide.shapes.add_textbox(x, y, w, h)
    tf = tb.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.alignment = align
    r = p.add_run()
    r.text = s
    r.font.size, r.font.name, r.font.bold, r.font.color.rgb = Pt(size), FONT, bold, color
    return tb


def bullets(slide, x, y, w, items, size=16):
    tb = slide.shapes.add_textbox(x, y, w, Inches(0.5) * len(items))
    tf = tb.text_frame
    tf.word_wrap = True
    for i, it in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.space_after = Pt(8)
        r = p.add_run()
        r.text = "•  " + it
        r.font.size, r.font.name, r.font.color.rgb = Pt(size), FONT, INK


def picture(slide, path: Path, x, y, max_w, max_h, frame=True):
    with Image.open(path) as im:
        iw, ih = im.size
    scale = min(max_w / iw, max_h / ih)
    w, h = int(iw * scale), int(ih * scale)
    px, py = x + int((max_w - w) / 2), y + int((max_h - h) / 2)
    if frame:
        bg = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, px - Inches(0.06), py - Inches(0.06), w + Inches(0.12), h + Inches(0.12))
        bg.adjustments[0] = 0.03
        bg.fill.solid()
        bg.fill.fore_color.rgb = LIGHT
        bg.line.fill.background()
        bg.shadow.inherit = False
    slide.shapes.add_picture(str(path), px, py, width=w, height=h)


def chart(slide, x, y, w, h):
    data = CategoryChartData()
    data.categories = [b[0] for b in BENCH]
    data.add_series(SERIES[LANG][0], [b[1] for b in BENCH])
    data.add_series(SERIES[LANG][1], [b[2] for b in BENCH])
    gf = slide.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, x, y, w, h, data)
    ch = gf.chart
    ch.has_legend = True
    ch.legend.include_in_layout = False
    ch.legend.font.size = Pt(12)
    ch.legend.font.name = FONT
    ch.value_axis.maximum_scale = 100
    ch.value_axis.has_major_gridlines = False
    ch.value_axis.tick_labels.font.size = Pt(11)
    ch.category_axis.tick_labels.font.size = Pt(12)
    ch.category_axis.tick_labels.font.name = FONT
    plot = ch.plots[0]
    plot.gap_width = 60
    plot.has_data_labels = True
    plot.data_labels.font.size = Pt(11)
    plot.data_labels.font.name = FONT
    plot.data_labels.number_format = '0.0"%"'
    plot.data_labels.position = XL_LABEL_POSITION.OUTSIDE_END
    for series, color in zip(plot.series, (BLUE, RGBColor(0xC2, 0x41, 0x0C))):
        series.format.fill.solid()
        series.format.fill.fore_color.rgb = color
        # the entry's own bars are emphasised, the others muted
        for idx, pt in enumerate(series.points):
            pt.format.fill.solid()
            pt.format.fill.fore_color.rgb = color if BENCH[idx][0] == "ClauseGuard" else RGBColor(0xB6, 0xBD, 0xC9) if series.name == SERIES[LANG][0] else RGBColor(0xE2, 0xB3, 0xA3)


def build(src: Path = SRC, out: Path = OUT) -> None:
    global LANG
    LANG = "id" if src.parent.name == "id" else "en"
    slides = parse(src.read_text(encoding="utf-8"))
    prs = Presentation()
    prs.slide_width, prs.slide_height = W, H
    blank = prs.slide_layouts[6]
    for i, s in enumerate(slides):
        sl = prs.slides.add_slide(blank)
        title_slide = i == 0
        if title_slide:
            band = sl.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, W, H)
            band.fill.solid()
            band.fill.fore_color.rgb = NAVY
            band.line.fill.background()
            if s["images"]:
                # the wordmark on a white card
                card = sl.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(3.9), Inches(1.2), Inches(5.5), Inches(2.2))
                card.adjustments[0] = 0.08
                card.fill.solid()
                card.fill.fore_color.rgb = WHITE
                card.line.fill.background()
                picture(sl, s["images"][0], Inches(4.1), Inches(1.35), Inches(5.1), Inches(1.9), frame=False)
            text(sl, MARGIN, Inches(3.8), W - 2 * MARGIN, Inches(1.2), s["line"], 30, WHITE, True, PP_ALIGN.CENTER)
            y = Inches(5.3)
            for b in s["bullets"]:
                text(sl, MARGIN, y, W - 2 * MARGIN, Inches(0.5), b, 16, RGBColor(0xC7, 0xD2, 0xFE), False, PP_ALIGN.CENTER)
                y += Inches(0.45)
        else:
            # accent bar + title + the one sentence
            bar = sl.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, Inches(0.18), H)
            bar.fill.solid()
            bar.fill.fore_color.rgb = BLUE
            bar.line.fill.background()
            text(sl, MARGIN, Inches(0.45), W - 2 * MARGIN, Inches(0.6), s["title"].upper(), 13, BLUE, True)
            text(sl, MARGIN, Inches(0.95), W - 2 * MARGIN, Inches(1.2), s["line"], 28, NAVY, True)
            top = Inches(2.25)
            has_visual = bool(s["images"]) or bool(s["chart"])
            if has_visual:
                vis_w = Inches(8.2) if s["bullets"] else W - 2 * MARGIN
                vis_h = H - top - Inches(0.6)
                if s["chart"] == "benchmark":
                    chart(sl, MARGIN, top, vis_w, vis_h)
                elif len(s["images"]) == 2:
                    half = int((vis_w - Inches(0.3)) / 2)
                    picture(sl, s["images"][0], MARGIN, top, half, vis_h)
                    picture(sl, s["images"][1], MARGIN + half + Inches(0.3), top, half, vis_h)
                else:
                    picture(sl, s["images"][0], MARGIN, top, vis_w, vis_h)
                if s["bullets"]:
                    bullets(sl, MARGIN + vis_w + Inches(0.4), top + Inches(0.2), W - MARGIN * 2 - vis_w - Inches(0.4), s["bullets"], 15)
            elif s["bullets"]:
                bullets(sl, MARGIN, top + Inches(0.3), W - 2 * MARGIN, s["bullets"], 20)
            text(sl, W - Inches(1.2), H - Inches(0.5), Inches(0.6), Inches(0.3), f"{i + 1}/{len(slides)}", 10, MUTED, False, PP_ALIGN.RIGHT)
        sl.notes_slide.notes_text_frame.text = s["notes"]
    prs.save(str(out))
    words = [len(s["notes"].split()) for s in slides]
    print(f"saved {out} | slides {len(slides)} | note words {words} | total {sum(words)} (~{sum(words) / 130:.1f} min spoken)")


if __name__ == "__main__":
    import sys

    if len(sys.argv) == 3:  # python docs/deck/build_deck.py SRC.md OUT.pptx
        build(Path(sys.argv[1]), Path(sys.argv[2]))
    else:
        build()
