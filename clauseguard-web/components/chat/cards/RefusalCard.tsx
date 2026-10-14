import { Info } from "lucide-react";
import type { ChatReply } from "@/lib/types";

const TITLES: Record<string, string> = {
  MISREPRESENTATION_REQUEST: "I can't help with that",
  T3_OUT_OF_BAND: "That change needs to go through the insurer directly",
  NOT_OWNER: "I can only access your own policies",
  AUTHORITY_OR_DATA_EXFIL: "I can't share that",
  UNSUPPORTED_ACTION: "I can't make that change",
};

export function RefusalCard({ reply }: { reply: ChatReply }) {
  const title = TITLES[reply.refusal_reason ?? ""] ?? "I can't do that";
  return (
    <div className="rounded-xl border border-border bg-muted/60 p-3.5">
      <div className="flex items-start gap-2.5">
        <Info className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
        <div className="min-w-0">
          <p className="text-sm font-semibold">{title}</p>
          <p className="mt-1 whitespace-pre-line text-sm text-muted-foreground">{reply.text}</p>
          {reply.escalation_ticket && (
            <p className="mt-2 inline-flex items-center gap-1 rounded-full bg-background px-2.5 py-1 text-xs font-medium text-foreground">
              Ticket {reply.escalation_ticket}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
