"use client";

import type { ReactNode } from "react";

/** The evidence cards behind an answer. Open for the first answer about a situation, folded for follow-ups so the chat reads like a conversation. */
export function EvidenceFold({ compact, label, children }: { compact: boolean; label: string; children: ReactNode }) {
  if (!compact) return <>{children}</>;
  return (
    <details className="rounded-xl border border-border bg-card/60 px-3.5 py-2.5">
      <summary className="cursor-pointer text-xs font-medium text-muted-foreground">{label}</summary>
      <div className="mt-2.5 flex flex-col gap-2.5">{children}</div>
    </details>
  );
}
