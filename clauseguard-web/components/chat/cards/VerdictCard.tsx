import { CheckCircle2, CircleDashed, HelpCircle, XCircle } from "lucide-react";
import type { PoliciesResponse, VerdictResult } from "@/lib/types";
import { formatMoney, titleCase } from "@/lib/format";
import { findPolicy, findTuple, clauseCitation } from "@/lib/clauses";
import { reasoningFor, stripVerdictPreamble } from "@/lib/parseReply";
import { ClauseQuote } from "./ClauseQuote";
import { cn } from "@/lib/utils";
import { branchSentence } from "@/lib/slots";

const STYLES: Record<string, { border: string; icon: typeof CheckCircle2; iconClass: string; label: string }> = {
  COVERED: { border: "border-l-success", icon: CheckCircle2, iconClass: "text-success", label: "Covered" },
  DENIED: { border: "border-l-destructive", icon: XCircle, iconClass: "text-destructive", label: "Not covered" },
  CLARIFY: { border: "border-l-warning", icon: HelpCircle, iconClass: "text-warning-foreground", label: "Depends on one fact" },
  NOT_APPLICABLE: { border: "border-l-muted-foreground/40", icon: CircleDashed, iconClass: "text-muted-foreground", label: "Not determinable" },
  NOT_SPECIFIED: { border: "border-l-muted-foreground/40", icon: CircleDashed, iconClass: "text-muted-foreground", label: "Not specified in your documents" },
};

export function VerdictCard({
  verdict,
  policies,
  replyText,
}: {
  verdict: VerdictResult;
  policies: PoliciesResponse | null;
  replyText: string;
}) {
  const nothingPayable = verdict.verdict === "COVERED" && verdict.payable !== null && Number(verdict.payable) === 0;
  const style = nothingPayable
    ? { ...STYLES.NOT_APPLICABLE, label: "Covered, but nothing payable here" }
    : STYLES[verdict.verdict] ?? STYLES.NOT_APPLICABLE;
  const Icon = style.icon;
  const policy = findPolicy(policies, verdict.policy_id);
  const name = policy?.product_name ?? verdict.policy_id;
  // a CLARIFY card explains itself through its branches; the transcript's "if slot = value" line is engine shorthand
  const reasoning = verdict.verdict === "CLARIFY" ? "" : stripVerdictPreamble(reasoningFor(replyText, verdict.policy_id) ?? "");
  const clauseIds = verdict.fired_tuple_ids.slice(0, 2);

  return (
    <div className={cn("rounded-xl border border-border border-l-[3px] bg-card p-3.5 shadow-soft", style.border)}>
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-2.5">
          <Icon className={cn("mt-0.5 h-4 w-4 shrink-0", style.iconClass)} />
          <div>
            <p className="text-sm font-semibold leading-tight">{name}</p>
            <p className="text-xs text-muted-foreground">{verdict.policy_id}</p>
          </div>
        </div>
        <span
          className={cn(
            "shrink-0 rounded-full px-2.5 py-0.5 text-xs font-medium",
            verdict.verdict === "COVERED" && !nothingPayable && "bg-success/10 text-success",
            verdict.verdict === "DENIED" && "bg-destructive/10 text-destructive",
            verdict.verdict === "CLARIFY" && "bg-warning/15 text-warning-foreground",
            (verdict.verdict === "NOT_APPLICABLE" || verdict.verdict === "NOT_SPECIFIED" || nothingPayable) && "bg-muted text-muted-foreground"
          )}
        >
          {style.label}
        </span>
      </div>

      {verdict.payable && !nothingPayable && (
        <p className="mt-2 text-lg font-semibold text-foreground">{formatMoney(verdict.payable, verdict.currency ?? "IDR")}</p>
      )}

      {reasoning && <p className="mt-1.5 text-sm text-muted-foreground">{reasoning}</p>}

      {verdict.denial_code && !reasoning && (
        <p className="mt-1.5 text-sm text-muted-foreground">Reason: {titleCase(verdict.denial_code)}.</p>
      )}

      {verdict.verdict === "CLARIFY" && verdict.clarification && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {Object.entries(verdict.clarification.verdict_by_value).map(([value, v]) => (
            <span key={value} className="rounded-full bg-muted px-2 py-0.5 text-[11px] text-muted-foreground">
              {branchSentence(verdict.clarification!.slot, value, v)}
            </span>
          ))}
        </div>
      )}

      {clauseIds.length > 0 &&
        clauseIds.map((tid) => {
          const t = findTuple(policies, verdict.policy_id, tid);
          if (!t) return null;
          return <ClauseQuote key={tid} citation={clauseCitation(t, verdict.policy_id)} text={t.text} />;
        })}
    </div>
  );
}
