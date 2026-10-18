"use client";

import { useEffect, useState } from "react";
import { AlertTriangle, Check, Download, Eye, FileText, Loader2, Pencil, X } from "lucide-react";
import { exportPdf, getChatPending, getMyClaim } from "@/lib/api";
import type { PoliciesResponse } from "@/lib/types";
import { policyName } from "@/lib/clauses";
import { formatDate, formatMoney, humanize } from "@/lib/format";
import { downloadBlob } from "@/lib/exportPdf";

import type { ChecklistItem, ClaimDraft as Draft, FormField } from "@/lib/replayTypes";

const DATE_SOURCES = new Set(["admission_date", "discharge_date", "filing_deadline", "date_prepared"]);
const MONEY_SOURCES = new Set(["billed_amount", "claimed_amount"]);

function fieldText(f: FormField, currency: string): string {
  if (f.state === "to_complete") return "(to be completed by hand)";
  if (f.state === "not_provided") return "—";
  const v = f.value;
  if (typeof v === "boolean") return v ? "Yes" : "No";
  if (DATE_SOURCES.has(f.source) && typeof v === "string") return formatDate(v);
  if (MONEY_SOURCES.has(f.source)) return formatMoney(String(v), currency);
  if (Array.isArray(v)) return v.map((x) => humanize(String(x))).join(", ");
  if (f.source === "event" || f.source === "cause") return humanize(String(v));
  return String(v);
}

// Fields the customer states about themselves and the event. The rest is derived (policy, insurer, deadline,
// amount claimed, documents) and can only change by changing the facts or the documents behind it.
const EDITABLE: Record<string, { input: "text" | "date" | "number"; say: (v: string) => string }> = {
  insured_name: { input: "text", say: (v) => `The insured person's name is ${v}.` },
  claimant_name: { input: "text", say: (v) => `The person submitting the claim is ${v}.` },
  facility_name: { input: "text", say: (v) => `The hospital is ${v}.` },
  diagnosis: { input: "text", say: (v) => `The diagnosis is ${v}.` },
  admission_date: { input: "date", say: (v) => `The admission date is ${v}.` },
  discharge_date: { input: "date", say: (v) => `The discharge date is ${v}.` },
  billed_amount: { input: "number", say: (v) => `The total hospital bill is ${v} rupiah.` },
};

function Row({ k, v, onEdit }: { k: string; v: React.ReactNode; onEdit?: { input: "text" | "date" | "number"; current: string; send: (value: string) => void } }) {
  const [editing, setEditing] = useState(false);
  const [val, setVal] = useState("");
  if (v === null || v === undefined || v === "") return null;
  return (
    <div className="grid grid-cols-[9.5rem_1fr] gap-2 border-b border-border/60 py-1 last:border-b-0">
      <dt className="text-[11px] uppercase tracking-wide text-muted-foreground">{k}</dt>
      <dd className="flex items-start gap-1.5 text-xs text-foreground">
        {editing && onEdit ? (
          <form
            className="flex w-full items-center gap-1.5"
            onSubmit={(e) => {
              e.preventDefault();
              if (val.trim()) onEdit.send(val.trim());
              setEditing(false);
            }}
          >
            <input
              autoFocus
              type={onEdit.input}
              value={val}
              onChange={(e) => setVal(e.target.value)}
              className="min-w-0 flex-1 rounded-md border border-input bg-background px-2 py-1 text-xs outline-none focus-visible:ring-2 focus-visible:ring-ring"
            />
            <button type="submit" aria-label="Apply change" className="rounded p-1 text-success hover:bg-muted"><Check className="h-3.5 w-3.5" /></button>
            <button type="button" aria-label="Cancel change" onClick={() => setEditing(false)} className="rounded p-1 text-muted-foreground hover:bg-muted"><X className="h-3.5 w-3.5" /></button>
          </form>
        ) : (
          <>
            <span className="min-w-0 flex-1">{v}</span>
            {onEdit && (
              <button
                type="button"
                aria-label={`Edit ${k}`}
                title="Correct this value"
                onClick={() => {
                  setVal(onEdit.input === "number" ? onEdit.current.replace(/[^0-9]/g, "") : onEdit.input === "date" ? onEdit.current : onEdit.current === "—" ? "" : onEdit.current);
                  setEditing(true);
                }}
                className="shrink-0 rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
              >
                <Pencil className="h-3 w-3" />
              </button>
            )}
          </>
        )}
      </dd>
    </div>
  );
}

/**
 * The claim form exactly as it will be sent to the insurer, field by field, so what the customer
 * confirms is what leaves. Read from the server's pending-action record (the draft the engine
 * prepared), never rebuilt in the browser. When the draft carries the insurer's own form layout
 * (derived from that policy's clauses), the form follows it; otherwise the standard rows show.
 */
export function ClaimFormPreview({ token, tool, policies, recordedDraft, claimId, sent, onCorrect }: {
  token?: string;
  tool: string;
  policies: PoliciesResponse | null;
  recordedDraft?: Draft;
  claimId?: string; // a claim already filed: the form is read from the customer's own claim record
  sent?: boolean; // heading for a form that has already been sent
  onCorrect?: (text: string) => void; // a pending form: the customer corrects a value, which goes back through the agent
}) {
  const replay = Boolean(recordedDraft); // a recorded scene carries its own draft: nothing is fetched, nothing is exported
  const [draft, setDraft] = useState<Draft | null | undefined>(recordedDraft ?? undefined);
  const [busy, setBusy] = useState(false);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  useEffect(() => () => { if (previewUrl) URL.revokeObjectURL(previewUrl); }, [previewUrl]);
  useEffect(() => {
    let cancelled = false;
    if (replay || !token) return;
    if (claimId) {
      getMyClaim(token, claimId)
        .then((c) => {
          const f = (c.form ?? {}) as Record<string, unknown>;
          const d: Draft = {
            policy_id: c.policy_id,
            currency: (f.currency as string) ?? "IDR",
            form_title: f.form_title as string | undefined,
            form_layout_source: f.form_layout_source as Draft["form_layout_source"],
            form_sections: (f.sections as Draft["form_sections"]) ?? [],
          };
          if (!cancelled) setDraft(d.form_sections?.length ? d : null);
        })
        .catch(() => !cancelled && setDraft(null));
      return () => {
        cancelled = true;
      };
    }
    getChatPending(token)
      .then((res) => {
        const p = res.pending.find((x) => x.tool === tool) as { args?: Record<string, { value?: unknown }> } | undefined;
        const d = p?.args?.draft_handle?.value as Draft | undefined;
        if (!cancelled) setDraft(d ?? null);
      })
      .catch(() => !cancelled && setDraft(null));
    return () => {
      cancelled = true;
    };
  }, [token, tool, replay, claimId]);

  if (draft === undefined) return <p className="mt-2 inline-flex items-center gap-1.5 text-xs text-muted-foreground"><Loader2 className="h-3 w-3 animate-spin" /> Loading the form…</p>;
  if (draft === null) return null;
  const currency = draft.currency ?? "IDR";
  const sections = draft.form_sections ?? [];

  function exportBody() {
    if (!draft) return null;
    return {
        title: (draft.form_title ?? "Claim form").slice(0, 120),
        subtitle: `${policyName(policies, draft.policy_id ?? "")} (${draft.policy_id}) · prepared by the assistant from your answers and the policy wording`,
        sections: sections.map((s) => ({
          heading: s.title.slice(0, 120),
          lines: s.fields.flatMap((f) =>
            f.source === "documents_checklist" && Array.isArray(f.value)
              ? [`${f.label}:`, ...(f.value as ChecklistItem[]).map((c) => `  [${c.attached ? "x" : " "}] ${c.label}${c.state === "declared" ? " (declared by the customer, not attached)" : ""}`)]
              : [`${f.label}: ${fieldText(f, currency)}`]
          ),
        })),
        footer: "This form was prepared by the assistant and sent only after the customer's confirmation. The insurer decides the claim.",
    };
  }

  async function preview() {
    const body = exportBody();
    if (!body || busy || !token) return;
    if (previewUrl) {
      setPreviewUrl(null);
      return;
    }
    setBusy(true);
    try {
      const blob = await exportPdf(token as string, body);
      setPreviewUrl(URL.createObjectURL(blob));
    } catch {
      /* the button simply stays available */
    } finally {
      setBusy(false);
    }
  }

  async function download() {
    const body = exportBody();
    if (!body || busy || !token) return;
    setBusy(true);
    try {
      const blob = await exportPdf(token as string, body);
      downloadBlob(blob, `${body.title.toLowerCase().replace(/[^a-z0-9]+/g, "-").slice(0, 60)}.pdf`);
    } catch {
      /* the button simply stays available */
    } finally {
      setBusy(false);
    }
  }

  if (sections.length > 0) {
    return (
      <div className="mt-2.5 rounded-lg border border-border bg-card p-3">
        <div className="flex items-start justify-between gap-2">
          <div>
            <p className="inline-flex items-center gap-1.5 text-xs font-semibold"><FileText className="h-3.5 w-3.5 text-primary" /> {draft.form_title ?? (sent ? "Claim form that was sent" : "Claim form that will be sent")}</p>
            <p className="mt-0.5 text-[11px] text-muted-foreground">
              {sent ? "This is the form the insurer received. " : ""}
              {draft.form_layout_source === "policy_clauses" ? "Laid out from this insurer's own policy wording; values from your answers only." : "Standard form; values from your answers only."}
            </p>
          </div>
          <div className={replay ? "hidden" : "flex shrink-0 gap-1.5"}>
            <button type="button" onClick={preview} disabled={busy} className="inline-flex items-center gap-1 rounded-full border border-border px-2.5 py-1 text-[11px] font-medium hover:bg-muted disabled:opacity-60">
              {busy ? <Loader2 className="h-3 w-3 animate-spin" /> : <Eye className="h-3 w-3" />} {previewUrl ? "Hide preview" : "Preview"}
            </button>
            <button type="button" onClick={download} disabled={busy} className="inline-flex items-center gap-1 rounded-full border border-border px-2.5 py-1 text-[11px] font-medium hover:bg-muted disabled:opacity-60">
              <Download className="h-3 w-3" /> PDF
            </button>
          </div>
        </div>
        {previewUrl && <iframe title="Claim form preview" src={previewUrl} className="mt-2.5 h-[28rem] w-full rounded-lg border border-border bg-white" />}
        {sections.map((s) => (
          <div key={s.title} className="mt-2.5">
            <p className="text-[11px] font-semibold uppercase tracking-wide text-primary/80">{s.title}</p>
            <dl className="mt-1">
              {s.fields.map((f) =>
                f.source === "documents_checklist" && Array.isArray(f.value) ? (
                  <div key={f.label} className="border-b border-border/60 py-1 last:border-b-0">
                    <dt className="text-[11px] uppercase tracking-wide text-muted-foreground">{f.label}</dt>
                    <dd className="mt-0.5 flex flex-col gap-0.5 text-xs">
                      {(f.value as ChecklistItem[]).map((c) => (
                        <span key={c.code} className="inline-flex items-center gap-1.5">
                          {c.attached ? <Check className="h-3 w-3 text-success" /> : c.state === "declared" ? <AlertTriangle className="h-3 w-3 text-warning-foreground" /> : <X className="h-3 w-3 text-destructive" />}
                          <span className={c.attached ? "" : "text-muted-foreground"}>
                            {c.label}
                            {c.state === "declared" && <span className="ml-1 text-[10px] text-warning-foreground">declared, not attached</span>}
                          </span>
                        </span>
                      ))}
                    </dd>
                  </div>
                ) : (
                  <Row
                    key={f.label}
                    k={f.label}
                    v={<span className={f.state === "filled" ? "" : "text-muted-foreground"}>{fieldText(f, currency)}</span>}
                    onEdit={
                      onCorrect && !replay && !sent && EDITABLE[f.source]
                        ? {
                            input: EDITABLE[f.source].input,
                            current: typeof f.value === "string" || typeof f.value === "number" ? String(f.value) : "",
                            send: (value) => onCorrect(EDITABLE[f.source].say(value)),
                          }
                        : undefined
                    }
                  />
                )
              )}
            </dl>
          </div>
        ))}
      </div>
    );
  }

  const facts = draft.facts?.values ?? {};
  const amount = draft.claim_amount ?? draft.amount;
  const attached = draft.document_handles?.length ?? 0;
  const required = draft.required_documents ?? [];
  const acknowledged = draft.missing_documents ?? [];
  return (
    <div className="mt-2.5 rounded-lg border border-border bg-card p-3">
      <p className="inline-flex items-center gap-1.5 text-xs font-semibold"><FileText className="h-3.5 w-3.5 text-primary" /> Claim form that will be sent</p>
      <dl className="mt-1.5">
        <Row k="Policy" v={`${policyName(policies, draft.policy_id ?? "")} (${draft.policy_id})`} />
        <Row k="Event" v={draft.event ? humanize(draft.event) : null} />
        <Row k="Admitted" v={draft.admission ? formatDate(draft.admission) : null} />
        <Row k="Discharged" v={draft.discharge ? formatDate(draft.discharge) : null} />
        <Row k="Days in hospital" v={facts.days_hospitalized != null ? String(facts.days_hospitalized) : null} />
        <Row k="Cause" v={facts.cause ? humanize(String(facts.cause)) : null} />
        <Row k="Diagnosis" v={draft.diagnosis ? humanize(draft.diagnosis) : null} />
        <Row k="Hospital bill" v={facts.billed_amount != null ? formatMoney(String(facts.billed_amount), currency) : null} />
        <Row k="Amount claimed" v={amount != null ? formatMoney(String(amount), currency) : null} />
        <Row k="Documents" v={`${attached} attached of ${required.length} required${acknowledged.length ? ` · ${acknowledged.length} missing, acknowledged` : ""}`} />
        <Row k="Declaration" v="Prepared by the assistant from your answers and the policy wording; sent only after your confirmation; the insurer decides." />
      </dl>
    </div>
  );
}
