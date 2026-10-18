"use client";

import { CheckCircle2, Clock, ShieldCheck, XCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { ChatMessage } from "@/lib/message";
import type { PendingAction, PoliciesResponse } from "@/lib/types";
import type { ClaimDraft } from "@/lib/replayTypes";
import { ClaimFormPreview } from "./ClaimFormPreview";

export function ConfirmCard({
  action,
  resolved,
  busy,
  onConfirm,
  onCancel,
  lockedBy,
  token,
  policies,
  recordedDraft,
  onCorrect,
}: {
  action: PendingAction;
  resolved?: ChatMessage["pendingResolved"];
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
  lockedBy?: "observe" | "draft";
  token?: string;
  policies?: PoliciesResponse | null;
  recordedDraft?: ClaimDraft;
  onCorrect?: (text: string) => void;
}) {
  if (resolved === "confirmed") {
    return (
      <div className="flex items-center gap-2 rounded-xl border border-success/30 bg-success/10 px-3.5 py-2.5 text-sm text-success">
        <CheckCircle2 className="h-4 w-4 shrink-0" />
        Confirmed and submitted.
      </div>
    );
  }
  if (resolved === "cancelled") {
    return (
      <div className="flex items-center gap-2 rounded-xl border border-border bg-muted px-3.5 py-2.5 text-sm text-muted-foreground">
        <XCircle className="h-4 w-4 shrink-0" />
        Cancelled — nothing was sent.
      </div>
    );
  }
  if (resolved === "superseded") {
    return (
      <div className="flex items-start gap-2 rounded-xl border border-border bg-muted px-3.5 py-2.5 text-sm text-muted-foreground">
        <Clock className="mt-0.5 h-4 w-4 shrink-0" />
        <div>
          <p>Replaced by an updated version below — nothing was sent.</p>
          <p className="mt-0.5 text-xs">Your correction changed the form, so this older one was withdrawn.</p>
        </div>
      </div>
    );
  }
  if (resolved === "expired") {
    return (
      <div className="flex items-start gap-2 rounded-xl border border-border bg-muted px-3.5 py-2.5 text-sm text-muted-foreground">
        <Clock className="mt-0.5 h-4 w-4 shrink-0" />
        <div>
          <p>This confirmation expired when the conversation was reopened — nothing was sent.</p>
          <p className="mt-0.5 text-xs">Ask again to get a fresh confirmation step.</p>
        </div>
      </div>
    );
  }
  return (
    <div className="rounded-xl border border-primary/30 bg-secondary p-3.5">
      <div className="flex items-start gap-2.5">
        <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
        <div className="min-w-0">
          <p className="text-sm font-semibold">Confirm submission?</p>
          {action.summary && <p className="mt-1 text-sm text-muted-foreground">{action.summary}</p>}
          {(token || recordedDraft) && action.tool === "submit_claim" && <ClaimFormPreview token={token} tool={action.tool} policies={policies ?? null} recordedDraft={recordedDraft} onCorrect={resolved ? undefined : onCorrect} />}
          <p className="mt-1 text-xs text-muted-foreground">
            {lockedBy ? `Nothing can be sent in ${lockedBy === "observe" ? "Observe" : "Draft"} mode. Switch the agent to Act to submit.` : "Nothing is sent until you confirm."}
          </p>
          <div className="mt-3 flex gap-2">
            <Button size="sm" onClick={onConfirm} disabled={busy || Boolean(lockedBy)}>
              {busy ? "Submitting…" : "Confirm and submit"}
            </Button>
            <Button size="sm" variant="outline" onClick={onCancel} disabled={busy}>
              Cancel
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
