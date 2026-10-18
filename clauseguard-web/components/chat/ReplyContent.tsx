"use client";

import { useState } from "react";
import { CalendarClock, ClipboardCheck, FlaskConical, ListChecks } from "lucide-react";
import type { ChatMessage } from "@/lib/message";
import { firstTier2Pending } from "@/lib/message";
import type { PendingAction, PoliciesResponse, ReadinessReport } from "@/lib/types";
import { formatDate, formatMoney, humanize } from "@/lib/format";
import { policyName } from "@/lib/clauses";
import { isPlainTranscript } from "@/lib/parseReply";
import { cn } from "@/lib/utils";
import { VerdictCard } from "./cards/VerdictCard";
import { ClarificationNote } from "./cards/ClarificationNote";
import { CobList } from "./cards/CobList";
import { AllocationCard } from "./cards/AllocationCard";
import { TimelineCard } from "./cards/TimelineCard";
import { ReadinessCard } from "./cards/ReadinessCard";
import { PlanCards } from "./cards/PlanCards";
import { ConfirmCard } from "./cards/ConfirmCard";
import { ClaimFormPreview } from "./cards/ClaimFormPreview";
import { RefusalCard } from "./cards/RefusalCard";
import { AlertBanner } from "./cards/AlertBanner";
import { DocumentReads } from "./cards/DocumentReads";
import { AiNoticeBanner } from "./cards/AiNoticeBanner";
import { EvidenceFold } from "./cards/EvidenceFold";
import { WhatIfPanel } from "./cards/WhatIfPanel";
import { StreamedProse } from "./StreamedProse";
import { EvidenceChain } from "./EvidenceChain";

function confirmSummary(
  action: PendingAction,
  readiness: ReadinessReport | null,
  policies: PoliciesResponse | null
): string {
  if (readiness?.verdict?.policy_id) {
    const parts: string[] = [policyName(policies, readiness.verdict.policy_id)];
    if (readiness.verdict.payable) parts.push(`expected benefit ${formatMoney(readiness.verdict.payable, readiness.verdict.currency ?? "IDR")}`);
    if (readiness.deadline) parts.push(`file by ${formatDate(readiness.deadline)}`);
    if (readiness.missing_documents.length) parts.push(`still need: ${readiness.missing_documents.map(humanize).join(", ")}`);
    return parts.join(" · ");
  }
  return action.summary ?? "";
}

type Extra = "readiness" | "timeline" | "plans" | "whatif";

export function ReplyContent({
  message,
  policies,
  onConfirm,
  onCancel,
  onQuickReply,
  isLatest,
  sessionToken,
  autonomy,
}: {
  message: ChatMessage;
  policies: PoliciesResponse | null;
  onConfirm: () => void;
  onCancel: () => void;
  onQuickReply?: (text: string) => void;
  isLatest?: boolean;
  sessionToken?: () => string | undefined;
  autonomy?: "observe" | "draft" | "act";
}) {
  const reply = message.reply;

  // Only a reply that just arrived live streams in; a reloaded, scene or offline message
  // renders instantly. Structured cards appear once the prose finishes (or immediately, when
  // there is no prose to wait for). Computed before any early return, so the hook calls stay
  // unconditional regardless of which reply shape this turns out to be.
  const hasProse = Boolean(reply && reply.text && (reply.composed || isPlainTranscript(reply.text)));
  const animateProse = Boolean(message.liveReply) && hasProse;
  const [proseDone, setProseDone] = useState(!animateProse);
  const [open, setOpen] = useState<Extra | null>(null);

  if (!reply) return null;

  if (reply.refused) {
    return (
      <div className="flex max-w-[min(34rem,88vw)] flex-col gap-2.5">
        <RefusalCard reply={reply} />
      </div>
    );
  }

  const decided = reply.verdicts.filter((v) => v.verdict === "COVERED" || v.verdict === "DENIED");
  const clarifyOnly = reply.verdicts.filter((v) => v.verdict === "CLARIFY");
  const pendingTier2 = firstTier2Pending(reply);
  // the cards parse the deterministic transcript; a composed reply keeps it in template_text
  const transcript = reply.composed && reply.template_text ? reply.template_text : reply.text;

  const allocation = message.entitlement?.allocation;
  const timeline = message.entitlement?.timeline;
  const intent = (reply.intent ?? "").toUpperCase();
  const claimIntent = /CLAIM|SUBMIT|ACTION|READINESS|DEADLINE|DOCUMENT/.test(intent) || Boolean(pendingTier2);
  // the reply that reports a filed claim: the customer can reopen and download what was sent
  const filedClaimId = pendingTier2 ? undefined : /filed in the sandbox insurer system as (CL-[A-Z0-9]{8})/.exec(reply.text ?? "")?.[1];

  // Answer first: verdicts, then at most one secondary card chosen by what the user asked.
  // Everything else is one tap away under "More".
  // Evidence cards open by default only for the first answer about a situation. Follow-ups, corrections and answers to a
  // question are read as text; the same evidence stays one tap away.
  const compact = Boolean(reply.context_relation) && reply.context_relation !== "NEW_SCENARIO" && !pendingTier2 && !reply.clarification;
  const showAllocationInline = Boolean(allocation);
  const showReadinessInline = Boolean(reply.readiness) && !showAllocationInline && claimIntent;
  const showTimelineInline = Boolean(timeline) && /DEADLINE|DIGEST|TIMELINE|DUE/.test(intent);

  const extras: { key: Extra; label: string; icon: typeof ListChecks }[] = [];
  if (reply.readiness && !showReadinessInline) extras.push({ key: "readiness", label: "Claim readiness", icon: ClipboardCheck });
  if (timeline?.events.length && !showTimelineInline) extras.push({ key: "timeline", label: "Upcoming dates", icon: CalendarClock });
  if (reply.recommendations.length) extras.push({ key: "plans", label: "Plans that close the gap", icon: ListChecks });
  const token = isLatest ? sessionToken?.() : undefined;
  if (token && (decided.length > 0 || clarifyOnly.length > 0)) extras.push({ key: "whatif", label: "What if…", icon: FlaskConical });

  const hasCards =
    decided.length > 0 ||
    clarifyOnly.length > 0 ||
    reply.cob.length > 0 ||
    showAllocationInline ||
    Boolean(reply.readiness) ||
    Boolean(timeline) ||
    reply.recommendations.length > 0 ||
    Boolean(pendingTier2) ||
    Boolean(reply.clarification) ||
    Boolean(reply.suggestions?.length) ||
    Boolean(filedClaimId);

  if (!hasCards) {
    return (
      <StreamedProse
        text={reply.text}
        animate={Boolean(message.liveReply)}
        className="max-w-[min(34rem,88vw)] whitespace-pre-line text-sm leading-relaxed"
      />
    );
  }

  return (
    <div className="flex max-w-[min(38rem,90vw)] flex-col gap-2.5">
      {hasProse && (
        <StreamedProse
          text={reply.text}
          animate={animateProse}
          className="whitespace-pre-line text-sm leading-relaxed"
          onDone={() => setProseDone(true)}
        />
      )}

      {proseDone && (
        <>
          <EvidenceFold compact={compact} label={reply.language === "id" ? "Lihat dasar jawaban ini" : "Show the evidence behind this answer"}>
            <EvidenceChain reply={reply} policies={policies} />

            {[...decided, ...clarifyOnly].map((v) => (
              <VerdictCard key={v.policy_id} verdict={v} policies={policies} replyText={transcript} />
            ))}

            {showAllocationInline ? (
              <AllocationCard allocation={allocation!} policies={policies} />
            ) : reply.cob.length > 0 ? (
              <CobList steps={reply.cob} policies={policies} />
            ) : null}

            {showReadinessInline && reply.readiness && <ReadinessCard readiness={reply.readiness} twin={message.entitlement?.twin} />}
            {showTimelineInline && timeline && <TimelineCard timeline={timeline} policies={policies} />}

          </EvidenceFold>

          {Boolean(reply.doc_reads?.length) && <DocumentReads reads={reply.doc_reads!} />}

          {reply.ai_notice && isLatest && <AiNoticeBanner notice={reply.ai_notice} sessionToken={sessionToken} />}

          {pendingTier2 && (
            <ConfirmCard
              action={{ ...pendingTier2, summary: confirmSummary(pendingTier2, reply.readiness, policies) }}
              resolved={message.pendingResolved}
              busy={message.confirmBusy}
              onConfirm={onConfirm}
              onCancel={onCancel}
              lockedBy={!message.claimDraft && autonomy && autonomy !== "act" ? autonomy : undefined}
              token={message.claimDraft ? undefined : sessionToken?.()}
              policies={policies}
              recordedDraft={message.claimDraft}
              onCorrect={isLatest ? onQuickReply : undefined}
            />
          )}

          {Boolean(reply.suggestions?.length) && isLatest && onQuickReply && (
            <div className="flex flex-wrap items-center gap-1.5">
              {reply.suggestions!.map((text) => (
                <button
                  key={text}
                  type="button"
                  onClick={() => onQuickReply(text)}
                  className="rounded-full border border-primary/40 bg-card px-3.5 py-1.5 text-xs font-medium text-primary transition-colors hover:bg-primary hover:text-primary-foreground"
                >
                  {text}
                </button>
              ))}
              <span className="self-center text-[11px] text-muted-foreground">{reply.language === "id" ? "atau ketik saja" : "or just type it"}</span>
            </div>
          )}

          {filedClaimId && (sessionToken?.() || message.claimDraft) && (
            <details className="rounded-lg border border-border bg-card px-3 py-2 text-xs">
              <summary className="cursor-pointer font-medium">View the form sent for claim {filedClaimId}</summary>
              <ClaimFormPreview token={message.claimDraft ? undefined : sessionToken?.()} tool="submit_claim" policies={policies} recordedDraft={message.claimDraft} claimId={filedClaimId} sent />
            </details>
          )}

          {reply.submit_offer && isLatest && onQuickReply && (
            <div className="flex flex-wrap items-center gap-1.5">
              {(reply.language === "id"
                ? [
                    { label: "Ajukan saja", text: "Ajukan saja, saya tahu dokumennya belum lengkap." },
                    { label: "Saya lampirkan dulu", text: "Saya lampirkan dokumennya dulu." },
                  ]
                : [
                    { label: "Submit anyway", text: "Submit anyway, I know documents are missing." },
                    { label: "I'll attach them first", text: "I'll attach the documents first." },
                  ]
              ).map((r) => (
                <button
                  key={r.label}
                  type="button"
                  onClick={() => onQuickReply(r.text)}
                  className="rounded-full border border-primary/40 bg-card px-3.5 py-1.5 text-xs font-medium text-primary transition-colors hover:bg-primary hover:text-primary-foreground"
                >
                  {r.label}
                </button>
              ))}
              <span className="self-center text-[11px] text-muted-foreground">{reply.language === "id" ? "atau unggah dari klip kertas" : "or upload with the paperclip"}</span>
            </div>
          )}

          {reply.clarification && (
            <ClarificationNote
              clarification={reply.clarification}
              replyText={transcript}
              policies={policies}
              onQuickReply={onQuickReply}
              answered={!isLatest}
              language={reply.language}
            />
          )}

          {extras.length > 0 && (
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">More</span>
              {extras.map((e) => (
                <button
                  key={e.key}
                  type="button"
                  onClick={() => setOpen((o) => (o === e.key ? null : e.key))}
                  className={cn(
                    "inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-xs font-medium transition-colors",
                    open === e.key ? "border-primary bg-primary text-primary-foreground" : "border-border bg-card text-muted-foreground hover:text-foreground"
                  )}
                >
                  <e.icon className="h-3 w-3" />
                  {e.label}
                </button>
              ))}
            </div>
          )}
          {open === "readiness" && reply.readiness && <ReadinessCard readiness={reply.readiness} twin={message.entitlement?.twin} />}
          {open === "timeline" && timeline && <TimelineCard timeline={timeline} policies={policies} />}
          {open === "plans" && reply.recommendations.length > 0 && <PlanCards recommendations={reply.recommendations} />}
          {open === "whatif" && token && <WhatIfPanel token={token} policies={policies} />}

          <AlertBanner alerts={reply.alerts} />
        </>
      )}
    </div>
  );
}
