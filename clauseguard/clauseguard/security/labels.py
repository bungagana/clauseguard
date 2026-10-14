"""Provenance labels and the Value Registry.

Security guarantee: every non-user value that enters the agent (document extracts, tool
results, LLM text) is stored here under an opaque handle ("$v12") together with its
provenance label (a `SourceTier`). The planner only ever sees handles and types; the
Policy Enforcement Point resolves handles and checks labels before any T2/T3 tool runs.
A derived value takes the *least trusted* label of its inputs (`combine`). A user click in
the UI can upgrade one value for one specific call (`confirmed_for`), never globally.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

from ..schema import TIER_RANK, SourceTier

HANDLE_RE = re.compile(r"^\$v\d+$")

# Labels a T2 tool may consume without an explicit per-call confirmation (R2).
# TOOL is allowed because registry values labelled TOOL were produced by T0/T1 tools
# of *this* session over the authenticated user's own records.
ALLOWED_T2_LABELS = frozenset(
    {SourceTier.USER, SourceTier.USER_CONFIRMED, SourceTier.POLICY_DOC_VERIFIED, SourceTier.TOOL, SourceTier.SYSTEM}
)
# Labels that may never feed a bank-account / beneficiary / payment-destination field (R3).
UNTRUSTED_FOR_SENSITIVE = frozenset({SourceTier.LLM, SourceTier.USER_UPLOAD, SourceTier.TOOL, SourceTier.POLICY_DOC_UNVERIFIED})


def combine(labels: Iterable[SourceTier]) -> SourceTier:
    """Least-trusted label wins. Empty input -> SYSTEM is *not* assumed; we return LLM (weakest)."""
    labels = list(labels)
    if not labels:
        return SourceTier.LLM
    return min(labels, key=lambda t: TIER_RANK[t])


def is_handle(x: Any) -> bool:
    return isinstance(x, str) and bool(HANDLE_RE.match(x))


@dataclass
class TypedValue:
    value: Any
    type: str  # e.g. "ClaimDraft", "Decimal", "date", "DocRef", "AccountForm"
    label: SourceTier
    source_id: Optional[str] = None  # tool name, doc id, "user:<session>" ...
    confirmed_for: set[str] = field(default_factory=set)  # call keys this value was confirmed for
    handle: Optional[str] = None

    def user_confirmed_for(self, call_key: str) -> bool:
        return call_key in self.confirmed_for

    def safe_render(self) -> dict:
        """What the planner is allowed to see: handle, type, label. Never the raw string."""
        return {"handle": self.handle, "type": self.type, "label": self.label.value}


class ValueRegistry:
    """Session-scoped handle -> TypedValue map. Literals never resolve (returns None)."""

    def __init__(self) -> None:
        self._values: dict[str, TypedValue] = {}
        self._n = 0

    def put(self, value: Any, type: str, label: SourceTier, source_id: Optional[str] = None) -> str:
        self._n += 1
        h = f"$v{self._n}"
        self._values[h] = TypedValue(value=value, type=type, label=label, source_id=source_id, handle=h)
        return h

    def resolve(self, handle: Any) -> Optional[TypedValue]:
        if not is_handle(handle):
            return None
        return self._values.get(handle)

    def confirm(self, handle: str, call_key: str) -> bool:
        """Upgrade one value for one call (UI click). Returns False if handle unknown."""
        tv = self.resolve(handle)
        if tv is None:
            return False
        tv.confirmed_for.add(call_key)
        return True

    def derive(self, value: Any, type: str, inputs: Iterable[str], source_id: Optional[str] = None) -> str:
        """Store a value derived from other handles; label = min over inputs."""
        labels = [tv.label for tv in (self.resolve(h) for h in inputs) if tv is not None]
        return self.put(value, type, combine(labels) if labels else SourceTier.LLM, source_id)

    def handles(self) -> list[str]:
        return list(self._values)

    def __len__(self) -> int:
        return len(self._values)
