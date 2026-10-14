import { AlertTriangle } from "lucide-react";

export function AlertBanner({ alerts }: { alerts: string[] }) {
  if (!alerts.length) return null;
  return (
    <div className="flex flex-col gap-1.5">
      {alerts.map((a, i) => (
        <div key={i} className="flex items-start gap-2 rounded-lg border border-warning/30 bg-warning/10 px-3 py-2 text-xs text-warning-foreground">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          <span>{a.replace(/^Alert:\s*/, "")}</span>
        </div>
      ))}
    </div>
  );
}
