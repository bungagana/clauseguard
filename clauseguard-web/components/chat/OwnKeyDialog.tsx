"use client";

import { useState } from "react";
import { KeyRound, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { ApiError, clearOwnKey, renewSession, setOwnKey } from "@/lib/api";

const inputClass =
  "w-full rounded-lg border border-input bg-card px-3 py-2 text-sm shadow-soft focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring";

/**
 * The customer's own Gemini key. Shown when the free AI service has run out, and always available in the session controls.
 * The key is checked with Google once and kept only in the server's memory for this session.
 */
export function OwnKeyDialog({ sessionToken, label, onChanged }: { sessionToken?: () => string | undefined; label?: string; onChanged?: () => void }) {
  const [open, setOpen] = useState(false);
  const [apiKey, setApiKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [active, setActive] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  async function save() {
    if (!apiKey.trim()) return;
    setBusy(true);
    setMsg(null);
    try {
      let token = sessionToken?.() ?? (await renewSession());
      if (!token) throw new ApiError("Sign in again, then retry.", 401);
      try {
        await setOwnKey(token, apiKey.trim());
      } catch (err) {
        // the server session ended (restart or redeploy): sign in again once and retry
        if (!(err instanceof ApiError && err.status === 401)) throw err;
        token = await renewSession();
        if (!token) throw err;
        await setOwnKey(token, apiKey.trim());
      }
      setActive(true);
      setApiKey("");
      setMsg({ ok: true, text: "Your key is in use for this session. Press Regenerate under the answer, or ask again, and it will use your key." });
      onChanged?.();
    } catch (e) {
      setMsg({ ok: false, text: e instanceof ApiError ? e.message : "Could not save the key. Try again." });
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    const token = sessionToken?.();
    if (!token) return;
    setBusy(true);
    try {
      await clearOwnKey(token);
      setActive(false);
      setMsg({ ok: true, text: "Your key was removed from this session." });
    } catch {
      setMsg({ ok: false, text: "Could not remove the key. Try again." });
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="outline" size="sm" className="gap-1.5">
          <KeyRound className="h-3.5 w-3.5" /> {label ?? "Use my own Gemini key"}
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Use your own Gemini key</DialogTitle>
          <DialogDescription>
            The free AI service has a daily limit. With your own key, answers keep their full quality. Get a free key at{" "}
            <a className="underline" href="https://aistudio.google.com/apikey" target="_blank" rel="noreferrer">
              aistudio.google.com/apikey
            </a>
            . Your key stays in the server&apos;s memory for this session only. It is never saved, logged or shared.
          </DialogDescription>
        </DialogHeader>
        <div className="flex flex-col gap-3">
          <input
            type="password"
            autoComplete="off"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && void save()}
            className={inputClass}
            placeholder="Paste your Gemini API key"
            aria-label="Gemini API key"
          />
          <div className="flex items-center gap-2">
            <Button onClick={() => void save()} disabled={busy || !apiKey.trim()} className="gap-1.5">
              {busy && <Loader2 className="h-3.5 w-3.5 animate-spin" />} Use this key
            </Button>
            {active && (
              <Button variant="ghost" onClick={() => void remove()} disabled={busy}>
                Remove my key
              </Button>
            )}
          </div>
          {msg && (
            <p role="status" className={msg.ok ? "text-sm text-success" : "text-sm text-destructive"}>
              {msg.text}
            </p>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
