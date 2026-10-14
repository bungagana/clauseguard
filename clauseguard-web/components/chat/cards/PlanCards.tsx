import { ShieldPlus } from "lucide-react";
import type { Recommendation } from "@/lib/types";
import { formatMoney } from "@/lib/format";

export function PlanCards({ recommendations }: { recommendations: Recommendation[] }) {
  if (!recommendations.length) return null;
  return (
    <div className="rounded-xl border border-border bg-card p-3.5 shadow-soft">
      <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Plans that would close your gaps</p>
      <div className="mt-2.5 -mx-1 flex gap-3 overflow-x-auto px-1 pb-1 no-scrollbar">
        {recommendations.slice(0, 3).map((r) => (
          <div key={r.plan_id} className="flex w-56 shrink-0 flex-col rounded-lg border border-border bg-background/70 p-3">
            <ShieldPlus className="h-4 w-4 text-primary" />
            <p className="mt-1.5 text-sm font-semibold leading-snug">{r.product_name}</p>
            <p className="text-base font-semibold text-primary">
              {r.monthly_premium_idr ? formatMoney(r.monthly_premium_idr, r.currency ?? "IDR") : "—"}
              <span className="text-xs font-normal text-muted-foreground">/mo</span>
            </p>
            <p className="mt-1 text-xs text-muted-foreground">
              Closes: {r.closes_gap_perils.map((p) => p.toLowerCase().replace(/_/g, " ")).join(", ")}
            </p>
            <p className="mt-auto pt-2 text-[11px] text-muted-foreground line-clamp-3">{r.rationale}</p>
          </div>
        ))}
      </div>
      <p className="mt-2 text-[11px] text-muted-foreground">Indicative mock catalogue; consult a licensed agent before buying.</p>
    </div>
  );
}
