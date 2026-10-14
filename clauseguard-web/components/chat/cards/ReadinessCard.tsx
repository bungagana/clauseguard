import { CheckCircle2, Circle } from "lucide-react";
import type { ReadinessReport, TwinResponse } from "@/lib/types";
import { formatDate, formatDaysLeft, humanize } from "@/lib/format";
import { cn } from "@/lib/utils";

function Gauge({ score, afterFix }: { score: number; afterFix?: number }) {
  const pct = Math.round(score * 100);
  const afterPct = afterFix !== undefined ? Math.round(afterFix * 100) : null;
  const r = 26;
  const c = 2 * Math.PI * r;
  const color = pct >= 80 ? "stroke-success" : pct >= 50 ? "stroke-warning" : "stroke-destructive";
  return (
    <div className="flex shrink-0 flex-col items-center gap-1">
      <div className="relative flex h-16 w-16 items-center justify-center">
        <svg viewBox="0 0 64 64" className="h-16 w-16 -rotate-90">
          <circle cx="32" cy="32" r={r} fill="none" strokeWidth="6" className="stroke-muted" />
          <circle
            cx="32"
            cy="32"
            r={r}
            fill="none"
            strokeWidth="6"
            strokeLinecap="round"
            className={color}
            strokeDasharray={`${c}`}
            strokeDashoffset={`${c - (pct / 100) * c}`}
          />
        </svg>
        <span className="absolute text-sm font-semibold">{pct}%</span>
      </div>
      {afterPct !== null && afterPct > pct && (
        <span className="whitespace-nowrap text-[10px] font-medium text-success">→ {afterPct}% if fixed</span>
      )}
    </div>
  );
}

export function ReadinessCard({
  readiness,
  twin,
}: {
  readiness: ReadinessReport;
  twin?: TwinResponse;
}) {
  return (
    <div className="rounded-xl border border-border bg-card p-3.5 shadow-soft">
      <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Claim readiness</p>
      <div className="mt-2.5 flex items-start gap-4">
        {twin && <Gauge score={twin.readiness_score} afterFix={twin.after_fix_score} />}
        <div className="min-w-0 flex-1">
          {readiness.deadline && (
            <p className="text-sm">
              File by <span className="font-medium">{formatDate(readiness.deadline)}</span>{" "}
              <span className={cn("rounded-full px-2 py-0.5 text-[11px] font-medium", (readiness.days_left ?? 99) < 14 ? "bg-destructive/10 text-destructive" : "bg-muted text-muted-foreground")}>
                {formatDaysLeft(readiness.days_left)}
              </span>
            </p>
          )}
          {readiness.late_effect && (
            <p className="mt-0.5 text-xs text-muted-foreground">
              {readiness.late_effect === "REJECT" ? "A late claim is rejected." : "A late claim may be rejected at the insurer's discretion."}
            </p>
          )}
        </div>
      </div>

      {twin && twin.grounds.length > 0 ? (
        <div className="mt-3">
          <p className="text-xs font-medium text-muted-foreground">What could get this claim rejected, and how to fix it:</p>
          <ul className="mt-1.5 flex flex-col gap-1.5">
            {twin.grounds.map((g, i) => (
              <li key={i} className="flex items-start gap-2 text-sm">
                {g.fixable ? <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-success" /> : <Circle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-muted-foreground" />}
                <div>
                  <span className="font-medium">{humanize(g.code)}</span>
                  {g.recourse?.description && <span className="text-muted-foreground"> — {g.recourse.description}</span>}
                  <span
                    className={cn(
                      "ml-1.5 rounded-full px-1.5 py-0.5 text-[10px] font-medium",
                      g.fixable ? "bg-success/10 text-success" : "bg-muted text-muted-foreground"
                    )}
                  >
                    {g.fixable ? "fixable" : "not fixable"}
                  </span>
                </div>
              </li>
            ))}
          </ul>
        </div>
      ) : readiness.missing_documents.length > 0 ? (
        <p className="mt-2.5 text-sm text-muted-foreground">
          Still missing: {readiness.missing_documents.map(humanize).join(", ")}.
        </p>
      ) : null}
    </div>
  );
}
