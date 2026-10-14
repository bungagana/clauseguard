import { WifiOff } from "lucide-react";

export function OfflineBanner() {
  return (
    <div className="flex items-center justify-center gap-2 bg-warning/10 px-4 py-1.5 text-center text-xs font-medium text-warning-foreground">
      <WifiOff className="h-3.5 w-3.5" />
      Demo backend is offline — showing recorded examples. Try a demo scene below to see the full experience.
    </div>
  );
}
