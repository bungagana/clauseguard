import type { ChatReply, PoliciesResponse } from "./types";
import { reasoningFor, stripVerdictPreamble } from "./parseReply";
import { findTuple, clauseCitation, policyName } from "./clauses";
import { formatMoney } from "./format";

/**
 * Plain-text version of an assistant reply's main answer, for the copy button. Deliberately
 * does not copy `reply.text` as-is for a card reply: that raw transcript carries clause ids
 * and "Clauses:"-style lines meant for the card parser, not for pasting into an email. This
 * covers the prose plus each decided/clarify policy's reasoning and lead clause — the core
 * answer — not every secondary card (allocation/timeline/plans), which stay visual-only.
 */
export function replyCopyText(reply: ChatReply, policies: PoliciesResponse | null): string {
  if (reply.refused) return reply.refusal_reason ?? reply.text;

  const decided = reply.verdicts.filter((v) => v.verdict === "COVERED" || v.verdict === "DENIED");
  const clarifyOnly = reply.verdicts.filter((v) => v.verdict === "CLARIFY");
  const hasVerdictCards = decided.length > 0 || clarifyOnly.length > 0;

  if (!hasVerdictCards) return reply.text;

  const transcript = reply.composed && reply.template_text ? reply.template_text : reply.text;
  const lines: string[] = [];
  if (reply.composed && reply.text) lines.push(reply.text.trim());

  for (const v of [...decided, ...clarifyOnly]) {
    const name = policyName(policies, v.policy_id);
    const reasoning = stripVerdictPreamble(reasoningFor(transcript, v.policy_id) ?? "");
    const amount = v.payable ? formatMoney(v.payable, v.currency ?? "IDR") : "";
    const summary = [amount, reasoning].filter(Boolean).join(" — ");
    lines.push(summary ? `${name}: ${summary}` : name);

    const tid = v.fired_tuple_ids[0];
    const tuple = findTuple(policies, v.policy_id, tid);
    if (tuple) {
      lines.push(`  "${tuple.text}" (${clauseCitation(tuple, v.policy_id)})`);
    }
  }

  return lines.join("\n");
}
