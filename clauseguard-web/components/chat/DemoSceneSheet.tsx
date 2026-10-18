"use client";

import { PlayCircle, Sparkles } from "lucide-react";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { personaMeta } from "@/lib/personas";
import type { Scene } from "@/lib/fixtures";

export function DemoSceneSheet({
  open,
  onOpenChange,
  scenes,
  onPick,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  scenes: Scene[];
  onPick: (scene: Scene) => void;
}) {
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="bottom" className="sm:max-w-xl sm:mx-auto">
        <SheetHeader>
          <SheetTitle className="flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-primary" />
            Try a demo scene
          </SheetTitle>
        </SheetHeader>
        <div className="mt-2 flex flex-col gap-2.5 overflow-y-auto">
          {scenes.map((scene) => {
            const meta = personaMeta(scene.personaKey);
            return (
              <button
                key={scene.id}
                type="button"
                onClick={() => onPick(scene)}
                className="flex items-start gap-3 rounded-xl border border-border bg-card p-3.5 text-left transition-colors hover:border-primary/40 hover:bg-secondary/60"
              >
                <PlayCircle className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
                <div className="min-w-0">
                  <p className="text-sm font-semibold">{scene.title}</p>
                  <p className="mt-0.5 text-xs text-muted-foreground">{scene.summary}</p>
                  <p className="mt-1 text-[11px] font-medium text-primary">
                    as {meta.name}
                    {scene.recorded && <span className="ml-2 rounded-full bg-warning/15 px-2 py-0.5 text-[10px] font-semibold text-warning-foreground">Recorded real run</span>}
                  </p>
                </div>
              </button>
            );
          })}
        </div>
      </SheetContent>
    </Sheet>
  );
}
