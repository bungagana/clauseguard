"use client";

import { useState } from "react";
import { ChevronDown } from "lucide-react";
import type { PayerStep, PoliciesResponse } from "@/lib/types";
import { formatMoney, humanize } from "@/lib/format";
import { policyName, findTuple, clauseCitation } from "@/lib/clauses";
import { cn } from "@/lib/utils";

const STATUS_LABEL: Record<string, string> = {
  PAYER: "Pays",
  PARALLEL: "Pays in parallel",
  UNCERTAIN: "Uncertain",
  NOT_CLAIMABLE: "Not claimable",
};

function StepRow({ step, policies }: { step: PayerStep; policies: PoliciesResponse | null }) {
  const [open, setOpen] = useState(false);
  const amount = step.expected_amount ? formatMoney(step.expected_amount, step.currency ?? "IDR") : step.status === "PAYER" ? "amount depends on the bill" : null;
  return (
    <li className="rounded-lg border border-border bg-background/60">
      <button type="button" onClick={() => setOpen((o) => !o)} className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left">
        <div className="flex min-w-0 items-center gap-2">
          <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-primary/10 text-[11px] font-semibold text-primary">
            {step.order}
          </span>
          <span className="truncate text-sm font-medium">{policyName(policies, step.payer_policy_id)}</span>
        </div>
        <div className="flex shrink-0 items-center gap-2 text-xs text-muted-foreground">
          <span
            className={cn(
              "rounded-full px-2 py-0.5 font-medium",
              step.status === "PAYER" || step.status === "PARALLEL" ? "bg-success/10 text-success" : step.status === "UNCERTAIN" ? "bg-warning/15 text-warning-foreground" : "bg-muted"
            )}
          >
            {STATUS_LABEL[step.status] ?? step.status}
          </span>
          <ChevronDown className={cn("h-3.5 w-3.5 transition-transform", open && "rotate-180")} />
        </div>
      </button>
      {open && (
        <div className="border-t border-border px-3 py-2 text-xs text-muted-foreground">
          {amount && <p className="text-sm font-medium text-foreground">{amount}</p>}
          {step.note && <p className="mt-1">{step.note}</p>}
          {step.deadline && <p className="mt-1">Deadline: {step.deadline}</p>}
          {step.documents.length > 0 && <p className="mt-1">Documents: {step.documents.map(humanize).join(", ")}</p>}
          {step.tuple_ids.slice(0, 1).map((tid) => {
            const t = findTuple(policies, step.payer_policy_id, tid);
            if (!t) return null;
            return (
              <blockquote key={tid} className="mt-2 rounded-md bg-muted/70 px-2.5 py-1.5 italic text-foreground/80">
                <span className="not-italic font-mono text-[10px] uppercase text-muted-foreground">
                  {clauseCitation(t, step.payer_policy_id)}
                </span>
                <p className="mt-0.5">&ldquo;{t.text}&rdquo;</p>
              </blockquote>
            );
          })}
        </div>
      )}
    </li>
  );
}

export function CobList({ steps, policies }: { steps: PayerStep[]; policies: PoliciesResponse | null }) {
  if (!steps.length) return null;
  return (
    <div className="rounded-xl border border-border bg-card p-3.5 shadow-soft">
      <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Who pays, in order</p>
      <ol className="mt-2 flex flex-col gap-1.5">
        {steps.map((s) => (
          <StepRow key={`${s.order}-${s.payer_policy_id}`} step={s} policies={policies} />
        ))}
      </ol>
    </div>
  );
}
