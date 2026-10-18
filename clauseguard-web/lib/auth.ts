// Account sign-in through Supabase Auth's REST API. The password goes to Supabase only; the backend is
// given the resulting access token and asks Supabase who it belongs to. Active only when the build has
// NEXT_PUBLIC_SUPABASE_URL set, otherwise the app keeps its open sandbox login.

const URL_BASE = (process.env.NEXT_PUBLIC_SUPABASE_URL ?? "").replace(/\/$/, "");
const KEY = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ?? "";
const SESSION_KEY = "clauseguard-auth";
const ACCOUNT_KEY = "clauseguard-account";

export const authEnabled = Boolean(URL_BASE && KEY);

interface StoredSession {
  access_token: string;
  refresh_token: string;
  expires_at: number; // seconds
  email: string;
}

export interface AccountInfo {
  email: string;
  personaKey: string; // rizky | santoso | dewi for a demo account, "account" otherwise
  demo: boolean;
}

export class AuthError extends Error {
  code: string;
  constructor(message: string, code = "") {
    super(message);
    this.code = code;
  }
}

async function call(path: string, body: unknown, bearer?: string): Promise<Record<string, unknown>> {
  let res: Response;
  try {
    res = await fetch(`${URL_BASE}/auth/v1${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json", apikey: KEY, ...(bearer ? { Authorization: `Bearer ${bearer}` } : {}) },
      body: JSON.stringify(body),
    });
  } catch {
    throw new AuthError("The sign-in service could not be reached. Check your connection and try again.");
  }
  const data = (await res.json().catch(() => ({}))) as Record<string, unknown>;
  if (!res.ok) {
    const code = String(data.error_code ?? data.code ?? "");
    const msg = String(data.msg ?? data.error_description ?? data.message ?? "Sign-in failed");
    throw new AuthError(friendly(code, msg), code);
  }
  return data;
}

function friendly(code: string, msg: string): string {
  switch (code) {
    case "invalid_credentials":
      return "The email or password is not correct.";
    case "email_not_confirmed":
      return "Confirm your email first. We sent you a link when you signed up.";
    case "user_already_exists":
    case "email_exists":
      return "An account with this email already exists. Sign in instead.";
    case "weak_password":
      return "Choose a stronger password (at least 8 characters).";
    case "over_email_send_rate_limit":
      return "Too many emails were requested. Wait a few minutes and try again.";
    default:
      return msg;
  }
}

function save(data: Record<string, unknown>, email: string): void {
  const s: StoredSession = {
    access_token: String(data.access_token),
    refresh_token: String(data.refresh_token),
    expires_at: Math.floor(Date.now() / 1000) + Number(data.expires_in ?? 3600),
    email,
  };
  localStorage.setItem(SESSION_KEY, JSON.stringify(s));
}

function read(): StoredSession | null {
  try {
    const raw = localStorage.getItem(SESSION_KEY);
    return raw ? (JSON.parse(raw) as StoredSession) : null;
  } catch {
    return null;
  }
}

export function hasSession(): boolean {
  return read() !== null;
}

export function storedAccount(): AccountInfo | null {
  try {
    const raw = localStorage.getItem(ACCOUNT_KEY);
    return raw ? (JSON.parse(raw) as AccountInfo) : null;
  } catch {
    return null;
  }
}

export function rememberAccount(a: AccountInfo): void {
  try {
    localStorage.setItem(ACCOUNT_KEY, JSON.stringify(a));
  } catch {
    /* storage unavailable */
  }
}

/** Chats cached in this browser belong to whoever used it last, so they are dropped whenever the account changes. */
function dropLocalData(): void {
  for (const k of ["clauseguard-history", "clauseguard-guest-account", ACCOUNT_KEY]) {
    try {
      localStorage.removeItem(k);
    } catch {
      /* noop */
    }
  }
}

export async function signIn(email: string, password: string): Promise<string> {
  const data = await call("/token?grant_type=password", { email, password });
  const prior = read();
  if (prior && prior.email !== email.toLowerCase()) dropLocalData();
  save(data, email.toLowerCase());
  return email.toLowerCase();
}

export async function signUp(email: string, password: string): Promise<"confirm" | "signed-in"> {
  const redirect = typeof window !== "undefined" ? `?redirect_to=${encodeURIComponent(`${window.location.origin}/login`)}` : "";
  const data = await call(`/signup${redirect}`, { email, password });
  if (data.access_token) {
    save(data, email.toLowerCase());
    return "signed-in";
  }
  return "confirm";
}

export async function resendConfirmation(email: string): Promise<void> {
  await call("/resend", { type: "signup", email });
}

export function signOut(): void {
  try {
    localStorage.removeItem(SESSION_KEY);
  } catch {
    /* noop */
  }
  dropLocalData();
}

/** A usable access token, refreshed shortly before it expires. Null when the person is signed out. */
export async function accessToken(): Promise<string | null> {
  const s = read();
  if (!s) return null;
  if (s.expires_at - 60 > Math.floor(Date.now() / 1000)) return s.access_token;
  try {
    const data = await call("/token?grant_type=refresh_token", { refresh_token: s.refresh_token });
    save(data, s.email);
    return String(data.access_token);
  } catch {
    signOut();
    return null;
  }
}
