"use client";

import { useEffect, useState } from "react";
import { FlaskConical, Loader2 } from "lucide-react";
import type { PoliciesResponse, WhatIfResponse, WhatIfOutcome } from "@/lib/types";
import { whatIf } from "@/lib/api";
import { formatMoney } from "@/lib/format";
import { policyName } from "@/lib/clauses";
import { cn } from "@/lib/utils";

const VERDICT_LABEL: Record<string, string> = {
  COVERED: "Covered",
  DENIED: "Not covered",
  CLARIFY: "Depends",
  NOT_APPLICABLE: "Not applicable",
  NOT_SPECIFIED: "Not specified",
};

function verdictClass(v: string, payable: string | null) {
  if (v === "COVERED" && payable !== null && Number(payable) === 0) return "bg-muted text-muted-foreground";
  if (v === "COVERED") return "bg-success/10 text-success";
  if (v === "DENIED") return "bg-destructive/10 text-destructive";
  if (v === "CLARIFY") return "bg-warning/15 text-warning-foreground";
  return "bg-muted text-muted-foreground";
}

function Outcome({ o, policies }: { o: WhatIfOutcome; policies: PoliciesResponse | null }) {
  const label = VERDICT_LABEL[o.verdict] ?? o.verdict;
  const amount = o.payable !== null && Number(o.payable) > 0 ? formatMoney(o.payable, o.currency ?? "IDR") : null;
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className={cn("rounded-full px-2 py-0.5 text-[11px] font-medium", verdictClass(o.verdict, o.payable))}>{label}</span>
      {amount && <span className="text-xs font-semibold tabular-nums">{amount}</span>}
      <span className="sr-only">{policyName(policies, o.policy_id)}</span>
    </span>
  );
}

/**
 * "What if…": flip a fact and watch every policy's answer recompute. Same solver as the chat,
 * on a copy of the facts; nothing in the conversation changes. Only facts that actually change
 * an outcome for this account are offered as controls.
 */
export function WhatIfPanel({ token, policies }: { token: string; policies: PoliciesResponse | null }) {
  const [data, setData] = useState<WhatIfResponse | null>(null);
  const [overrides, setOverrides] = useState<Record<string, boolean | number>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setBusy(true);
    whatIf(token, overrides)
      .then((d) => {
        if (!cancelled) {
          setData(d);
          setError(null);
        }
      })
      .catch((e) => !cancelled && setError(e instanceof Error ? e.message : "what-if failed"))
      .finally(() => !cancelled && setBusy(false));
    return () => {
      cancelled = true;
    };
  }, [token, overrides]);

  if (error) return <p className="text-xs text-muted-foreground">What-if is unavailable right now ({error}).</p>;
  if (!data) return <p className="inline-flex items-center gap-1.5 text-xs text-muted-foreground"><Loader2 className="h-3 w-3 animate-spin" /> Computing…</p>;
  if (!data.available) return <p className="text-xs text-muted-foreground">What-if is unavailable: {data.reason}</p>;
  if (!data.controls.length) return <p className="text-xs text-muted-foreground">No fact you could change would alter these answers.</p>;

  const byId = Object.fromEntries(data.baseline.map((b) => [b.policy_id, b]));
  const touched = Object.keys(overrides).length > 0;

  return (
    <div className="rounded-xl border border-primary/25 bg-primary/5 p-3.5">
      <div className="flex items-center justify-between gap-2">
        <p className="inline-flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-primary/80">
          <FlaskConical className="h-3.5 w-3.5" /> What if…
        </p>
        <span className="inline-flex items-center gap-2 text-[11px] text-muted-foreground">
          {busy && <Loader2 className="h-3 w-3 animate-spin" />}
          {touched && (
            <button type="button" onClick={() => setOverrides({})} className="font-medium text-primary hover:underline">
              Reset
            </button>
          )}
        </span>
      </div>
      <p className="mt-1 text-xs text-muted-foreground">Change a fact and every answer is recomputed by the same engine. Your conversation is not changed.</p>

      <div className="mt-3 flex flex-col gap-2">
        {data.controls.map((c) => {
          const current = overrides[c.slot] ?? c.current;
          return (
            <div key={c.slot} className="flex flex-wrap items-center justify-between gap-2">
              <span className="text-sm">{c.label}</span>
              <div className="flex flex-wrap gap-1">
                {c.options.map((opt) => {
                  const active = current !== null && current !== undefined && String(current) === String(opt);
                  const label = c.kind === "bool" ? (opt ? "Yes" : "No") : c.kind === "choice" && c.slot === "vehicles_involved" ? (opt === 1 ? "Only me" : "Another vehicle") : String(opt);
                  return (
                    <button
                      key={String(opt)}
                      type="button"
                      onClick={() => setOverrides((o) => ({ ...o, [c.slot]: opt as boolean | number }))}
                      className={cn(
                        "rounded-full border px-2.5 py-1 text-xs font-medium transition-colors",
                        active ? "border-primary bg-primary text-primary-foreground" : "border-border bg-card text-muted-foreground hover:text-foreground"
                      )}
                    >
                      {label}
                    </button>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>

      <ul className="mt-3 flex flex-col gap-1.5 border-t border-border/70 pt-3">
        {data.result.map((o) => {
          const before = byId[o.policy_id];
          const changed = data.changed.includes(o.policy_id);
          return (
            <li key={o.policy_id} className={cn("flex flex-wrap items-center justify-between gap-2 rounded-lg px-2 py-1 text-sm", changed && "bg-card")}>
              <span className="min-w-0 truncate">{policyName(policies, o.policy_id)}</span>
              <span className="inline-flex items-center gap-1.5">
                {changed && before && (
                  <>
                    <Outcome o={before} policies={policies} />
                    <span className="text-xs text-muted-foreground">→</span>
                  </>
                )}
                <Outcome o={o} policies={policies} />
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
