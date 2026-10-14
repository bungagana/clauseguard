"""Deterministic PDF rendering of a reply the user already saw: title, sections of plain lines.
No model runs here; the text comes from solver output the interface has already displayed.
"""
from __future__ import annotations

import io
from datetime import date
from typing import Optional
from xml.sax.saxutils import escape

from pydantic import Field

from ..schema import Strict

MAX_SECTIONS = 30
MAX_LINES = 80
MAX_LINE_CHARS = 600


class ExportSection(Strict):
    heading: str = Field(min_length=1, max_length=120)
    lines: list[str] = Field(default_factory=list, max_length=MAX_LINES)


class ExportRequest(Strict):
    title: str = Field(min_length=1, max_length=120)
    subtitle: Optional[str] = Field(default=None, max_length=200)
    sections: list[ExportSection] = Field(min_length=1, max_length=MAX_SECTIONS)
    footer: Optional[str] = Field(default=None, max_length=300)


def render(req: ExportRequest, *, prepared_for: str, as_of: date, audit_ref: Optional[str] = None) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=styles["Title"], fontSize=18, leading=22, alignment=0, spaceAfter=2)
    meta = ParagraphStyle("meta", parent=styles["Normal"], fontSize=9, textColor=colors.HexColor("#5b5f73"), spaceAfter=10)
    h2 = ParagraphStyle("h2", parent=styles["Heading2"], fontSize=12, leading=15, spaceBefore=10, spaceAfter=4, textColor=colors.HexColor("#3b3fb0"))
    body = ParagraphStyle("body", parent=styles["Normal"], fontSize=10, leading=14)
    quote = ParagraphStyle("quote", parent=body, leftIndent=10, textColor=colors.HexColor("#444a66"), fontName="Helvetica-Oblique")
    foot = ParagraphStyle("foot", parent=meta, spaceBefore=14)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=18 * mm, bottomMargin=18 * mm,
                            title=req.title, author="ClauseGuard")
    flow = [Paragraph(escape(req.title), h1)]
    sub = f"Prepared for {escape(prepared_for)} · {as_of.isoformat()}"
    if req.subtitle:
        sub = f"{escape(req.subtitle)}<br/>{sub}"
    flow.append(Paragraph(sub, meta))
    for sec in req.sections:
        flow.append(Paragraph(escape(sec.heading), h2))
        for line in sec.lines:
            text = escape(line[:MAX_LINE_CHARS])
            is_quote = text.startswith("&quot;") or text.startswith("“")
            flow.append(Paragraph(text, quote if is_quote else body))
            flow.append(Spacer(1, 2))
    footer = req.footer or ("Indicative, computed from the extracted policy wording; the policy wording prevails. "
                            "ClauseGuard never moves money or changes a policy.")
    if audit_ref:
        footer += f" Audit reference: {audit_ref}."
    flow.append(Paragraph(escape(footer), foot))
    doc.build(flow)
    return buf.getvalue()
