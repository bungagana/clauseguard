"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import { Bot, FileDown, FileUp, Loader2, Paperclip, RefreshCw, ShieldAlert } from "lucide-react";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { ChatMessage } from "@/lib/message";
import { firstTier2Pending } from "@/lib/message";
import type { PoliciesResponse } from "@/lib/types";
import { ReplyContent } from "./ReplyContent";
import { CopyButton } from "./CopyButton";
import { replyCopyText } from "@/lib/copyText";
import { buildExport, downloadBlob } from "@/lib/exportPdf";
import { exportPdf } from "@/lib/api";
import { cn } from "@/lib/utils";

function DownloadPdfButton({ message, policies, token }: { message: ChatMessage; policies: PoliciesResponse | null; token?: () => string | undefined }) {
  const [state, setState] = useState<"idle" | "busy" | "error">("idle");
  const body = buildExport(message, policies);
  const t = token?.();
  if (!body || !t) return null;
  return (
    <button
      type="button"
      disabled={state === "busy"}
      onClick={async () => {
        setState("busy");
        try {
          const blob = await exportPdf(t, body);
          downloadBlob(blob, `${body.title.replace(/[^a-z0-9]+/gi, "-").toLowerCase()}.pdf`);
          setState("idle");
        } catch {
          setState("error");
        }
      }}
      className="inline-flex items-center gap-1 text-xs font-medium text-muted-foreground transition-colors hover:text-foreground disabled:opacity-50"
      title="Download this answer, its clauses and dates as a PDF"
    >
      {state === "busy" ? <Loader2 className="h-3 w-3 animate-spin" /> : <FileDown className="h-3 w-3" />}
      {state === "error" ? "PDF failed, retry" : "Download PDF"}
    </button>
  );
}

function PolicyUploadCard({ upload, onView }: { upload: NonNullable<ChatMessage["policyUpload"]>; onView: (policyId: string) => void }) {
  if (upload.status === "extracting") {
    return (
      <div className="flex max-w-[min(34rem,88vw)] items-center gap-2.5 rounded-xl border border-primary/30 bg-card px-3.5 py-2.5 text-sm">
        <Loader2 className="h-4 w-4 shrink-0 animate-spin text-primary" />
        <div>
          <p className="font-medium text-foreground">Reading your policy…</p>
          <p className="text-xs text-muted-foreground">Extracting clauses from {upload.filename} — this runs the real extractor, live.</p>
        </div>
      </div>
    );
  }
  if (upload.status === "error") {
    return (
      <div className="flex max-w-[min(34rem,88vw)] items-start gap-2.5 rounded-xl border border-destructive/30 bg-destructive/5 px-3.5 py-2.5 text-sm">
        <FileUp className="mt-0.5 h-4 w-4 shrink-0 text-destructive" />
        <div>
          <p className="font-medium text-destructive">Couldn&apos;t extract {upload.filename}</p>
          <p className="text-xs text-muted-foreground">{upload.error}</p>
        </div>
      </div>
    );
  }
  const { policy, extraction } = upload.result!;
  return (
    <div className="flex max-w-[min(34rem,88vw)] flex-col gap-2 rounded-xl border border-primary/30 bg-card px-3.5 py-3 text-sm">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="font-semibold leading-tight text-foreground">{policy.product_name}</p>
          <p className="text-xs text-muted-foreground">{policy.insurer}</p>
        </div>
        <Badge variant="warning" className="shrink-0">
          Unverified — just extracted, not yet reviewed
        </Badge>
      </div>
      <p className="text-xs text-muted-foreground">
        {extraction.tuple_count} clauses extracted · {Math.round(extraction.extraction_coverage * 100)}% section coverage ·{" "}
        {extraction.elapsed_seconds.toFixed(1)}s{extraction.model ? ` · ${extraction.model}` : ""}
        {extraction.hidden_text_flagged ? " · hidden-text flagged (proceeded, never trusted)" : ""}
      </p>
      <Button type="button" size="sm" variant="secondary" className="w-fit" onClick={() => onView(policy.id)}>
        View clauses
      </Button>
    </div>
  );
}

function TypingDots() {
  return (
    <div className="flex items-center gap-1 rounded-2xl bg-muted px-4 py-3">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted-foreground/60"
          style={{ animationDelay: `${i * 120}ms` }}
        />
      ))}
    </div>
  );
}

export function MessageBubble({
  message,
  policies,
  onConfirm,
  onCancel,
  onViewPolicy,
  onRegenerate,
  canRegenerate,
  onQuickReply,
  sessionToken,
  autonomy,
}: {
  message: ChatMessage;
  policies: PoliciesResponse | null;
  onConfirm: () => void;
  onCancel: () => void;
  onViewPolicy: (policyId: string) => void;
  onRegenerate: () => void;
  canRegenerate: boolean;
  onQuickReply?: (text: string) => void;
  sessionToken?: () => string | undefined;
  autonomy?: "observe" | "draft" | "act";
}) {
  const anim = {
    initial: { opacity: 0, y: 8 },
    animate: { opacity: 1, y: 0 },
    transition: { duration: 0.18, ease: "easeOut" as const },
  };

  if (message.role === "system") {
    return (
      <motion.div {...anim} className="flex justify-center">
        <span className="rounded-full bg-muted px-3 py-1 text-xs text-muted-foreground">{message.text}</span>
      </motion.div>
    );
  }

  if (message.role === "user") {
    return (
      <motion.div {...anim} className="flex justify-end">
        <div className="flex max-w-[min(30rem,85vw)] flex-col items-end gap-1">
          {message.policyUpload ? (
            <PolicyUploadCard upload={message.policyUpload} onView={onViewPolicy} />
          ) : message.doc ? (
            <div className="flex items-center gap-2 rounded-2xl bg-primary px-4 py-2.5 text-sm text-primary-foreground">
              <Paperclip className="h-3.5 w-3.5" />
              {message.doc.filename}
            </div>
          ) : (
            <div className="rounded-2xl bg-primary px-4 py-2.5 text-sm text-primary-foreground">{message.text}</div>
          )}
        </div>
      </motion.div>
    );
  }

  // assistant
  const pendingUnresolved = message.reply ? Boolean(firstTier2Pending(message.reply)) && !message.pendingResolved : false;
  const showRegenerate = canRegenerate && Boolean(message.liveReply) && !message.typing && !pendingUnresolved;

  return (
    <motion.div {...anim} className="flex items-start gap-2.5">
      <Avatar className="mt-0.5 h-7 w-7 shrink-0">
        <AvatarFallback className="bg-primary/10 text-primary">
          <Bot className="h-3.5 w-3.5" />
        </AvatarFallback>
      </Avatar>
      <div className="min-w-0 flex-1">
        {message.typing ? (
          <TypingDots />
        ) : message.doc ? (
          <div
            className={cn(
              "flex max-w-[min(34rem,88vw)] items-start gap-2.5 rounded-xl border px-3.5 py-2.5 text-sm",
              message.doc.suspicious ? "border-border bg-muted/60" : "border-border bg-card"
            )}
          >
            <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
            <div>
              <p className="text-foreground">{message.text}</p>
              {message.doc.findings && message.doc.findings.length > 0 && (
                <div className="mt-2 rounded-lg bg-background/80 px-2.5 py-2 font-mono text-[11px] text-muted-foreground">
                  {message.doc.findings.map((f, i) => (
                    <div key={i} className="truncate">
                      {f}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        ) : message.reply ? (
          <>
            <div className="rounded-2xl bg-muted px-4 py-3">
              <ReplyContent
                message={message}
                policies={policies}
                onConfirm={onConfirm}
                onCancel={onCancel}
                onQuickReply={onQuickReply}
                isLatest={canRegenerate}
                sessionToken={sessionToken}
                autonomy={autonomy}
              />
            </div>
            <div className="mt-1 flex items-center gap-2.5 px-1">
              <CopyButton getText={() => replyCopyText(message.reply!, policies)} label="Copy reply" />
              {!message.typing && !message.replayed && <DownloadPdfButton message={message} policies={policies} token={sessionToken} />}
              {showRegenerate && (
                <button
                  type="button"
                  onClick={onRegenerate}
                  className="inline-flex items-center gap-1 text-xs font-medium text-muted-foreground transition-colors hover:text-foreground"
                >
                  <RefreshCw className="h-3 w-3" />
                  Regenerate
                </button>
              )}
            </div>
          </>
        ) : (
          <>
            <div className="max-w-[min(34rem,88vw)] rounded-2xl bg-muted px-4 py-3 text-sm leading-relaxed">{message.text}</div>
            <div className="mt-1 px-1">
              <CopyButton getText={() => message.text ?? ""} label="Copy" />
            </div>
          </>
        )}
      </div>
    </motion.div>
  );
}
