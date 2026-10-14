"use client";

import { useState } from "react";
import type { PoliciesResponse, TimelineEvent, TimelineResponse } from "@/lib/types";
import { formatDate, formatDaysLeft, formatMoney, humanize } from "@/lib/format";
import { policyName } from "@/lib/clauses";
import { cn } from "@/lib/utils";

const NEAR_DAYS = 120;
const NEAR_MAX = 4;

function dotColor(ev: TimelineEvent) {
  if (ev.days_left < 14) return "bg-destructive";
  if (ev.days_left < 30) return "bg-warning";
  return "bg-primary";
}

export function TimelineCard({ timeline, policies }: { timeline: TimelineResponse; policies: PoliciesResponse | null }) {
  const [all, setAll] = useState(false);
  const sorted = [...timeline.events].sort((a, b) => a.days_left - b.days_left);
  const near = sorted.filter((e) => e.days_left <= NEAR_DAYS).slice(0, NEAR_MAX);
  const events = all ? sorted.slice(0, 8) : near.length ? near : sorted.slice(0, 2);
  const hidden = sorted.length - events.length;
  if (!sorted.length) return null;
  return (
    <div className="rounded-xl border border-border bg-card p-3.5 shadow-soft">
      <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Upcoming dates</p>
      <ol className="mt-2.5 flex flex-col gap-3">
        {events.map((ev, i) => (
          <li key={`${ev.policy_id}-${ev.kind}-${i}`} className="flex gap-3">
            <div className="flex flex-col items-center">
              <span className={cn("mt-1 h-2.5 w-2.5 shrink-0 rounded-full", dotColor(ev))} />
              {i < events.length - 1 && <span className="mt-1 w-px flex-1 bg-border" />}
            </div>
            <div className="min-w-0 pb-1">
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="text-sm font-medium">{formatDate(ev.date)}</span>
                <span
                  className={cn(
                    "rounded-full px-2 py-0.5 text-[11px] font-medium",
                    ev.days_left < 14 ? "bg-destructive/10 text-destructive" : "bg-muted text-muted-foreground"
                  )}
                >
                  {formatDaysLeft(ev.days_left)}
                </span>
              </div>
              <p className="text-xs text-muted-foreground">
                {policyName(policies, ev.policy_id)} — {humanize(ev.kind)}
                {ev.money_at_risk ? ` · ${formatMoney(ev.money_at_risk)} at stake` : ""}
              </p>
            </div>
          </li>
        ))}
      </ol>
      {hidden > 0 && (
        <button type="button" onClick={() => setAll((a) => !a)} className="mt-2 text-xs font-medium text-primary hover:underline">
          {all ? "Show fewer" : `Show ${hidden} more date${hidden > 1 ? "s" : ""}`}
        </button>
      )}
    </div>
  );
}
