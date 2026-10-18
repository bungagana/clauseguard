"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Building2, CheckCircle2, Loader2, OctagonX, Play, RefreshCw, ShieldCheck, XCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ThemeToggle } from "@/components/chat/ThemeToggle";
import { insurer, ApiError } from "@/lib/api";
import type { BackofficeClaim, BackofficeClaimDetail, BackofficeTicket } from "@/lib/types";
import { formatDate, formatMoney, humanize } from "@/lib/format";
import { cn } from "@/lib/utils";

const STORAGE_KEY = "clauseguard-admin-token";
const STATUS_STYLE: Record<string, string> = {
  draft: "bg-muted text-muted-foreground",
  submitted: "bg-primary/10 text-primary",
  under_review: "bg-warning/15 text-warning-foreground",
  approved: "bg-success/10 text-success",
  paid: "bg-success/10 text-success",
  rejected: "bg-destructive/10 text-destructive",
};
const FLOW = ["submitted", "under_review", "approved", "paid"] as const;

interface FormSection {
  title: string;
  fields: Array<{ label: string; source: string; value: unknown; state: "filled" | "not_provided" | "to_complete" }>;
}

/**
 * The insurer's desk: a separate back-office application over the same sandbox. Nothing here is
 * reachable by the assistant; it needs the back-office token. This is where the assistant's
 * actions land and where a person decides.
 */
export default function InsurerPage() {
  const [token, setToken] = useState("");
  // open an attached document in a new tab; the admin token travels in a header, so the file is fetched here, not by a plain link
  async function openDocument(docId: string) {
    try {
      const res = await fetch(`/api/cg/backoffice/documents/${encodeURIComponent(docId)}`, { headers: { "X-Admin-Token": token } });
      if (!res.ok) throw new Error(String(res.status));
      const url = URL.createObjectURL(await res.blob());
      window.open(url, "_blank", "noopener");
      setTimeout(() => URL.revokeObjectURL(url), 60000);
    } catch {
      setError("That document could not be opened.");
    }
  }
  const [input, setInput] = useState("");
  const [claims, setClaims] = useState<BackofficeClaim[]>([]);
  const [tickets, setTickets] = useState<BackofficeTicket[]>([]);
  const [halted, setHalted] = useState<boolean | null>(null);
  const [selected, setSelected] = useState<BackofficeClaimDetail | null>(null);
  const [filter, setFilter] = useState<string>("all");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    try {
      setToken(sessionStorage.getItem(STORAGE_KEY) ?? "");
    } catch {
      /* no storage */
    }
  }, []);

  const refresh = useCallback(async (t: string) => {
    if (!t) return;
    setBusy(true);
    try {
      const [k, c, tk] = await Promise.all([insurer.killStatus(t), insurer.claims(t), insurer.tickets(t)]);
      setHalted(k.active);
      setClaims(c);
      setTickets(tk);
      setError(null);
    } catch (e) {
      setError(e instanceof ApiError && e.status === 403 ? "That token was not accepted." : "Could not reach the back office.");
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    if (!token) return;
    void refresh(token);
    const id = setInterval(() => void refresh(token), 10000);
    return () => clearInterval(id);
  }, [token, refresh]);

  async function openClaim(id: string) {
    try {
      const d = await insurer.claim(token, id);
      setSelected(d);
      setNote("");
    } catch {
      setError("Could not load that claim.");
    }
  }

  async function decide(decision: "under_review" | "approved" | "rejected" | "paid") {
    if (!selected) return;
    setBusy(true);
    try {
      await insurer.decide(token, selected.id, decision, note.trim() || undefined);
      await refresh(token);
      await openClaim(selected.id);
    } catch {
      setError("Decision failed.");
    } finally {
      setBusy(false);
    }
  }

  const shown = claims.filter((c) => filter === "all" || c.status === filter);
  const counts = Object.fromEntries(["submitted", "under_review", "approved", "rejected", "paid"].map((s) => [s, claims.filter((c) => c.status === s).length]));

  return (
    <div className="flex min-h-dvh flex-col bg-background text-foreground">
      <header className="border-b border-border bg-card/80 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-3 px-4 py-3 sm:px-6">
          <div className="flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-navy text-navy-foreground">
              <Building2 className="h-4 w-4" />
            </div>
            <div>
              <p className="font-display text-sm font-semibold leading-none">Sandbox Insurer · Claims desk</p>
              <p className="text-[11px] text-muted-foreground">Where the assistant&rsquo;s submissions land. A person decides here.</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {halted !== null && (
              <span className={cn("hidden items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium sm:inline-flex", halted ? "bg-destructive/10 text-destructive" : "bg-success/10 text-success")}>
                {halted ? <OctagonX className="h-3 w-3" /> : <ShieldCheck className="h-3 w-3" />} {halted ? "Assistant halted" : "Assistant running"}
              </span>
            )}
            <Button asChild variant="outline" size="sm"><Link href="/chat?mode=demo">Customer app</Link></Button>
            <ThemeToggle />
          </div>
        </div>
      </header>

      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-6 sm:px-6">
        {!token ? (
          <div className="mx-auto max-w-md rounded-2xl border border-border bg-card p-5 shadow-soft">
            <p className="font-display text-base font-semibold">Back-office sign-in</p>
            <p className="mt-1 text-xs text-muted-foreground">Enter the value of <code>CG_ADMIN_TOKEN</code> configured on the backend. It stays in this tab.</p>
            <div className="mt-3 flex gap-2">
              <input type="password" value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") { try { sessionStorage.setItem(STORAGE_KEY, input.trim()); } catch { /* noop */ } setToken(input.trim()); } }} className="min-w-0 flex-1 rounded-lg border border-input bg-background px-3 py-2 text-sm" placeholder="back-office token" />
              <Button onClick={() => { try { sessionStorage.setItem(STORAGE_KEY, input.trim()); } catch { /* noop */ } setToken(input.trim()); }} disabled={!input.trim()}>Sign in</Button>
            </div>
            {error && <p className="mt-2 text-xs text-destructive">{error}</p>}
          </div>
        ) : (
          <div className="grid gap-6 lg:grid-cols-[1.1fr_1fr]">
            <section>
              <div className="flex flex-wrap items-center gap-2">
                <p className="font-display text-base font-semibold">Claims inbox</p>
                <span className="text-xs text-muted-foreground">{claims.length} on file</span>
                <button type="button" onClick={() => void refresh(token)} className="ml-auto inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
                  {busy ? <Loader2 className="h-3 w-3 animate-spin" /> : <RefreshCw className="h-3 w-3" />} refresh
                </button>
              </div>
              <div className="mt-3 flex flex-wrap gap-1.5">
                {["all", "submitted", "under_review", "approved", "rejected", "paid"].map((s) => (
                  <button key={s} type="button" onClick={() => setFilter(s)} className={cn("rounded-full border px-2.5 py-1 text-xs font-medium", filter === s ? "border-primary bg-primary text-primary-foreground" : "border-border bg-card text-muted-foreground hover:text-foreground")}>
                    {s === "all" ? "All" : humanize(s)}{s !== "all" && counts[s] ? ` · ${counts[s]}` : ""}
                  </button>
                ))}
              </div>
              <ul className="mt-3 flex flex-col gap-1.5">
                {shown.length === 0 && <li className="text-xs text-muted-foreground">Nothing here.</li>}
                {shown.map((c) => (
                  <li key={c.id}>
                    <button type="button" onClick={() => void openClaim(c.id)} className={cn("flex w-full items-center justify-between gap-3 rounded-xl border bg-card px-3.5 py-2.5 text-left shadow-soft transition-colors hover:border-primary/40", selected?.id === c.id ? "border-primary" : "border-border")}>
                      <div className="min-w-0">
                        <p className="font-mono text-xs font-semibold">{c.id}</p>
                        <p className="truncate text-xs text-muted-foreground">
                          {c.customer_id} · {c.policy_id} · {c.event_type ? humanize(c.event_type) : "—"}{c.filed_date ? ` · filed ${formatDate(c.filed_date)}` : ""}{c.created_via === "assistant" ? " · via assistant" : ""}
                        </p>
                      </div>
                      <div className="flex shrink-0 flex-col items-end gap-1">
                        {c.claim_amount ? <span className="text-xs font-semibold tabular-nums">{formatMoney(String(c.claim_amount), "IDR")}</span> : null}
                        <span className={cn("rounded-full px-2 py-0.5 text-[10px] font-medium", STATUS_STYLE[c.status ?? ""] ?? "bg-muted text-muted-foreground")}>{humanize(c.status ?? "")}</span>
                      </div>
                    </button>
                  </li>
                ))}
              </ul>

              <div className="mt-6">
                <p className="font-display text-base font-semibold">Tickets for a person</p>
                <ul className="mt-2 flex flex-col gap-1.5">
                  {tickets.length === 0 && <li className="text-xs text-muted-foreground">No tickets.</li>}
                  {tickets.slice(0, 10).map((t) => (
                    <li key={t.id} className="rounded-xl border border-border bg-card px-3.5 py-2.5 text-xs shadow-soft">
                      <div className="flex items-center justify-between gap-2">
                        <span className="font-mono font-semibold">{t.id}</span>
                        <span className="rounded-full bg-warning/15 px-2 py-0.5 text-[10px] font-medium text-warning-foreground">{humanize(t.status)}</span>
                      </div>
                      <p className="mt-0.5 text-muted-foreground">{t.customer_id} · {humanize(t.type)}{t.requested_via ? ` · ${t.requested_via}` : ""}{t.note ? ` · ${t.note}` : ""}</p>
                    </li>
                  ))}
                </ul>
              </div>
            </section>

            <section className="flex flex-col gap-4">
              <div className={cn("flex items-center justify-between gap-3 rounded-2xl border p-4 shadow-soft", halted ? "border-destructive/40 bg-destructive/5" : "border-success/40 bg-success/5")}>
                <div>
                  <p className="text-sm font-semibold">{halted === null ? "Checking the assistant…" : halted ? "Assistant halted" : "Assistant running"}</p>
                  <p className="text-xs text-muted-foreground">{halted ? "Every assistant action is refused for every customer until resumed." : "The insurer can stop every assistant action at once."}</p>
                </div>
                <Button size="sm" variant={halted ? "default" : "destructive"} disabled={busy || halted === null} onClick={async () => { setBusy(true); try { const r = halted ? await insurer.resume(token) : await insurer.halt(token, "halted from the claims desk"); setHalted(r.active); } catch { setError("The halt switch did not respond."); } finally { setBusy(false); } }}>
                  {halted ? <Play className="h-3.5 w-3.5" /> : <OctagonX className="h-3.5 w-3.5" />} {halted ? "Resume" : "Halt assistant"}
                </Button>
              </div>

              {selected ? (
                <div className="rounded-2xl border border-border bg-card p-4 shadow-soft">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="font-mono text-sm font-semibold">{selected.id}</p>
                      <p className="text-xs text-muted-foreground">{selected.customer_name ?? selected.customer_id} · {selected.policy_id}</p>
                    </div>
                    <span className={cn("rounded-full px-2.5 py-0.5 text-xs font-medium", STATUS_STYLE[selected.status ?? ""] ?? "")}>{humanize(selected.status ?? "")}</span>
                  </div>

                  <ol className="mt-3 flex items-center gap-1 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
                    {FLOW.map((s, i) => {
                      const idx = FLOW.indexOf((selected.status as typeof FLOW[number]) ?? "submitted");
                      const done = selected.status === "rejected" ? i === 0 : i <= idx;
                      return (
                        <li key={s} className="flex items-center gap-1">
                          <span className={cn("h-2 w-2 rounded-full", done ? "bg-primary" : "bg-border")} />
                          <span className={done ? "text-foreground" : ""}>{humanize(s)}</span>
                          {i < FLOW.length - 1 && <span className="mx-1 h-px w-4 bg-border" />}
                        </li>
                      );
                    })}
                    {selected.status === "rejected" && <li className="ml-2 text-destructive">Rejected</li>}
                  </ol>

                  <p className="mt-4 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    {typeof selected.form?.form_title === "string" ? selected.form.form_title : "Submitted form"}
                  </p>
                  {Array.isArray(selected.form?.sections) && (selected.form.sections as FormSection[]).length > 0 && (
                    <div className="mt-1.5 rounded-xl border border-border/70 p-3">
                      {(selected.form.sections as FormSection[]).map((s) => (
                        <div key={s.title} className="mb-2.5 last:mb-0">
                          <p className="text-[11px] font-semibold uppercase tracking-wide text-primary/80">{s.title}</p>
                          <dl className="mt-1 text-xs">
                            {s.fields.map((f) => (
                              <div key={f.label} className="grid grid-cols-[11rem_1fr] gap-2 border-b border-border/60 py-1 last:border-b-0">
                                <dt className="text-[11px] uppercase tracking-wide text-muted-foreground">{f.label}</dt>
                                <dd className="break-words">
                                  {f.source === "documents_checklist" && Array.isArray(f.value)
                                    ? (f.value as Array<{ code: string; label: string; attached: boolean; state?: string }>).map((c) => (
                                        <span key={c.code} className={cn("mr-2 inline-block", c.attached ? "" : c.state === "declared" ? "text-warning-foreground" : "text-muted-foreground line-through")}>
                                          {c.label}{c.state === "declared" ? " (declared, not attached)" : ""}
                                        </span>
                                      ))
                                    : f.state === "to_complete"
                                      ? <span className="text-muted-foreground">(to be completed by the customer)</span>
                                      : f.state === "not_provided"
                                        ? <span className="text-muted-foreground">not provided</span>
                                        : typeof f.value === "boolean"
                                          ? (f.value ? "yes" : "no")
                                          : /amount/.test(f.source) ? formatMoney(String(f.value), "IDR") : Array.isArray(f.value) ? f.value.map((x) => humanize(String(x))).join(", ") : String(f.value)}
                                </dd>
                              </div>
                            ))}
                          </dl>
                        </div>
                      ))}
                      <p className="mt-2 text-[11px] text-muted-foreground">{selected.form.form_layout_source === "policy_clauses" ? "Layout derived from this policy's own wording; values are typed facts from the customer's session." : "Standard layout; values are typed facts from the customer's session."}</p>
                    </div>
                  )}
                  {selected.form ? (
                    <dl className="mt-1.5 text-xs">
                      {Object.entries(selected.form).filter(([k, v]) => !["sections", "form_title", "form_layout_source"].includes(k) && v !== null && v !== undefined && v !== "" && !(Array.isArray(v) && v.length === 0)).map(([k, v]) => (
                        <div key={k} className="grid grid-cols-[11rem_1fr] gap-2 border-b border-border/60 py-1 last:border-b-0">
                          <dt className="text-[11px] uppercase tracking-wide text-muted-foreground">{humanize(k)}</dt>
                          <dd className="break-words">{typeof v === "boolean" ? (v ? "yes" : "no") : Array.isArray(v) ? v.map((x) => humanize(String(x))).join(", ") : /amount/.test(k) && !Number.isNaN(Number(v)) ? formatMoney(String(v), "IDR") : String(v)}</dd>
                        </div>
                      ))}
                    </dl>
                  ) : (
                    <p className="mt-1 text-xs text-muted-foreground">No form on file (a seeded claim, not one the assistant submitted).</p>
                  )}

                  <p className="mt-4 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Documents</p>
                  <ul className="mt-1.5 text-xs text-muted-foreground">
                    {selected.documents.length === 0 && <li>None attached.</li>}
                    {selected.documents.map((d) => (
                      <li key={d.id}>
                        <a href={`/api/cg/backoffice/documents/${encodeURIComponent(d.id)}`} target="_blank" rel="noreferrer" className="underline-offset-4 hover:underline" onClick={(e) => { e.preventDefault(); void openDocument(d.id); }}>
                          {d.id}
                        </a>{" "}
                        · {humanize(d.type)} · {d.taint_label}
                      </li>
                    ))}
                  </ul>

                  {selected.decision_note && <p className="mt-3 rounded-lg bg-muted px-3 py-2 text-xs"><span className="font-semibold">Note:</span> {selected.decision_note}{selected.decided_at ? ` · ${selected.decided_at.slice(0, 16).replace("T", " ")}` : ""}</p>}

                  <div className="mt-4">
                    <label className="text-xs font-semibold uppercase tracking-wide text-muted-foreground" htmlFor="note">Decision note (the customer will see it)</label>
                    <textarea id="note" value={note} onChange={(e) => setNote(e.target.value)} rows={2} className="mt-1 w-full rounded-lg border border-input bg-background px-3 py-2 text-sm" placeholder="e.g. Approved at the policy limit; itemised bill verified." />
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      <Button size="sm" variant="outline" disabled={busy} onClick={() => decide("under_review")}>Start review</Button>
                      <Button size="sm" disabled={busy} onClick={() => decide("approved")}><CheckCircle2 className="h-3.5 w-3.5" /> Approve</Button>
                      <Button size="sm" variant="destructive" disabled={busy} onClick={() => decide("rejected")}><XCircle className="h-3.5 w-3.5" /> Reject</Button>
                      <Button size="sm" variant="secondary" disabled={busy} onClick={() => decide("paid")}>Mark paid</Button>
                    </div>
                    <p className="mt-2 text-[11px] text-muted-foreground">Decisions are made here by a person. The assistant can only read the result and help the customer respond.</p>
                  </div>
                </div>
              ) : (
                <div className="rounded-2xl border border-dashed border-border p-6 text-center text-sm text-muted-foreground">Select a claim to see the form the assistant submitted.</div>
              )}
              {error && <p className="text-xs text-destructive">{error}</p>}
            </section>
          </div>
        )}
      </main>
    </div>
  );
}
