"""Security layer: labels, registry, PEP, nonces, audit chain, output guard, kill switch.

The language model never touches these modules' decisions. See SECURITY.md.
"""
from .labels import ALLOWED_T2_LABELS, TypedValue, ValueRegistry, combine, is_handle  # noqa: F401
from .pep import Decision, PepSession, ToolCall, pep_check  # noqa: F401
from .registry import REGISTRY, ToolSpec  # noqa: F401
