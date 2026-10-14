// Types mirror the real JSON shapes returned by the ClauseGuard sandbox API
// (clauseguard/sandbox/api.py, clauseguard/agent/loop.py::Reply,
// clauseguard/schema.py). Decimal amounts come back as strings; dates as
// ISO "YYYY-MM-DD" strings.

export type Verdict = "COVERED" | "DENIED" | "NOT_APPLICABLE" | "NOT_SPECIFIED" | "CLARIFY";

export interface TraceStep {
  rule: string;
  tuple_id: string | null;
  result: string;
  detail: string | null;
}

export interface ClarificationRequest {
  slot: string;
  verdict_by_value: Record<string, Verdict>;
  why_tuple_id: string | null;
}

export interface VerdictResult {
  policy_id: string;
  verdict: Verdict;
  fired_tuple_ids: string[];
  payable: string | null;
  currency: string | null;
  trace: TraceStep[];
  missing_slots: string[];
  clarification: ClarificationRequest | null;
  denial_code: string | null;
  min_source_tier: string | null;
}

export interface PayerStep {
  order: number;
  payer_policy_id: string;
  expected_amount: string | null;
  basis: "INDEMNITY" | "FIXED_BENEFIT";
  documents: string[];
  deadline: string | null;
  tuple_ids: string[];
  uncertain_slots: string[];
  status: "PAYER" | "PARALLEL" | "UNCERTAIN" | "NOT_CLAIMABLE";
  denial_code: string | null;
  note: string | null;
  currency: string | null;
  jurisdiction_rule: string | null;
}

export interface ReadinessReport {
  verdict: VerdictResult;
  deadline: string | null;
  days_left: number | null;
  late_effect: "REJECT" | "DISCRETIONARY" | null;
  required_documents: string[];
  missing_documents: string[];
  denial_codes: string[];
  deadline_tuple_id: string | null;
  event_date: string | null;
}

export interface PendingAction {
  tool: string;
  tier: number;
  args?: Record<string, unknown>;
  requires_confirmation?: boolean;
  pep_reason?: string;
  summary?: string;
  draft_id?: string;
  draft_label?: string;
  channel?: string;
  status?: string;
  ticket?: string;
}

export interface Recommendation {
  plan_id: string;
  product_name: string;
  closes_gap_perils: string[];
  monthly_premium_idr: number | null;
  rationale: string;
  caveats: string[];
  mock?: boolean;
  currency?: string;
  catalogue?: string;
  cost_basis?: string;
}

export interface ToolCallLog {
  name: string;
  tier: number;
  allowed: boolean;
  reason: string;
  args?: Record<string, unknown>;
}

// clauseguard/agent/loop.py::Reply, as returned by POST /chat and /chat/confirm
export interface ChatReply {
  text: string;
  intent?: string;
  verdicts: VerdictResult[];
  clarification: ClarificationRequest | null;
  actions_pending: PendingAction[];
  escalation_ticket: string | null;
  audit_ids: string[];
  refused: boolean;
  refusal_reason: string | null;
  tool_calls: ToolCallLog[];
  denial_codes: Record<string, string>;
  readiness: ReadinessReport | null;
  cob: PayerStep[];
  gap: Record<string, unknown> | null;
  deadline: string | null;
  payable: string | null;
  facts: Record<string, unknown>;
  alerts: string[];
  changed: string[];
  recommendations: Recommendation[];
  violations: string[];
  // true when `text` was worded by the reply composer (verified against the solver output);
  // `template_text` then holds the deterministic transcript the cards parse
  composed: boolean;
  template_text: string;
  context_relation?: string | null;
  hypothetical?: boolean;
  language?: "en" | "id";
  // the submission was held back for missing documents; the customer chooses to attach them or submit anyway
  submit_offer?: boolean;
  paused?: boolean;
  stub?: boolean;
}

export interface Persona {
  key: string;
  label: string;
  user_id: string;
  description: string;
}

export interface PolicyTuple {
  id: string;
  head?: string;
  relation: string;
  object: string;
  section: string | null;
  text: string;
  source_tier: string;
  language: string;
  summary: string;
  confidence?: number;
}

export interface PolicyPayStatus {
  status: "active" | "grace" | "lapsed";
  premium_status: string | null;
  days_overdue: number;
  due_date: string | null;
  grace_end: string | null;
}

export interface PolicyView {
  id: string;
  record_id: string;
  product_name: string;
  insurer: string;
  product_type: string;
  basis: "INDEMNITY" | "FIXED_BENEFIT";
  effective_date: string;
  expiry_date: string;
  grace_days: number | null;
  sum_assured: string | null;
  currency: string;
  insured: string[];
  source_badges: string[];
  extraction_coverage: number;
  pay: PolicyPayStatus;
  tuples: PolicyTuple[];
}

export interface ClaimRow {
  id: string;
  policy_id: string;
  customer_id: string;
  event_type: string;
  status: string;
  deadline_date: string | null;
}

export interface PoliciesResponse {
  user_id: string;
  persona: string;
  persons: Record<string, string>;
  policies: PolicyView[];
  claims: ClaimRow[];
}

export interface TimelineEvent {
  date: string;
  policy_id: string;
  kind: string;
  money_at_risk: string | null;
  days_left: number;
  clause_id: string | null;
  claim_id: string | null;
  message: string;
}

export interface TimelineResponse {
  events: TimelineEvent[];
  available: boolean;
  reason?: string;
}

export interface AllocationStep {
  order: number;
  policy_id: string;
  payer_type: string;
  basis: "INDEMNITY" | "FIXED_BENEFIT" | null;
  amount: string | null;
  currency: string | null;
  presented: Record<string, string>;
  documents_required: string[];
  filing_deadline: string | null;
  clause_ids: string[];
  rule_id: string | null;
  note: string | null;
}

export interface AllocationUncertain {
  policy_id: string;
  basis: string | null;
  slots: string[];
  potential_amount: string | null;
  clause_ids: string[];
  documents_required: string[];
  filing_deadline: string | null;
  rule_id: string | null;
  note: string | null;
}

export interface AllocationExcluded {
  policy_id: string;
  code: string | null;
  basis: string | null;
  clause_ids: string[];
  filing_deadline: string | null;
  rule_id: string | null;
  note: string | null;
}

export interface AllocationResponse {
  steps: AllocationStep[];
  total_recovered: string | null;
  indemnity_total: string | null;
  fixed_benefit_total: string | null;
  out_of_pocket: string | null;
  greedy_total: string | null;
  single_policy_total: string | null;
  uncertain: AllocationUncertain[];
  excluded: AllocationExcluded[];
  circular_excess: boolean;
  circular_clause_ids: string[];
  rule_pack: string | null;
  bill_total: string | null;
  currency: string | null;
  evaluation_order: string[];
  solver: string | null;
  notes: string[];
  available: boolean;
  reason?: string;
}

export interface RecourseActionCost {
  days: number;
  money: number;
  effort: number;
}

export interface RecourseAction {
  kind: string;
  description: string;
  cost: RecourseActionCost;
  earliest_date: string | null;
  deadline: string | null;
  documents: string[];
  other_policy_id: string | null;
}

export interface RecourseOption {
  policy_id: string;
  actions: RecourseAction[];
  verdict: Verdict;
  payable: string | null;
  currency: string | null;
  clause_ids: string[];
  cost: RecourseActionCost;
  description: string;
}

export interface Ground {
  code: string;
  clause_id: string | null;
  evidence_text: string;
  fixable: boolean;
  recourse: RecourseOption | null;
  weight: number;
  source: string;
}

export interface TwinResponse {
  policy_id: string;
  verdict: Verdict;
  denial_code: string | null;
  grounds: Ground[];
  open_slots: string[];
  checks: unknown[];
  readiness: ReadinessReport | null;
  documents_present: string[];
  readiness_score: number;
  after_fix_score: number;
  payable: string | null;
  currency: string | null;
  available: boolean;
  reason?: string;
}

export interface RecourseResponse {
  policy_id: string;
  baseline_verdict: Verdict;
  baseline_denial_code: string | null;
  options: RecourseOption[];
  blocked_by_immutable: string[];
  notes: string[];
  searched: number;
  available: boolean;
  reason?: string;
}

export interface PlansResponse {
  chosen: Array<{ plan_id: string; product_name?: string; monthly_cost?: string }>;
  perils_closed: string[];
  gaps_closed: string[];
  residual_gaps: string[];
  open_gaps: string[];
  monthly_cost: string;
  cost_basis: string;
  budget_monthly: string | null;
  objective: string;
  solver: string;
  alternatives: unknown[];
  excluded: Array<{ plan_id: string; reason: string }>;
  caveats: string[];
  available: boolean;
  currency: string;
  reason?: string;
}

export interface DemoAttack {
  key: string;
  kind: "chat" | "upload";
  title: string;
  description: string;
  text?: string;
  file?: string;
  available?: boolean;
  files?: string[];
}

export interface UploadResult {
  handle: string;
  label: string;
  doc_id: string;
}

// POST /policies/upload (clauseguard/sandbox/api.py::upload_policy) — the live, in-session
// extraction of the user's OWN policy document via clauseguard.extractor.policy_extractor.
export interface PolicyUploadExtractionStats {
  tuple_count: number;
  extraction_coverage: number;
  elapsed_seconds: number;
  model: string | null;
  calls: number | null;
  hidden_text_flagged: boolean;
}

export interface PolicyUploadResult {
  policy: PolicyView;
  extraction: PolicyUploadExtractionStats;
}

export interface LoginResult {
  session_token: string;
  session_id: string;
  user_id: string;
  persona: string;
}

// clauseguard/agent/digest.py::DigestAction / DigestItem, via GET /entitlement/digest
// (clauseguard/sandbox/api.py::entitlement_digest -> sandbox/entitlement.py::digest).
export interface DigestAction {
  type: "start_claim_plan" | "pay_premium_info" | "renew_info" | "none";
  label_en: string;
  label_id: string;
  prompt?: string | null;
}

export interface DigestItem {
  date: string;
  days_left: number;
  policy_id: string;
  product_name: string;
  kind: string;
  money_at_risk: string | null;
  currency: string;
  clause_id: string | null;
  claim_id: string | null;
  urgency: "overdue" | "this_week" | "soon" | "later";
  message_en: string;
  message_id: string;
  action: DigestAction;
}

export interface DigestResponse {
  items: DigestItem[];
  available: boolean;
  reason?: string;
}

export interface AuditEvent {
  seq: number;
  event_type: string;
  ts_utc: string;
  session_id?: string;
  user_id?: string;
  findings?: string[];
  [key: string]: unknown;
}

// ---------------------------------------------------------------- what-if (POST /entitlement/whatif)
export interface WhatIfControl {
  slot: string;
  kind: "bool" | "choice" | "int";
  label: string;
  options: Array<boolean | number>;
  current: boolean | number | null;
}

export interface WhatIfOutcome {
  policy_id: string;
  product_name: string;
  verdict: Verdict;
  payable: string | null;
  currency: string | null;
  denial_code: string | null;
  clarify_slot: string | null;
}

export interface WhatIfResponse {
  available: boolean;
  reason?: string;
  controls: WhatIfControl[];
  overrides: Record<string, boolean | number>;
  baseline: WhatIfOutcome[];
  result: WhatIfOutcome[];
  changed: string[];
}

// ---------------------------------------------------------------- session controls
export type AutonomyMode = "observe" | "draft" | "act";

export interface SessionState {
  autonomy: AutonomyMode;
  tier_cap: number;
  as_of: string;
  as_of_offset_days: number;
  kill_switch: boolean;
  denials: number;
}

export interface BackofficeTicket {
  id: string;
  customer_id: string;
  type: string;
  status: string;
  created_at: string;
  requested_via?: string | null;
  note?: string | null;
}

export interface BackofficeClaim {
  id: string;
  customer_id?: string;
  policy_id?: string;
  status?: string;
  event_type?: string;
  event_date?: string | null;
  claim_amount?: number | string | null;
  billed_amount?: number | string | null;
  filed_date?: string | null;
  deadline_date?: string | null;
  created_via?: string | null;
  rejection_code?: string | null;
  decided_at?: string | null;
  decision_note?: string | null;
  [key: string]: unknown;
}

export interface BackofficeClaimDetail extends BackofficeClaim {
  form: Record<string, unknown> | null;
  documents: Array<{ id: string; type: string; taint_label: string; uploaded_by?: string; uploaded_at?: string }>;
  customer_name?: string | null;
}
