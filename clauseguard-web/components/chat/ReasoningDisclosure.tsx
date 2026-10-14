"use client";

import { useState } from "react";
import { ChevronDown, ScrollText } from "lucide-react";
import type { ChatReply, PoliciesResponse, VerdictResult } from "@/lib/types";
import { reasoningFor, stripVerdictPreamble } from "@/lib/parseReply";
import { findPolicy, findTuple, clauseCitation } from "@/lib/clauses";
import { cn } from "@/lib/utils";

interface Item {
  policyName: string;
  reasoning: string | null;
  citation: string | null;
  quote: string | null;
}

function buildItems(reply: ChatReply, policies: PoliciesResponse | null, transcript: string): Item[] {
  const decided = reply.verdicts.filter((v) => v.verdict === "COVERED" || v.verdict === "DENIED");
  const clarifyOnly = reply.verdicts.filter((v) => v.verdict === "CLARIFY");
  let source: VerdictResult[] = [...decided, ...clarifyOnly];
  // No per-policy verdict card to carry this reply's clause (e.g. a readiness-only turn) —
  // fall back to the readiness verdict so the prose summary still has something to point to.
  if (!source.length && reply.readiness?.verdict?.fired_tuple_ids?.length) {
    source = [reply.readiness.verdict];
  }
  return source
    .slice(0, 3)
    .map((v) => {
      const policy = findPolicy(policies, v.policy_id);
      const tuple = findTuple(policies, v.policy_id, v.fired_tuple_ids[0]);
      return {
        policyName: policy?.product_name ?? v.policy_id,
        reasoning: stripVerdictPreamble(reasoningFor(transcript, v.policy_id) ?? "") || null,
        citation: tuple ? clauseCitation(tuple, v.policy_id) : null,
        quote: tuple?.text ?? null,
      };
    })
    .filter((it) => it.quote || it.reasoning);
}

/**
 * Collapsed-by-default, plain-prose reasoning link directly under an answer's main text — the
 * lightweight, always-visible counterpart to the Developer panel's dense trace. Each
 * VerdictCard already carries its own "Show clause" toggle underneath it, so this one
 * sits above those, right under the headline summary, and only ever shows up to three clauses
 * total.
 */
export function ReasoningDisclosure({
  reply,
  policies,
  transcript,
}: {
  reply: ChatReply;
  policies: PoliciesResponse | null;
  transcript: string;
}) {
  const [open, setOpen] = useState(false);
  const items = buildItems(reply, policies, transcript);
  if (!items.length) return null;

  return (
    <div className="mt-0.5">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="inline-flex items-center gap-1 text-xs font-medium text-muted-foreground transition-colors hover:text-foreground"
      >
        <ScrollText className="h-3 w-3" />
        {open ? "Hide reasoning" : "Why this answer"}
        <ChevronDown className={cn("h-3 w-3 transition-transform", open && "rotate-180")} />
      </button>
      {open && (
        <div className="mt-2 flex flex-col gap-2.5 rounded-lg border border-border bg-muted/40 px-3 py-2.5 text-xs leading-relaxed text-muted-foreground">
          {items.map((it, i) => (
            <div key={i}>
              <p className="font-medium text-foreground/90">{it.policyName}</p>
              {it.reasoning && <p className="mt-0.5">{it.reasoning}</p>}
              {it.quote && (
                <blockquote className="mt-1 border-l-2 border-border pl-2 italic text-foreground/80">
                  &ldquo;{it.quote}&rdquo;
                  {it.citation && <span className="ml-1 not-italic text-[10px] uppercase text-muted-foreground/70">— {it.citation}</span>}
                </blockquote>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
