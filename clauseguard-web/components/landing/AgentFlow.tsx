"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { AnimatePresence, motion } from "framer-motion";
import { Pause, Play, RotateCcw, ArrowRight } from "lucide-react";
import { cn } from "@/lib/utils";

// Every line below is copied from a real reply the backend gave on 2026-10-14 (see public/screens).
// The animation replays those replies; it does not invent anything.
type Gate = "auto" | "tap" | "never";

interface Scenario {
  key: string;
  persona: string;
  chip: string;
  question: string;
  context: string;
  facts: string[];
  rules: string[];
  gate: Gate;
  gateNote: string;
  outcome: { kind: "verdict" | "allocation" | "refusal"; title: string; lines: string[]; clause?: string; question?: string };
}

const SCENARIOS: Scenario[] = [
  {
    key: "dengue",
    persona: "Rizky, graduate student",
    chip: "Hospital claim",
    question: "I was admitted for dengue on 25 September for 3 days. Can I claim, and what is the deadline?",
    context: "New situation: an illness with a hospital stay. Nothing earlier in the chat applies.",
    facts: ["Admitted 25 Sep 2026", "3 days in hospital", "Cause: illness (dengue)", "Discharge date: computed 28 Sep"],
    rules: ["Hospital Cash Plan: daily cash if illness requires hospitalization", "Filing window: 60 days after treatment ends", "National health: depends on partner facility"],
    gate: "auto",
    gateNote: "Reading and calculating: runs by itself.",
    outcome: {
      kind: "verdict",
      title: "Covered · Rp 1.500.000",
      lines: ["File by 26 Nov 2026 (43 days left)."],
      clause: "“This Policy provide daily cash compensation to Participants … if during the Insurance period, the Participant is affected by an illness … and requires Hospitalization.”",
      question: "Is the hospital a BPJS Kesehatan partner facility?",
    },
  },
  {
    key: "accident",
    persona: "Dewi, delivery rider",
    chip: "Who pays first",
    question: "A car hit me while I was delivering an order. 6 days in hospital, bill Rp 22 million. My licence had expired.",
    context: "New situation: a road accident while working, four policies could respond.",
    facts: ["Accident with another vehicle", "On an active delivery", "6 days in hospital · bill Rp 22.000.000", "Driving licence: expired"],
    rules: ["Road-accident fund: up to Rp 20.000.000 when two vehicles are involved", "Platform cover: excess over other recoveries, on-trip only", "Personal accident: excludes riding without a valid licence"],
    gate: "auto",
    gateNote: "Ordering payers is a calculation: runs by itself.",
    outcome: {
      kind: "allocation",
      title: "Rp 22.000.000 recovered",
      lines: ["1. Road-accident fund (Jasa Raharja) · Rp 20.000.000", "2. Platform on-trip cover · Rp 2.000.000", "Personal accident: not covered (licence)", "Single policy only would recover Rp 20.000.000"],
    },
  },
  {
    key: "account",
    persona: "Sari, family plan",
    chip: "Change payout account",
    question: "Change the payout bank account for my policy to 0123456789 at Bank ABC.",
    context: "Not a claim question: a request to change money or identity details.",
    facts: ["No facts needed: the request itself decides the route"],
    rules: ["Payout account, beneficiary and premium account changes have no tool the AI can call"],
    gate: "never",
    gateNote: "Handled by a person at the insurer, who verifies you through a separate channel.",
    outcome: {
      kind: "refusal",
      title: "Handed to a human",
      lines: ["Ticket OOB-A0F84325 opened, marked “requested via AI assistant”.", "Nothing on your account has been changed."],
    },
  },
];

type Stage = 0 | 1 | 2 | 3 | 4 | 5 | 6; // 0 idle, 1 question, 2 context, 3 facts, 4 rules, 5 guardian, 6 outcome
const STAGE_MS = [0, 900, 1500, 2200, 2200, 1500, 5200];

export function AgentFlow() {
  const [index, setIndex] = useState(0);
  const [stage, setStage] = useState<Stage>(0);
  const [paused, setPaused] = useState(false);
  const s = SCENARIOS[index];

  useEffect(() => {
    if (paused) return;
    const next = stage >= 6 ? null : ((stage + 1) as Stage);
    const t = setTimeout(() => {
      if (next === null) {
        setIndex((i) => (i + 1) % SCENARIOS.length);
        setStage(0);
      } else setStage(next);
    }, next === null ? STAGE_MS[6] : STAGE_MS[stage]);
    return () => clearTimeout(t);
  }, [stage, paused, index]);

  function pick(i: number) {
    setIndex(i);
    setStage(0);
    setPaused(false);
  }

  const gateColor = s.gate === "never" ? "hsl(var(--destructive))" : s.gate === "tap" ? "hsl(var(--warning))" : "hsl(var(--success))";
  const lit = (n: number) => stage >= n;

  return (
    <div className="overflow-hidden rounded-2xl border border-border bg-card shadow-float">
      <div className="flex flex-wrap items-center gap-1.5 border-b border-border bg-muted/50 px-3 py-2">
        {SCENARIOS.map((sc, i) => (
          <button
            key={sc.key}
            type="button"
            onClick={() => pick(i)}
            className={cn("rounded-full px-2.5 py-1 text-xs font-medium transition-colors", i === index ? "bg-primary text-primary-foreground" : "bg-card text-muted-foreground hover:text-foreground")}
          >
            {sc.chip}
          </button>
        ))}
        <span className="ml-auto flex items-center gap-1">
          <button type="button" onClick={() => setPaused((p) => !p)} aria-label={paused ? "Play" : "Pause"} className="rounded-full p-1.5 text-muted-foreground hover:bg-card hover:text-foreground">
            {paused ? <Play className="h-3.5 w-3.5" /> : <Pause className="h-3.5 w-3.5" />}
          </button>
          <button type="button" onClick={() => { setStage(0); setPaused(false); }} aria-label="Replay" className="rounded-full p-1.5 text-muted-foreground hover:bg-card hover:text-foreground">
            <RotateCcw className="h-3.5 w-3.5" />
          </button>
        </span>
      </div>

      <div className="grid gap-0 md:grid-cols-[1fr_1.35fr]">
        {/* left: the conversation side */}
        <div className="flex min-h-[460px] flex-col gap-3 border-b border-border p-4 md:border-b-0 md:border-r">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">{s.persona} asks</p>
          <AnimatePresence mode="wait">
            <motion.div key={s.key + "-q"} initial={{ opacity: 0, y: 6 }} animate={{ opacity: lit(1) ? 1 : 0, y: lit(1) ? 0 : 6 }} transition={{ duration: 0.3 }} className="self-end rounded-2xl bg-primary px-3.5 py-2 text-sm text-primary-foreground">
              {s.question}
            </motion.div>
          </AnimatePresence>

          <ol className="mt-1 flex flex-col gap-2 text-sm">
            <Step on={lit(2)} label="Conversation Agent" value={s.context} />
            <Step on={lit(3)} label="Fact Agent" value={s.facts.join(" · ")} />
            <Step on={lit(4)} label="Rules Engine" value={s.rules.join(" · ")} />
            <Step on={lit(5)} label="Guardian" value={s.gateNote} color={gateColor} />
          </ol>

        </div>

        {/* right: the agent map */}
        <div className="relative flex flex-col gap-3 p-3">
          <FlowSvg stage={stage} gate={s.gate} gateColor={gateColor} />
          <AnimatePresence>
            {lit(6) && (
              <motion.div key={s.key + "-out"} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.35 }}
                className={cn("rounded-xl border border-l-[3px] bg-background p-3", s.gate === "never" ? "border-destructive/40 border-l-destructive" : "border-border border-l-success")}>
                <p className="text-sm font-semibold">{s.outcome.title}</p>
                {s.outcome.lines.map((l) => (
                  <p key={l} className="mt-0.5 text-xs text-muted-foreground">{l}</p>
                ))}
                {s.outcome.clause && <p className="mt-1.5 border-l-2 border-border pl-2 text-[11px] italic text-foreground/75">{s.outcome.clause}</p>}
                {s.outcome.question && <p className="mt-1.5 text-xs font-medium text-primary">One question: {s.outcome.question}</p>}
              </motion.div>
            )}
          </AnimatePresence>
          <div className="mt-auto self-end">
            <Link href="/chat?mode=demo" className="inline-flex items-center gap-1 rounded-full bg-primary px-3 py-1.5 text-xs font-semibold text-primary-foreground shadow-soft hover:bg-primary/90">
              Try it live <ArrowRight className="h-3 w-3" />
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}

function Step({ on, label, value, color }: { on: boolean; label: string; value: string; color?: string }) {
  return (
    <li className={cn("flex items-start gap-2 transition-opacity duration-300", on ? "opacity-100" : "opacity-30")}>
      <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full" style={{ background: on ? color ?? "hsl(var(--primary))" : "hsl(var(--border))" }} />
      <div className="min-w-0">
        <p className="text-xs font-semibold">{label}</p>
        <p className="text-xs leading-snug text-muted-foreground">{on ? value : "…"}</p>
      </div>
    </li>
  );
}

const NODE = { w: 168, h: 44 };

function FlowSvg({ stage, gate, gateColor }: { stage: Stage; gate: Gate; gateColor: string }) {
  const P = "hsl(var(--primary))";
  const M = "hsl(var(--muted-foreground))";
  const nodes = useMemo(
    () => [
      { id: "conv", x: 20, y: 24, label: "Conversation", badge: "AI", on: 2 },
      { id: "fact", x: 20, y: 104, label: "Fact Agent", badge: "AI", on: 3 },
      { id: "reader", x: 220, y: 24, label: "Document Reader", badge: "AI", on: 4 },
      { id: "engine", x: 120, y: 184, label: "Rules Engine", badge: "code", on: 4 },
      { id: "guard", x: 120, y: 264, label: "Guardian", badge: "code", on: 5 },
      { id: "expl", x: 20, y: 344, label: "Explainer Agent", badge: "AI", on: 6 },
    ],
    []
  );
  const outs = [
    { id: "auto", x: 300, y: 240, label: "Automatic", color: "hsl(var(--success))", key: "auto" as Gate },
    { id: "tap", x: 300, y: 276, label: "Only after your tap", color: "hsl(var(--warning))", key: "tap" as Gate },
    { id: "never", x: 300, y: 312, label: "A person handles it", color: "hsl(var(--destructive))", key: "never" as Gate },
  ];
  const edge = (d: string, on: boolean, color = P) => (
    <motion.path d={d} fill="none" stroke={on ? color : "hsl(var(--border))"} strokeWidth={on ? 2 : 1.4} initial={false} animate={{ pathLength: 1, opacity: on ? 1 : 0.7 }} />
  );
  return (
    <svg viewBox="0 0 452 404" className="h-auto w-full text-foreground" role="img" aria-label="How the agents hand a question to each other">
      {/* edges */}
      {edge("M104 68 V104", stage >= 3)}
      {edge("M104 148 V184 H120", stage >= 4)}
      {edge("M304 68 V184 H288", stage >= 4)}
      {edge("M204 228 V264", stage >= 5)}
      {outs.map((o) => edge(`M288 286 H${o.x}`.replace("286", String(o.y + 16)), stage >= 5 && gate === o.key, o.color))}
      {edge("M204 308 V344 H188", stage >= 6, gate === "never" ? gateColor : P)}
      {/* nodes */}
      {nodes.map((n) => {
        const on = stage >= n.on;
        return (
          <g key={n.id}>
            <motion.rect x={n.x} y={n.y} width={NODE.w} height={NODE.h} rx={10} fill="hsl(var(--card))" stroke={on ? (n.badge === "code" ? P : "currentColor") : "hsl(var(--border))"} strokeWidth={on ? 1.8 : 1.2} initial={false} animate={{ opacity: on ? 1 : 0.5 }} />
            <text x={n.x + 10} y={n.y + 27} fontSize={12.5} fontWeight={700} fill={on ? (n.badge === "code" ? P : "currentColor") : M}>{n.label}</text>
            <rect x={n.x + NODE.w - 36} y={n.y + 14} width={28} height={16} rx={8} fill={n.badge === "code" ? P : M} fillOpacity={0.12} />
            <text x={n.x + NODE.w - 22} y={n.y + 25.5} textAnchor="middle" fontSize={8.5} fontWeight={700} fill={n.badge === "code" ? P : M}>{n.badge}</text>
          </g>
        );
      })}
      {outs.map((o) => {
        const on = stage >= 5 && gate === o.key;
        return (
          <g key={o.id}>
            <rect x={o.x} y={o.y} width={140} height={32} rx={9} fill="hsl(var(--card))" stroke={on ? o.color : "hsl(var(--border))"} strokeWidth={on ? 1.8 : 1.2} opacity={on || stage < 5 ? 1 : 0.45} />
            <text x={o.x + 10} y={o.y + 20.5} fontSize={11.5} fontWeight={700} fill={on ? o.color : M}>{o.label}</text>
          </g>
        );
      })}
      <text x={20} y={400} fontSize={10} fill={M}>Every step is written to a tamper-evident audit trail.</text>
    </svg>
  );
}
