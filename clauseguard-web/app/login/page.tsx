"use client";

import Image from "next/image";
import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Loader2, MailCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { AuthError, authEnabled, hasSession, resendConfirmation, signIn, signUp } from "@/lib/auth";
import { login } from "@/lib/api";

type Tab = "signin" | "signup";

export default function LoginPage() {
  const router = useRouter();
  const [tab, setTab] = useState<Tab>("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [needsConfirm, setNeedsConfirm] = useState(false);
  const [info, setInfo] = useState<string | null>(null);

  useEffect(() => {
    // no accounts configured: the open sandbox, straight to the chat
    if (!authEnabled) router.replace("/chat?mode=demo");
    else if (hasSession()) router.replace("/chat");
  }, [router]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setInfo(null);
    setNeedsConfirm(false);
    setBusy(true);
    try {
      if (tab === "signup") {
        const r = await signUp(email.trim(), password);
        if (r === "confirm") {
          setInfo("We sent a confirmation link to your email. Open it, then sign in here.");
          setNeedsConfirm(true);
          setTab("signin");
          return;
        }
      } else {
        await signIn(email.trim(), password);
      }
      await login("");
      router.replace("/chat");
    } catch (err) {
      if (err instanceof AuthError && err.code === "email_not_confirmed") setNeedsConfirm(true);
      setError(err instanceof Error ? err.message : "Sign-in failed");
    } finally {
      setBusy(false);
    }
  }

  async function resend() {
    try {
      await resendConfirmation(email.trim());
      setInfo("A new confirmation email is on its way.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not resend");
    }
  }

  return (
    <main className="flex min-h-dvh items-center justify-center bg-background px-4 py-10">
      <div className="w-full max-w-sm">
        <Link href="/" className="mb-6 flex items-center justify-center gap-2">
          <Image src="/brand/mark.png" alt="" width={36} height={36} />
          <span className="text-lg font-semibold">ClauseGuard</span>
        </Link>
        <div className="rounded-2xl border border-border bg-card p-6 shadow-soft">
          <h1 className="text-xl font-semibold">{tab === "signin" ? "Sign in" : "Create your account"}</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {tab === "signin" ? "Your policies, claims and chats stay on your account." : "We email you a link to confirm your address."}
          </p>

          <form onSubmit={submit} className="mt-5 space-y-3">
            <label className="block text-sm font-medium">
              Email
              <input
                type="email"
                required
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="mt-1 w-full rounded-lg border border-input bg-background px-3 py-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
              />
            </label>
            <label className="block text-sm font-medium">
              Password
              <input
                type="password"
                required
                minLength={8}
                autoComplete={tab === "signin" ? "current-password" : "new-password"}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="mt-1 w-full rounded-lg border border-input bg-background px-3 py-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
              />
            </label>
            {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
            {info && (
              <p className="flex items-start gap-2 text-sm text-success">
                <MailCheck className="mt-0.5 h-4 w-4 shrink-0" /> {info}
              </p>
            )}
            {needsConfirm && (
              <button type="button" onClick={resend} className="text-sm font-medium text-primary underline-offset-4 hover:underline">
                Resend the confirmation email
              </button>
            )}
            <Button type="submit" className="w-full" disabled={busy || !authEnabled}>
              {busy && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              {tab === "signin" ? "Sign in" : "Create account"}
            </Button>
          </form>

          <p className="mt-4 text-center text-sm text-muted-foreground">
            {tab === "signin" ? "New here?" : "Already have an account?"}{" "}
            <button
              type="button"
              className="font-medium text-primary underline-offset-4 hover:underline"
              onClick={() => {
                setTab(tab === "signin" ? "signup" : "signin");
                setError(null);
                setInfo(null);
              }}
            >
              {tab === "signin" ? "Create an account" : "Sign in"}
            </button>
          </p>
        </div>
        <p className="mt-4 text-center text-xs text-muted-foreground">
          Sandbox insurer. Nothing you do here reaches a real insurer or account.
        </p>
      </div>
    </main>
  );
}
