"""Local, deterministic privacy layer: redaction, OCR and layout analysis."""
from .redact import RedactionResult, Finding, redact, restore, final_gate

__all__ = ["RedactionResult", "Finding", "redact", "restore", "final_gate"]
