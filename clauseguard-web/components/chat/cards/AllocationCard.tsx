"use client";

import { useState } from "react";
import { ChevronDown } from "lucide-react";
import type { AllocationResponse, PoliciesResponse } from "@/lib/types";
import { formatMoney, humanize } from "@/lib/format";
import { policyName, findTuple, clauseCitation } from "@/lib/clauses";
import { cn } from "@/lib/utils";

function Bar({ label, value, max, highlight }: { label: string; value: number; max: number; highlight?: boolean }) {
  const pct = max > 0 ? Math.max(4, Math.round((value / max) * 100)) : 0;
  return (
    <div>
      <div className="flex items-baseline justify-between text-xs">
        <span className="font-medium text-muted-foreground">{label}</span>
        <span className={cn("font-semibold", highlight ? "text-primary" : "text-foreground")}>{formatMoney(value, "IDR")}</span>
      </div>
      <div className="mt-1 h-2 w-full rounded-full bg-muted">
        <div
          className={cn("h-2 rounded-full transition-all", highlight ? "bg-primary" : "bg-muted-foreground/40")}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

function StepRow({ step, policies }: { step: AllocationResponse["steps"][number]; policies: PoliciesResponse | null }) {
  const [open, setOpen] = useState(false);
  return (
    <li className="rounded-lg border border-border bg-background/60">
      <button type="button" onClick={() => setOpen((o) => !o)} className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left">
        <div className="flex min-w-0 items-center gap-2">
          <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-primary/10 text-[11px] font-semibold text-primary">
            {step.order}
          </span>
          <span className="truncate text-sm font-medium">{policyName(policies, step.policy_id)}</span>
        </div>
        <div className="flex shrink-0 items-center gap-2 text-xs text-muted-foreground">
          <span className="font-semibold text-foreground">{step.amount && Number(step.amount) > 0 ? formatMoney(step.amount, step.currency ?? "IDR") : <span className="font-normal text-muted-foreground">needs the bill</span>}</span>
          <ChevronDown className={cn("h-3.5 w-3.5 transition-transform", open && "rotate-180")} />
        </div>
      </button>
      {open && (
        <div className="border-t border-border px-3 py-2 text-xs text-muted-foreground">
          {step.note && <p>{step.note}</p>}
          {step.filing_deadline && <p className="mt-1">Deadline: {step.filing_deadline}</p>}
          {step.documents_required.length > 0 && <p className="mt-1">Documents: {step.documents_required.map(humanize).join(", ")}</p>}
          {step.clause_ids.slice(0, 1).map((tid) => {
            const t = findTuple(policies, step.policy_id, tid);
            if (!t) return null;
            return (
              <blockquote key={tid} className="mt-2 rounded-md bg-muted/70 px-2.5 py-1.5 italic text-foreground/80">
                <span className="not-italic font-mono text-[10px] uppercase text-muted-foreground">{clauseCitation(t, step.policy_id)}</span>
                <p className="mt-0.5">&ldquo;{t.text}&rdquo;</p>
              </blockquote>
            );
          })}
        </div>
      )}
    </li>
  );
}

export function AllocationCard({ allocation, policies }: { allocation: AllocationResponse; policies: PoliciesResponse | null }) {
  const optimized = Number(allocation.total_recovered ?? 0);
  const greedy = allocation.greedy_total !== null ? Number(allocation.greedy_total) : null;
  const single = allocation.single_policy_total !== null ? Number(allocation.single_policy_total) : null;
  // Without a hospital bill the engine can order the payers but not size the amounts: say so
  // instead of showing "Rp 0 recovered".
  const noBill = !allocation.bill_total || Number(allocation.bill_total) === 0;
  const showComparison = !noBill && greedy !== null && single !== null;
  const max = Math.max(optimized, greedy ?? 0, single ?? 0, 1);
  const extra = showComparison ? optimized - Math.max(greedy!, single!) : 0;

  return (
    <div className="rounded-xl border border-border bg-card p-3.5 shadow-soft">
      <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Claim allocation</p>

      {showComparison && (
        <div className="mt-2.5 flex flex-col gap-2.5">
          <Bar label="Optimized (what I'd recommend)" value={optimized} max={max} highlight />
          <Bar label="Greedy (claim in the order you hold them)" value={greedy!} max={max} />
          <Bar label="Single policy only" value={single!} max={max} />
          {extra > 0 && (
            <p className="text-xs text-primary">
              {formatMoney(extra, allocation.currency ?? "IDR")} more recovered than the next-best approach.
            </p>
          )}
        </div>
      )}
      {!showComparison && !noBill && (
        <p className="mt-2 text-lg font-semibold">{formatMoney(allocation.total_recovered, allocation.currency ?? "IDR")} recovered</p>
      )}
      {noBill && (
        <p className="mt-2 text-sm text-muted-foreground">This is the order to claim in. Tell me the total hospital bill and I will work out how much each one pays.</p>
      )}

      <ol className="mt-3 flex flex-col gap-1.5">
        {allocation.steps.map((s) => (
          <StepRow key={`${s.order}-${s.policy_id}`} step={s} policies={policies} />
        ))}
      </ol>

      {allocation.uncertain.length > 0 && (
        <p className="mt-2 text-xs text-muted-foreground">
          Uncertain: {allocation.uncertain.map((u) => policyName(policies, u.policy_id)).join(", ")} — depends on a fact not yet known.
        </p>
      )}
      {allocation.excluded.length > 0 && (
        <p className="mt-1 text-xs text-muted-foreground">
          Not part of this claim: {allocation.excluded.map((e) => policyName(policies, e.policy_id)).join(", ")}.
        </p>
      )}
    </div>
  );
}
