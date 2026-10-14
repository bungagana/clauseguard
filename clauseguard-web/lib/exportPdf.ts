import type { ExportRequest, ExportSection } from "./api";
import type { ChatMessage } from "./message";
import type { PoliciesResponse } from "./types";
import { reasoningFor, stripVerdictPreamble } from "./parseReply";
import { findTuple, clauseCitation, policyName } from "./clauses";
import { formatDate, formatDaysLeft, formatMoney, humanize } from "./format";

const VERDICT_LABEL: Record<string, string> = {
  COVERED: "Covered",
  DENIED: "Not covered",
  CLARIFY: "Depends on one fact",
  NOT_APPLICABLE: "Not determinable",
  NOT_SPECIFIED: "Not specified in the documents",
};

// Everything the user already saw in the reply, as plain sections for the PDF renderer.
export function buildExport(message: ChatMessage, policies: PoliciesResponse | null): ExportRequest | null {
  const reply = message.reply;
  if (!reply || reply.refused) return null;
  const transcript = reply.composed && reply.template_text ? reply.template_text : reply.text;
  const sections: ExportSection[] = [];

  if (message.forText) sections.push({ heading: "Your question", lines: [message.forText] });
  if (reply.composed && reply.text) sections.push({ heading: "Answer", lines: reply.text.split(/\n{2,}/).map((s) => s.trim()).filter(Boolean) });

  const verdicts = reply.verdicts.filter((v) => v.verdict !== "NOT_APPLICABLE" && v.verdict !== "NOT_SPECIFIED");
  if (verdicts.length) {
    const lines: string[] = [];
    for (const v of verdicts) {
      const amount = v.payable ? ` · ${formatMoney(v.payable, v.currency ?? "IDR")}` : "";
      lines.push(`${policyName(policies, v.policy_id)} (${v.policy_id}): ${VERDICT_LABEL[v.verdict] ?? v.verdict}${amount}`);
      const reasoning = stripVerdictPreamble(reasoningFor(transcript, v.policy_id) ?? "");
      if (reasoning) lines.push(reasoning);
      for (const tid of v.fired_tuple_ids.slice(0, 2)) {
        const t = findTuple(policies, v.policy_id, tid);
        if (t) lines.push(`“${t.text}” (${clauseCitation(t, v.policy_id)})`);
      }
    }
    sections.push({ heading: "Verdicts and the clauses that decide them", lines });
  }

  const alloc = message.entitlement?.allocation;
  if (alloc?.steps.length) {
    const lines = alloc.steps.map((s) => {
      const amt = s.amount ? formatMoney(s.amount, s.currency ?? "IDR") : "amount not yet known";
      const docs = s.documents_required.length ? ` · documents: ${s.documents_required.map(humanize).join(", ")}` : "";
      const due = s.filing_deadline ? ` · file by ${formatDate(s.filing_deadline)}` : "";
      return `${s.order}. ${policyName(policies, s.policy_id)} — ${amt}${due}${docs}`;
    });
    if (alloc.total_recovered) lines.push(`Total recovered: ${formatMoney(alloc.total_recovered, alloc.currency ?? "IDR")}`);
    if (alloc.greedy_total) lines.push(`If claimed in the order you hold the policies: ${formatMoney(alloc.greedy_total, alloc.currency ?? "IDR")}`);
    sections.push({ heading: "Who pays, in what order", lines });
  } else if (reply.cob.length) {
    sections.push({
      heading: "Who pays, in what order",
      lines: reply.cob.map((s) => `${s.order}. ${policyName(policies, s.payer_policy_id)}${s.expected_amount ? ` — ${formatMoney(s.expected_amount, "IDR")}` : ""}`),
    });
  }

  if (reply.readiness) {
    const r = reply.readiness;
    const lines: string[] = [];
    if (r.deadline) lines.push(`File by ${formatDate(r.deadline)} (${formatDaysLeft(r.days_left)})${r.late_effect === "REJECT" ? " — a late claim is rejected" : ""}`);
    if (r.required_documents.length) lines.push(`Required documents: ${r.required_documents.map(humanize).join(", ")}`);
    if (r.missing_documents.length) lines.push(`Still missing: ${r.missing_documents.map(humanize).join(", ")}`);
    const twin = message.entitlement?.twin;
    if (twin?.grounds.length) {
      for (const g of twin.grounds) lines.push(`${g.fixable ? "Fixable" : "Not fixable"}: ${humanize(g.code)}${g.recourse?.description ? ` — ${g.recourse.description}` : ""}`);
    }
    if (lines.length) sections.push({ heading: "Claim readiness", lines });
  }

  const tl = message.entitlement?.timeline;
  if (tl?.events.length) {
    const events = [...tl.events].sort((a, b) => a.days_left - b.days_left).slice(0, 8);
    sections.push({
      heading: "Upcoming dates",
      lines: events.map((e) => `${formatDate(e.date)} (${formatDaysLeft(e.days_left)}): ${policyName(policies, e.policy_id)} — ${humanize(e.kind)}${e.money_at_risk ? ` · ${formatMoney(e.money_at_risk)} at stake` : ""}`),
    });
  }

  if (reply.recommendations.length) {
    sections.push({
      heading: "Plans that would close the gap (indicative)",
      lines: reply.recommendations.map((p) => `${p.product_name}${p.monthly_premium_idr ? ` — ${formatMoney(p.monthly_premium_idr, p.currency ?? "IDR")}/month` : ""}: ${p.rationale}`),
    });
  }

  if (reply.alerts.length) sections.push({ heading: "Heads-up", lines: reply.alerts.map((a) => a.replace(/^Alert:\s*/, "")) });

  if (!sections.length) return null;
  const primary = verdicts[0];
  const title = primary ? `Claim pack — ${policyName(policies, primary.policy_id)}` : "ClauseGuard summary";
  return { title: title.slice(0, 120), subtitle: "Computed from the extracted policy wording; every amount is traced to a clause.", sections };
}

export function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}
