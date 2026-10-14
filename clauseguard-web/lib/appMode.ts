// Single toggle for the demo/production surface (Section 3). Demo mode shows the persona
// picker, the "Demo mode" badge and the demo scene button; production mode hides all three
// and starts from an upload-first empty state instead. The default comes from
// NEXT_PUBLIC_APP_MODE (inlined at build time), and a visit carrying ?mode=... overrides it
// for this browser via the same localStorage pattern ThemeToggle already uses for the theme.

export type AppMode = "demo" | "production";

const STORAGE_KEY = "clauseguard-app-mode";

export function defaultAppMode(): AppMode {
  return process.env.NEXT_PUBLIC_APP_MODE === "production" ? "production" : "demo";
}

export function readStoredAppMode(): AppMode | null {
  try {
    const v = localStorage.getItem(STORAGE_KEY);
    return v === "demo" || v === "production" ? v : null;
  } catch {
    return null;
  }
}

export function setStoredAppMode(mode: AppMode): void {
  try {
    localStorage.setItem(STORAGE_KEY, mode);
  } catch {
    /* private browsing or blocked storage: the mode just won't persist across visits */
  }
}

export function parseAppMode(value: string | undefined | null): AppMode | undefined {
  return value === "demo" || value === "production" ? value : undefined;
}
