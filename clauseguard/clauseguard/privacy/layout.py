from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from difflib import SequenceMatcher

FUZZY_THRESHOLD = 0.85
MIN_LEN = 3
MAX_LEN = 110

_BAB = re.compile(r"^(?:BAB|CHAPTER|BAGIAN|PART)\s+(?:[IVXLC]+|\d+)\b", re.I)
_PASAL = re.compile(r"^(?:PASAL|ARTICLE|CLAUSE|SECTION|SEC\.)\s+\d+(?:\.\d+)*[A-Za-z]?\b", re.I)
_NUM = re.compile(r"^(\d{1,2}(?:\.\d{1,2}){0,3})\.?\s+[A-ZÀ-Ý]")


@dataclass
class Heading:
    text: str
    page: int
    level: int
    size: float
    bold: bool


@dataclass
class Section:
    heading: Heading | None
    text: str
    page_start: int
    page_end: int


@dataclass
class CrossCheck:
    matched: list
    unmatched_llm: list
    unmatched_detected: list


def _clean(text: str) -> str:
    text = "".join(c for c in text if unicodedata.category(c) not in ("Co", "Cn", "Cs", "Cc") or c in "	")
    text = text.replace("�", "")
    text = re.sub(r"[\s.…_\-]{3,}\d*$", "", text)
    return text.strip()


def _lines(page) -> list[tuple[str, float, bool]]:
    out = []
    for block in page.get_text("dict").get("blocks", []):
        for line in block.get("lines", []):
            spans = [s for s in line.get("spans", []) if s.get("text", "").strip()]
            if not spans:
                continue
            text = _clean("".join(s["text"] for s in spans))
            if not text:
                continue
            weights = [len(s["text"].strip()) for s in spans]
            size = max(s["size"] for s in spans)
            bold_chars = sum(w for s, w in zip(spans, weights) if (s["flags"] & 16) or "bold" in s["font"].lower())
            out.append((text, round(size, 1), bold_chars >= 0.6 * sum(weights)))
    return out


def _all_caps(text: str) -> bool:
    letters = [c for c in text if c.isalpha()]
    return len(letters) >= 4 and all(c.isupper() for c in letters)


def _pattern_level(text: str) -> int | None:
    if _BAB.match(text):
        return 1
    if _PASAL.match(text):
        m = re.search(r"\d+((?:\.\d+)*)", text)
        return 2 + (m.group(1).count(".") if m else 0)
    m = _NUM.match(text)
    if m:
        return 1 + m.group(1).count(".")
    return None


def detect_headings(path) -> list[Heading]:
    import pymupdf as fitz

    with fitz.open(str(path)) as doc:
        per_page = [_lines(p) for p in doc]
    sizes: Counter = Counter()
    for lines in per_page:
        for text, size, _b in lines:
            sizes[size] += len(text)
    if not sizes:
        return []
    body = sizes.most_common(1)[0][0]
    raw: list[Heading] = []
    for pno, lines in enumerate(per_page, start=1):
        for text, size, bold in lines:
            if not MIN_LEN <= len(text) <= MAX_LEN or text.endswith((",", ";")):
                continue
            if re.fullmatch(r"[\d\W]+", text):
                continue
            lvl = _pattern_level(text)
            larger = size >= body * 1.12
            ok = False
            if lvl is not None and (bold or larger or _all_caps(text) or _BAB.match(text) or _PASAL.match(text)) and len(text) <= 90:
                ok = True
            elif larger and len(text) <= 90 and not text.endswith("."):
                ok = True
            elif bold and _all_caps(text) and len(text) <= 60:
                ok = True
            elif _all_caps(text) and len(text) <= 50 and len(text.split()) >= 2 and size >= body:
                ok = True
            if ok:
                raw.append(Heading(text, pno, lvl or 0, size, bold))
    n_pages = len(per_page)
    if n_pages >= 4:
        freq = Counter(h.text.lower() for h in raw)
        raw = [h for h in raw if freq[h.text.lower()] <= max(2, n_pages // 4)]
    sized = sorted({h.size for h in raw if h.level == 0}, reverse=True)
    for h in raw:
        if h.level == 0:
            h.level = 1 + sized.index(h.size)
    return raw


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def _page_str(p) -> str:
    return p if isinstance(p, str) else p.text


def slice_by_headings(page_texts, headings: list[Heading]) -> list[Section]:
    pages = [_page_str(p) for p in page_texts]
    offsets, full, pos = [], [], 0
    for t in pages:
        offsets.append(pos)
        full.append(t)
        pos += len(t) + 1
    doc = "\n".join(full)
    low = doc.lower()
    found: list[tuple[int, Heading]] = []
    cursor = 0
    for h in sorted(headings, key=lambda x: x.page):
        start_from = max(cursor, offsets[h.page - 1] if 0 < h.page <= len(offsets) else 0)
        idx = low.find(h.text.lower(), start_from)
        if idx < 0:
            pat = r"\s+".join(re.escape(w) for w in h.text.split())
            m = re.compile(pat, re.I).search(doc, start_from)
            idx = m.start() if m else -1
        if idx >= 0:
            found.append((idx, h))
            cursor = idx + len(h.text)

    def page_of(i: int) -> int:
        p = 1
        for k, o in enumerate(offsets):
            if o <= i:
                p = k + 1
        return p

    sections: list[Section] = []
    if found and doc[:found[0][0]].strip():
        sections.append(Section(None, doc[:found[0][0]].strip(), 1, page_of(found[0][0])))
    for k, (idx, h) in enumerate(found):
        end = found[k + 1][0] if k + 1 < len(found) else len(doc)
        sections.append(Section(h, doc[idx:end].strip(), page_of(idx), page_of(max(idx, end - 1))))
    if not found and doc.strip():
        sections.append(Section(None, doc.strip(), 1, max(1, len(pages))))
    return sections


def cross_check(llm_headings: list[str], detected: list[Heading], threshold: float = FUZZY_THRESHOLD) -> CrossCheck:
    remaining = list(detected)
    matched, unmatched_llm = [], []
    for title in llm_headings:
        nt = _norm(title)
        best, best_score = None, 0.0
        for h in remaining:
            nh = _norm(h.text)
            if not nt or not nh:
                continue
            score = 1.0 if nt == nh else SequenceMatcher(None, nt, nh).ratio()
            short, long_ = sorted((nt, nh), key=len)
            if len(short) >= 6 and short in long_:
                score = max(score, 0.9)
            if score > best_score:
                best, best_score = h, score
        if best is not None and best_score >= threshold:
            matched.append((title, best, round(best_score, 3)))
            remaining.remove(best)
        else:
            unmatched_llm.append(title)
    return CrossCheck(matched, unmatched_llm, remaining)
