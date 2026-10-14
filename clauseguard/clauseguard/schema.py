"""Typed clause store schema — the contract every module builds on.

A policy document is compiled into ClauseTuples: (head, relation, object, qualifiers)
with clause-level evidence. Qualifiers are *typed data*, never free text. Free text
exists only in `Evidence.text` for display/citation and never reaches a decision.

Security note: every tuple carries `source_tier`. Action-tier tools (T2/T3) may only
rely on tuples at POLICY_DOC_VERIFIED or user-confirmed tiers; see security/pep.py.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Optional, Union

from pydantic import BaseModel, ConfigDict, Field


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --------------------------------------------------------------------------- enums
class EventCode(str, Enum):
    """Canonical, language-neutral event/peril vocabulary (closed)."""

    DEATH = "DEATH"
    ACCIDENTAL_DEATH = "ACCIDENTAL_DEATH"
    SUICIDE = "SUICIDE"
    HOSPITALIZATION = "HOSPITALIZATION"
    ICU = "ICU"
    SURGERY = "SURGERY"
    OUTPATIENT = "OUTPATIENT"
    ACCIDENT_MEDICAL = "ACCIDENT_MEDICAL"
    CRITICAL_ILLNESS = "CRITICAL_ILLNESS"
    TERMINAL_ILLNESS = "TERMINAL_ILLNESS"
    CHRONIC_ILLNESS = "CHRONIC_ILLNESS"
    TPD = "TPD"  # total permanent disability
    TEMPORARY_DISABILITY = "TEMPORARY_DISABILITY"
    DENTAL = "DENTAL"
    PREGNANCY = "PREGNANCY"
    PRE_EXISTING_CONDITION = "PRE_EXISTING_CONDITION"
    SPECIFIED_DISEASE = "SPECIFIED_DISEASE"
    WAR = "WAR"
    AVIATION = "AVIATION"
    INTOXICATION = "INTOXICATION"
    HAZARDOUS_ACTIVITY = "HAZARDOUS_ACTIVITY"
    CRIMINAL_ACT = "CRIMINAL_ACT"
    NO_VALID_LICENSE = "NO_VALID_LICENSE"
    COMMERCIAL_MOTORCYCLING = "COMMERCIAL_MOTORCYCLING"
    COSMETIC = "COSMETIC"
    CONGENITAL = "CONGENITAL"
    MISREPRESENTATION = "MISREPRESENTATION"
    POLICY_LOAN = "POLICY_LOAN"
    SURRENDER = "SURRENDER"
    PARTIAL_WITHDRAWAL = "PARTIAL_WITHDRAWAL"
    CONVERSION = "CONVERSION"
    REINSTATEMENT = "REINSTATEMENT"
    PREMIUM_WAIVER = "PREMIUM_WAIVER"
    LAPSE = "LAPSE"
    GROUP_TERMINATION = "GROUP_TERMINATION"
    RETURN_OF_PREMIUM = "RETURN_OF_PREMIUM"
    FREE_LOOK = "FREE_LOOK"
    OTHER = "OTHER"


class Relation(str, Enum):
    COVERS = "COVERS"  # Policy|Rider -> Event
    EXCLUDES = "EXCLUDES"  # Policy|Rider -> Event|Cause
    EXCEPTS = "EXCEPTS"  # Clause -> Clause (exception to an exclusion)
    CONDITIONED_ON = "CONDITIONED_ON"  # Clause -> Condition(s) that must hold
    HAS_PERIOD = "HAS_PERIOD"  # Policy -> Period (grace, waiting, suicide, ...)
    PAYS = "PAYS"  # Clause -> Benefit formula/amount
    PERMITS = "PERMITS"  # Policy -> Action (loan, conversion, surrender)
    TERMINATES_IF = "TERMINATES_IF"  # Policy -> Event|Condition
    REQUIRES_DOCUMENT = "REQUIRES_DOCUMENT"  # Event -> Document
    DEFINES = "DEFINES"  # Policy -> Term
    REFERS_TO = "REFERS_TO"  # Clause -> Clause
    HAS_RIDER = "HAS_RIDER"  # Policy -> Rider
    UNMODELED_RULE = "UNMODELED_RULE"  # open relation: verbatim rule the closed relations cannot express; never decides a verdict


class PeriodKind(str, Enum):
    GRACE = "GRACE"
    WAITING = "WAITING"
    WAITING_SPECIFIED = "WAITING_SPECIFIED"
    CONTESTABILITY = "CONTESTABILITY"
    FREE_LOOK = "FREE_LOOK"
    SUICIDE = "SUICIDE"
    SURVIVAL = "SURVIVAL"
    ELIMINATION = "ELIMINATION"
    FILING_DEADLINE = "FILING_DEADLINE"
    NOTICE_DEADLINE = "NOTICE_DEADLINE"
    SURRENDER_CHARGE = "SURRENDER_CHARGE"


class WindowFrom(str, Enum):
    ISSUE = "ISSUE"
    EFFECTIVE = "EFFECTIVE"
    REINSTATEMENT = "REINSTATEMENT"
    RIDER_START = "RIDER_START"
    DIAGNOSIS = "DIAGNOSIS"
    EVENT = "EVENT"
    DISCHARGE = "DISCHARGE"
    TREATMENT_END = "TREATMENT_END"
    DEATH = "DEATH"
    ACCIDENT = "ACCIDENT"
    PREMIUM_DUE = "PREMIUM_DUE"


class TimeUnit(str, Enum):
    DAYS = "DAYS"
    MONTHS = "MONTHS"
    YEARS = "YEARS"


class SourceTier(str, Enum):
    """Trust is a qualifier. Higher is more trusted."""

    LLM = "LLM"
    USER_UPLOAD = "USER_UPLOAD"  # documents uploaded in-session (claims, unknown policies)
    TOOL = "TOOL"
    POLICY_DOC_UNVERIFIED = "POLICY_DOC_UNVERIFIED"
    POLICY_DOC_VERIFIED = "POLICY_DOC_VERIFIED"  # reviewed once by a human, fixed set
    USER = "USER"  # typed by the authenticated user this session
    USER_CONFIRMED = "USER_CONFIRMED"
    SYSTEM = "SYSTEM"


TIER_RANK = {t: i for i, t in enumerate(SourceTier)}


class Basis(str, Enum):
    INDEMNITY = "INDEMNITY"  # reimburses actual expense; does not stack
    FIXED_BENEFIT = "FIXED_BENEFIT"  # pays a fixed amount; stacks across policies


class Verdict(str, Enum):
    COVERED = "COVERED"
    DENIED = "DENIED"
    NOT_APPLICABLE = "NOT_APPLICABLE"  # no clause governs the scenario
    NOT_SPECIFIED = "NOT_SPECIFIED"  # document is a summary / extraction incomplete
    CLARIFY = "CLARIFY"  # an unbound slot would change the verdict


class Op(str, Enum):
    EQ = "EQ"
    NE = "NE"
    LT = "LT"
    LE = "LE"
    GT = "GT"
    GE = "GE"
    IN = "IN"
    NOT_IN = "NOT_IN"
    IS_TRUE = "IS_TRUE"
    IS_FALSE = "IS_FALSE"


class Slot(str, Enum):
    """Scenario fact slots the solver can reference. Keep closed; extend deliberately."""

    EVENT = "event"
    CAUSE = "cause"  # EventCode-like cause: ACCIDENT, ILLNESS, SUICIDE, WAR, ...
    IS_ACCIDENT = "is_accident"
    IS_EMERGENCY = "is_emergency"
    DAYS_SINCE_EFFECTIVE = "days_since_effective"
    MONTHS_SINCE_ISSUE = "months_since_issue"
    MONTHS_SINCE_REINSTATEMENT = "months_since_reinstatement"
    DAYS_SINCE_DIAGNOSIS = "days_since_diagnosis"
    DIAGNOSIS_ICD10 = "diagnosis_icd10"  # document-sourced only; see agent/loop.py upload handling
    DAYS_SINCE_EVENT = "days_since_event"
    DAYS_SINCE_DISCHARGE = "days_since_discharge"
    DAYS_SINCE_TREATMENT_END = "days_since_treatment_end"
    DAYS_SINCE_DEATH = "days_since_death"
    PREMIUM_STATUS = "premium_status"  # PAID | OVERDUE | LAPSED
    DAYS_OVERDUE = "days_overdue"
    IN_FORCE = "in_force"
    AGE = "age"
    AGE_AT_ISSUE = "age_at_issue"
    RIDER_ATTACHED = "rider_attached"
    PLAN = "plan"
    DIAGNOSIS_BEFORE_EFFECTIVE = "diagnosis_before_effective"
    DISEASE_IN_SPECIFIED_LIST = "disease_in_specified_list"
    SURVIVAL_DAYS = "survival_days"
    DOCUMENTS_PRESENT = "documents_present"
    EMPLOYMENT_ACTIVE = "employment_active"
    FACILITY_IN_NETWORK = "facility_in_network"
    FACILITY_BPJS_PARTNER = "facility_bpjs_partner"
    WORK_RELATED = "work_related"
    VEHICLES_INVOLVED = "vehicles_involved"
    LICENSE_VALID = "license_valid"
    OCCUPATION_CLASS = "occupation_class"
    INTOXICATED = "intoxicated"
    PILOT_ROLE = "pilot_role"  # PASSENGER | CREW | PRIVATE_PILOT
    MILITARY_SERVICE = "military_service"
    POLICY_YEAR = "policy_year"
    DAYS_HOSPITALIZED = "days_hospitalized"
    DAYS_ICU = "days_icu"
    BILLED_AMOUNT = "billed_amount"
    MISREPRESENTATION = "misrepresentation"
    LOAN_BALANCE = "loan_balance"
    CASH_VALUE = "cash_value"
    PARTIES_BOTH_DEAD = "parties_both_dead"


# --------------------------------------------------------------------------- building blocks
Scalar = Union[str, int, float, bool, None]


class Condition(Strict):
    slot: Slot
    op: Op
    value: Union[Scalar, list[Scalar]] = None
    note: Optional[str] = Field(default=None, max_length=120, description="display only")


class Evidence(Strict):
    doc_id: str
    section: Optional[str] = Field(default=None, max_length=80)
    page: Optional[int] = None
    char_start: Optional[int] = None
    char_end: Optional[int] = None
    text: str = Field(max_length=1200, description="verbatim clause text; display/citation only")


class Qualifiers(Strict):
    """All optional, all typed. Monetary values are Decimal; time windows are explicit."""

    # money / limits
    amount: Optional[Decimal] = None
    currency: Optional[str] = Field(default=None, pattern=r"^[A-Z]{3}$")
    pct_of_sum_assured: Optional[float] = None
    per_day_limit: Optional[Decimal] = None
    per_case_limit: Optional[Decimal] = None
    per_week_amount: Optional[Decimal] = None
    max_days: Optional[int] = None
    max_days_per_year: Optional[int] = None
    max_weeks: Optional[int] = None
    annual_cap: Optional[Decimal] = None
    lifetime_cap: Optional[Decimal] = None
    deductible_amount: Optional[Decimal] = None
    deductible_days: Optional[int] = None
    copay_pct: Optional[float] = None
    copay_amount: Optional[Decimal] = None  # flat co-payment per visit/admission (e.g. a US copay)
    copay_cap: Optional[Decimal] = None  # cap on the member's own cost sharing (e.g. a US annual out-of-pocket maximum)
    multiplier_of_daily: Optional[float] = None  # e.g. surgical = 5x daily benefit
    # time windows
    waiting_days: Optional[int] = None
    window_len: Optional[int] = None
    window_unit: Optional[TimeUnit] = None
    window_from: Optional[WindowFrom] = None
    resets_on_reinstatement: Optional[bool] = None
    deadline_days: Optional[int] = None
    from_event: Optional[WindowFrom] = None
    late_effect: Optional[str] = Field(default=None, pattern=r"^(REJECT|DISCRETIONARY|NONE)$")
    # conditions
    applies_if: list[Condition] = Field(default_factory=list)
    unless_clause_ids: list[str] = Field(default_factory=list)
    age_min: Optional[int] = None
    age_max: Optional[int] = None
    # classification
    basis: Optional[Basis] = None
    plan: Optional[str] = Field(default=None, max_length=40)
    benefit_type: Optional[str] = Field(default=None, pattern=r"^(FULL|RETURN_PREMIUMS|REDUCED|NONE|GRADED)$")
    period_kind: Optional[PeriodKind] = None
    diseases: list[str] = Field(default_factory=list)  # closed codes, e.g. HERNIA, CATARACT
    icd10_codes: list[str] = Field(default_factory=list)  # WHO ICD-10 codes/ranges a COVERS clause is limited to, e.g. "I21", "C00-C97"
    document_codes: list[str] = Field(default_factory=list)
    formula: Optional[str] = Field(default=None, max_length=200, description="display only")
    other_insurance: Optional[str] = Field(default=None, pattern=r"^(EXCESS|PRO_RATA|NONE|STACKABLE)$")
    proposed_label: Optional[str] = Field(default=None, max_length=80, description="UNMODELED_RULE only: free-text relation label proposed by the extractor")
    entity_types: list[str] = Field(default_factory=list, description="UNMODELED_RULE only: free-text entity types proposed by the extractor")


class ClauseTuple(Strict):
    id: str
    policy_id: str
    head: str = Field(description="policy_id or rider_id")
    relation: Relation
    object: str = Field(description="EventCode, PeriodKind, clause id, document code or term")
    qualifiers: Qualifiers = Field(default_factory=Qualifiers)
    evidence: Evidence
    confidence: float = Field(ge=0, le=1, default=1.0)
    source_tier: SourceTier = SourceTier.POLICY_DOC_UNVERIFIED
    extractor_version: str = "cg-extract-0.1"
    language: str = Field(default="en", pattern=r"^[a-z]{2}$")


class RiderRecord(Strict):
    id: str
    rider_type: str = Field(max_length=60)
    attached: bool = True
    sum_assured: Optional[Decimal] = None
    start_date: Optional[date] = None


class PolicyRecord(Strict):
    id: str
    doc_id: str
    insurer: str = Field(max_length=80)
    product_name: str = Field(max_length=120)
    product_type: str = Field(max_length=40)  # term_life, hospital_cash, pa, group_health, ...
    basis: Basis = Basis.INDEMNITY
    effective_date: Optional[date] = None
    issue_date: Optional[date] = None
    expiry_date: Optional[date] = None
    reinstatement_date: Optional[date] = None
    status: str = Field(default="active", pattern=r"^(active|grace|lapsed|cancelled|terminated)$")
    grace_days: Optional[int] = None
    sum_assured: Optional[Decimal] = None
    currency: str = "IDR"
    riders: list[RiderRecord] = Field(default_factory=list)
    tuples: list[ClauseTuple] = Field(default_factory=list)
    verified: bool = False
    extraction_coverage: float = Field(default=1.0, ge=0, le=1, description="share of sections with tuples")

    def tuples_by(self, relation: Relation) -> list[ClauseTuple]:
        return [t for t in self.tuples if t.relation == relation]

    def tuple_index(self) -> dict[str, ClauseTuple]:
        return {t.id: t for t in self.tuples}


class ScenarioFacts(Strict):
    """Bound slots for one scenario. Missing keys are *unbound* (not False, not None)."""

    values: dict[Slot, Scalar] = Field(default_factory=dict)
    as_of: Optional[date] = None

    def get(self, slot: Slot) -> Scalar:
        if slot not in self.values:
            raise MissingSlot(slot)
        return self.values[slot]

    def has(self, slot: Slot) -> bool:
        return slot in self.values

    def bind(self, slot: Slot, value: Scalar) -> "ScenarioFacts":
        v = dict(self.values)
        v[slot] = value
        return ScenarioFacts(values=v, as_of=self.as_of)


class MissingSlot(Exception):
    def __init__(self, slot: Slot):
        super().__init__(f"unbound slot: {slot.value}")
        self.slot = slot


class TraceStep(Strict):
    rule: str
    tuple_id: Optional[str] = None
    result: str
    detail: Optional[str] = Field(default=None, max_length=300)


class ClarificationRequest(Strict):
    slot: Slot
    verdict_by_value: dict[str, Verdict]
    why_tuple_id: Optional[str] = None


class VerdictResult(Strict):
    policy_id: str
    verdict: Verdict
    fired_tuple_ids: list[str] = Field(default_factory=list)
    payable: Optional[Decimal] = None
    currency: Optional[str] = None
    trace: list[TraceStep] = Field(default_factory=list)
    missing_slots: list[Slot] = Field(default_factory=list)
    clarification: Optional[ClarificationRequest] = None
    denial_code: Optional[str] = None
    min_source_tier: Optional[SourceTier] = None  # weakest tier among fired tuples
    uncertain: bool = False  # an UNMODELED_RULE plausibly applies; the verdict above is not confident
    unmodeled_clause_ids: list[str] = Field(default_factory=list)


# Default domains used for verdict-sensitivity when a slot is unbound.
SLOT_DOMAINS: dict[Slot, list[Scalar]] = {
    Slot.CAUSE: ["ILLNESS", "ACCIDENT", "SUICIDE", "WAR", "AVIATION", "INTOXICATION", "CRIMINAL_ACT"],
    Slot.IS_ACCIDENT: [True, False],
    Slot.IS_EMERGENCY: [True, False],
    Slot.DAYS_SINCE_EFFECTIVE: [0, 15, 29, 30, 31, 90, 365, 400],
    Slot.MONTHS_SINCE_ISSUE: [0, 6, 11, 12, 13, 23, 24, 25, 36],
    Slot.MONTHS_SINCE_REINSTATEMENT: [0, 6, 12, 23, 24, 25],
    Slot.DAYS_SINCE_DIAGNOSIS: [0, 10, 29, 30, 31, 90, 91, 200],
    Slot.DAYS_SINCE_EVENT: [0, 7, 29, 30, 31, 59, 60, 61, 89, 90, 91],
    Slot.DAYS_SINCE_DISCHARGE: [0, 29, 30, 31, 59, 60, 61, 89, 90, 91],
    Slot.DAYS_SINCE_TREATMENT_END: [0, 59, 60, 61],
    Slot.DAYS_SINCE_DEATH: [0, 59, 60, 61, 89, 90, 91],
    Slot.PREMIUM_STATUS: ["PAID", "OVERDUE", "LAPSED"],
    Slot.DAYS_OVERDUE: [0, 15, 29, 30, 31, 45, 61, 62],
    Slot.IN_FORCE: [True, False],
    Slot.AGE: [5, 17, 18, 25, 59, 60, 64, 65, 70, 84, 85, 86],
    Slot.RIDER_ATTACHED: [True, False],
    Slot.DIAGNOSIS_BEFORE_EFFECTIVE: [True, False],
    Slot.DISEASE_IN_SPECIFIED_LIST: [True, False],
    Slot.SURVIVAL_DAYS: [0, 13, 14, 15, 29, 30, 31],
    Slot.EMPLOYMENT_ACTIVE: [True, False],
    Slot.FACILITY_IN_NETWORK: [True, False],
    Slot.FACILITY_BPJS_PARTNER: [True, False],
    Slot.WORK_RELATED: [True, False],
    Slot.VEHICLES_INVOLVED: [1, 2],
    Slot.LICENSE_VALID: [True, False],
    Slot.INTOXICATED: [True, False],
    Slot.PILOT_ROLE: ["PASSENGER", "CREW", "PRIVATE_PILOT"],
    Slot.MILITARY_SERVICE: [True, False],
    Slot.POLICY_YEAR: [1, 2, 3, 5, 10, 15, 20],
    Slot.MISREPRESENTATION: [True, False],
    Slot.PARTIES_BOTH_DEAD: [True, False],
}
