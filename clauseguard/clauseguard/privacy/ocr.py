from __future__ import annotations

import io
import shutil
import threading
from dataclasses import dataclass, field
from typing import Any

MIN_EMBEDDED_CHARS = 40
RETAKE_CONFIDENCE = 0.70
RETAKE_MIN_CHARS = 15
OCR_DPI = 200

_lock = threading.Lock()
_rapid: Any = None
_rapid_failed = False


@dataclass
class OcrLine:
    text: str
    confidence: float
    box: tuple[int, int, int, int]


@dataclass
class OcrResult:
    text: str
    mean_confidence: float
    per_line: list[OcrLine] = field(default_factory=list)
    engine: str | None = None
    available: bool = True
    error: str | None = None


@dataclass
class PageText:
    page: int
    text: str
    method: str
    confidence: float | None
    needs_retake: bool
    engine: str | None = None
    ocr_available: bool = True


def unavailable(reason: str = "no OCR engine installed") -> OcrResult:
    return OcrResult("", 0.0, [], None, False, reason)


def _rapid_engine():
    global _rapid, _rapid_failed
    if _rapid is not None or _rapid_failed:
        return _rapid
    with _lock:
        if _rapid is None and not _rapid_failed:
            try:
                from rapidocr_onnxruntime import RapidOCR

                _rapid = RapidOCR()
            except Exception:
                _rapid_failed = True
    return _rapid


def _tesseract_ok() -> bool:
    if shutil.which("tesseract") is None:
        return False
    try:
        import pytesseract  # noqa: F401
    except Exception:
        return False
    return True


def available_engines() -> list[str]:
    out = []
    if _rapid_engine() is not None:
        out.append("rapidocr")
    if _tesseract_ok():
        out.append("tesseract")
    return out


def _to_array(data: bytes):
    import numpy as np
    from PIL import Image

    img = Image.open(io.BytesIO(data)).convert("RGB")
    return np.asarray(img)


def _box_ltrb(pts) -> tuple[int, int, int, int]:
    xs = [int(p[0]) for p in pts]
    ys = [int(p[1]) for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def _run_rapid(data: bytes) -> OcrResult:
    eng = _rapid_engine()
    if eng is None:
        return unavailable("rapidocr not installed")
    result, _ = eng(_to_array(data))
    lines = [OcrLine(str(t), float(s), _box_ltrb(b)) for b, t, s in (result or [])]
    return _finish(lines, "rapidocr")


def _run_tesseract(data: bytes, lang: str = "eng") -> OcrResult:
    import pytesseract
    from PIL import Image

    img = Image.open(io.BytesIO(data)).convert("RGB")
    d = pytesseract.image_to_data(img, lang=lang, output_type=pytesseract.Output.DICT)
    groups: dict = {}
    for i, w in enumerate(d["text"]):
        conf = float(d["conf"][i])
        if not w.strip() or conf < 0:
            continue
        key = (d["block_num"][i], d["par_num"][i], d["line_num"][i])
        g = groups.setdefault(key, {"w": [], "c": [], "b": [10**9, 10**9, 0, 0]})
        g["w"].append(w)
        g["c"].append(conf / 100.0)
        x, y, ww, hh = d["left"][i], d["top"][i], d["width"][i], d["height"][i]
        b = g["b"]
        b[0], b[1], b[2], b[3] = min(b[0], x), min(b[1], y), max(b[2], x + ww), max(b[3], y + hh)
    lines = [OcrLine(" ".join(g["w"]), sum(g["c"]) / len(g["c"]), tuple(g["b"])) for g in groups.values()]
    return _finish(lines, "tesseract")


def _finish(lines: list[OcrLine], engine: str) -> OcrResult:
    text = "\n".join(l.text for l in lines)
    total = sum(len(l.text) for l in lines)
    mean = (sum(l.confidence * len(l.text) for l in lines) / total) if total else 0.0
    return OcrResult(text, mean, lines, engine, True, None)


def ocr_image(data: bytes, engine: str | None = None) -> OcrResult:
    """Local OCR of encoded image bytes. Never raises; returns available=False when no engine exists."""
    try:
        engines = available_engines()
        if engine is not None:
            engines = [e for e in engines if e == engine]
        if not engines:
            return unavailable()
        return _run_rapid(data) if engines[0] == "rapidocr" else _run_tesseract(data)
    except Exception as exc:
        return OcrResult("", 0.0, [], engine, False, f"{type(exc).__name__}: {exc}")


def needs_retake(res: OcrResult) -> bool:
    if not res.available:
        return True
    return res.mean_confidence < RETAKE_CONFIDENCE or len(res.text.strip()) < RETAKE_MIN_CHARS


def pdf_pages_text(path, min_chars: int = MIN_EMBEDDED_CHARS, dpi: int = OCR_DPI,
                   engine: str | None = None) -> list[PageText]:
    import pymupdf as fitz

    pages: list[PageText] = []
    with fitz.open(str(path)) as doc:
        for i, page in enumerate(doc):
            embedded = page.get_text("text") or ""
            if len(embedded.strip()) >= min_chars:
                pages.append(PageText(i + 1, embedded, "embedded", None, False))
                continue
            try:
                png = page.get_pixmap(dpi=dpi).tobytes("png")
            except Exception:
                pages.append(PageText(i + 1, embedded, "ocr", 0.0, True, None, False))
                continue
            res = ocr_image(png, engine)
            if not res.available:
                pages.append(PageText(i + 1, embedded, "ocr", 0.0, True, None, False))
            else:
                pages.append(PageText(i + 1, res.text, "ocr", res.mean_confidence, needs_retake(res), res.engine, True))
    return pages


def flagged_line_boxes(res: OcrResult, known_names=()) -> list[tuple[int, int, int, int]]:
    from .redact import redact

    boxes = []
    ctx = res.text
    flagged_full = redact(ctx, known_names)
    if not flagged_full.findings:
        return boxes
    offset = 0
    spans = [(f.start, f.end) for f in flagged_full.findings]
    for line in res.per_line:
        s, e = offset, offset + len(line.text)
        if any(a < e and b > s for a, b in spans):
            boxes.append(line.box)
        offset = e + 1
    return boxes


def black_out_regions(image, boxes, pad: int = 2):
    """Fill rectangles (left, top, right, bottom) with black. Accepts PIL image or encoded bytes."""
    from PIL import Image, ImageDraw

    was_bytes = isinstance(image, (bytes, bytearray))
    img = Image.open(io.BytesIO(bytes(image))).convert("RGB") if was_bytes else image.convert("RGB")
    draw = ImageDraw.Draw(img)
    for l, t, r, b in boxes:
        draw.rectangle((l - pad, t - pad, r + pad, b + pad), fill=(0, 0, 0))
    if not was_bytes:
        return img
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
