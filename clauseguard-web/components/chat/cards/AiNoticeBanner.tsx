"use client";

import { Sparkles } from "lucide-react";
import type { AiNotice } from "@/lib/types";
import { OwnKeyDialog } from "../OwnKeyDialog";

/** The AI could not be used for this answer: say why in plain words and offer the way out. */
export function AiNoticeBanner({ notice, sessionToken, onRetry }: { notice: AiNotice; sessionToken?: () => string | undefined; onRetry?: () => void }) {
  return (
    <div role="status" className="flex flex-col gap-2 rounded-xl border border-warning/40 bg-warning/10 px-3.5 py-2.5 text-sm text-warning-foreground">
      <p className="flex items-start gap-2">
        <Sparkles className="mt-0.5 h-4 w-4 shrink-0" />
        <span>{notice.text}</span>
      </p>
      <div className="flex flex-wrap gap-2">
        {notice.can_use_own_key && <OwnKeyDialog sessionToken={sessionToken} onChanged={onRetry} />}
        {onRetry && (
          <button type="button" onClick={onRetry} className="rounded-md px-2.5 py-1.5 text-xs font-medium text-foreground underline-offset-4 hover:underline">
            Try again
          </button>
        )}
      </div>
    </div>
  );
}
