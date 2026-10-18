"use client";

import { useEffect, useState } from "react";
import { Sparkles, Wrench } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { checkLlmStatus, type LlmStatus } from "@/lib/api";

const POLL_MS = 20_000;

/**
 * Shows whether this turn's chat understanding is likely to run on the live language
 * model or on the deterministic rule-based fallback. This is a status indicator only —
 * every coverage decision is rule-based either way, so this badge never changes what the
 * agent decides, only how naturally it is likely to phrase a free-text question.
 */
export function LlmStatusBadge({ backendOnline }: { backendOnline: boolean }) {
  const [status, setStatus] = useState<LlmStatus | null>(null);

  useEffect(() => {
    if (!backendOnline) {
      setStatus(null);
      return;
    }
    let cancelled = false;
    const poll = async () => {
      const s = await checkLlmStatus();
      if (!cancelled) setStatus(s);
    };
    poll();
    const id = setInterval(poll, POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [backendOnline]);

  if (!backendOnline || !status) return null;

  // not configured: the backend has no model key at all (a deployment mistake, not a quota pause); say so plainly
  const live = status.configured && status.available;
  const noKey = !status.configured;
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Badge
          variant={live ? "success" : "warning"}
          className="hidden items-center gap-1 whitespace-nowrap sm:flex"
        >
          {live ? <Sparkles className="h-3 w-3" /> : <Wrench className="h-3 w-3" />}
          {live ? "Live AI" : noKey ? "No model key" : "Rule-based mode"}
        </Badge>
      </TooltipTrigger>
      <TooltipContent className="max-w-[260px] text-xs">
        {live
          ? "The language model is reachable, so free-text questions and explanations are being phrased live. Coverage decisions are always rule-based, with or without it."
          : noKey
            ? "This backend has no model key configured (GEMINI_API_KEYS), so understanding and wording fall back to deterministic templates. Set the key on the server to enable the live agents. Coverage decisions are unaffected — they are always rule-based."
            : "The language model's free quota is exhausted right now, so this turn's chat understanding uses deterministic templates instead. Coverage decisions are unaffected — they are always rule-based."}
      </TooltipContent>
    </Tooltip>
  );
}
