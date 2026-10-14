"use client";

import { useState } from "react";
import { AlertTriangle, ChevronDown, X } from "lucide-react";
import type { DigestItem } from "@/lib/types";
import { formatMoney } from "@/lib/format";
import { cn } from "@/lib/utils";

const URGENCY_STYLE: Record<DigestItem["urgency"], string> = {
  overdue: "bg-destructive/10 text-destructive",
  this_week: "bg-warning/15 text-warning-foreground",
  soon: "bg-muted text-muted-foreground",
  later: "bg-muted text-muted-foreground",
};

function shortLabel(item: DigestItem): string {
  const kind = item.kind.toLowerCase().replace(/_/g, " ");
  return `${item.product_name.replace(/\s*\(.*$/, "")} · ${kind}`;
}

/**
 * Proactive summary of what's coming due, from GET /entitlement/digest. Collapsed to one line
 * by default so it never competes with the conversation; expands to the full list on click.
 */
export function DigestCard({ items, onAsk, onDismiss }: { items: DigestItem[]; onAsk: (item: DigestItem) => void; onDismiss: () => void }) {
  const [open, setOpen] = useState(false);
  if (!items.length) return null;
  const top = items.slice(0, 3);
  const overdue = items.filter((i) => i.urgency === "overdue").length;
  const soonest = items[0];

  return (
    <div className="mx-auto w-full max-w-3xl px-4 pt-3 sm:px-6">
      <div className="rounded-2xl border border-warning/30 bg-warning/[0.06]">
        <div className="flex items-center gap-2 px-3.5 py-2">
          <AlertTriangle className="h-4 w-4 shrink-0 text-warning" />
          <button type="button" onClick={() => setOpen((o) => !o)} className="flex min-w-0 flex-1 items-center gap-2 text-left">
            <span className="text-sm font-semibold text-foreground">
              {items.length} {items.length === 1 ? "thing needs" : "things need"} your attention
            </span>
            <span className="hidden truncate text-xs text-muted-foreground sm:inline">
              {overdue ? `${overdue} overdue · ` : ""}next: {shortLabel(soonest)}
            </span>
            <ChevronDown className={cn("ml-auto h-4 w-4 shrink-0 text-muted-foreground transition-transform", open && "rotate-180")} />
          </button>
          <button type="button" onClick={onDismiss} aria-label="Dismiss" className="shrink-0 text-muted-foreground hover:text-foreground">
            <X className="h-4 w-4" />
          </button>
        </div>
        {open && (
          <ul className="flex flex-col gap-1.5 px-3.5 pb-3">
            {top.map((item, i) => (
              <li key={`${item.policy_id}-${item.kind}-${i}`}>
                <button
                  type="button"
                  onClick={() => onAsk(item)}
                  className="flex w-full items-start justify-between gap-3 rounded-xl border border-border bg-card px-3 py-2 text-left text-sm shadow-soft transition-colors hover:border-primary/40 hover:bg-primary/5"
                >
                  <span className="min-w-0 text-foreground/90">{item.message_en}</span>
                  <span className="flex shrink-0 flex-col items-end gap-1">
                    {item.money_at_risk && (
                      <span className="text-xs font-semibold text-foreground">{formatMoney(item.money_at_risk, item.currency)}</span>
                    )}
                    <span className={cn("rounded-full px-2 py-0.5 text-[10px] font-medium", URGENCY_STYLE[item.urgency])}>
                      {item.kind === "CLAIM_STATUS" ? "claim update" : item.days_left < 0 ? `${Math.abs(item.days_left)}d overdue` : `${item.days_left}d left`}
                    </span>
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
