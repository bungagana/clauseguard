"use client";

import { useRef, useState } from "react";
import { FileUp, Loader2, Paperclip, Send, Sparkles, Square, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import type { AppMode } from "@/lib/appMode";

export function Composer({
  mode,
  awaitingUpload,
  onSend,
  onAttach,
  onUploadPolicy,
  onOpenDemo,
  onStop,
  followUps,
  uploadedFilename,
  onClearUpload,
  uploadBusy,
  sending,
  disabled,
}: {
  mode: AppMode;
  awaitingUpload?: boolean;
  onSend: (text: string) => void;
  onAttach: (file: File) => void;
  onUploadPolicy: (file: File) => void;
  onOpenDemo: () => void;
  onStop: () => void;
  followUps: string[];
  uploadedFilename?: string | null;
  onClearUpload: () => void;
  uploadBusy?: boolean;
  sending: boolean;
  disabled?: boolean;
}) {
  const [value, setValue] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);
  const policyFileInputRef = useRef<HTMLInputElement>(null);

  function submit() {
    if (!value.trim() || sending) return;
    onSend(value);
    setValue("");
  }

  return (
    <div className="border-t border-border bg-background/95 backdrop-blur">
      <div className="mx-auto max-w-3xl px-4 py-3 sm:px-6">
        {followUps.length > 0 && (
          <div className="mb-2.5 flex flex-wrap gap-1.5">
            {followUps.map((f, i) => (
              <button
                key={i}
                type="button"
                onClick={() => onSend(f)}
                disabled={sending}
                className="rounded-full border border-primary/30 bg-secondary px-3 py-1.5 text-xs font-medium text-secondary-foreground transition-colors hover:bg-secondary/70 disabled:opacity-50"
              >
                {f}
              </button>
            ))}
          </div>
        )}

        {(uploadedFilename || uploadBusy) && (
          <div className="mb-2 flex items-center gap-2 rounded-full bg-muted px-3 py-1 text-xs text-muted-foreground">
            {uploadBusy ? <Loader2 className="h-3 w-3 animate-spin" /> : <Paperclip className="h-3 w-3" />}
            <span className="truncate">{uploadBusy ? "Uploading…" : uploadedFilename}</span>
            {!uploadBusy && (
              <button type="button" onClick={onClearUpload} aria-label="Remove attachment">
                <X className="h-3 w-3" />
              </button>
            )}
          </div>
        )}

        <input
          ref={fileInputRef}
          type="file"
          accept="application/pdf,image/*"
          multiple
          className="hidden"
          onChange={(e) => {
            for (const f of Array.from(e.target.files ?? [])) onAttach(f);
            e.target.value = "";
          }}
        />
        <input
          ref={policyFileInputRef}
          type="file"
          accept="application/pdf"
          className="hidden"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) onUploadPolicy(f);
            e.target.value = "";
          }}
        />

        {awaitingUpload ? (
          <button
            type="button"
            onClick={() => policyFileInputRef.current?.click()}
            disabled={uploadBusy}
            className="flex w-full flex-col items-center justify-center gap-2 rounded-2xl border-2 border-dashed border-primary/40 bg-card px-4 py-6 text-center shadow-soft transition-colors hover:border-primary/70 hover:bg-primary/5 disabled:opacity-60"
          >
            {uploadBusy ? <Loader2 className="h-5 w-5 animate-spin text-primary" /> : <FileUp className="h-5 w-5 text-primary" />}
            <span className="text-sm font-medium text-foreground">{uploadBusy ? "Uploading…" : "Upload your policy (PDF) to get started"}</span>
            <span className="text-xs text-muted-foreground">We&apos;ll extract the clauses live and show exactly what it covers.</span>
          </button>
        ) : (
          <div className="flex items-end gap-2 rounded-2xl border border-input bg-card p-2 shadow-soft">
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="shrink-0"
              onClick={() => fileInputRef.current?.click()}
              aria-label="Attach a document to this claim"
              title="Attach a document to this claim"
            >
              <Paperclip className="h-4 w-4" />
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="shrink-0 text-primary"
              onClick={() => policyFileInputRef.current?.click()}
              aria-label="Upload a policy document"
              title="Upload a policy document — extract a new policy from your own PDF, live"
            >
              <FileUp className="h-4 w-4" />
            </Button>
            {mode === "demo" && (
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="shrink-0"
                onClick={onOpenDemo}
                aria-label="Try a demo scene"
                title="Try a demo scene"
              >
                <Sparkles className="h-4 w-4" />
              </Button>
            )}
            <Textarea
              value={value}
              onChange={(e) => setValue(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  submit();
                }
              }}
              placeholder="Ask what's covered, or about a claim…"
              className="min-h-[2.5rem] max-h-32 flex-1 border-0 bg-transparent px-2 py-1.5 shadow-none focus-visible:ring-0"
              rows={1}
              disabled={disabled}
            />
            <Button
              type="button"
              size="icon"
              className="shrink-0"
              onClick={sending ? onStop : submit}
              disabled={disabled || (!sending && !value.trim())}
              aria-label={sending ? "Stop" : "Send"}
              title={sending ? "Stop" : "Send"}
            >
              {sending ? <Square className="h-3.5 w-3.5" /> : <Send className="h-4 w-4" />}
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}
