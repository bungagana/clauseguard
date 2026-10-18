// Types shared by the claim form card and the recorded (replayed) scenes.

export interface ChecklistItem {
  code: string;
  label: string;
  attached: boolean;
  // attached: an uploaded file proves it; declared: the customer says they have it; missing: neither
  state?: "attached" | "declared" | "missing";
}

export interface FormField {
  label: string;
  source: string;
  value: unknown;
  state: "filled" | "not_provided" | "to_complete";
}

export interface FormSection {
  title: string;
  fields: FormField[];
}

/** The claim draft the engine prepared, as stored with the pending submission. */
export interface ClaimDraft {
  policy_id?: string;
  event?: string;
  amount?: string | number | null;
  claim_amount?: string | number | null;
  currency?: string | null;
  admission?: string | null;
  discharge?: string | null;
  diagnosis?: string | null;
  required_documents?: string[];
  document_handles?: string[];
  missing_documents?: string[];
  facts?: { values?: Record<string, unknown> };
  form_title?: string;
  form_layout_source?: "policy_clauses" | "standard";
  form_sections?: FormSection[];
}

/** Where a recorded scene came from; shown to the viewer so a replay is never mistaken for a live run. */
export interface RecordedMeta {
  recordedAt: string; // ISO timestamp of the real run
  claimId: string;
  auditSeqFrom: number;
  auditSeqTo: number;
  backend: string; // e.g. "sandbox insurer API, Gemini 3.5 Flash-Lite"
}
