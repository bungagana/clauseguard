"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Check, History, MessageSquarePlus, Pencil, Search, Trash2, X } from "lucide-react";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import type { ConversationSummary, HistoryMode } from "@/lib/history";
import { personaMeta } from "@/lib/personas";
import { cn } from "@/lib/utils";

const DAY_MS = 24 * 60 * 60 * 1000;

function startOfDay(ts: number): number {
  const d = new Date(ts);
  d.setHours(0, 0, 0, 0);
  return d.getTime();
}

function groupLabel(updatedAt: number, now: number): string {
  const today = startOfDay(now);
  const day = startOfDay(updatedAt);
  if (day >= today) return "Today";
  if (day >= today - DAY_MS) return "Yesterday";
  if (day >= today - 7 * DAY_MS) return "Previous 7 days";
  if (day >= today - 30 * DAY_MS) return "Previous 30 days";
  return new Date(updatedAt).toLocaleDateString("en-GB", { month: "long", year: "numeric" });
}

function timeLabel(updatedAt: number, now: number): string {
  const d = new Date(updatedAt);
  if (startOfDay(updatedAt) >= startOfDay(now) - DAY_MS) {
    return d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
  }
  return d.toLocaleDateString("en-GB", { day: "numeric", month: "short" });
}

function groupConversations(list: ConversationSummary[], now: number) {
  const groups: { label: string; items: ConversationSummary[] }[] = [];
  for (const c of list) {
    const label = groupLabel(c.updatedAt, now);
    const last = groups[groups.length - 1];
    if (last && last.label === label) last.items.push(c);
    else groups.push({ label, items: [c] });
  }
  return groups;
}

function ConversationRow({
  conversation,
  active,
  now,
  onSelect,
  onRename,
  onDelete,
}: {
  conversation: ConversationSummary;
  active: boolean;
  now: number;
  onSelect: () => void;
  onRename: (title: string) => void;
  onDelete: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(conversation.title);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const meta = personaMeta(conversation.personaKey);

  useEffect(() => {
    if (editing) inputRef.current?.select();
  }, [editing]);

  function commitRename() {
    const next = draft.trim();
    if (next && next !== conversation.title) onRename(next);
    setEditing(false);
  }

  if (editing) {
    return (
      <div className="flex items-center gap-1 rounded-lg border border-primary/40 bg-card px-2 py-1">
        <input
          ref={inputRef}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") commitRename();
            if (e.key === "Escape") {
              setDraft(conversation.title);
              setEditing(false);
            }
          }}
          className="min-w-0 flex-1 bg-transparent text-sm text-foreground outline-none"
          aria-label="Conversation title"
        />
        <button type="button" onClick={commitRename} aria-label="Save title" className="rounded p-0.5 text-primary hover:bg-muted">
          <Check className="h-3.5 w-3.5" />
        </button>
        <button
          type="button"
          onClick={() => {
            setDraft(conversation.title);
            setEditing(false);
          }}
          aria-label="Cancel rename"
          className="rounded p-0.5 text-muted-foreground hover:bg-muted"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      </div>
    );
  }

  if (confirmDelete) {
    return (
      <div className="flex items-center gap-2 rounded-lg border border-destructive/30 bg-destructive/5 px-2.5 py-1.5 text-xs">
        <span className="min-w-0 flex-1 truncate text-foreground">Delete this chat?</span>
        <Button size="sm" variant="destructive" className="h-6 px-2 text-[11px]" onClick={onDelete}>
          Delete
        </Button>
        <Button size="sm" variant="ghost" className="h-6 px-2 text-[11px]" onClick={() => setConfirmDelete(false)}>
          Keep
        </Button>
      </div>
    );
  }

  return (
    <div
      className={cn(
        "group relative flex items-center gap-2 rounded-lg px-2 py-1.5 transition-colors",
        active ? "bg-secondary text-secondary-foreground" : "hover:bg-muted/70"
      )}
    >
      <button type="button" onClick={onSelect} className="flex min-w-0 flex-1 items-center gap-2 text-left" title={conversation.title}>
        <Avatar className="h-6 w-6 shrink-0">
          <AvatarFallback className={cn(meta.accent, "text-[10px]")}>{meta.initials}</AvatarFallback>
        </Avatar>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-sm leading-tight">{conversation.title}</span>
          <span className="block text-[11px] text-muted-foreground">
            {timeLabel(conversation.updatedAt, now)} · {conversation.messageCount} msgs
          </span>
        </span>
      </button>
      <div
        className={cn(
          "flex shrink-0 items-center gap-0.5 opacity-0 transition-opacity group-hover:opacity-100 group-focus-within:opacity-100",
          active && "opacity-100"
        )}
      >
        <button
          type="button"
          onClick={() => {
            setDraft(conversation.title);
            setEditing(true);
          }}
          aria-label="Rename conversation"
          title="Rename"
          className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
        >
          <Pencil className="h-3.5 w-3.5" />
        </button>
        <button
          type="button"
          onClick={() => setConfirmDelete(true)}
          aria-label="Delete conversation"
          title="Delete"
          className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-destructive"
        >
          <Trash2 className="h-3.5 w-3.5" />
        </button>
      </div>
    </div>
  );
}

export interface HistorySidebarProps {
  conversations: ConversationSummary[];
  mode: HistoryMode;
  activeId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
  onRename: (id: string, title: string) => void;
  onDelete: (id: string) => void;
  onClearAll: () => void;
  // who is signed in: the demo persona, or the production account
  profile?: { name: string; subtitle: string; initials: string; accent: string; demo: boolean };
}

export function HistorySidebarBody({ conversations, mode, activeId, onSelect, onNew, onRename, onDelete, onClearAll, profile }: HistorySidebarProps) {
  const [query, setQuery] = useState("");
  const [confirmClear, setConfirmClear] = useState(false);
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    setNow(Date.now());
  }, [conversations]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return conversations;
    return conversations.filter((c) => c.title.toLowerCase().includes(q) || personaMeta(c.personaKey).name.toLowerCase().includes(q));
  }, [conversations, query]);

  const groups = useMemo(() => groupConversations(filtered, now), [filtered, now]);

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex flex-col gap-2 px-3 pt-3">
        <Button variant="outline" className="w-full justify-start gap-2" onClick={onNew}>
          <MessageSquarePlus className="h-4 w-4" />
          New chat
        </Button>
        <div className="flex items-center gap-2 rounded-lg border border-input bg-background px-2.5 py-1.5">
          <Search className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search chats"
            aria-label="Search conversations"
            className="min-w-0 flex-1 bg-transparent text-sm text-foreground placeholder:text-muted-foreground focus:outline-none"
          />
          {query && (
            <button type="button" onClick={() => setQuery("")} aria-label="Clear search" className="text-muted-foreground hover:text-foreground">
              <X className="h-3.5 w-3.5" />
            </button>
          )}
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-3 py-3">
        {groups.length === 0 ? (
          <div className="flex flex-col items-center gap-2 px-2 py-10 text-center">
            <History className="h-6 w-6 text-muted-foreground/60" />
            <p className="text-sm text-muted-foreground">
              {conversations.length === 0 ? "No saved chats yet. Conversations are saved here automatically." : "No chats match your search."}
            </p>
          </div>
        ) : (
          <div className="flex flex-col gap-4">
            {groups.map((group) => (
              <section key={group.label} className="flex flex-col gap-0.5">
                <p className="px-2 pb-1 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">{group.label}</p>
                {group.items.map((c) => (
                  <ConversationRow
                    key={c.id}
                    conversation={c}
                    active={c.id === activeId}
                    now={now}
                    onSelect={() => onSelect(c.id)}
                    onRename={(title) => onRename(c.id, title)}
                    onDelete={() => onDelete(c.id)}
                  />
                ))}
              </section>
            ))}
          </div>
        )}
      </div>

      {conversations.length > 0 && (
        <div className="border-t border-border px-3 py-2">
          {confirmClear ? (
            <div className="flex items-center justify-between gap-2 text-xs">
              <span className="text-foreground">Delete all {conversations.length} chats?</span>
              <div className="flex gap-1">
                <Button
                  size="sm"
                  variant="destructive"
                  className="h-6 px-2 text-[11px]"
                  onClick={() => {
                    onClearAll();
                    setConfirmClear(false);
                  }}
                >
                  Delete all
                </Button>
                <Button size="sm" variant="ghost" className="h-6 px-2 text-[11px]" onClick={() => setConfirmClear(false)}>
                  Keep
                </Button>
              </div>
            </div>
          ) : (
            <button
              type="button"
              onClick={() => setConfirmClear(true)}
              className="flex items-center gap-1.5 text-xs text-muted-foreground transition-colors hover:text-destructive"
            >
              <Trash2 className="h-3 w-3" />
              Clear all history
            </button>
          )}
        </div>
      )}
      {profile && (
        <div className="flex items-center gap-2.5 border-t border-border px-3 py-2.5">
          <Avatar className="h-8 w-8 shrink-0">
            <AvatarFallback className={cn(profile.accent, "text-[11px] font-semibold")}>{profile.initials}</AvatarFallback>
          </Avatar>
          <div className="min-w-0">
            <p className="truncate text-sm font-medium leading-tight">{profile.name}</p>
            <p className="truncate text-[11px] text-muted-foreground">{profile.subtitle}</p>
          </div>
          <span className="ml-auto inline-flex shrink-0 items-center gap-1 whitespace-nowrap text-[10px] text-success" title={profile.demo ? "Signed in to a demo account" : "Signed in"}>
            <span className="h-1.5 w-1.5 rounded-full bg-success" /> {profile.demo ? "Demo" : "Online"}
          </span>
        </div>
      )}
      <p
        className="border-t border-border px-3 py-1.5 text-[10px] text-muted-foreground"
        title={mode === "backend" ? "Saved by the ClauseGuard backend on this computer" : "The backend history store is unreachable; chats stay in this browser until it returns"}
      >
        {mode === "backend" ? "Stored locally on this computer" : "Stored locally in this browser only"}
      </p>
    </div>
  );
}

export function HistorySidebar({
  desktopOpen,
  mobileOpen,
  onMobileOpenChange,
  ...props
}: HistorySidebarProps & { desktopOpen: boolean; mobileOpen: boolean; onMobileOpenChange: (open: boolean) => void }) {
  return (
    <>
      <aside
        className={cn(
          "hidden shrink-0 overflow-hidden border-r border-border bg-card transition-[width] duration-200 ease-in-out md:flex md:flex-col",
          desktopOpen ? "md:w-72" : "md:w-0 md:border-r-0"
        )}
        aria-hidden={!desktopOpen}
      >
        <div className="flex h-full w-72 flex-col">
          <HistorySidebarBody {...props} />
        </div>
      </aside>

      <Sheet open={mobileOpen} onOpenChange={onMobileOpenChange}>
        <SheetContent side="left" className="w-5/6 p-0 sm:max-w-sm md:hidden">
          <SheetHeader className="px-4 pt-4">
            <SheetTitle className="flex items-center gap-2 text-sm">
              <History className="h-4 w-4 text-primary" />
              Chat history
            </SheetTitle>
          </SheetHeader>
          <div className="min-h-0 flex-1">
            <HistorySidebarBody
              {...props}
              onSelect={(id) => {
                props.onSelect(id);
                onMobileOpenChange(false);
              }}
              onNew={() => {
                props.onNew();
                onMobileOpenChange(false);
              }}
            />
          </div>
        </SheetContent>
      </Sheet>
    </>
  );
}
