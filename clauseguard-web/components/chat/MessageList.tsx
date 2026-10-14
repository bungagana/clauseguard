"use client";

import { useEffect, useRef } from "react";
import { AnimatePresence } from "framer-motion";
import type { ChatMessage } from "@/lib/message";
import type { PoliciesResponse } from "@/lib/types";
import { MessageBubble } from "./MessageBubble";

export function MessageList({
  messages,
  policies,
  onConfirm,
  onCancel,
  onViewPolicy,
  onRegenerate,
  onQuickReply,
  sessionToken,
  autonomy,
}: {
  messages: ChatMessage[];
  policies: PoliciesResponse | null;
  onConfirm: (id: string) => void;
  onCancel: (id: string) => void;
  onViewPolicy: (policyId: string) => void;
  onRegenerate: (id: string) => void;
  onQuickReply?: (text: string) => void;
  sessionToken?: () => string | undefined;
  autonomy?: "observe" | "draft" | "act";
}) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const last = messages[messages.length - 1];
  const lastTyping = last?.typing;
  const lastEntitlement = last?.entitlement;
  const lastAssistantReplyId = [...messages].reverse().find((m) => m.role === "assistant" && m.reply)?.id;

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages.length, lastTyping, lastEntitlement]);

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="mx-auto flex max-w-3xl flex-col gap-4 px-4 py-6 sm:px-6">
        <AnimatePresence initial={false}>
          {messages.map((m) => (
            <MessageBubble
              key={m.id}
              message={m}
              policies={policies}
              onConfirm={() => onConfirm(m.id)}
              onCancel={() => onCancel(m.id)}
              onViewPolicy={onViewPolicy}
              onRegenerate={() => onRegenerate(m.id)}
              canRegenerate={m.id === lastAssistantReplyId}
              onQuickReply={onQuickReply}
              sessionToken={sessionToken}
              autonomy={autonomy}
            />
          ))}
        </AnimatePresence>
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
