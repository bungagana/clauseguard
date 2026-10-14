"use client";

import { Eye, FileEdit, Send } from "lucide-react";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import type { AutonomyMode, SessionState } from "@/lib/types";
import { cn } from "@/lib/utils";

const MODES: { key: AutonomyMode; label: string; icon: typeof Eye; help: string }[] = [
  { key: "observe", label: "Observe", icon: Eye, help: "Answers and explains only. Nothing is prepared or sent." },
  { key: "draft", label: "Draft", icon: FileEdit, help: "Prepares claim drafts and letters for your review. Cannot submit." },
  { key: "act", label: "Act", icon: Send, help: "May submit a claim or book a call-back, but only after you tap Confirm." },
];

/**
 * The customer's own settings: how far the agent may go. A real server-side limit (the
 * permission enforcer's tier cap), not a display preference.
 */
export function SessionControls({
  open, onOpenChange, sessionState, online, onAutonomyChange, children,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  sessionState: SessionState | null;
  online: boolean;
  onAutonomyChange: (m: AutonomyMode) => void;
  children?: React.ReactNode;
}) {
  const current = sessionState?.autonomy ?? "act";
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="flex w-full flex-col gap-5 overflow-y-auto sm:max-w-md">
        <SheetHeader>
          <SheetTitle>How far may the assistant go?</SheetTitle>
          <SheetDescription>You decide. Money and identity changes are impossible in every setting.</SheetDescription>
        </SheetHeader>

        <div role="radiogroup" aria-label="Assistant autonomy" className="flex flex-col gap-1.5">
          {MODES.map((m) => {
            const active = m.key === current;
            return (
              <button
                key={m.key}
                type="button"
                role="radio"
                aria-checked={active}
                disabled={!online || !sessionState}
                onClick={() => onAutonomyChange(m.key)}
                className={cn(
                  "flex items-start gap-3 rounded-xl border p-3 text-left transition-colors disabled:opacity-50",
                  active ? "border-primary bg-primary/5" : "border-border bg-card hover:border-primary/40"
                )}
              >
                <span className={cn("mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg", active ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground")}>
                  <m.icon className="h-3.5 w-3.5" />
                </span>
                <span>
                  <span className="block text-sm font-semibold">{m.label}</span>
                  <span className="block text-xs text-muted-foreground">{m.help}</span>
                </span>
              </button>
            );
          })}
        </div>
        <p className="text-[11px] text-muted-foreground">This limit is enforced by the server, not just by this screen.</p>
        {children}
      </SheetContent>
    </Sheet>
  );
}
