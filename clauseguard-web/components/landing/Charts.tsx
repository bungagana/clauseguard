// Horizontal bar charts as inline SVG: one hue, the highlighted row in the brand colour, all text
// in text tokens. Values are copied from the evidence folder and the benchmark authors' result files.
export interface BarRow {
  label: string;
  value: number;
  note?: string;
  highlight?: boolean;
  ceiling?: number;      // a lighter extension past `value`, e.g. the oracle ceiling
  ceilingLabel?: string;
}

export function BarChart({
  rows, unit = "%", max = 100, title, caption, lowerIsBetter = false,
}: {
  rows: BarRow[]; unit?: string; max?: number; title: string; caption: string; lowerIsBetter?: boolean;
}) {
  const rowH = 34;
  const labelW = 190;
  const width = 560;
  const plotW = width - labelW - (rows.some((r) => r.ceiling) ? 125 : 70);
  const height = rows.length * rowH + 8;
  return (
    <figure className="rounded-2xl border border-border bg-card p-5 shadow-soft">
      <figcaption className="mb-3">
        <p className="text-sm font-semibold">{title}</p>
        <p className="text-xs text-muted-foreground">{caption}{lowerIsBetter ? " Lower is better." : ""}</p>
      </figcaption>
      <svg viewBox={`0 0 ${width} ${height}`} className="h-auto w-full" role="img" aria-label={title}>
        {rows.map((r, i) => {
          const y = i * rowH + 4;
          const w = Math.max(4, (r.value / max) * plotW);
          const fill = r.highlight ? "hsl(var(--primary))" : "hsl(var(--muted-foreground) / 0.35)";
          const cw = r.ceiling ? Math.max(0, (r.ceiling / max) * plotW - w) : 0;
          const valueX = labelW + w + cw + 8;
          return (
            <g key={r.label}>
              <title>{`${r.label}: ${r.value}${unit}${r.ceiling ? `, ${r.ceilingLabel ?? "ceiling"} ${r.ceiling}${unit}` : ""}${r.note ? ` (${r.note})` : ""}`}</title>
              <text x={labelW - 10} y={y + 17} textAnchor="end" fontSize={12} fontWeight={r.highlight ? 700 : 500} fill="hsl(var(--foreground))">{r.label}</text>
              <rect x={labelW} y={y + 6} width={plotW} height={16} rx={4} fill="hsl(var(--muted))" />
              {cw > 0 && <rect x={labelW + w - 4} y={y + 6} width={cw + 4} height={16} rx={4} fill="hsl(var(--primary) / 0.28)" />}
              <rect x={labelW} y={y + 6} width={w} height={16} rx={4} fill={fill} />
              <text x={valueX} y={y + 18} fontSize={12} fontWeight={700} fill="hsl(var(--foreground))" className="tabular-nums">
                {r.value}{unit}{r.ceiling ? ` → ${r.ceiling}${unit}` : ""}
              </text>
            </g>
          );
        })}
      </svg>
      <ul className="mt-2 space-y-0.5 text-[11px] text-muted-foreground">
        {rows.filter((r) => r.note).map((r) => (
          <li key={r.label}>{r.label}: {r.note}</li>
        ))}
      </ul>
    </figure>
  );
}

export function StatTile({ value, label, note }: { value: string; label: string; note: string }) {
  return (
    <div className="rounded-2xl border border-border bg-card p-5 shadow-soft">
      <p className="text-3xl font-semibold tabular-nums tracking-tight">{value}</p>
      <p className="mt-1 text-sm font-medium">{label}</p>
      <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{note}</p>
    </div>
  );
}
