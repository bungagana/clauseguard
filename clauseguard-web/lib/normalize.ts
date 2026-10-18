import type { ChatReply } from "./types";

/**
 * Backfills every array/object field of a Reply with its schema default.
 * Belt-and-braces for two real situations: (1) a fixture captured from an
 * older build of the backend before a field existed (`model_dump()` only
 * serializes fields the running process actually knows about), and (2) a
 * live backend on a slightly different version than this client was built
 * against. Without this, a missing field reads as `undefined` at runtime
 * even though the TypeScript type says otherwise (a plain `as ChatReply`
 * cast does not check that).
 */
export function normalizeChatReply(raw: Partial<ChatReply>): ChatReply {
  return {
    text: raw.text ?? "",
    intent: raw.intent,
    verdicts: raw.verdicts ?? [],
    clarification: raw.clarification ?? null,
    actions_pending: raw.actions_pending ?? [],
    escalation_ticket: raw.escalation_ticket ?? null,
    audit_ids: raw.audit_ids ?? [],
    refused: raw.refused ?? false,
    refusal_reason: raw.refusal_reason ?? null,
    tool_calls: raw.tool_calls ?? [],
    denial_codes: raw.denial_codes ?? {},
    readiness: raw.readiness ?? null,
    cob: raw.cob ?? [],
    gap: raw.gap ?? null,
    deadline: raw.deadline ?? null,
    payable: raw.payable ?? null,
    facts: raw.facts ?? {},
    alerts: raw.alerts ?? [],
    changed: raw.changed ?? [],
    recommendations: raw.recommendations ?? [],
    violations: raw.violations ?? [],
    composed: raw.composed ?? false,
    context_relation: raw.context_relation ?? null,
    hypothetical: raw.hypothetical ?? false,
    language: raw.language === "id" ? "id" : "en",
    submit_offer: raw.submit_offer ?? false,
    suggestions: Array.isArray(raw.suggestions) ? raw.suggestions : [],
    conflicts: Array.isArray(raw.conflicts) ? raw.conflicts : [],
    doc_reads: Array.isArray(raw.doc_reads) ? raw.doc_reads : [],
    ai_notice: raw.ai_notice ?? null,
    template_text: raw.template_text || raw.text || "",
    paused: raw.paused,
    stub: raw.stub,
  };
}
