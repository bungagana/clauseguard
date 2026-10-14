"use client";

import { useEffect, useRef, useState } from "react";
import { ChevronDown, FileText } from "lucide-react";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import type { PoliciesResponse, PolicyView } from "@/lib/types";
import { formatDate } from "@/lib/format";
import { groupPolicyTuples } from "@/lib/clauseGroups";
import { cn } from "@/lib/utils";

const STATUS_VARIANT: Record<string, "success" | "warning" | "destructive" | "muted"> = {
  active: "success",
  grace: "warning",
  lapsed: "destructive",
};

function PolicyCard({ policy, focused }: { policy: PolicyView; focused?: boolean }) {
  const [open, setOpen] = useState(Boolean(focused));
  const ref = useRef<HTMLDivElement>(null);
  const status = policy.pay?.status ?? "active";
  const unverified = policy.source_badges.includes("unverified");

  useEffect(() => {
    if (focused) {
      setOpen(true);
      ref.current?.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }, [focused]);

  return (
    <div ref={ref} className={cn("rounded-xl border bg-card", focused ? "border-primary ring-1 ring-primary/40" : "border-border")}>
      <button type="button" onClick={() => setOpen((o) => !o)} className="flex w-full items-start justify-between gap-2 p-3.5 text-left">
        <div className="min-w-0">
          <p className="text-sm font-semibold leading-tight">{policy.product_name}</p>
          <p className="mt-0.5 text-xs text-muted-foreground">{policy.insurer}</p>
        </div>
        <div className="flex shrink-0 flex-wrap items-center justify-end gap-1.5">
          {unverified ? (
            <Badge variant="warning" className="border-warning/40">
              Unverified
            </Badge>
          ) : (
            <Badge variant="muted">Verified</Badge>
          )}
          <Badge variant={STATUS_VARIANT[status] ?? "muted"} className="capitalize">
            {status}
          </Badge>
          <ChevronDown className={cn("h-3.5 w-3.5 text-muted-foreground transition-transform", open && "rotate-180")} />
        </div>
      </button>
      {open && (
        <div className="border-t border-border p-3.5 pt-3">
          <p className="text-xs text-muted-foreground">
            {formatDate(policy.effective_date)} – {formatDate(policy.expiry_date)}
            {policy.sum_assured ? ` · sum assured ${policy.currency} ${Number(policy.sum_assured).toLocaleString("en-US")}` : ""}
          </p>
          <div className="mt-2.5 flex flex-col gap-3">
            {groupPolicyTuples(policy.tuples).map((group) => (
              <div key={group.heading}>
                <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">{group.heading}</p>
                <ul className="mt-1 flex flex-col gap-1.5">
                  {group.items.map((item) => (
                    <li key={item.tupleIds.join("+")} className="flex items-start gap-2 text-xs">
                      <FileText className="mt-0.5 h-3 w-3 shrink-0 text-muted-foreground" />
                      <span className="text-foreground/90">
                        {item.label}
                        {item.detail ? <span className="text-muted-foreground"> — {item.detail}</span> : null}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export function PoliciesPanel({
  open,
  onOpenChange,
  policies,
  focusPolicyId,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  policies: PoliciesResponse | null;
  focusPolicyId?: string | null;
}) {
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-5/6 sm:max-w-md">
        <SheetHeader>
          <SheetTitle>My policies</SheetTitle>
        </SheetHeader>
        <Separator className="my-2" />
        <div className="flex flex-1 flex-col gap-2.5 overflow-y-auto pb-4">
          {policies?.policies.length ? (
            policies.policies.map((p) => <PolicyCard key={p.id} policy={p} focused={p.id === focusPolicyId} />)
          ) : (
            <p className="text-sm text-muted-foreground">No policies loaded yet.</p>
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}
