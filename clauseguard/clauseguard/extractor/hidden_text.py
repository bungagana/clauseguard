"""Hidden-text and instruction-pattern detection for uploaded PDFs (pure code, no LLM).

Techniques detected:
  render_mode_invisible  text drawn with render mode 3/7 (invisible / clip-only)
  tiny_font              font size < 4 pt
  color_matches_bg       text colour within a small distance of the page background
  off_page               text bbox (mostly) outside the page rectangle
  low_opacity            text drawn with alpha < 0.1
  metadata               document Info dictionary / XMP packet carries text
  annotation             annotation contents (free text, sticky notes, ...)
  form_field             widget / form-field values
  image_alt              /Alt or /ActualText entries on images or structure elements
plus `instruction_patterns`: regex hits over *all* text (visible + hidden + metadata).

Every snippet is capped at 200 chars and is display-only.
"""
from __future__ import annotations

import logging
import math
import re
import threading
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

try:  # the `fitz` alias can be a broken namespace package on some installs
    import pymupdf as fitz
except ImportError:  # pragma: no cover
    import fitz  # type: ignore

log = logging.getLogger("clauseguard.hidden_text")

SNIPPET_MAX = 200
TINY_FONT_PT = 4.0
COLOR_DISTANCE = 0.12  # max per-channel distance (0..1) to count as "same as background"
LOW_OPACITY = 0.1
TINY_TEXT_MIN_CHARS = 40
LONG_TEXT_FINDING = 200  # metadata / alt text longer than this is reported even without a pattern hit


class Finding(BaseModel):
    model_config = ConfigDict(extra="forbid")
    technique: str
    page: int
    snippet: str = Field(max_length=SNIPPET_MAX)


class HiddenTextReport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    suspicious: bool
    findings: list[Finding]
    instruction_patterns: list[str]


# ----------------------------------------------------------------------- instruction regexes
# name -> compiled pattern. Names are what we report (closed vocabulary; never the matched text).
INSTRUCTION_PATTERNS: dict[str, re.Pattern[str]] = {
    "ignore_previous": re.compile(r"\b(ignore|disregard|forget|override)\b[^.\n]{0,40}\b(previous|prior|above|earlier|all|system|your)\b[^.\n]{0,30}\b(instruction|prompt|rule|guideline|message|context)s?\b", re.I),
    "ignore_previous_id": re.compile(r"\b(abaikan|lupakan)\b[^.\n]{0,40}\b(instruksi|perintah|aturan)\b", re.I),
    "system_role_marker": re.compile(r"(^|\n|\[|<)\s*(system|assistant|user|developer)\s*(:|\]|>)", re.I),
    "role_assignment": re.compile(r"\byou are (now )?(a|an|the)\b[^.\n]{0,40}\b(assistant|agent|ai|model|bot|insurer|adjuster)\b", re.I),
    "approve_claim": re.compile(r"\b(approve|approved|authorise|authorize|pay out|payout|setujui|cairkan)\b[^.\n]{0,40}\b(claim|klaim|payment|pembayaran|amount|benefit|immediately|now)\b", re.I),
    "transfer_funds": re.compile(r"\b(transfer|wire|send|kirim|remit)\b[^.\n]{0,40}\b(funds?|money|payment|amount|uang|dana|benefit|balance|to the account|ke rekening)\b", re.I),
    "bank_account": re.compile(r"\b(account|acct|rekening|iban|swift)\b[^.\n]{0,20}\b\d[\d \-]{7,}\d\b", re.I),
    "change_beneficiary": re.compile(r"\b(change|update|ubah|ganti)\b[^.\n]{0,30}\b(beneficiary|payee|penerima|account|rekening|phone|email|address)\b", re.I),
    "tool_call_syntax": re.compile(r"\b(call|invoke|run|execute)\b\s*(the )?(tool|function)\b|\b[a-z_]+\((?:[a-z_]+=)", re.I),
    "secrecy": re.compile(r"\b(do not|don't|never)\b[^.\n]{0,20}\b(tell|mention|reveal|disclose|inform|show)\b[^.\n]{0,20}\b(user|customer|anyone|human)\b", re.I),
    "base64_blob": re.compile(r"(?<![A-Za-z0-9+/])[A-Za-z0-9+/]{48,}={0,2}(?![A-Za-z0-9+/])"),
}


def scan_text_for_instructions(text: str) -> list[str]:
    """Return the names of instruction patterns found in `text` (sorted, unique)."""
    hits = [name for name, pat in INSTRUCTION_PATTERNS.items() if pat.search(text or "")]
    return sorted(hits)


def _snip(s: str) -> str:
    s = re.sub(r"\s+", " ", (s or "")).strip()
    return s[:SNIPPET_MAX]


# ----------------------------------------------------------------------- helpers
def _rgb(color_int: int) -> tuple[float, float, float]:
    c = int(color_int or 0)
    return ((c >> 16) & 255) / 255.0, ((c >> 8) & 255) / 255.0, (c & 255) / 255.0


def _close(a: tuple[float, float, float], b: tuple[float, float, float], tol: float = COLOR_DISTANCE) -> bool:
    return all(abs(x - y) <= tol for x, y in zip(a, b))


class _PageRaster:
    """Low-resolution render of a page used to sample the real background under a text span
    (works for vector fills, images and gradients alike)."""

    def __init__(self, page):
        self.rect = page.rect
        self.ok = False
        try:
            pix = page.get_pixmap(dpi=72, colorspace=fitz.csRGB, alpha=False)
            import numpy as np

            self.np = np
            self.arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)[:, :, :3]
            self.ok = True
        except Exception as e:  # pragma: no cover
            log.debug("raster failed: %s", e)

    def median_under(self, bbox) -> Optional[tuple[float, float, float]]:
        if not self.ok:
            return None
        r = fitz.Rect(bbox) + (-2, -2, 2, 2)
        r = r & self.rect
        if r.is_empty:
            return None
        x0 = int(r.x0 - self.rect.x0)
        y0 = int(r.y0 - self.rect.y0)
        x1 = int(math.ceil(r.x1 - self.rect.x0))
        y1 = int(math.ceil(r.y1 - self.rect.y0))
        h, w = self.arr.shape[:2]
        x0, y0, x1, y1 = max(0, x0), max(0, y0), min(w, x1), min(h, y1)
        if x1 <= x0 or y1 <= y0:
            return None
        region = self.arr[y0:y1, x0:x1].reshape(-1, 3)
        med = self.np.median(region, axis=0)
        return float(med[0]) / 255.0, float(med[1]) / 255.0, float(med[2]) / 255.0


def _background_at(page, bbox, raster: "_PageRaster") -> tuple[float, float, float]:
    """Dominant colour of the rendered page under `bbox` (white if rendering is unavailable)."""
    med = raster.median_under(bbox)
    return med if med is not None else (1.0, 1.0, 1.0)


def _texttrace(page) -> list[dict]:
    try:
        return page.get_texttrace()
    except Exception as e:  # pragma: no cover - older PyMuPDF
        log.debug("get_texttrace unavailable: %s", e)
        return []


def _span_text(span: dict) -> str:
    chars = span.get("chars")
    if chars:
        return "".join(chr(c[0]) if isinstance(c[0], int) else str(c[0]) for c in chars)
    return span.get("text", "")


def _content_stream_render_modes(page) -> set[int]:
    """Render modes used in the page's content stream(s) (e.g. {3} when `3 Tr` appears)."""
    modes: set[int] = set()
    try:
        data = page.read_contents() or b""
    except Exception:  # pragma: no cover
        return modes
    for m in re.finditer(rb"(?<![\d.])(\d)\s+Tr\b", data):
        modes.add(int(m.group(1)))
    return modes


# ----------------------------------------------------------------------- page scan
def _scan_page(page, pno: int, findings: list[Finding], all_text: list[str]) -> None:
    prect = page.rect
    drawings = _PageRaster(page)  # background sampler (name kept for the helper signature)
    tiny_parts: list[str] = []

    visible_text = page.get_text("text") or ""
    all_text.append(visible_text)

    stream_modes = _content_stream_render_modes(page)
    invisible_stream = bool(stream_modes & {3, 7})

    # --- per-span analysis via texttrace (has render type, opacity, colour, size, bbox)
    for span in _texttrace(page):
        text = _span_text(span)
        if not text.strip():
            continue
        all_text.append(text)
        size = float(span.get("size", 0) or 0)
        bbox = span.get("bbox")
        stype = span.get("type", 0)
        opacity = float(span.get("opacity", 1.0) if span.get("opacity") is not None else 1.0)
        color = span.get("color")

        if stype in (3, 7):  # texttrace `type` is the PDF text render mode: 3 = invisible, 7 = clip only
            findings.append(Finding(technique="render_mode_invisible", page=pno, snippet=_snip(text)))
        if 0 < size < TINY_FONT_PT:
            tiny_parts.append(text)
        if opacity < LOW_OPACITY:
            findings.append(Finding(technique="low_opacity", page=pno, snippet=_snip(text)))
        if bbox is not None:
            r = fitz.Rect(bbox)
            if r.is_empty or r.is_infinite:
                pass
            else:
                inter = r & prect
                visible_frac = (inter.get_area() / r.get_area()) if r.get_area() > 0 else 1.0
                if visible_frac < 0.5:
                    findings.append(Finding(technique="off_page", page=pno, snippet=_snip(text)))
                elif color is not None and stype in (0, 1, 2):
                    try:
                        rgb = tuple(float(x) for x in color[:3]) if isinstance(color, (tuple, list)) else _rgb(color)
                        if len(rgb) == 1:
                            rgb = (rgb[0],) * 3
                        bg = _background_at(page, r, drawings)
                        if _close(rgb, bg):  # type: ignore[arg-type]
                            findings.append(Finding(technique="color_matches_bg", page=pno, snippet=_snip(text)))
                    except Exception:  # pragma: no cover
                        pass

    # fallback for installs where texttrace is missing: "dict" spans still give size/colour/bbox
    if not _texttrace(page):
        for block in page.get_text("dict").get("blocks", []):
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    text = span.get("text", "")
                    if not text.strip():
                        continue
                    if 0 < float(span.get("size", 0)) < TINY_FONT_PT:
                        tiny_parts.append(text)
                    r = fitz.Rect(span["bbox"])
                    inter = r & prect
                    if r.get_area() > 0 and inter.get_area() / r.get_area() < 0.5:
                        findings.append(Finding(technique="off_page", page=pno, snippet=_snip(text)))
                    elif _close(_rgb(span.get("color", 0)), _background_at(page, r, drawings)):
                        findings.append(Finding(technique="color_matches_bg", page=pno, snippet=_snip(text)))
        if invisible_stream:
            findings.append(Finding(technique="render_mode_invisible", page=pno, snippet=_snip(visible_text[:SNIPPET_MAX])))

    # tiny text: app-store badges and legal footers legitimately use <4pt for a few words;
    # a payload is a sentence. Flag when the page's tiny text is long or instruction-like.
    if tiny_parts:
        joined = " ".join(tiny_parts)
        if len(joined.strip()) >= TINY_TEXT_MIN_CHARS or scan_text_for_instructions(joined):
            findings.append(Finding(technique="tiny_font", page=pno, snippet=_snip(joined)))

    # --- annotations and form fields
    try:
        for annot in page.annots() or []:
            info = annot.info or {}
            content = " ".join(str(info.get(k, "")) for k in ("content", "title", "subject") if info.get(k))
            if content.strip():
                all_text.append(content)
                findings.append(Finding(technique="annotation", page=pno, snippet=_snip(content)))
    except Exception as e:  # pragma: no cover
        log.debug("annots failed on page %d: %s", pno, e)
    try:
        for w in page.widgets() or []:
            val = w.field_value
            label = w.field_label or w.field_name or ""
            if val not in (None, "", False, "Off"):
                s = f"{label}: {val}" if label else str(val)
                all_text.append(s)
                findings.append(Finding(technique="form_field", page=pno, snippet=_snip(s)))
    except Exception as e:  # pragma: no cover
        log.debug("widgets failed on page %d: %s", pno, e)


def _scan_xrefs_for_alt(doc, findings: list[Finding], all_text: list[str]) -> None:
    """Image /Alt, /ActualText and structure-element alt text anywhere in the xref table."""
    try:
        n = doc.xref_length()
    except Exception:  # pragma: no cover
        return
    for xref in range(1, n):
        for key in ("Alt", "ActualText", "E"):
            try:
                kind, val = doc.xref_get_key(xref, key)
            except Exception:
                continue
            if kind == "string" and val:
                s = val.strip("()")
                if s.strip():
                    all_text.append(s)
                    if len(s) > LONG_TEXT_FINDING or scan_text_for_instructions(s):
                        findings.append(Finding(technique="image_alt", page=0, snippet=_snip(s)))


def _scan_metadata(doc, findings: list[Finding], all_text: list[str]) -> None:
    md = doc.metadata or {}
    for k, v in md.items():
        if not v or k in ("format", "encryption"):
            continue
        s = str(v)
        all_text.append(s)
        if k in ("creationDate", "modDate") or (len(s) <= LONG_TEXT_FINDING and not scan_text_for_instructions(s)):
            continue  # ordinary producer/title strings are not findings
        findings.append(Finding(technique="metadata", page=0, snippet=_snip(f"{k}: {s}")))
    try:
        xmp = doc.get_xml_metadata() or ""
    except Exception:  # pragma: no cover
        xmp = ""
    if xmp.strip():
        # every producer writes a long XMP packet (dates, tool names, ids); only the human-text
        # elements can carry a payload
        texty = re.findall(r"<(?:dc:title|dc:description|dc:subject|dc:creator|pdf:Keywords|xmp:Label|xmpRights:UsageTerms)[^>]*>(.*?)</(?:dc:title|dc:description|dc:subject|dc:creator|pdf:Keywords|xmp:Label|xmpRights:UsageTerms)>", xmp, flags=re.S | re.I)
        payload = " ".join(re.sub(r"<[^>]+>", " ", t) for t in texty)
        payload = re.sub(r"\s+", " ", payload).strip()
        whole = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", xmp)).strip()
        all_text.append(whole)
        if scan_text_for_instructions(whole) or len(payload) > LONG_TEXT_FINDING:
            findings.append(Finding(technique="metadata", page=0, snippet=_snip("xmp: " + (payload or whole))))


# ----------------------------------------------------------------------- public API
def extract_all_text(path: str | Path) -> str:
    """All text the scanner can see (visible, hidden, metadata, annotations). For regex scans."""
    doc = fitz.open(str(path))
    texts: list[str] = []
    f: list[Finding] = []
    try:
        for pno, page in enumerate(doc, start=1):
            _scan_page(page, pno, f, texts)
        _scan_metadata(doc, f, texts)
        _scan_xrefs_for_alt(doc, f, texts)
    finally:
        doc.close()
    return "\n".join(texts)


def scan_pdf(path: str | Path) -> HiddenTextReport:
    """Scan a PDF for hidden text techniques and instruction-like patterns."""
    path = Path(path)
    doc = fitz.open(str(path))
    findings: list[Finding] = []
    all_text: list[str] = []
    try:
        for pno, page in enumerate(doc, start=1):
            try:
                _scan_page(page, pno, findings, all_text)
            except Exception as e:  # pragma: no cover - never let a malformed page skip the scan
                log.warning("page %d scan error: %s", pno, e)
                findings.append(Finding(technique="scan_error", page=pno, snippet=_snip(str(e))))
        _scan_metadata(doc, findings, all_text)
        _scan_xrefs_for_alt(doc, findings, all_text)
    finally:
        doc.close()

    # de-duplicate findings (same technique/page/snippet)
    seen: set[tuple[str, int, str]] = set()
    uniq: list[Finding] = []
    for f in findings:
        key = (f.technique, f.page, f.snippet)
        if key not in seen:
            seen.add(key)
            uniq.append(f)

    patterns = scan_text_for_instructions("\n".join(all_text))
    return HiddenTextReport(suspicious=bool(uniq) or bool(patterns), findings=uniq, instruction_patterns=patterns)


SCAN_TIMEOUT_S = 30

# Fixed, non-leaking reason vocabulary for a PDF that can't be meaningfully parsed. Never put a
# raw exception message (which can carry a server-side file path) into a user-visible report.
REASON_CORRUPT = "corrupt_or_unreadable_pdf"
REASON_PASSWORD = "password_protected_pdf"
REASON_ZERO_PAGE = "zero_page_pdf"
REASON_TIMEOUT = "pdf_parse_timeout"
REASON_PII_BLOCKED = "pii_blocked"


class PdfUnreadable(Exception):
    """A PDF that opens (or fails to) but cannot be meaningfully parsed: corrupt, truncated,
    password-protected, or zero pages. `args[0]` is one of the REASON_* constants above."""


def check_pdf_readable(path: str | Path) -> None:
    """Cheap preflight: raises PdfUnreadable before any expensive scan/LLM work is attempted."""
    try:
        doc = fitz.open(str(path))
    except Exception:
        raise PdfUnreadable(REASON_CORRUPT) from None
    try:
        if doc.needs_pass:
            raise PdfUnreadable(REASON_PASSWORD)
        if doc.page_count == 0:
            raise PdfUnreadable(REASON_ZERO_PAGE)
    finally:
        doc.close()


def parse_error_report(reason: str) -> HiddenTextReport:
    return HiddenTextReport(
        suspicious=True,
        findings=[Finding(technique="parse_error", page=0, snippet=reason[:SNIPPET_MAX])],
        instruction_patterns=[],
    )


def scan_pdf_safe(path: str | Path, timeout_s: float = SCAN_TIMEOUT_S) -> HiddenTextReport:
    """`scan_pdf`, but never raises and never blocks past `timeout_s`: a malformed, truncated,
    password-protected, zero-page or otherwise pathological PDF (pymupdf is a C extension and
    can't be reliably interrupted from the calling thread for a worst-case hang; a thread-based
    timeout bounds the common cases) returns a `parse_error` finding instead. A thread that
    actually times out is abandoned (daemon) rather than joined further, so the request does not
    wait on it; it is a bounded, rare leak, not a hang."""
    out: dict = {}

    def _run() -> None:
        try:
            check_pdf_readable(path)
            out["result"] = scan_pdf(path)
        except PdfUnreadable as e:
            out["error_reason"] = str(e.args[0]) if e.args else REASON_CORRUPT
        except Exception as e:  # noqa: BLE001 - any other parse failure is also "couldn't parse"
            log.warning("pdf scan failed: %s", str(e)[:200])
            out["error_reason"] = REASON_CORRUPT

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout_s)
    if t.is_alive():
        log.warning("pdf scan timed out after %ss", timeout_s)
        return parse_error_report(REASON_TIMEOUT)
    if "error_reason" in out:
        return parse_error_report(out["error_reason"])
    return out["result"]


def visible_text(path: str | Path) -> str:
    """Plain visible text (page.get_text) for all pages, pages separated by form feeds."""
    doc = fitz.open(str(path))
    try:
        return "\f".join((p.get_text("text") or "") for p in doc)
    finally:
        doc.close()
