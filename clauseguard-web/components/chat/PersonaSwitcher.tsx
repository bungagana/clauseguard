"use client";

import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { personaMeta } from "@/lib/personas";
import type { Persona } from "@/lib/types";
import { cn } from "@/lib/utils";

export function PersonaSwitcher({
  personas,
  activeKey,
  onSwitch,
}: {
  personas: Persona[];
  activeKey: string;
  onSwitch: (key: string) => void;
}) {
  return (
    <div className="flex items-center gap-1 sm:gap-1.5">
      {personas.map((p) => {
        const meta = personaMeta(p.key);
        const active = p.key === activeKey;
        return (
          <Tooltip key={p.key}>
            <TooltipTrigger asChild>
              <button
                type="button"
                onClick={() => onSwitch(p.key)}
                aria-label={`Switch to ${meta.name}`}
                className={cn(
                  "rounded-full p-0.5 transition-all",
                  active ? "ring-2 ring-primary ring-offset-2 ring-offset-background" : "opacity-60 hover:opacity-100"
                )}
              >
                <Avatar className="h-7 w-7 sm:h-8 sm:w-8">
                  <AvatarFallback className={cn(meta.accent, "text-[11px] sm:text-xs")}>{meta.initials}</AvatarFallback>
                </Avatar>
              </button>
            </TooltipTrigger>
            <TooltipContent side="bottom" className="max-w-56">
              <p className="font-medium">{meta.name}</p>
              <p className="text-muted-foreground">{p.description}</p>
            </TooltipContent>
          </Tooltip>
        );
      })}
    </div>
  );
}
