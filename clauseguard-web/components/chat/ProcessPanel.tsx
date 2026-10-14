"use client";

import { Bot, Building2, CalendarClock, Code2, RotateCcw, Terminal, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { ChatMessage } from "@/lib/message";
import type { PoliciesResponse, SessionState } from "@/lib/types";
import { findTuple, clauseCitation, policyName } from "@/lib/clauses";
import { formatMoney, humanize } from "@/lib/format";
import { cn } from "@/lib/utils";

const RELATION: Record<string, string> = {
  ANSWER: "an answer to the agent's last question",
  CORRECTION: "a correction to the same situation",
  CONTINUE: "a follow-up about the same situation",
  NEW_SCENARIO: "a new situation",
  HYPOTHETICAL: "a what-if, not a report",
  GENERAL: "a general question",
};
const VERDICT: Record<string, string> = { COVERED: "covered", DENIED: "not covered", CLARIFY: "one fact open", NOT_APPLICABLE: "not applicable", NOT_SPECIFIED: "not specified" };

function fact(k: string, v: unknown) {
  if (typeof v === "boolean") return `${humanize(k)}: ${v ? "yes" : "no"}`;
  if (k === "billed_amount" && v != null) return `${humanize(k)}: ${formatMoney(String(v), "IDR")}`;
  return `${humanize(k)}: ${String(v).toLowerCase().replace(/_/g, " ")}`;
}

/**
 * The judge's / developer's view, shown beside the product: which agent did what for the latest
 * reply, with the data each one produced, plus the sandbox tools. The product itself (the chat)
 * is unchanged by this panel; everything here is read from the reply the backend already sent.
 */
export function ProcessPanel({
  open, onClose, messages, policies, sessionState, online, onMoveClock, onOpenInsurer, onOpenDeveloper,
}: {
  open: boolean;
  onClose: () => void;
  messages: ChatMessage[];
  policies: PoliciesResponse | null;
  sessionState: SessionState | null;
  online: boolean;
  onMoveClock: (days: number, reset?: boolean) => void;
  onOpenInsurer: () => void;
  onOpenDeveloper: () => void;
}) {
  if (!open) return null;
  const last = [...messages].reverse().find((m) => m.role === "assistant" && m.reply);
  const reply = last?.reply;
  const facts = Object.entries(reply?.facts ?? {}).filter(([k, v]) => v != null && !k.startsWith("days_since") && !k.startsWith("months_since"));
  const verdicts = (reply?.verdicts ?? []).filter((v) => v.verdict !== "NOT_APPLICABLE" && v.verdict !== "NOT_SPECIFIED");
  const calls = reply?.tool_calls ?? [];
  const denied = calls.filter((c) => !c.allowed);
  const t2 = calls.filter((c) => c.tier >= 2);
  const offset = sessionState?.as_of_offset_days ?? 0;

  return (
    <aside className="hidden w-[340px] shrink-0 flex-col border-l border-border bg-muted/30 lg:flex">
      <div className="flex items-center justify-between border-b border-border px-4 py-3">
        <div>
          <p className="text-sm font-semibold">Behind the answer</p>
          <p className="text-[11px] text-muted-foreground">For judges and developers. Not shown to customers.</p>
        </div>
        <button type="button" onClick={onClose} aria-label="Hide process panel" className="text-muted-foreground hover:text-foreground">
          <X className="h-4 w-4" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-3">
        {!reply ? (
          <p className="text-xs text-muted-foreground">Send a message and the pipeline for that reply appears here.</p>
        ) : (
          <ol className="flex flex-col">
            <Stage name="Conversation Agent" kind="ai" body={<>Read the message as <b>{RELATION[reply.context_relation ?? ""] ?? "a question about the policies"}</b>{reply.hypothetical ? "; answered in the conditional" : ""}.</>} />
            <Stage name="Fact Agent" kind="ai" body={facts.length ? facts.map(([k, v]) => fact(k, v)).join(" · ") : "No facts needed for this turn."} />
            <Stage
              name="Rules Engine"
              kind="code"
              body={
                verdicts.length ? (
                  <ul className="flex flex-col gap-1.5">
                    {verdicts.map((v) => {
                      const t = findTuple(policies, v.policy_id, v.fired_tuple_ids[0]);
                      return (
                        <li key={v.policy_id}>
                          <span className="font-medium text-foreground/90">{policyName(policies, v.policy_id)}</span>: {VERDICT[v.verdict] ?? v.verdict}
                          {v.payable && Number(v.payable) > 0 ? `, ${formatMoney(v.payable, v.currency ?? "IDR")}` : ""}
                          {t && <span className="mt-0.5 block border-l-2 border-primary/40 pl-2 italic text-foreground/70">&ldquo;{t.text.length > 180 ? t.text.slice(0, 180) + "…" : t.text}&rdquo; <span className="not-italic font-mono text-[10px] uppercase">{clauseCitation(t, v.policy_id)}</span></span>}
                        </li>
                      );
                    })}
                  </ul>
                ) : (
                  "No coverage decision was needed."
                )
              }
            />
            <Stage
              name="Guardian"
              kind="code"
              body={
                calls.length ? (
                  <>
                    {calls.length} tool call{calls.length > 1 ? "s" : ""} checked
                    {denied.length ? <>, <b className="text-destructive">{denied.length} refused</b> ({denied.map((d) => `${d.name}: ${d.reason}`).join("; ")})</> : ", all allowed"}
                    {t2.length ? <>; {t2.length} needed your tap</> : null}.
                    {reply.escalation_ticket ? <> Ticket for a human: <span className="font-mono">{reply.escalation_ticket}</span>.</> : null}
                  </>
                ) : (
                  "No tool was called."
                )
              }
            />
            <Stage
              name="Explainer Agent"
              kind="ai"
              body={reply.composed ? "Wrote the reply; every amount, date and ID matched the engine, so it was accepted." : reply.violations?.length ? `Draft rejected (${reply.violations.join(", ")}); the engine's exact wording was shown instead.` : "Engine wording shown directly."}
            />
            <Stage name="Audit trail" kind="code" body={`${reply.audit_ids.length} entries written for this turn.`} last />
          </ol>
        )}

        <div className="mt-5 rounded-xl border border-dashed border-border p-3">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Sandbox tools</p>
          <div className="mt-2 flex flex-wrap items-center gap-1.5">
            <span className="inline-flex items-center gap-1 rounded-lg border border-border bg-card px-2 py-1 text-xs tabular-nums">
              <CalendarClock className="h-3 w-3 text-muted-foreground" /> {sessionState?.as_of ?? "—"}{offset !== 0 ? ` (${offset > 0 ? "+" : ""}${offset} d)` : ""}
            </span>
            <Button size="sm" variant="outline" className="h-7 px-2 text-xs" disabled={!online} onClick={() => onMoveClock(7)}>+7 d</Button>
            <Button size="sm" variant="outline" className="h-7 px-2 text-xs" disabled={!online} onClick={() => onMoveClock(30)}>+30 d</Button>
            {offset !== 0 && (
              <Button size="sm" variant="ghost" className="h-7 px-2 text-xs" disabled={!online} onClick={() => onMoveClock(0, true)}>
                <RotateCcw className="h-3 w-3" /> reset
              </Button>
            )}
          </div>
          <p className="mt-1 text-[11px] text-muted-foreground">Moves this session&rsquo;s &ldquo;today&rdquo; so deadlines come due. Nothing on file changes.</p>
          <div className="mt-2 flex flex-col gap-1.5">
            <Button variant="outline" size="sm" className="justify-start" onClick={onOpenInsurer}>
              <Building2 className="h-3.5 w-3.5" /> Insurer side: inbox, tickets, halt switch
            </Button>
            <Button variant="outline" size="sm" className="justify-start" onClick={onOpenDeveloper}>
              <Terminal className="h-3.5 w-3.5" /> Raw trace: tool calls, labels, audit
            </Button>
          </div>
        </div>
      </div>
    </aside>
  );
}

function Stage({ name, kind, body, last = false }: { name: string; kind: "ai" | "code"; body: React.ReactNode; last?: boolean }) {
  return (
    <li className="flex gap-2.5">
      <div className="flex flex-col items-center">
        <span className={cn("flex h-6 w-6 shrink-0 items-center justify-center rounded-lg", kind === "code" ? "bg-primary/10 text-primary" : "bg-muted text-muted-foreground")}>
          {kind === "code" ? <Code2 className="h-3.5 w-3.5" /> : <Bot className="h-3.5 w-3.5" />}
        </span>
        {!last && <span className="my-1 w-px flex-1 bg-border" />}
      </div>
      <div className={cn("min-w-0 pb-3", last && "pb-0")}>
        <p className="text-xs font-semibold">
          {name} <span className={cn("ml-1 rounded-full px-1.5 py-px text-[9px] font-bold uppercase", kind === "code" ? "bg-primary/10 text-primary" : "bg-muted text-muted-foreground")}>{kind === "code" ? "code" : "AI"}</span>
        </p>
        <div className="mt-0.5 text-xs leading-relaxed text-muted-foreground">{body}</div>
      </div>
    </li>
  );
}
