"""Shared local-extraction + redaction pipeline for policy_extractor.py and claim_doc.py.

Policy: a PDF's text is extracted locally (`privacy.ocr.pdf_pages_text`: embedded text, or OCR
for an image-only page), redacted (`privacy.redact.redact`) and verified clean
(`privacy.redact.final_gate`) before any of it reaches the LLM. Raw PDF bytes are never sent to
the model for a text-bearing document; only the redacted text is.

A page whose local extraction is unreliable (OCR under-confident or near-empty) is flagged
DEGRADED and still goes through the same redact + gate path on whatever text it produced. It is
never sent to the LLM as an image or as raw bytes: a page local extraction could not read
reliably cannot be cleared as "no PII found" either, so there is no safe fallback to bytes for
that page, only a flag for reduced confidence.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Sequence

from ..privacy import ocr as _ocr
from ..privacy.redact import RedactionResult, final_gate, redact
from ..security import audit as _audit

log = logging.getLogger("clauseguard.extractor.redact_pipeline")

PAGE_SEP = "\f"


class PiiBlocked(RuntimeError):
    """Redacted text still failed final_gate; nothing was sent to the LLM."""


@dataclass
class RedactedDoc:
    text: str
    page_starts: list[tuple[int, int]] = field(default_factory=list)  # (offset in `text`, page number), ascending
    degraded_pages: list[int] = field(default_factory=list)
    mapping: dict = field(default_factory=dict)

    def page_at(self, offset: Optional[int]) -> Optional[int]:
        if offset is None:
            return None
        page: Optional[int] = None
        for off, n in self.page_starts:
            if offset >= off:
                page = n
            else:
                break
        return page


def _violation_types(violations: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for v in violations:
        typ = v.split("@")[0].split("#")[0]
        counts[typ] = counts.get(typ, 0) + 1
    return counts


def _audit_blocked(doc_id: Optional[str], session_id: Optional[str], user_id: Optional[str], violations: list[str]) -> None:
    try:
        _audit.append({
            "event_type": "PII_BLOCKED", "session_id": session_id, "user_id": user_id, "doc_id": doc_id,
            "decision": "BLOCKED", "reason": f"final_gate violations by type: {_violation_types(violations)}",
        })
    except Exception as e:  # noqa: BLE001 - a failed audit write must never turn a block into a send
        log.warning("PII_BLOCKED audit append failed: %s", str(e)[:200])


def _audit_degraded(doc_id: Optional[str], session_id: Optional[str], user_id: Optional[str], pages: list[int]) -> None:
    try:
        _audit.append({
            "event_type": "PII_REDACTION_DEGRADED", "session_id": session_id, "user_id": user_id, "doc_id": doc_id,
            "decision": "DEGRADED", "reason": f"{len(pages)} page(s) with low-confidence local text extraction: {pages}",
        })
    except Exception as e:  # noqa: BLE001
        log.warning("PII_REDACTION_DEGRADED audit append failed: %s", str(e)[:200])


def _redact_and_gate(full_text: str, known_names: Sequence[str], doc_id: Optional[str],
                      session_id: Optional[str], user_id: Optional[str]) -> RedactionResult:
    result = redact(full_text, known_names)
    violations = final_gate(result.text_clean, known_names)
    if violations:
        _audit_blocked(doc_id, session_id, user_id, violations)
        raise PiiBlocked(f"redacted text failed final_gate ({len(violations)} violation(s))")
    return result


def redact_pdf(path: str | Path, *, known_names: Sequence[str] = (), doc_id: Optional[str] = None,
               session_id: Optional[str] = None, user_id: Optional[str] = None) -> RedactedDoc:
    """Extract a PDF's text locally page by page, redact once over the whole document (so
    placeholder numbering stays consistent across pages) and verify it clean. Raises
    `PiiBlocked` instead of ever returning text that still fails the gate."""
    try:
        pages = _ocr.pdf_pages_text(path)
    except Exception as e:  # noqa: BLE001 - a PDF that opens for the caller but not for pymupdf's
        log.warning("local text extraction failed for %s: %s", doc_id, str(e)[:200])  # page loop never reaches the LLM with raw bytes either; it degrades to empty text
        pages = []

    bodies = [p.text or "" for p in pages]
    full_text = PAGE_SEP.join(bodies)
    degraded_pages = [p.page for p in pages if p.needs_retake]

    result = _redact_and_gate(full_text, known_names, doc_id, session_id, user_id)
    if degraded_pages:
        _audit_degraded(doc_id, session_id, user_id, degraded_pages)

    parts = result.text_clean.split(PAGE_SEP)
    page_starts: list[tuple[int, int]] = []
    if len(parts) == len(pages) and pages:
        pos = 0
        for i, part in enumerate(parts):
            page_starts.append((pos, pages[i].page))
            pos += len(part) + len(PAGE_SEP)
    elif pages:
        page_starts = [(0, pages[0].page)]

    return RedactedDoc(text=result.text_clean, page_starts=page_starts, degraded_pages=degraded_pages, mapping=result.mapping)


def redact_plain_text(text: str, *, known_names: Sequence[str] = (), doc_id: Optional[str] = None,
                       session_id: Optional[str] = None, user_id: Optional[str] = None) -> RedactedDoc:
    """Same redact + gate guarantee as `redact_pdf`, for an already-text document (.txt upload)."""
    result = _redact_and_gate(text, known_names, doc_id, session_id, user_id)
    return RedactedDoc(text=result.text_clean, page_starts=[(0, 1)], degraded_pages=[], mapping=result.mapping)


def name_tokens(mapping: dict, name: str) -> list[str]:
    """Placeholder token(s) in `mapping` whose original surface text is the given name, so a
    prompt can ask about a name match without ever sending the name itself."""
    if not name or not name.strip():
        return []
    target = " ".join(name.lower().split())
    return sorted(tok for tok, surface in mapping.items() if tok.startswith("[NAMA_") and " ".join(surface.lower().split()) == target)
