"use client";

import { AlertTriangle, CheckCircle2, FileSearch } from "lucide-react";
import type { DocRead } from "@/lib/types";

/**
 * What the assistant read from each file the customer sent: the values it took, the checks it ran, and which
 * of the insurer's required documents the file now counts as. The claim rests on these, so they are shown, not hidden.
 */
export function DocumentReads({ reads }: { reads: DocRead[] }) {
  if (!reads.length) return null;
  return (
    <details open className="rounded-xl border border-border bg-card px-3.5 py-3 text-xs">
      <summary className="flex cursor-pointer items-center gap-2 text-sm font-semibold">
        <FileSearch className="h-4 w-4 text-primary" /> What I read from your documents ({reads.length})
      </summary>
      <div className="mt-3 space-y-3">
        {reads.map((d, i) => (
          <div key={`${d.filename}-${i}`} className="rounded-lg border border-border/70 bg-background px-3 py-2.5">
            <p className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
              <span className="font-medium text-foreground">{d.filename}</span>
              <span className="rounded-full bg-primary/10 px-2 py-0.5 text-[10px] font-medium capitalize text-primary">{d.type}</span>
            </p>
            {d.fields.length > 0 ? (
              <dl className="mt-1.5">
                {d.fields.map((f) => (
                  <div key={f.label} className="grid grid-cols-[8.5rem_1fr] gap-2 border-b border-border/50 py-1 last:border-b-0">
                    <dt className="text-[11px] uppercase tracking-wide text-muted-foreground">{f.label}</dt>
                    <dd className="text-foreground">{f.value}</dd>
                  </div>
                ))}
              </dl>
            ) : (
              <p className="mt-1.5 text-muted-foreground">No values could be read from this file.</p>
            )}
            {d.checks.map((c) => (
              <p key={c} className="mt-1.5 flex items-start gap-1.5 text-warning-foreground">
                <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" /> {c}
              </p>
            ))}
            {d.counts_as.length > 0 && (
              <p className="mt-1.5 flex items-start gap-1.5 text-muted-foreground">
                <CheckCircle2 className="mt-0.5 h-3 w-3 shrink-0 text-success" />
                <span>Counts as: {d.counts_as.join(", ")}</span>
              </p>
            )}
          </div>
        ))}
      </div>
      <p className="mt-2 text-[11px] text-muted-foreground">Something wrong? Tell me in the chat, for example &ldquo;the total is 2,700,000&rdquo;, and I will correct it.</p>
    </details>
  );
}
