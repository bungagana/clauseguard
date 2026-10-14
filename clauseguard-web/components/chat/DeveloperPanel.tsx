"use client";

import { Fragment, useMemo, useState } from "react";
import { ChevronDown } from "lucide-react";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import type { ChatMessage } from "@/lib/message";
import type { PoliciesResponse, PolicyTuple, PolicyView, TraceStep, VerdictResult } from "@/lib/types";
import { titleCase } from "@/lib/format";
import { cn } from "@/lib/utils";

const VERDICT_VARIANT: Record<string, "success" | "warning" | "destructive" | "muted"> = {
  COVERED: "success",
  DENIED: "destructive",
  CLARIFY: "warning",
  NOT_APPLICABLE: "muted",
  NOT_SPECIFIED: "muted",
};

const RELATION_COLOR: Record<string, string> = {
  COVERS: "#2f9e62",
  PAYS: "#2f9e62",
  PERMITS: "#2f9e62",
  HAS_RIDER: "#2f9e62",
  EXCLUDES: "#c4463a",
  TERMINATES_IF: "#c4463a",
  EXCEPTS: "#b8872f",
  CONDITIONED_ON: "#9a5fd1",
  HAS_PERIOD: "#2f7dd1",
  DEFINES: "#6b7280",
  REQUIRES_DOCUMENT: "#0e9aa7",
};
const DEFAULT_RELATION_COLOR = "#6b7280";

function relationColor(relation: string): string {
  return RELATION_COLOR[relation] ?? DEFAULT_RELATION_COLOR;
}

function confidencePct(c: number | undefined): string {
  return typeof c === "number" ? `${Math.round(c * 100)}%` : "—";
}

function TupleDetail({ tuple }: { tuple: PolicyTuple }) {
  return (
    <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-[11px] text-foreground/80">
      <dt className="text-muted-foreground">section</dt>
      <dd>{tuple.section ?? "—"}</dd>
      <dt className="text-muted-foreground">language</dt>
      <dd>{tuple.language}</dd>
      <dt className="text-muted-foreground">source_tier</dt>
      <dd>{tuple.source_tier}</dd>
      <dt className="text-muted-foreground">confidence</dt>
      <dd>{confidencePct(tuple.confidence)}</dd>
      <dt className="col-span-2 text-muted-foreground">clause text</dt>
      <dd className="col-span-2 whitespace-pre-wrap rounded-md bg-muted/60 p-2 font-mono text-[11px]">{tuple.text || "—"}</dd>
    </dl>
  );
}

function TupleTable({ tuples, firedIds }: { tuples: PolicyTuple[]; firedIds?: Set<string> }) {
  const [expandedId, setExpandedId] = useState<string | null>(null);

  if (!tuples.length) {
    return <p className="text-xs text-muted-foreground">No clause tuples extracted.</p>;
  }
  return (
    <div className="overflow-x-auto rounded-lg border border-border">
      <table className="w-full min-w-[640px] border-collapse font-mono text-[11px]">
        <thead>
          <tr className="bg-muted/60 text-left text-muted-foreground">
            <th className="w-5 px-1 py-1.5" />
            <th className="px-2 py-1.5 font-medium">id</th>
            <th className="px-2 py-1.5 font-medium">head</th>
            <th className="px-2 py-1.5 font-medium">relation</th>
            <th className="px-2 py-1.5 font-medium">object</th>
            <th className="px-2 py-1.5 font-medium">summary</th>
            <th className="px-2 py-1.5 font-medium">confidence</th>
            <th className="px-2 py-1.5 font-medium">source_tier</th>
          </tr>
        </thead>
        <tbody>
          {tuples.map((t) => {
            const open = expandedId === t.id;
            return (
              <Fragment key={t.id}>
                <tr
                  onClick={() => setExpandedId(open ? null : t.id)}
                  className={cn(
                    "cursor-pointer border-t border-border/70 align-top hover:bg-muted/40",
                    firedIds?.has(t.id) && "bg-primary/5"
                  )}
                >
                  <td className="px-1 py-1.5 text-center">
                    <ChevronDown className={cn("h-3 w-3 text-muted-foreground transition-transform", open && "rotate-180")} />
                  </td>
                  <td className="px-2 py-1.5 text-muted-foreground">
                    {t.id}
                    {firedIds?.has(t.id) && (
                      <Badge variant="default" className="ml-1.5 align-middle text-[9px]">
                        fired
                      </Badge>
                    )}
                  </td>
                  <td className="px-2 py-1.5">{t.head ?? "—"}</td>
                  <td className="px-2 py-1.5">{t.relation}</td>
                  <td className="px-2 py-1.5">{t.object}</td>
                  <td className="max-w-[240px] whitespace-pre-wrap px-2 py-1.5 text-foreground/80">{t.summary}</td>
                  <td className="px-2 py-1.5">{confidencePct(t.confidence)}</td>
                  <td className="px-2 py-1.5">{t.source_tier}</td>
                </tr>
                {open && (
                  <tr className="border-t border-border/40 bg-muted/20">
                    <td colSpan={8} className="px-3 py-2">
                      <TupleDetail tuple={t} />
                    </td>
                  </tr>
                )}
              </Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

interface GraphNode {
  key: string;
  kind: "doc" | "tuple" | "object";
  label: string;
  x: number;
  y: number;
  color: string;
  tuple?: PolicyTuple;
}

function circularMean(angles: number[]): number {
  const sx = angles.reduce((s, a) => s + Math.cos(a), 0);
  const sy = angles.reduce((s, a) => s + Math.sin(a), 0);
  return Math.atan2(sy, sx);
}

function buildGraph(tuples: PolicyTuple[], docLabel: string) {
  const size = 440;
  const cx = size / 2;
  const cy = size / 2;
  const tupleRadius = 140;
  const objectRadius = 205;

  const nodes: GraphNode[] = [];
  const edges: { from: string; to: string; color: string }[] = [];

  nodes.push({ key: "__doc__", kind: "doc", label: docLabel, x: cx, y: cy, color: "#1f2937" });

  const tupleAngle = new Map<string, number>();
  tuples.forEach((t, i) => {
    const angle = (2 * Math.PI * i) / Math.max(tuples.length, 1) - Math.PI / 2;
    tupleAngle.set(t.id, angle);
    nodes.push({
      key: t.id,
      kind: "tuple",
      label: t.relation,
      x: cx + tupleRadius * Math.cos(angle),
      y: cy + tupleRadius * Math.sin(angle),
      color: relationColor(t.relation),
      tuple: t,
    });
    edges.push({ from: "__doc__", to: t.id, color: "#d1d5db" });
  });

  const objectAngles = new Map<string, number[]>();
  tuples.forEach((t) => {
    const a = tupleAngle.get(t.id) ?? 0;
    const list = objectAngles.get(t.object) ?? [];
    list.push(a);
    objectAngles.set(t.object, list);
  });

  const sortedObjects = Array.from(objectAngles.entries()).sort(
    (a, b) => circularMean(a[1]) - circularMean(b[1])
  );
  const objectFinalAngle = new Map<string, number>();
  sortedObjects.forEach(([object], i) => {
    objectFinalAngle.set(object, (2 * Math.PI * i) / Math.max(sortedObjects.length, 1) - Math.PI / 2);
  });

  sortedObjects.forEach(([object]) => {
    const angle = objectFinalAngle.get(object) ?? 0;
    nodes.push({
      key: `obj:${object}`,
      kind: "object",
      label: titleCase(object) || object,
      x: cx + objectRadius * Math.cos(angle),
      y: cy + objectRadius * Math.sin(angle),
      color: "#9ca3af",
    });
  });

  tuples.forEach((t) => {
    edges.push({ from: t.id, to: `obj:${t.object}`, color: relationColor(t.relation) });
  });

  return { size, nodes, edges };
}

function PolicyGraph({ policy, firedIds }: { policy: PolicyView; firedIds: Set<string> }) {
  const { size, nodes, edges } = useMemo(() => buildGraph(policy.tuples, policy.product_name), [policy]);
  const [selected, setSelected] = useState<string | null>(null);
  const byKey = new Map(nodes.map((n) => [n.key, n]));
  const selectedTuple = selected ? byKey.get(selected)?.tuple : undefined;

  if (!policy.tuples.length) {
    return <p className="text-xs text-muted-foreground">No clause tuples extracted.</p>;
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap gap-x-3 gap-y-1 text-[10px] text-muted-foreground">
        {Object.entries(RELATION_COLOR)
          .filter(([rel]) => policy.tuples.some((t) => t.relation === rel))
          .map(([rel, color]) => (
            <span key={rel} className="inline-flex items-center gap-1">
              <span className="inline-block h-2 w-2 rounded-full" style={{ backgroundColor: color }} />
              {rel}
            </span>
          ))}
      </div>
      <svg viewBox={`0 0 ${size} ${size}`} className="h-[320px] w-full rounded-lg border border-border bg-card">
        <g>
          {edges.map((e, i) => {
            const from = byKey.get(e.from);
            const to = byKey.get(e.to);
            if (!from || !to) return null;
            return (
              <line
                key={i}
                x1={from.x}
                y1={from.y}
                x2={to.x}
                y2={to.y}
                stroke={e.color}
                strokeWidth={1}
                opacity={0.5}
              />
            );
          })}
        </g>
        <g>
          {nodes.map((n) => {
            const isSelected = n.key === selected;
            const fired = n.tuple ? firedIds.has(n.tuple.id) : false;
            const r = n.kind === "doc" ? 10 : n.kind === "tuple" ? 6 : 5;
            return (
              <g
                key={n.key}
                className={cn(n.kind === "tuple" && "cursor-pointer")}
                onClick={() => n.kind === "tuple" && setSelected(isSelected ? null : n.key)}
              >
                <circle
                  cx={n.x}
                  cy={n.y}
                  r={r}
                  fill={n.color}
                  stroke={isSelected ? "#111827" : fired ? "#111827" : "none"}
                  strokeWidth={isSelected ? 2.5 : fired ? 1.5 : 0}
                />
                <text
                  x={n.x}
                  y={n.y + r + 9}
                  textAnchor="middle"
                  className="select-none"
                  style={{ fontSize: n.kind === "object" ? 8 : 8.5, fill: "currentColor", opacity: n.kind === "doc" ? 1 : 0.75 }}
                >
                  {n.label.length > 16 ? `${n.label.slice(0, 15)}…` : n.label}
                </text>
              </g>
            );
          })}
        </g>
      </svg>
      {selectedTuple ? (
        <div className="rounded-lg border border-border bg-muted/20 p-2.5">
          <div className="mb-1.5 flex flex-wrap items-center gap-1.5">
            <Badge variant="outline" className="font-mono text-[10px]">
              {selectedTuple.id}
            </Badge>
            <span className="text-xs font-semibold">{selectedTuple.relation}</span>
            <span className="text-xs text-muted-foreground">→ {selectedTuple.object}</span>
            {firedIds.has(selectedTuple.id) && (
              <Badge variant="default" className="text-[9px]">
                fired
              </Badge>
            )}
          </div>
          <p className="mb-1.5 text-xs text-foreground/80">{selectedTuple.summary}</p>
          <TupleDetail tuple={selectedTuple} />
        </div>
      ) : (
        <p className="text-[11px] text-muted-foreground">Click a clause node to see its full detail.</p>
      )}
    </div>
  );
}

function TraceRow({ step, fired }: { step: TraceStep; fired: boolean }) {
  return (
    <li
      className={cn(
        "flex flex-wrap items-center gap-2 rounded-md border border-border/70 px-2.5 py-1.5 font-mono text-[11px]",
        fired && "border-primary/40 bg-primary/5"
      )}
    >
      <Badge variant="outline" className="shrink-0">
        {step.rule}
      </Badge>
      <span className="font-semibold">{step.result}</span>
      {step.tuple_id && <span className="text-muted-foreground">{step.tuple_id}</span>}
      {step.detail && <span className="text-foreground/70">— {step.detail}</span>}
      {fired && (
        <Badge variant="default" className="ml-auto shrink-0 text-[9px]">
          fired
        </Badge>
      )}
    </li>
  );
}

function VerdictTrace({ verdict }: { verdict: VerdictResult }) {
  const fired = new Set(verdict.fired_tuple_ids);
  return (
    <div className="flex flex-col gap-2 rounded-xl border border-border bg-card p-3">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant={VERDICT_VARIANT[verdict.verdict] ?? "muted"} className="font-mono">
          {verdict.verdict}
        </Badge>
        <span className="text-xs text-muted-foreground">policy {verdict.policy_id}</span>
        {verdict.payable && (
          <span className="text-xs text-muted-foreground">
            payable {verdict.currency} {verdict.payable}
          </span>
        )}
        {verdict.denial_code && (
          <Badge variant="destructive" className="font-mono text-[10px]">
            {verdict.denial_code}
          </Badge>
        )}
      </div>
      {verdict.trace?.length ? (
        <ul className="flex flex-col gap-1.5">
          {verdict.trace.map((step, i) => (
            <TraceRow key={`${step.rule}-${i}`} step={step} fired={Boolean(step.tuple_id && fired.has(step.tuple_id))} />
          ))}
        </ul>
      ) : (
        <p className="text-xs text-muted-foreground">No evaluation steps recorded for this verdict.</p>
      )}
    </div>
  );
}

function PolicyClauseSection({ policy, firedIds, defaultOpen }: { policy: PolicyView; firedIds: Set<string>; defaultOpen: boolean }) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <div className="rounded-xl border border-border bg-card">
      <button type="button" onClick={() => setOpen((o) => !o)} className="flex w-full items-center justify-between gap-2 p-3 text-left">
        <div className="flex min-w-0 items-center gap-2">
          <p className="truncate text-xs font-semibold">{policy.product_name}</p>
          <Badge variant="muted" className="shrink-0 text-[10px]">
            {policy.id}
          </Badge>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <span className="text-[10px] text-muted-foreground">{policy.tuples.length} tuples</span>
          <ChevronDown className={cn("h-3.5 w-3.5 text-muted-foreground transition-transform", open && "rotate-180")} />
        </div>
      </button>
      {open && (
        <div className="border-t border-border p-3 pt-2.5">
          <Tabs defaultValue="table">
            <TabsList>
              <TabsTrigger value="table">Table</TabsTrigger>
              <TabsTrigger value="graph">Graph</TabsTrigger>
            </TabsList>
            <TabsContent value="table">
              <TupleTable tuples={policy.tuples} firedIds={firedIds} />
            </TabsContent>
            <TabsContent value="graph">
              <PolicyGraph policy={policy} firedIds={firedIds} />
            </TabsContent>
          </Tabs>
        </div>
      )}
    </div>
  );
}

export function DeveloperPanel({
  open,
  onOpenChange,
  policies,
  messages,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  policies: PoliciesResponse | null;
  messages: ChatMessage[];
}) {
  const lastReply = [...messages].reverse().find((m) => m.role === "assistant" && m.reply)?.reply;
  const traceVerdicts: VerdictResult[] = lastReply?.verdicts?.length
    ? lastReply.verdicts
    : lastReply?.readiness?.verdict
      ? [lastReply.readiness.verdict]
      : [];
  const tracedPolicyIds = new Set(traceVerdicts.map((v) => v.policy_id));

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-5/6 sm:max-w-xl">
        <SheetHeader>
          <SheetTitle>Developer</SheetTitle>
          <p className="text-xs text-muted-foreground">
            What the extractor pulled from each policy, and how the last answer was decided.
          </p>
        </SheetHeader>
        <Separator className="my-2" />
        <div className="flex flex-1 flex-col gap-5 overflow-y-auto pb-4">
          <section className="flex flex-col gap-2">
            <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Last answer trace</p>
            {lastReply ? (
              traceVerdicts.length ? (
                <div className="flex flex-col gap-2">
                  {traceVerdicts.map((v, i) => (
                    <VerdictTrace key={`${v.policy_id}-${i}`} verdict={v} />
                  ))}
                </div>
              ) : (
                <p className="text-xs text-muted-foreground">
                  trace not available — the last reply did not evaluate a coverage verdict.
                </p>
              )
            ) : (
              <p className="text-xs text-muted-foreground">No chat reply yet this session.</p>
            )}
          </section>

          <section className="flex flex-col gap-3">
            <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Extracted clause tuples</p>
            {policies?.policies.length ? (
              policies.policies.map((p) => (
                <PolicyClauseSection
                  key={p.id}
                  policy={p}
                  firedIds={new Set(traceVerdicts.find((v) => v.policy_id === p.id)?.fired_tuple_ids ?? [])}
                  defaultOpen={tracedPolicyIds.has(p.id) || policies.policies.length === 1}
                />
              ))
            ) : (
              <p className="text-xs text-muted-foreground">No policies loaded yet.</p>
            )}
          </section>
        </div>
      </SheetContent>
    </Sheet>
  );
}
