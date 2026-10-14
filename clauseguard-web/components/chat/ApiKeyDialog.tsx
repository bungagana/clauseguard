"use client";

import { useState } from "react";
import { KeyRound, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { addLlmKey, ApiError } from "@/lib/api";

const inputClass =
  "w-full rounded-lg border border-input bg-card px-3 py-2 text-sm shadow-soft focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring";

export function ApiKeyDialog() {
  const [adminToken, setAdminToken] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; text: string } | null>(null);

  async function submit() {
    if (!adminToken.trim() || !apiKey.trim()) return;
    setBusy(true);
    setResult(null);
    try {
      const { poolSize } = await addLlmKey(adminToken.trim(), apiKey.trim());
      setResult({ ok: true, text: `Ditambahkan. Pool sekarang ${poolSize} key.` });
      setApiKey("");
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : "Gagal menambahkan key.";
      setResult({ ok: false, text: msg });
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog>
      <DialogTrigger asChild>
        <Button variant="ghost" size="icon" aria-label="Tambah API key" className="h-8 w-8 sm:h-9 sm:w-9">
          <KeyRound className="h-4 w-4" />
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Tambah Gemini API key</DialogTitle>
          <DialogDescription>
            Kalau key yang terpasang kehabisan kuota saat demo, tambahkan key baru di sini. Hanya
            tersimpan di memori server berjalan — hilang saat server di-restart, tidak ditulis ke
            file konfigurasi. Butuh token admin (CG_ADMIN_TOKEN).
          </DialogDescription>
        </DialogHeader>
        <div className="flex flex-col gap-3">
          <div className="flex flex-col gap-1">
            <label className="text-xs font-medium text-muted-foreground" htmlFor="admin-token-input">
              Token admin
            </label>
            <input
              id="admin-token-input"
              type="password"
              autoComplete="off"
              value={adminToken}
              onChange={(e) => setAdminToken(e.target.value)}
              className={inputClass}
              placeholder="CG_ADMIN_TOKEN"
            />
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-xs font-medium text-muted-foreground" htmlFor="gemini-key-input">
              Gemini API key baru
            </label>
            <input
              id="gemini-key-input"
              type="password"
              autoComplete="off"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              className={inputClass}
              placeholder="AIzaSy... atau AQ.Ab8R..."
            />
          </div>
          <Button onClick={submit} disabled={busy || !adminToken.trim() || !apiKey.trim()} className="gap-2">
            {busy && <Loader2 className="h-4 w-4 animate-spin" />}
            Tambahkan
          </Button>
          {result && (
            <p className={`text-xs ${result.ok ? "text-success" : "text-destructive"}`}>{result.text}</p>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
