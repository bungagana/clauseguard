"use client";

import { ShieldCheck, Sparkles, FolderClosed, PanelLeft, History, MessageSquarePlus, CalendarClock, OctagonX, SlidersHorizontal, PanelRight } from "lucide-react";
import type { SessionState } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { PersonaSwitcher } from "./PersonaSwitcher";
import { ThemeToggle } from "./ThemeToggle";
import { LlmStatusBadge } from "./LlmStatusBadge";
import type { Persona } from "@/lib/types";
import type { AppMode } from "@/lib/appMode";

export function TopBar({
  mode,
  personas,
  activePersona,
  onSwitchPersona,
  fromHistory,
  onOpenPolicies,
  onOpenControls,
  onToggleSidebar,
  onOpenHistory,
  onNewConversation,
  backendOnline,
  sessionState,
  onToggleProcess,
  processOpen,
}: {
  mode: AppMode;
  personas: Persona[];
  activePersona: string;
  onSwitchPersona: (key: string) => void;
  fromHistory: boolean;
  onOpenPolicies: () => void;
  onOpenControls: () => void;
  onToggleSidebar: () => void;
  onOpenHistory: () => void;
  onNewConversation: () => void;
  backendOnline: boolean;
  sessionState?: SessionState | null;
  onToggleProcess?: () => void;
  processOpen?: boolean;
}) {
  return (
    <header className="flex items-center justify-between gap-2 border-b border-border bg-background/95 px-3 py-2.5 backdrop-blur sm:gap-3 sm:px-6">
      <div className="flex min-w-0 flex-1 items-center gap-2 sm:gap-2.5">
        <Button
          variant="ghost"
          size="icon"
          onClick={onToggleSidebar}
          aria-label="Toggle chat history"
          title="Toggle chat history"
          className="hidden h-8 w-8 shrink-0 md:inline-flex sm:h-9 sm:w-9"
        >
          <PanelLeft className="h-4 w-4" />
        </Button>
        <Button
          variant="ghost"
          size="icon"
          onClick={onOpenHistory}
          aria-label="Chat history"
          title="Chat history"
          className="h-8 w-8 shrink-0 md:hidden"
        >
          <History className="h-4 w-4" />
        </Button>
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-navy text-navy-foreground">
          <ShieldCheck className="h-4 w-4" />
        </div>
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="truncate text-sm font-semibold leading-none">ClauseGuard</span>
            {mode === "demo" && (
              <Badge variant="secondary" className="hidden items-center gap-1 whitespace-nowrap sm:flex">
                <Sparkles className="h-3 w-3" />
                Demo mode
              </Badge>
            )}
            {fromHistory && (
              <Badge variant="muted" className="hidden items-center gap-1 sm:flex">
                <History className="h-3 w-3" />
                From history
              </Badge>
            )}
            <LlmStatusBadge backendOnline={backendOnline} />
            {sessionState?.kill_switch && (
              <Badge variant="destructive" className="hidden items-center gap-1 whitespace-nowrap sm:flex">
                <OctagonX className="h-3 w-3" /> Agent halted by insurer
              </Badge>
            )}
            {sessionState && sessionState.as_of_offset_days !== 0 && (
              <Badge variant="warning" className="hidden items-center gap-1 whitespace-nowrap sm:flex">
                <CalendarClock className="h-3 w-3" /> {sessionState.as_of} · simulated
              </Badge>
            )}
          </div>
          <p className="hidden truncate text-xs text-muted-foreground lg:block">Know what your insurance actually covers</p>
        </div>
      </div>

      <div className="flex shrink-0 items-center gap-0.5 sm:gap-2">
        {mode === "demo" && <PersonaSwitcher personas={personas} activeKey={activePersona} onSwitch={onSwitchPersona} />}
        <Button
          variant="ghost"
          size="icon"
          onClick={onNewConversation}
          aria-label="New conversation"
          title="New conversation"
          className="h-8 w-8 sm:h-9 sm:w-9"
        >
          <MessageSquarePlus className="h-4 w-4" />
        </Button>
        <Button variant="ghost" size="icon" onClick={onOpenPolicies} aria-label="My policies" title="My policies" className="h-8 w-8 sm:h-9 sm:w-9">
          <FolderClosed className="h-4 w-4" />
        </Button>
        <Button
          variant={sessionState && sessionState.autonomy !== "act" ? "secondary" : "ghost"}
          size="sm"
          onClick={onOpenControls}
          aria-label="Session controls"
          title="Session controls"
          className="h-8 gap-1.5 px-2.5 sm:h-9"
        >
          <SlidersHorizontal className="h-4 w-4" />
          <span className="hidden text-xs md:inline">{sessionState && sessionState.autonomy !== "act" ? (sessionState.autonomy === "observe" ? "Observe" : "Draft") : "Controls"}</span>
        </Button>
        {onToggleProcess && (
          <Button
            variant={processOpen ? "secondary" : "ghost"}
            size="sm"
            onClick={onToggleProcess}
            aria-label="Behind the answer"
            title="Behind the answer (judges and developers)"
            className="hidden h-8 gap-1.5 px-2.5 lg:inline-flex sm:h-9"
          >
            <PanelRight className="h-4 w-4" />
            <span className="text-xs">Behind the answer</span>
          </Button>
        )}
        <ThemeToggle />
      </div>
    </header>
  );
}
