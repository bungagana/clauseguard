"use client";

import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import type { SessionState } from "@/lib/types";

/**
 * Session controls beyond the autonomy switch (which lives in the top bar): what the host app
 * mounts here, such as the security explainer and the customer's own model key.
 */
export function SessionControls({
  open, onOpenChange, sessionState, children,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  sessionState: SessionState | null;
  online?: boolean;
  children?: React.ReactNode;
}) {
  const mode = sessionState?.autonomy ?? "act";
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="flex w-full flex-col gap-5 overflow-y-auto sm:max-w-md">
        <SheetHeader>
          <SheetTitle>Session controls</SheetTitle>
          <SheetDescription>
            The assistant is in <span className="font-medium text-foreground">{mode === "observe" ? "Observe" : mode === "draft" ? "Draft" : "Act"}</span> mode; change it with the switch in the top bar.
            Money and identity changes are impossible in every mode.
          </SheetDescription>
        </SheetHeader>
        {children}
      </SheetContent>
    </Sheet>
  );
}
