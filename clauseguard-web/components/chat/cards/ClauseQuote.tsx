"use client";

import { useState } from "react";
import { ChevronDown, Quote } from "lucide-react";
import { cn } from "@/lib/utils";
import { AnimatePresence, motion } from "framer-motion";
import { CopyButton } from "../CopyButton";

export function ClauseQuote({
  citation,
  text,
  label = "Show clause",
}: {
  citation: string;
  text: string;
  label?: string;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div className="mt-1.5">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="inline-flex items-center gap-1 text-xs font-medium text-muted-foreground hover:text-foreground transition-colors"
      >
        <Quote className="h-3 w-3" />
        {open ? "Hide" : label}
        <ChevronDown className={cn("h-3 w-3 transition-transform", open && "rotate-180")} />
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.18 }}
            className="overflow-hidden"
          >
            <blockquote className="mt-2 rounded-lg border border-border bg-muted/60 px-3 py-2 text-xs leading-relaxed text-muted-foreground">
              <div className="flex items-start justify-between gap-2">
                <span className="font-mono text-[10px] uppercase tracking-wide text-muted-foreground/70">{citation}</span>
                <CopyButton getText={() => `"${text}" (${citation})`} label="Copy clause" className="shrink-0" />
              </div>
              <p className="mt-1 italic text-foreground/80">&ldquo;{text}&rdquo;</p>
            </blockquote>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
