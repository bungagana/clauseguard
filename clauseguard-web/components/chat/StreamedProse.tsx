"use client";

import { useEffect, useRef, useState } from "react";

const WORD_DELAY_MS = 22;

/**
 * Simulated streaming reveal for text the backend already returned in full. Only animates
 * when `animate` is true (a reply that just arrived live); history, scene and offline replies
 * render instantly. Clicking anywhere on the text reveals the rest immediately.
 */
export function StreamedProse({
  text,
  animate,
  className,
  onDone,
}: {
  text: string;
  animate: boolean;
  className?: string;
  onDone?: () => void;
}) {
  const tokensRef = useRef<string[]>(text.split(/(\s+)/));
  const [count, setCount] = useState(animate ? 0 : tokensRef.current.length);
  const notifiedRef = useRef(!animate);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!animate) {
      if (!notifiedRef.current) {
        notifiedRef.current = true;
        onDone?.();
      }
      return;
    }
    if (count >= tokensRef.current.length) {
      if (!notifiedRef.current) {
        notifiedRef.current = true;
        onDone?.();
      }
      return;
    }
    const timer = setTimeout(() => setCount((c) => Math.min(c + 1, tokensRef.current.length)), WORD_DELAY_MS);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [animate, count]);

  useEffect(() => {
    if (animate && count < tokensRef.current.length) {
      rootRef.current?.scrollIntoView({ block: "nearest" });
    }
  }, [animate, count]);

  const finished = count >= tokensRef.current.length;

  function skip() {
    if (!finished) setCount(tokensRef.current.length);
  }

  return (
    <div
      ref={rootRef}
      className={className}
      onClick={skip}
      role={!finished ? "button" : undefined}
      aria-label={!finished ? "Show the rest of this reply" : undefined}
    >
      {tokensRef.current.slice(0, count).join("")}
      {!finished && <span className="ml-0.5 inline-block h-3.5 w-1.5 animate-pulse bg-current align-middle opacity-60" />}
    </div>
  );
}
