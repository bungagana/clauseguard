"use client";

import { Check } from "lucide-react";
import type { ChatMessage } from "@/lib/message";
import { firstTier2Pending } from "@/lib/message";
import type { DigestResponse } from "@/lib/types";
import { cn } from "@/lib/utils";

const STAGES = ["Question answered", "Documents read", "Form ready", "Sent to insurer", "Insurer decided"] as const;

/** How far the current claim has travelled, derived from the conversation itself (no extra state). */
export function claimStage(messages: ChatMessage[], digest: DigestResponse | null): number {
  let stage = 0;
  for (const m of messages) {
    if (m.reply?.verdicts?.some((v) => v.verdict === "COVERED" || v.verdict === "DENIED")) stage = Math.max(stage, 1);
    if (m.role === "user" && m.doc) stage = Math.max(stage, 2);
    const pending = m.reply ? firstTier2Pending(m.reply) : null;
    if (pending?.tool === "submit_claim") stage = Math.max(stage, m.pendingResolved === "confirmed" ? 4 : 3);
  }
  // The claim this conversation filed: its id is quoted in the assistant's confirmation. Only that claim's decision counts,
  // so an older approved or paid claim on the same account does not mark the new one as decided.
  let filedId: string | null = null;
  if (stage >= 4) {
    for (const m of messages) {
      const found = m.role === "assistant" ? (m.text ?? "").match(/\bCL-[A-Z0-9]{8}\b/) : null;
      if (found) filedId = found[0];
    }
  }
  const settled = /approved|rejected|paid/;
  const decided =
    filedId !== null &&
    (digest?.items.some((i) => i.kind === "CLAIM_STATUS" && i.claim_id === filedId && settled.test(i.message_en)) ||
      messages.some((m) => m.role === "assistant" && /^News from the insurer:/.test(m.text ?? "") && (m.text ?? "").includes(filedId as string) && settled.test(m.text ?? "")));
  if (stage >= 4 && decided) stage = 5;
  return stage;
}

export function ClaimStageStrip({ messages, digest }: { messages: ChatMessage[]; digest: DigestResponse | null }) {
  const stage = claimStage(messages, digest);
  if (stage === 0) return null;
  return (
    <ol aria-label="Claim progress" className="flex items-center gap-1 overflow-x-auto border-b border-border/60 bg-muted/30 px-3 py-1.5 text-[11px] sm:px-6">
      {STAGES.map((label, i) => {
        const n = i + 1;
        const done = n < stage || (n === stage && stage === 5);
        const current = n === stage && stage < 5;
        return (
          <li key={label} className="flex shrink-0 items-center gap-1">
            <span
              className={cn(
                "flex h-4 w-4 items-center justify-center rounded-full text-[9px] font-semibold",
                done ? "bg-success text-white" : current ? "bg-primary text-primary-foreground" : "bg-border text-muted-foreground"
              )}
            >
              {done ? <Check className="h-2.5 w-2.5" /> : n}
            </span>
            <span className={cn("whitespace-nowrap", done || current ? "text-foreground" : "text-muted-foreground")}>{label}</span>
            {i < STAGES.length - 1 && <span className="mx-1 h-px w-4 bg-border" />}
          </li>
        );
      })}
    </ol>
  );
}
