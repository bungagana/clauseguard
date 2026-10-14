"""Tool registry: the explicit allow-list of what the agent can call.

Security guarantee: a tool exists for the agent only if it is listed here with a tier and
a strict (extra='forbid') argument schema. Tier-3 contains exactly one tool,
`create_account_change_request`, which only opens a ticket. There is no tool anywhere in
this registry that approves/denies a claim, moves money, or updates an account; those
operations live in the sandbox back-office API under a different credential and are
therefore unreachable from the planner even if it is fully compromised.

Implementations (`fn`) are bound later by `clauseguard.sandbox.tools` so that the security
spec (tier, schema, sensitive fields) stays in one auditable file.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Type

from pydantic import BaseModel, ConfigDict, Field


class Args(BaseModel):
    """Base for all tool argument schemas. Unknown fields are rejected (R1)."""

    model_config = ConfigDict(extra="forbid")


# ------------------------------------------------------------------ T0 read own data
class GetMyPoliciesArgs(Args):
    pass


class GetPolicyClauseArgs(Args):
    policy_id: str = Field(max_length=40)
    tuple_id: str = Field(max_length=80)


class GetClaimStatusArgs(Args):
    claim_id: str = Field(max_length=40)


class GetPaymentStatusArgs(Args):
    policy_id: str = Field(max_length=40)


class GetDeadlineDigestArgs(Args):
    pass


# ------------------------------------------------------------------ T1 compute / draft
class CheckCoverageArgs(Args):
    scenario_facts: Any = Field(description="dict of slot->scalar or a $v handle to one")


class GapAnalysisArgs(Args):
    pass


class ClaimReadinessArgs(Args):
    policy_id: str = Field(max_length=40)
    claim_facts: Any


class CobPlanArgs(Args):
    claim_facts: Any


class DraftClaimArgs(Args):
    policy_id: str = Field(max_length=40)
    claim_facts: Any
    document_handles: list[str] = Field(default_factory=list, max_length=20)


class EstimatePayoutArgs(Args):
    policy_id: str = Field(max_length=40)
    claim_facts: Any


class ExtractDocumentArgs(Args):
    doc_handle: str = Field(max_length=40)


class ClaimPlanArgs(Args):
    claim_facts: Any


class DraftAppealArgs(Args):
    policy_id: str = Field(max_length=40)
    claim_id: Optional[str] = Field(default=None, max_length=40)


# ------------------------------------------------------------------ T2 submit (needs nonce)
class SubmitClaimArgs(Args):
    draft_handle: str = Field(max_length=40)
    confirm_token: Optional[str] = Field(default=None, max_length=128)


class AttachDocumentArgs(Args):
    claim_id: str = Field(max_length=40)
    doc_handle: str = Field(max_length=40)
    confirm_token: Optional[str] = Field(default=None, max_length=128)


class FileAppealArgs(Args):
    appeal_handle: str = Field(max_length=40, description="$v handle to an appeal produced by draft_appeal")
    confirm_token: Optional[str] = Field(default=None, max_length=128)


class ScheduleCallbackArgs(Args):
    slot: str = Field(max_length=40, description="$v handle to a datetime slot chosen by the user")
    confirm_token: Optional[str] = Field(default=None, max_length=128)


# ------------------------------------------------------------------ T3 ticket only
class CreateAccountChangeRequestArgs(Args):
    form_handle: str = Field(max_length=40, description="$v handle to a form the user typed (label USER)")


# Field names that may never be fed from DOC/LLM/TOOL-labelled values (R3), on any tool.
SENSITIVE_FIELDS: frozenset = frozenset(
    {"form_handle", "bank_account", "account_number", "beneficiary", "beneficiary_id", "payout_account", "payment_destination", "iban", "nik"}
)

NONCE_FIELD = "confirm_token"


@dataclass
class ToolSpec:
    name: str
    tier: int  # 0..3
    schema: Type[Args]
    fn: Optional[Callable[..., Any]] = None  # bound by sandbox.tools
    sensitive_fields: set[str] = field(default_factory=set)
    description: str = ""
    result_type: str = "ToolResult"

    def __post_init__(self) -> None:
        if self.tier not in (0, 1, 2, 3):
            raise ValueError("tier must be 0..3")
        if self.tier == 3 and self.name != "create_account_change_request":
            raise ValueError("the only T3 tool is create_account_change_request")


REGISTRY: dict[str, ToolSpec] = {}


def register(spec: ToolSpec) -> ToolSpec:
    if spec.name in REGISTRY:
        raise ValueError(f"duplicate tool {spec.name}")
    REGISTRY[spec.name] = spec
    return spec


def bind(name: str, fn: Callable[..., Any]) -> None:
    """Attach an implementation. The spec (tier/schema) cannot be changed from here."""
    REGISTRY[name].fn = fn


# ------------------------------------------------------------------ the allow-list
register(ToolSpec("get_my_policies", 0, GetMyPoliciesArgs, description="List the authenticated user's policies", result_type="PolicyList"))
register(ToolSpec("get_policy_clause", 0, GetPolicyClauseArgs, description="One clause tuple (evidence text is display-only)", result_type="ClauseTuple"))
register(ToolSpec("get_claim_status", 0, GetClaimStatusArgs, description="Status of one of the user's claims", result_type="ClaimStatus"))
register(ToolSpec("get_payment_status", 0, GetPaymentStatusArgs, description="Premium payment status of one of the user's policies", result_type="PaymentStatus"))
register(ToolSpec("get_deadline_digest", 0, GetDeadlineDigestArgs, description="Upcoming deadlines and money at risk on the user's own policies and open claims", result_type="DeadlineDigest"))

register(ToolSpec("check_coverage", 1, CheckCoverageArgs, description="Deterministic verdict over the user's policies", result_type="VerdictList"))
register(ToolSpec("gap_analysis", 1, GapAnalysisArgs, description="Coverage gap/overlap matrix", result_type="GapReport"))
register(ToolSpec("claim_readiness", 1, ClaimReadinessArgs, description="Deadline + required/missing documents", result_type="ReadinessReport"))
register(ToolSpec("cob_plan", 1, CobPlanArgs, description="Ordered payer plan (coordination of benefits)", result_type="PayerPlan"))
register(ToolSpec("draft_claim", 1, DraftClaimArgs, description="Build a claim draft (no side effect)", result_type="ClaimDraft"))
register(ToolSpec("estimate_payout", 1, EstimatePayoutArgs, description="Payable amount from the solver", result_type="PayoutEstimate"))
register(ToolSpec("extract_document", 1, ExtractDocumentArgs, description="Quarantined extraction of an uploaded document", result_type="ClaimDocExtract"))
register(ToolSpec("claim_plan", 1, ClaimPlanArgs, description="Multi-payer claim plan: claiming order, amount, documents and deadline per payer", result_type="ClaimPlan"))
register(ToolSpec("draft_appeal", 1, DraftAppealArgs, description="Appeal analysis and letter draft for a rejected claim (no side effect)", result_type="AppealDraft"))

register(ToolSpec("submit_claim", 2, SubmitClaimArgs, description="Submit a draft claim (creates a record; no money moves)", result_type="ClaimId"))
register(ToolSpec("attach_document", 2, AttachDocumentArgs, description="Attach an uploaded document to a claim", result_type="DocumentId"))
register(ToolSpec("file_appeal", 2, FileAppealArgs, description="File a drafted appeal with the insurer (creates a record; no money moves)", result_type="AppealId"))
register(ToolSpec("schedule_callback", 2, ScheduleCallbackArgs, description="Book a callback with a human agent", result_type="TicketId"))

register(
    ToolSpec(
        "create_account_change_request",
        3,
        CreateAccountChangeRequestArgs,
        sensitive_fields={"form_handle"},
        description="Open a ticket for an out-of-band account/beneficiary change. Never changes anything itself.",
        result_type="TicketId",
    )
)

T3_TOOLS = frozenset(n for n, s in REGISTRY.items() if s.tier == 3)
assert T3_TOOLS == {"create_account_change_request"}
FORBIDDEN_TOOL_NAMES = frozenset({"approve_claim", "deny_claim", "update_account", "update_beneficiary", "transfer", "pay_claim", "cancel_policy"})
assert not (FORBIDDEN_TOOL_NAMES & set(REGISTRY)), "money/identity tools must not exist in the registry"


def ensure_bound() -> None:
    """Import the sandbox implementations if nothing is bound yet."""
    if any(s.fn is None for s in REGISTRY.values()):
        from ..sandbox import tools as _tools  # noqa: F401  (binds on import)


def listing() -> list[dict[str, Any]]:
    """Generated registry table for SECURITY.md / UI."""
    return [
        {"name": s.name, "tier": s.tier, "schema": s.schema.__name__, "sensitive_fields": sorted(s.sensitive_fields), "description": s.description}
        for s in sorted(REGISTRY.values(), key=lambda s: (s.tier, s.name))
    ]
