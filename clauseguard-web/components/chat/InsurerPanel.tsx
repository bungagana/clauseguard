"use client";

import { useCallback, useEffect, useState } from "react";
import { Building2, Loader2, OctagonX, Play, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { insurer, ApiError } from "@/lib/api";
import type { BackofficeClaim, BackofficeTicket } from "@/lib/types";
import { formatMoney } from "@/lib/format";
import { cn } from "@/lib/utils";

const STORAGE_KEY = "clauseguard-admin-token";

function readToken(): string {
  try {
    return sessionStorage.getItem(STORAGE_KEY) ?? "";
  } catch {
    return "";
  }
}

/**
 * The insurer's side of the sandbox: what the agent's actions look like when they land at the
 * other end. Claims submitted after a Confirm tap, tickets opened for a human, and the insurer's
 * own halt switch for the agent. Everything here needs the back-office token; the agent has no
 * tool that reaches any of it.
 */
export function InsurerPanel({ open, onOpenChange, onKillSwitchChange }: { open: boolean; onOpenChange: (o: boolean) => void; onKillSwitchChange?: (active: boolean) => void }) {
  const [token, setToken] = useState("");
  const [input, setInput] = useState("");
  const [halted, setHalted] = useState<boolean | null>(null);
  const [claims, setClaims] = useState<BackofficeClaim[]>([]);
  const [tickets, setTickets] = useState<BackofficeTicket[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setToken(readToken());
  }, []);

  const refresh = useCallback(async (t: string) => {
    if (!t) return;
    setBusy(true);
    try {
      const [k, c, tk] = await Promise.all([insurer.killStatus(t), insurer.claims(t), insurer.tickets(t)]);
      setHalted(k.active);
      onKillSwitchChange?.(k.active);
      setClaims(c);
      setTickets(tk);
      setError(null);
    } catch (e) {
      setError(e instanceof ApiError && e.status === 403 ? "That token was not accepted." : "Could not reach the back office.");
    } finally {
      setBusy(false);
    }
  }, [onKillSwitchChange]);

  useEffect(() => {
    if (!open || !token) return;
    void refresh(token);
    const id = setInterval(() => void refresh(token), 8000);
    return () => clearInterval(id);
  }, [open, token, refresh]);

  async function toggleHalt() {
    if (!token || halted === null) return;
    setBusy(true);
    try {
      const r = halted ? await insurer.resume(token) : await insurer.halt(token, "halted from the insurer console");
      setHalted(r.active);
      onKillSwitchChange?.(r.active);
    } catch {
      setError("The halt switch did not respond.");
    } finally {
      setBusy(false);
    }
  }

  function saveToken() {
    const t = input.trim();
    try {
      sessionStorage.setItem(STORAGE_KEY, t);
    } catch {
      /* private mode: token lives for this render only */
    }
    setToken(t);
    setInput("");
  }

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="flex w-full flex-col gap-4 overflow-y-auto sm:max-w-lg">
        <SheetHeader>
          <SheetTitle className="inline-flex items-center gap-2">
            <Building2 className="h-4 w-4" /> Insurer side
            <a href="/insurer" target="_blank" rel="noreferrer" className="ml-auto text-xs font-medium text-primary hover:underline">Open the full claims desk ↗</a>
          </SheetTitle>
          <SheetDescription>What the agent&rsquo;s actions look like from the insurer&rsquo;s desk. The agent has no tool that reaches this screen.</SheetDescription>
        </SheetHeader>

        {!token ? (
          <div className="rounded-xl border border-border bg-muted/40 p-3 text-sm">
            <p className="font-medium">Back-office token</p>
            <p className="mt-0.5 text-xs text-muted-foreground">The value of <code>CG_ADMIN_TOKEN</code> on the backend. Kept in this tab only.</p>
            <div className="mt-2 flex gap-2">
              <input type="password" value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={(e) => e.key === "Enter" && saveToken()} className="min-w-0 flex-1 rounded-lg border border-input bg-background px-2.5 py-1.5 text-sm" placeholder="token" />
              <Button size="sm" onClick={saveToken} disabled={!input.trim()}>Open</Button>
            </div>
          </div>
        ) : (
          <>
            <div className={cn("flex items-center justify-between gap-3 rounded-xl border p-3", halted ? "border-destructive/40 bg-destructive/5" : "border-success/40 bg-success/5")}>
              <div>
                <p className="text-sm font-semibold">{halted === null ? "Checking…" : halted ? "Agent halted" : "Agent running"}</p>
                <p className="text-xs text-muted-foreground">
                  {halted ? "Every tool call is refused until the insurer resumes it. Customers still get a plain explanation." : "The insurer can stop every agent action at once, for every customer."}
                </p>
              </div>
              <Button size="sm" variant={halted ? "default" : "destructive"} onClick={toggleHalt} disabled={busy || halted === null}>
                {halted ? <Play className="h-3.5 w-3.5" /> : <OctagonX className="h-3.5 w-3.5" />}
                {halted ? "Resume" : "Halt agent"}
              </Button>
            </div>

            <section>
              <div className="flex items-center justify-between">
                <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Claims inbox</p>
                <button type="button" onClick={() => void refresh(token)} className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
                  {busy ? <Loader2 className="h-3 w-3 animate-spin" /> : <RefreshCw className="h-3 w-3" />} refresh
                </button>
              </div>
              <ul className="mt-2 flex flex-col gap-1.5">
                {claims.length === 0 && <li className="text-xs text-muted-foreground">No claims on file.</li>}
                {claims.slice(0, 12).map((c) => (
                  <li key={c.id} className="rounded-lg border border-border bg-card px-3 py-2 text-xs">
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-mono font-medium">{c.id}</span>
                      <span className={cn("rounded-full px-2 py-0.5 text-[10px] font-medium", c.status === "submitted" ? "bg-primary/10 text-primary" : c.status === "draft" ? "bg-muted text-muted-foreground" : c.status === "rejected" ? "bg-destructive/10 text-destructive" : "bg-success/10 text-success")}>
                        {c.status}
                      </span>
                    </div>
                    <p className="mt-0.5 text-muted-foreground">
                      {c.customer_id} · {c.policy_id}{c.claim_amount ? ` · ${formatMoney(String(c.claim_amount), "IDR")}` : ""}{c.requested_via ? ` · via ${c.requested_via}` : ""}
                    </p>
                    {c.status === "submitted" && (
                      <div className="mt-1.5 flex gap-1.5">
                        {(["approved", "rejected", "paid"] as const).map((d) => (
                          <button key={d} type="button" onClick={() => insurer.decide(token, c.id, d).then(() => refresh(token)).catch(() => setError("Decision failed."))} className="rounded-full border border-border px-2 py-0.5 text-[11px] hover:bg-muted">
                            {d}
                          </button>
                        ))}
                      </div>
                    )}
                  </li>
                ))}
              </ul>
            </section>

            <section>
              <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Tickets for a human</p>
              <ul className="mt-2 flex flex-col gap-1.5">
                {tickets.length === 0 && <li className="text-xs text-muted-foreground">No tickets.</li>}
                {tickets.slice(0, 8).map((t) => (
                  <li key={t.id} className="rounded-lg border border-border bg-card px-3 py-2 text-xs">
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-mono font-medium">{t.id}</span>
                      <span className="rounded-full bg-warning/15 px-2 py-0.5 text-[10px] font-medium text-warning-foreground">{t.status}</span>
                    </div>
                    <p className="mt-0.5 text-muted-foreground">{t.customer_id} · {t.type}{t.requested_via ? ` · ${t.requested_via}` : ""}</p>
                  </li>
                ))}
              </ul>
            </section>

            {error && <p className="text-xs text-destructive">{error}</p>}
            <button type="button" onClick={() => { try { sessionStorage.removeItem(STORAGE_KEY); } catch { /* noop */ } setToken(""); }} className="self-start text-[11px] text-muted-foreground hover:text-foreground">
              Forget token
            </button>
          </>
        )}
      </SheetContent>
    </Sheet>
  );
}
