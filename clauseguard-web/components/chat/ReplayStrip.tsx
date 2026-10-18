"use client";

import { Film } from "lucide-react";
import type { RecordedMeta } from "@/lib/replayTypes";

/** Shown for the whole of a recorded scene: a replay must never look like a live run. */
export function ReplayStrip({ meta }: { meta: RecordedMeta }) {
  const when = new Date(meta.recordedAt).toLocaleString("en-GB", { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
  return (
    <div role="status" className="flex items-start gap-2 border-b border-warning/40 bg-warning/10 px-3 py-2 text-[12px] text-warning-foreground sm:px-6">
      <Film className="mt-0.5 h-3.5 w-3.5 shrink-0" />
      <p>
        <span className="font-semibold">Recorded from a real run</span> · {when} · claim {meta.claimId} · audit entries {meta.auditSeqFrom}–{meta.auditSeqTo} · {meta.backend}.
        This scene is replayed in your browser: no server or model is involved while it plays. The insurer&rsquo;s decision was entered at the sandbox claims desk by the team acting as the adjuster; the assistant cannot approve or reject a claim.
      </p>
    </div>
  );
}
