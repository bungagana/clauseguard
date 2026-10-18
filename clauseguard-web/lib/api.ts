// Typed client for the ClauseGuard sandbox API (clauseguard/sandbox/api.py).
// All calls go through this app's own origin at /api/cg/*; next.config.mjs
// rewrites that prefix to NEXT_PUBLIC_API_URL server-side, so the browser
// never makes a cross-origin request against a backend that ships no CORS
// headers.
import type {
  AllocationResponse,
  AuditEvent,
  ChatReply,
  DemoAttack,
  DigestResponse,
  LoginResult,
  PlansResponse,
  PoliciesResponse,
  Persona,
  PolicyUploadResult,
  RecourseResponse,
  TimelineResponse,
  TwinResponse,
  UploadResult,
  WhatIfResponse,
  AutonomyMode,
  BackofficeClaim,
  BackofficeClaimDetail,
  BackofficeTicket,
  SessionState,
} from "./types";
import { normalizeChatReply } from "./normalize";
import { accessToken, authEnabled, rememberAccount } from "./auth";

const BASE = "/api/cg";

export class ApiError extends Error {
  status: number;
  body: unknown;
  constructor(message: string, status: number, body?: unknown) {
    super(message);
    this.status = status;
    this.body = body;
  }
}

async function request<T>(
  path: string,
  init: RequestInit = {},
  token?: string,
  timeoutMs = 15000,
  externalSignal?: AbortSignal
): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  const onExternalAbort = () => controller.abort();
  if (externalSignal) {
    if (externalSignal.aborted) controller.abort();
    else externalSignal.addEventListener("abort", onExternalAbort);
  }
  try {
    const headers = new Headers(init.headers);
    if (token) headers.set("X-Session-Token", token);
    if (init.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) {
      headers.set("Content-Type", "application/json");
    }
    const res = await fetch(`${BASE}${path}`, { ...init, headers, signal: controller.signal });
    const text = await res.text();
    const data = text ? safeJson(text) : null;
    if (!res.ok) {
      throw new ApiError(
        typeof data === "object" && data && "detail" in (data as Record<string, unknown>)
          ? String((data as Record<string, unknown>).detail)
          : `Request failed (${res.status})`,
        res.status,
        data
      );
    }
    return data as T;
  } finally {
    clearTimeout(timer);
    externalSignal?.removeEventListener("abort", onExternalAbort);
  }
}

function safeJson(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

// ---------------------------------------------------------------- health
let healthCache: { ok: boolean; at: number } | null = null;
const HEALTH_TTL_MS = 20_000;

/** Health check, cached briefly so re-renders don't re-ping the backend. */
export async function checkBackendOnline(force = false): Promise<boolean> {
  if (!force && healthCache && Date.now() - healthCache.at < HEALTH_TTL_MS) {
    return healthCache.ok;
  }
  try {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 4000);
    const res = await fetch(`${BASE}/health`, { signal: controller.signal, cache: "no-store" });
    clearTimeout(timer);
    if (!res.ok) throw new Error("not ok");
    const data = (await res.json()) as { ok?: boolean };
    const ok = Boolean(data?.ok);
    healthCache = { ok, at: Date.now() };
    return ok;
  } catch {
    healthCache = { ok: false, at: Date.now() };
    return false;
  }
}

// ---------------------------------------------------------------- llm status
export interface LlmStatus {
  configured: boolean;
  available: boolean;
  poolSize: number;
}

let llmStatusCache: { status: LlmStatus; at: number } | null = null;
const LLM_STATUS_TTL_MS = 20_000;

/**
 * Whether the backend's language-model key pool currently has quota, for a UI indicator
 * only. This never affects what the agent decides: the solver and permission tiers never
 * read it. When it reports unavailable, the backend automatically falls back to
 * deterministic templates and rule-based parsing for that turn's chat understanding.
 */
export async function checkLlmStatus(force = false): Promise<LlmStatus> {
  if (!force && llmStatusCache && Date.now() - llmStatusCache.at < LLM_STATUS_TTL_MS) {
    return llmStatusCache.status;
  }
  const fallback: LlmStatus = { configured: false, available: false, poolSize: 0 };
  try {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 4000);
    const res = await fetch(`${BASE}/system/status`, { signal: controller.signal, cache: "no-store" });
    clearTimeout(timer);
    if (!res.ok) throw new Error("not ok");
    const data = (await res.json()) as { configured?: boolean; available?: boolean; pool_size?: number };
    const status: LlmStatus = {
      configured: Boolean(data?.configured),
      available: Boolean(data?.available),
      poolSize: Number(data?.pool_size ?? 0),
    };
    llmStatusCache = { status, at: Date.now() };
    return status;
  } catch {
    llmStatusCache = { status: fallback, at: Date.now() };
    return fallback;
  }
}

/**
 * Adds a Gemini API key to the live pool for this session's running backend, for when the
 * configured keys run out mid-demo. In-memory only — the key is gone on the next restart,
 * and this never touches a coverage decision, which stays rule-based either way.
 */
export async function addLlmKey(adminToken: string, apiKey: string): Promise<{ poolSize: number }> {
  const data = await request<{ pool_size: number }>("/system/add-key", {
    method: "POST",
    headers: { "X-Admin-Token": adminToken },
    body: JSON.stringify({ api_key: apiKey }),
  });
  llmStatusCache = null;
  return { poolSize: data.pool_size };
}

// ---------------------------------------------------------------- auth / persona
const GUEST_KEY = "clauseguard-guest-account";

export async function login(persona: string): Promise<LoginResult> {
  if (authEnabled) {
    // signed-in accounts: the person is identified by the verified access token, never by a persona name
    const token = await accessToken();
    if (!token) throw new ApiError("signed out", 401);
    const res = await request<LoginResult>("/login", { method: "POST", body: JSON.stringify({ access_token: token }) }, undefined, 60000);
    rememberAccount({ email: res.account ?? "", personaKey: res.persona_key ?? "account", demo: Boolean(res.demo) });
    return res;
  }
  // open sandbox login: production mode signs in as a guest account; the browser remembers its id so a reload
  // keeps the same uploaded policies and history. The id grants nothing by itself.
  let account_id: string | undefined;
  if (persona === "guest") {
    try {
      account_id = localStorage.getItem(GUEST_KEY) ?? undefined;
    } catch {
      /* storage unavailable: a fresh account each time */
    }
  }
  return request<LoginResult>("/login", { method: "POST", body: JSON.stringify(account_id ? { persona, account_id } : { persona }) }).then((res) => {
    if (persona === "guest" && res.user_id) {
      try {
        localStorage.setItem(GUEST_KEY, res.user_id);
      } catch {
        /* noop */
      }
    }
    return res;
  });
}

export function getPersonas(): Promise<Persona[]> {
  return request<Persona[]>("/personas");
}

export function getPolicies(token: string): Promise<PoliciesResponse> {
  return request<PoliciesResponse>("/policies", {}, token);
}

// ---------------------------------------------------------------- chat
export async function sendChat(
  token: string,
  text: string,
  uploads: string[] = [],
  signal?: AbortSignal
): Promise<ChatReply> {
  const raw = await request<ChatReply>(
    "/chat",
    { method: "POST", body: JSON.stringify({ text, uploads }) },
    token,
    // reading several uploaded documents can take over a minute; the typing indicator stays until the reply
    uploads.length ? 240000 : 180000,
    signal
  );
  return normalizeChatReply(raw);
}

export interface MyClaim {
  id: string;
  policy_id: string;
  status: string;
  claim_amount?: number | null;
  filed_date?: string | null;
  deadline_date?: string | null;
  decided_at?: string | null;
  decision_note?: string | null;
  form: Record<string, unknown> | null;
  documents: Array<{ id: string; type: string; uploaded_at?: string }>;
}

/** One of the customer's own claims, with the form the assistant submitted. */
export function getMyClaim(token: string, claimId: string): Promise<MyClaim> {
  return request<MyClaim>(`/claims/${encodeURIComponent(claimId)}`, {}, token);
}

/** Open one of the customer's own uploads in a new tab (the file is fetched with the session token, then shown). */
export async function openUpload(token: string, docId: string): Promise<void> {
  const res = await fetch(`${BASE}/uploads/${encodeURIComponent(docId)}`, { headers: { "X-Session-Token": token } });
  if (!res.ok) throw new ApiError(`upload fetch failed (${res.status})`, res.status);
  const url = URL.createObjectURL(await res.blob());
  window.open(url, "_blank", "noopener");
  setTimeout(() => URL.revokeObjectURL(url), 60000);
}

export function getChatPending(token: string): Promise<{ pending: Array<Record<string, unknown>> }> {
  return request("/chat/pending", {}, token);
}

export async function confirmChat(token: string, index: number): Promise<ChatReply> {
  const raw = await request<ChatReply>(
    "/chat/confirm",
    { method: "POST", body: JSON.stringify({ index }) },
    token,
    45000
  );
  return normalizeChatReply(raw);
}

// ---------------------------------------------------------------- session controls
export function getSession(token: string): Promise<SessionState> {
  return request<SessionState>("/session", {}, token);
}
export function setAutonomy(token: string, mode: AutonomyMode): Promise<SessionState> {
  return request<SessionState>("/session/autonomy", { method: "POST", body: JSON.stringify({ mode }) }, token);
}
export function moveClock(token: string, days: number, reset = false): Promise<SessionState> {
  return request<SessionState>("/session/clock", { method: "POST", body: JSON.stringify({ days, reset }) }, token);
}

// ---------------------------------------------------------------- insurer side (admin token, never the agent)
async function adminRequest<T>(path: string, adminToken: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("X-Admin-Token", adminToken);
  if (init.body) headers.set("Content-Type", "application/json");
  const res = await fetch(`${BASE}${path}`, { ...init, headers });
  const text = await res.text();
  const data = text ? safeJson(text) : null;
  if (!res.ok) throw new ApiError((data as { detail?: string } | null)?.detail ?? `admin request failed (${res.status})`, res.status, data);
  return data as T;
}
export const insurer = {
  killStatus: (adminToken: string) => adminRequest<{ active: boolean }>("/admin/kill", adminToken),
  halt: (adminToken: string, reason: string) => adminRequest<{ active: boolean }>("/admin/kill", adminToken, { method: "POST", body: JSON.stringify({ reason }) }),
  resume: (adminToken: string) => adminRequest<{ active: boolean }>("/admin/kill", adminToken, { method: "DELETE" }),
  tickets: (adminToken: string) => adminRequest<BackofficeTicket[]>("/backoffice/tickets", adminToken),
  claims: (adminToken: string) => adminRequest<BackofficeClaim[]>("/backoffice/claims", adminToken),
  claim: (adminToken: string, claimId: string) => adminRequest<BackofficeClaimDetail>(`/backoffice/claims/${encodeURIComponent(claimId)}`, adminToken),
  decide: (adminToken: string, claimId: string, decision: "under_review" | "approved" | "rejected" | "paid", note?: string) =>
    adminRequest<{ claim_id: string; status: string }>(`/backoffice/claims/${encodeURIComponent(claimId)}/decide`, adminToken, { method: "POST", body: JSON.stringify({ decision, note }) }),
};

// ---------------------------------------------------------------- what-if
export function whatIf(token: string, overrides: Record<string, boolean | number>): Promise<WhatIfResponse> {
  return request<WhatIfResponse>("/entitlement/whatif", { method: "POST", body: JSON.stringify({ overrides }) }, token, 20000);
}

// ---------------------------------------------------------------- export
export interface ExportSection {
  heading: string;
  lines: string[];
}
export interface ExportRequest {
  title: string;
  subtitle?: string;
  sections: ExportSection[];
  footer?: string;
}

export async function exportPdf(token: string, body: ExportRequest): Promise<Blob> {
  const res = await fetch(`${BASE}/export/pdf`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Session-Token": token },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new ApiError(`export failed (${res.status})`, res.status, await res.text().catch(() => null));
  return res.blob();
}

// ---------------------------------------------------------------- documents
export function uploadDocument(token: string, file: File): Promise<UploadResult> {
  const form = new FormData();
  form.append("file", file);
  // several files go up together and each one writes an audit entry; a distant database makes that slow, so allow time
  return request<UploadResult>("/upload", { method: "POST", body: form }, token, 180000);
}

export function getAudit(token: string): Promise<{ chain_ok: boolean; events: AuditEvent[] }> {
  return request("/audit", {}, token);
}

// Upload the user's OWN policy document and run it through the real extractor live, in front
// of them. Distinct from uploadDocument() above (claim-document attachment): this creates a
// new, unverified policy visible immediately in /policies, not a claim attachment.
export function uploadPolicy(token: string, file: File, productTypeHint?: string): Promise<PolicyUploadResult> {
  const form = new FormData();
  form.append("file", file);
  if (productTypeHint) form.append("product_type_hint", productTypeHint);
  // extraction runs two LLM passes synchronously server-side; allow generous time for a real PDF.
  return request<PolicyUploadResult>("/policies/upload", { method: "POST", body: form }, token, 120000);
}

// ---------------------------------------------------------------- demo scenes
export function getDemoAttacks(token: string): Promise<DemoAttack[]> {
  return request<DemoAttack[]>("/demo/attacks", {}, token);
}

export function runDemoAttack(
  token: string,
  kind: string,
  file?: string
): Promise<{ kind: string; text?: string; doc_id?: string; handle?: string; filename?: string }> {
  return request("/demo/attack", { method: "POST", body: JSON.stringify({ kind, file }) }, token);
}

// ---------------------------------------------------------------- entitlement
export function getTimeline(token: string): Promise<TimelineResponse> {
  return request<TimelineResponse>("/entitlement/timeline", {}, token);
}

export function getDigest(token: string): Promise<DigestResponse> {
  return request<DigestResponse>("/entitlement/digest", {}, token);
}

export function getAllocation(token: string, claim = "draft", bill?: Record<string, number>): Promise<AllocationResponse> {
  const params = new URLSearchParams({ claim });
  if (bill) params.set("bill", JSON.stringify(bill));
  return request<AllocationResponse>(`/entitlement/allocation?${params.toString()}`, {}, token);
}

export function getTwin(token: string, claim = "draft", policy?: string): Promise<TwinResponse> {
  const params = new URLSearchParams({ claim });
  if (policy) params.set("policy", policy);
  return request<TwinResponse>(`/entitlement/twin?${params.toString()}`, {}, token);
}

export function getRecourse(token: string, policy: string, claim = "draft"): Promise<RecourseResponse> {
  const params = new URLSearchParams({ policy, claim });
  return request<RecourseResponse>(`/entitlement/recourse?${params.toString()}`, {}, token);
}

export function getPlans(token: string, budget?: number, jurisdiction: "ID" | "US" = "ID"): Promise<PlansResponse> {
  const params = new URLSearchParams({ jurisdiction });
  if (budget) params.set("budget", String(budget));
  return request<PlansResponse>(`/entitlement/plans?${params.toString()}`, {}, token);
}

// ---------------------------------------------------------------- conversation history
export interface HistorySummary {
  id: string;
  persona: string;
  title: string;
  created_at: number;
  updated_at: number;
  message_count: number;
}

export interface HistoryDetail extends HistorySummary {
  messages: unknown[];
}

export interface HistoryPutBody {
  title: string;
  messages: unknown[];
  created_at?: number;
  updated_at?: number;
}

export function listHistory(token: string): Promise<{ conversations: HistorySummary[] }> {
  return request("/history", {}, token);
}

export function getHistory(token: string, id: string): Promise<HistoryDetail> {
  return request<HistoryDetail>(`/history/${encodeURIComponent(id)}`, {}, token);
}

export function putHistory(token: string, id: string, body: HistoryPutBody): Promise<{ id: string; created: boolean }> {
  return request(`/history/${encodeURIComponent(id)}`, { method: "PUT", body: JSON.stringify(body) }, token, 30000);
}

export function renameHistory(token: string, id: string, title: string): Promise<{ id: string; title: string }> {
  return request(`/history/${encodeURIComponent(id)}`, { method: "PATCH", body: JSON.stringify({ title }) }, token);
}

export function deleteHistory(token: string, id: string): Promise<{ deleted: number }> {
  return request(`/history/${encodeURIComponent(id)}`, { method: "DELETE" }, token);
}

export function clearHistoryRemote(token: string): Promise<{ deleted: number }> {
  return request("/history", { method: "DELETE" }, token);
}

/** New chat: the agent forgets the situation on the table (not the account's policies or claims). */
export function resetSession(token: string): Promise<{ ok: boolean }> {
  return request<{ ok: boolean }>("/session/reset", { method: "POST" }, token);
}

// The chat engine registers how to sign in again for the active account, so a dialog outside the chat flow
// (the own-key dialog) can recover from an expired server session the same way the chat does.
let sessionRenewer: (() => Promise<string | null>) | null = null;
export function setSessionRenewer(fn: (() => Promise<string | null>) | null): void {
  sessionRenewer = fn;
}
export async function renewSession(): Promise<string | null> {
  return sessionRenewer ? sessionRenewer() : null;
}

/** The customer's own Gemini key for this session. It is checked with Google once and kept only in the server's memory. */
export function setOwnKey(token: string, apiKey: string): Promise<{ ok: boolean }> {
  return request<{ ok: boolean }>("/session/api-key", { method: "POST", body: JSON.stringify({ api_key: apiKey }) }, token, 40000);
}

export function clearOwnKey(token: string): Promise<{ ok: boolean }> {
  return request<{ ok: boolean }>("/session/api-key", { method: "DELETE" }, token);
}
