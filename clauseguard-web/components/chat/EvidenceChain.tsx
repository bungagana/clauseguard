"use client";

import { useState } from "react";
import { ChevronDown, Link2 } from "lucide-react";
import type { ChatReply, PoliciesResponse } from "@/lib/types";
import { findTuple, clauseCitation, policyName } from "@/lib/clauses";
import { formatMoney, humanize } from "@/lib/format";
import { cn } from "@/lib/utils";

const RELATION_LABEL: Record<string, string> = {
  ANSWER: "your answer to its last question",
  CORRECTION: "a correction to the same situation",
  CONTINUE: "a follow-up about the same situation",
  NEW_SCENARIO: "a new situation",
  HYPOTHETICAL: "a what-if, not a report",
  GENERAL: "a general question, no situation involved",
};

const VERDICT_WORD: Record<string, string> = {
  COVERED: "covered",
  DENIED: "not covered",
  CLARIFY: "one fact still open",
  NOT_APPLICABLE: "the policy does not address this",
  NOT_SPECIFIED: "not specified in the documents",
};

function factLabel(k: string, v: unknown): string {
  const key = humanize(k);
  if (typeof v === "boolean") return `${key}: ${v ? "yes" : "no"}`;
  if (k === "billed_amount" && v != null) return `${key}: ${formatMoney(String(v), "IDR")}`;
  return `${key}: ${String(v).toLowerCase().replace(/_/g, " ")}`;
}

/**
 * The chain of evidence behind one answer, in the order it was built: what the message was
 * taken as, the facts that were bound, the rules that fired with their policy sentences, the
 * decision, the checks on the wording, and the audit entries. Everything shown here is data the
 * backend returned for this turn; nothing is re-derived in the browser.
 */
export function EvidenceChain({ reply, policies }: { reply: ChatReply; policies: PoliciesResponse | null }) {
  const [open, setOpen] = useState(false);
  const facts = Object.entries(reply.facts ?? {}).filter(([k, v]) => v !== null && v !== undefined && !k.startsWith("days_since") && !k.startsWith("months_since"));
  const verdicts = reply.verdicts.filter((v) => v.verdict !== "NOT_APPLICABLE" && v.verdict !== "NOT_SPECIFIED");
  if (!verdicts.length && !facts.length) return null;

  return (
    <div className="mt-0.5">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="inline-flex items-center gap-1 text-xs font-medium text-muted-foreground transition-colors hover:text-foreground"
      >
        <Link2 className="h-3 w-3" />
        {open ? "Hide the evidence" : "How was this decided?"}
        <ChevronDown className={cn("h-3 w-3 transition-transform", open && "rotate-180")} />
      </button>
      {open && (
        <ol className="mt-2 flex flex-col gap-0 rounded-xl border border-border bg-muted/40 px-3 py-2 text-xs">
          <Step n={1} title="Understood as" body={RELATION_LABEL[reply.context_relation ?? ""] ?? "a question about your policies"} />
          <Step n={2} title="Facts used" body={facts.length ? facts.map(([k, v]) => factLabel(k, v)).join(" · ") : "none needed"} />
          <Step
            n={3}
            title="Rules that fired"
            body={
              verdicts.length ? (
                <ul className="flex flex-col gap-1.5">
                  {verdicts.map((v) => {
                    const t = findTuple(policies, v.policy_id, v.fired_tuple_ids[0]);
                    return (
                      <li key={v.policy_id}>
                        <span className="font-medium text-foreground/90">{policyName(policies, v.policy_id)}</span>
                        {t ? (
                          <blockquote className="mt-0.5 border-l-2 border-primary/40 pl-2 italic text-foreground/75">
                            &ldquo;{t.text}&rdquo; <span className="not-italic font-mono text-[10px] uppercase text-muted-foreground">{clauseCitation(t, v.policy_id)}</span>
                          </blockquote>
                        ) : (
                          <span className="text-muted-foreground"> — no single clause; decided from the policy&rsquo;s terms</span>
                        )}
                      </li>
                    );
                  })}
                </ul>
              ) : (
                "no coverage rule was needed for this turn"
              )
            }
          />
          <Step
            n={4}
            title="Decision (rules engine)"
            body={
              verdicts.length
                ? verdicts.map((v) => `${policyName(policies, v.policy_id)}: ${VERDICT_WORD[v.verdict] ?? v.verdict}${v.payable && Number(v.payable) > 0 ? `, ${formatMoney(v.payable, v.currency ?? "IDR")}` : ""}`).join(" · ")
                : "none"
            }
          />
          <Step
            n={5}
            title="Wording check"
            body={
              reply.composed
                ? "the Explainer's text was accepted: every amount, date and ID matched the engine's output"
                : reply.violations?.length
                  ? `the Explainer's draft was rejected (${reply.violations.join(", ")}) and the exact engine wording was shown instead`
                  : "shown in the engine's exact wording"
            }
          />
          <Step n={6} title="On record" body={`${reply.audit_ids.length} audit entries written for this turn${reply.audit_ids.length ? ` (${reply.audit_ids.slice(0, 3).join(", ")}${reply.audit_ids.length > 3 ? ", …" : ""})` : ""}`} last />
        </ol>
      )}
    </div>
  );
}

function Step({ n, title, body, last = false }: { n: number; title: string; body: React.ReactNode; last?: boolean }) {
  return (
    <li className={cn("flex gap-2.5 py-1.5", !last && "border-b border-border/60")}>
      <span className="mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-primary/10 text-[10px] font-bold text-primary">{n}</span>
      <div className="min-w-0">
        <p className="font-semibold text-foreground/90">{title}</p>
        <div className="mt-0.5 leading-relaxed text-muted-foreground">{body}</div>
      </div>
    </li>
  );
}
