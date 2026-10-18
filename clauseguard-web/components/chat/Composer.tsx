"use client";

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { FileText, FileUp, Image as ImageIcon, Loader2, Paperclip, Repeat2, Send, Sparkles, Square, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import type { AppMode } from "@/lib/appMode";

function AttachmentCard({ file, name, caption, onOpen, onRemove, onSwitch, switchLabel }: { file?: File; name: string; caption: string; onOpen: () => void; onRemove: () => void; onSwitch?: () => void; switchLabel?: string }) {
  const isImage = file?.type.startsWith("image/");
  const kb = file ? Math.max(1, Math.round(file.size / 1024)) : null;
  return (
    <div className="group relative flex w-44 items-center gap-2 rounded-xl border border-border bg-card px-2.5 py-2 text-left shadow-soft">
      <button type="button" onClick={onOpen} disabled={!file} className="flex min-w-0 flex-1 items-center gap-2 text-left disabled:cursor-default" title={file ? "Click to preview" : name}>
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
          {isImage ? <ImageIcon className="h-4 w-4" /> : <FileText className="h-4 w-4" />}
        </span>
        <span className="min-w-0">
          <span className="block truncate text-xs font-medium">{name}</span>
          <span className="block truncate text-[10px] text-muted-foreground">
            {caption}
            {kb ? ` · ${kb} KB` : ""}
          </span>
        </span>
      </button>
      {onSwitch && switchLabel && (
        <button type="button" onClick={onSwitch} title={switchLabel} aria-label={switchLabel} className="shrink-0 rounded-full p-1 text-muted-foreground hover:bg-muted hover:text-foreground">
          <Repeat2 className="h-3.5 w-3.5" />
        </button>
      )}
      <button type="button" onClick={onRemove} aria-label={`Remove ${name}`} className="shrink-0 rounded-full p-1 text-muted-foreground hover:bg-muted hover:text-foreground">
        <X className="h-3.5 w-3.5" />
      </button>
    </div>
  );
}

export function Composer({
  mode,
  awaitingUpload,
  onSend,
  onAttach,
  onUploadPolicy,
  onOpenDemo,
  onStop,
  followUps,
  attachments,
  onRemoveAttachment,
  uploadBusy,
  sending,
  disabled,
}: {
  mode: AppMode;
  awaitingUpload?: boolean;
  onSend: (text: string) => void;
  onAttach: (file: File) => void;
  onUploadPolicy: (file: File) => void | Promise<void>;
  onOpenDemo: () => void;
  onStop: () => void;
  followUps: string[];
  attachments: Array<{ doc_id: string; filename: string; file?: File }>;
  onRemoveAttachment: (docId: string) => void;
  uploadBusy?: boolean;
  sending: boolean;
  disabled?: boolean;
}) {
  const [value, setValue] = useState("");
  // a policy chosen from the folder waits here; it is read when the customer presses Send, like any attachment
  const [policyFiles, setPolicyFiles] = useState<File[]>([]);
  const [previewing, setPreviewing] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  useEffect(() => {
    if (!previewing) {
      setPreviewUrl(null);
      return;
    }
    const url = URL.createObjectURL(previewing);
    setPreviewUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [previewing]);
  useEffect(() => {
    if (!previewing) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setPreviewing(null);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [previewing]);
  const fileInputRef = useRef<HTMLInputElement>(null);

  async function submit() {
    if ((!value.trim() && policyFiles.length === 0) || sending) return;
    const text = value;
    const files = policyFiles;
    setValue("");
    setPolicyFiles([]);
    for (const f of files) await onUploadPolicy(f);
    if (text.trim()) onSend(text);
  }

  // One attach button for everything. A file is a claim document unless the account has no policy yet, in which
  // case the first file is taken as the customer's policy. Every card can be switched with one tap.
  function addFile(file: File) {
    if (awaitingUpload && policyFiles.length === 0 && attachments.length === 0) setPolicyFiles((p) => [...p, file]);
    else onAttach(file);
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

        {(policyFiles.length > 0 || attachments.length > 0 || uploadBusy) && (
          <div className="mb-2 flex flex-wrap gap-2">
            {policyFiles.map((f, i) => (
              <AttachmentCard
                key={`${f.name}-${i}`}
                file={f}
                name={f.name}
                caption="My policy"
                switchLabel="Use as a claim document"
                onSwitch={() => {
                  setPolicyFiles((p) => p.filter((_, j) => j !== i));
                  onAttach(f);
                }}
                onOpen={() => setPreviewing(f)}
                onRemove={() => setPolicyFiles((p) => p.filter((_, j) => j !== i))}
              />
            ))}
            {attachments.map((d) => (
              <AttachmentCard
                key={d.doc_id}
                file={d.file}
                name={d.filename}
                caption="Claim document"
                switchLabel={d.file ? "Use as my policy" : undefined}
                onSwitch={() => {
                  if (!d.file) return;
                  onRemoveAttachment(d.doc_id);
                  setPolicyFiles((p) => [...p, d.file as File]);
                }}
                onOpen={() => d.file && setPreviewing(d.file)}
                onRemove={() => onRemoveAttachment(d.doc_id)}
              />
            ))}
            {uploadBusy && (
              <div className="flex items-center gap-2 rounded-xl border border-border bg-muted px-3 py-2 text-xs text-muted-foreground">
                <Loader2 className="h-3.5 w-3.5 animate-spin" /> Uploading…
              </div>
            )}
          </div>
        )}

        {previewing && previewUrl && createPortal(
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" role="dialog" aria-modal="true" aria-label={`Preview ${previewing.name}`} onClick={() => setPreviewing(null)}>
            <div className="flex h-[85vh] w-full max-w-3xl flex-col rounded-2xl border border-border bg-card shadow-xl" onClick={(e) => e.stopPropagation()}>
              <div className="flex items-center justify-between gap-3 border-b border-border px-4 py-3">
                <p className="truncate text-sm font-semibold">{previewing.name}</p>
                <button type="button" onClick={() => setPreviewing(null)} aria-label="Close preview" className="rounded p-1 hover:bg-muted">
                  <X className="h-4 w-4" />
                </button>
              </div>
              {previewing.type.startsWith("image/") ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={previewUrl} alt={previewing.name} className="min-h-0 flex-1 object-contain p-4" />
              ) : (
                <iframe title={previewing.name} src={previewUrl} className="min-h-0 flex-1 rounded-b-2xl bg-white" />
              )}
            </div>
          </div>,
          document.body
        )}

        <input
          ref={fileInputRef}
          type="file"
          accept="application/pdf,image/*"
          multiple
          className="hidden"
          onChange={(e) => {
            for (const f of Array.from(e.target.files ?? [])) addFile(f);
            e.target.value = "";
          }}
        />

        {awaitingUpload && (
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            disabled={uploadBusy}
            className="mb-2.5 flex w-full items-center gap-3 rounded-2xl border border-dashed border-primary/40 bg-primary/5 px-4 py-3 text-left transition-colors hover:border-primary/70 hover:bg-primary/10 disabled:opacity-60"
          >
            {uploadBusy ? <Loader2 className="h-5 w-5 shrink-0 animate-spin text-primary" /> : <FileUp className="h-5 w-5 shrink-0 text-primary" />}
            <span className="min-w-0">
              <span className="block text-sm font-medium text-foreground">{uploadBusy ? "Reading your policy…" : "Upload your policy (PDF) to get answers about your own cover"}</span>
              <span className="block text-xs text-muted-foreground">The clauses are extracted live. You can also type a general question below.</span>
            </span>
          </button>
        )}
        <div className="flex items-end gap-2 rounded-2xl border border-input bg-card p-2 shadow-soft">
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="shrink-0"
              onClick={() => fileInputRef.current?.click()}
              aria-label="Attach a file: a claim document or your policy"
              title="Attach a file: a claim document or your policy"
            >
              <Paperclip className="h-4 w-4" />
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
                  void submit();
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
              onClick={sending ? onStop : () => void submit()}
              disabled={disabled || (!sending && !value.trim() && policyFiles.length === 0)}
              aria-label={sending ? "Stop" : "Send"}
              title={sending ? "Stop" : "Send"}
            >
              {sending ? <Square className="h-3.5 w-3.5" /> : <Send className="h-4 w-4" />}
            </Button>
          </div>
      </div>
    </div>
  );
}
