import { HelpCircle } from "lucide-react";
import type { ClarificationRequest, PoliciesResponse } from "@/lib/types";
import { extractClarificationLine } from "@/lib/parseReply";
import { findTuple, clauseCitation } from "@/lib/clauses";
import { titleCase } from "@/lib/format";
import { quickRepliesFor } from "@/lib/quickReplies";
import { ClauseQuote } from "./ClauseQuote";

export function ClarificationNote({
  clarification,
  replyText,
  policies,
  onQuickReply,
  answered,
  language = "en",
}: {
  clarification: ClarificationRequest;
  replyText: string;
  policies: PoliciesResponse | null;
  onQuickReply?: (text: string) => void;
  answered?: boolean;
  language?: "en" | "id";
}) {
  const line = extractClarificationLine(replyText);
  const question = line ? line.split(/\s*The clause that makes this matter/)[0] : null;
  const tuple = findTuple(policies, "", clarification.why_tuple_id);
  const policyId = policies?.policies.find((p) => p.tuples.some((t) => t.id === clarification.why_tuple_id))?.id;
  const replies = onQuickReply && !answered ? quickRepliesFor(clarification, language) : [];

  return (
    <div className="rounded-xl border border-primary/25 bg-primary/5 p-3.5">
      <div className="flex items-start gap-2.5">
        <HelpCircle className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
        <div className="min-w-0 flex-1">
          <p className="text-xs font-semibold uppercase tracking-wide text-primary/80">One fact decides this</p>
          <p className="mt-1 text-sm text-foreground">
            {question ?? <>Could you tell me <span className="rounded bg-primary/10 px-1.5 py-0.5 font-medium">{titleCase(clarification.slot)}</span>?</>}
          </p>
          {replies.length > 0 && (
            <div className="mt-2.5 flex flex-wrap gap-1.5">
              {replies.map((r) => (
                <button
                  key={r.label}
                  type="button"
                  onClick={() => onQuickReply?.(r.text)}
                  className="rounded-full border border-primary/40 bg-card px-3.5 py-1.5 text-xs font-medium text-primary transition-colors hover:bg-primary hover:text-primary-foreground"
                >
                  {r.label}
                </button>
              ))}
              <span className="self-center text-[11px] text-muted-foreground">{language === "id" ? "atau ketik saja" : "or just type it"}</span>
            </div>
          )}
          {tuple && policyId && <ClauseQuote citation={clauseCitation(tuple, policyId)} text={tuple.text} label="See the clause that decides this" />}
        </div>
      </div>
    </div>
  );
}
