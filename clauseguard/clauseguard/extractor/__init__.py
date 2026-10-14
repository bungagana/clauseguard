"""Quarantined extractors: policy documents -> ClauseTuples; claim documents -> ClaimDocExtract.

Every extractor here is single-shot (no conversation history, no tools), schema-constrained
and treats document content strictly as DATA. Nothing free-text that comes out of a document
reaches the planner; see ARCHITECTURE.md, design rule 2.
"""
from . import hidden_text  # noqa: F401

__all__ = ["hidden_text", "policy_extractor", "claim_doc"]
