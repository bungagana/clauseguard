import * as api from "./api";
import { firstTier2Pending, type ChatMessage } from "./message";

export const HISTORY_STORAGE_KEY = "clauseguard-history";
const HISTORY_VERSION = 1;
const MAX_CONVERSATIONS = 60;
const TITLE_MAX_CHARS = 64;
const BACKEND_TITLE_MAX = 200;
const UNAVAILABLE_STATUSES = new Set([404, 405, 502, 503, 504]);

export interface ConversationSummary {
  id: string;
  personaKey: string;
  title: string;
  createdAt: number;
  updatedAt: number;
  messageCount: number;
}

export interface StoredConversation {
  id: string;
  personaKey: string;
  title: string;
  createdAt: number;
  updatedAt: number;
  messages: ChatMessage[];
}

export type HistoryMode = "backend" | "local";

export interface HistoryAuth {
  tokenFor: (personaKey: string) => string | undefined;
  tokenPersonas: () => string[];
  renew: (personaKey: string) => Promise<string | null>;
}

type Outcome<T> = { kind: "ok"; value: T } | { kind: "unavailable" } | { kind: "failed" };

interface HistoryFile {
  version: number;
  conversations: StoredConversation[];
}

export function newConversationId(): string {
  return `c${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}

export function deriveTitle(messages: ChatMessage[]): string | null {
  const first = messages.find((m) => m.role === "user");
  if (!first) return null;
  const raw = first.text ?? first.doc?.filename ?? first.policyUpload?.filename ?? "";
  const oneLine = raw.replace(/\s+/g, " ").trim();
  if (!oneLine) return null;
  return oneLine.length > TITLE_MAX_CHARS ? `${oneLine.slice(0, TITLE_MAX_CHARS - 1)}…` : oneLine;
}

export function countTurns(messages: ChatMessage[]): number {
  return messages.filter((m) => m.role !== "system" && !m.typing).length;
}

// A confirmation card only makes sense against the backend session that produced it; once the
// conversation is reloaded that session is gone, so an unresolved card must never be submittable.
export function sanitizeForStorage(messages: ChatMessage[]): ChatMessage[] {
  return messages
    .filter((m) => !m.typing)
    .map((m) => {
      const next: ChatMessage = { ...m };
      delete next.confirmBusy;
      delete next.typing;
      delete next.liveReply;
      delete next.forText;
      delete next.usedUploads;
      if (next.policyUpload?.status === "extracting") {
        next.policyUpload = { filename: next.policyUpload.filename, status: "error", error: "Extraction was interrupted before it finished." };
      }
      return next;
    });
}

export function reviveFromStorage(messages: ChatMessage[]): ChatMessage[] {
  return sanitizeForStorage(messages).map((m) => {
    if (m.reply && !m.pendingResolved && firstTier2Pending(m.reply)) {
      return { ...m, pendingResolved: "expired" };
    }
    return m;
  });
}

function readFile(): HistoryFile {
  try {
    const raw = localStorage.getItem(HISTORY_STORAGE_KEY);
    if (!raw) return { version: HISTORY_VERSION, conversations: [] };
    const parsed = JSON.parse(raw) as Partial<HistoryFile>;
    if (parsed.version !== HISTORY_VERSION || !Array.isArray(parsed.conversations)) {
      return { version: HISTORY_VERSION, conversations: [] };
    }
    const conversations = parsed.conversations.filter(
      (c): c is StoredConversation =>
        Boolean(c) &&
        typeof c.id === "string" &&
        typeof c.personaKey === "string" &&
        typeof c.title === "string" &&
        typeof c.updatedAt === "number" &&
        Array.isArray(c.messages)
    );
    return { version: HISTORY_VERSION, conversations };
  } catch {
    return { version: HISTORY_VERSION, conversations: [] };
  }
}

function writeFile(conversations: StoredConversation[]): boolean {
  let list = conversations;
  for (let attempt = 0; attempt < 3; attempt += 1) {
    try {
      localStorage.setItem(HISTORY_STORAGE_KEY, JSON.stringify({ version: HISTORY_VERSION, conversations: list }));
      return true;
    } catch {
      if (list.length <= 1) return false;
      list = list.slice(0, Math.ceil(list.length / 2));
    }
  }
  return false;
}

function clearLocal(): void {
  try {
    localStorage.removeItem(HISTORY_STORAGE_KEY);
  } catch {
    /* storage unavailable: nothing to clear */
  }
}

function byRecency<T extends { updatedAt: number }>(list: T[]): T[] {
  return [...list].sort((a, b) => b.updatedAt - a.updatedAt);
}

function localConversations(): StoredConversation[] {
  return byRecency(readFile().conversations);
}

function upsertLocal(conversation: StoredConversation): void {
  const rest = localConversations().filter((c) => c.id !== conversation.id);
  writeFile(byRecency([conversation, ...rest]).slice(0, MAX_CONVERSATIONS));
}

function removeLocal(ids: Set<string>): void {
  if (!ids.size) return;
  const rest = localConversations().filter((c) => !ids.has(c.id));
  if (rest.length) writeFile(rest);
  else clearLocal();
}

function toSummary(c: StoredConversation): ConversationSummary {
  return { id: c.id, personaKey: c.personaKey, title: c.title, createdAt: c.createdAt, updatedAt: c.updatedAt, messageCount: countTurns(c.messages) };
}

function fromBackend(s: api.HistorySummary): ConversationSummary {
  return { id: s.id, personaKey: s.persona, title: s.title, createdAt: s.created_at, updatedAt: s.updated_at, messageCount: s.message_count };
}

function putBody(c: StoredConversation): api.HistoryPutBody {
  return { title: c.title.slice(0, BACKEND_TITLE_MAX), messages: c.messages, created_at: c.createdAt, updated_at: c.updatedAt };
}

async function withSession<T>(auth: HistoryAuth, personaKey: string, run: (token: string) => Promise<T>): Promise<Outcome<T>> {
  let token = auth.tokenFor(personaKey);
  if (!token) return { kind: "unavailable" };
  for (let attempt = 0; attempt < 2; attempt += 1) {
    try {
      return { kind: "ok", value: await run(token) };
    } catch (err) {
      if (!(err instanceof api.ApiError)) return { kind: "unavailable" };
      if (err.status === 401 && attempt === 0) {
        const fresh = await auth.renew(personaKey);
        if (!fresh) return { kind: "unavailable" };
        token = fresh;
        continue;
      }
      return UNAVAILABLE_STATUSES.has(err.status) ? { kind: "unavailable" } : { kind: "failed" };
    }
  }
  return { kind: "failed" };
}

async function pushLocalToBackend(
  auth: HistoryAuth,
  personaKey: string,
  remote: Map<string, api.HistorySummary>
): Promise<ConversationSummary[]> {
  const settled = new Set<string>();
  const uploaded: ConversationSummary[] = [];
  for (const c of localConversations().filter((x) => x.personaKey === personaKey)) {
    const known = remote.get(c.id);
    if (known && known.updated_at >= c.updatedAt) {
      settled.add(c.id);
      continue;
    }
    const res = await withSession(auth, personaKey, (token) => api.putHistory(token, c.id, putBody(c)));
    if (res.kind !== "ok") break;
    settled.add(c.id);
    uploaded.push(toSummary(c));
  }
  removeLocal(settled);
  return uploaded;
}

export function loadLocalSummaries(): ConversationSummary[] {
  return localConversations().map(toSummary);
}

/**
 * Lists history for every persona that currently has a session token. Conversations left in
 * localStorage (written while the backend was unreachable, or by the pre-backend version of
 * this app) are uploaded for personas whose backend answered and then dropped locally. A
 * persona without a token yet keeps its local copy until its first login.
 */
export async function loadHistory(auth: HistoryAuth): Promise<{ items: ConversationSummary[]; mode: HistoryMode }> {
  const personas = auth.tokenPersonas();
  const outcomes = await Promise.all(
    personas.map(async (personaKey) => ({
      personaKey,
      res: await withSession(auth, personaKey, (token) => api.listHistory(token)),
    }))
  );
  const merged = new Map<string, ConversationSummary>();
  let reachable = 0;
  for (const { personaKey, res } of outcomes) {
    if (res.kind !== "ok") continue;
    reachable += 1;
    const remote = new Map(res.value.conversations.map((s) => [s.id, s]));
    for (const s of Array.from(remote.values())) merged.set(s.id, fromBackend(s));
    for (const s of await pushLocalToBackend(auth, personaKey, remote)) merged.set(s.id, s);
  }
  for (const c of localConversations()) {
    if (!merged.has(c.id)) merged.set(c.id, toSummary(c));
  }
  return {
    items: byRecency(Array.from(merged.values())),
    mode: personas.length > 0 && reachable === personas.length ? "backend" : "local",
  };
}

export async function fetchConversation(auth: HistoryAuth, summary: ConversationSummary): Promise<StoredConversation | null> {
  const res = await withSession(auth, summary.personaKey, (token) => api.getHistory(token, summary.id));
  if (res.kind === "ok") {
    const d = res.value;
    return {
      id: d.id,
      personaKey: d.persona,
      title: d.title,
      createdAt: d.created_at,
      updatedAt: d.updated_at,
      messages: d.messages as ChatMessage[],
    };
  }
  return readFile().conversations.find((c) => c.id === summary.id) ?? null;
}

export async function saveConversation(auth: HistoryAuth, conversation: StoredConversation): Promise<HistoryMode> {
  const res = await withSession(auth, conversation.personaKey, (token) => api.putHistory(token, conversation.id, putBody(conversation)));
  if (res.kind === "ok") {
    removeLocal(new Set([conversation.id]));
    return "backend";
  }
  upsertLocal(conversation);
  return "local";
}

export async function renameStored(
  auth: HistoryAuth,
  personaKey: string,
  id: string,
  title: string,
  cached?: StoredConversation
): Promise<boolean> {
  const res = await withSession(auth, personaKey, (token) => api.renameHistory(token, id, title.slice(0, BACKEND_TITLE_MAX)));
  if (res.kind === "ok") return true;
  const local = readFile().conversations.find((c) => c.id === id) ?? cached;
  if (!local) return false;
  upsertLocal({ ...local, title });
  return true;
}

export async function deleteStored(auth: HistoryAuth, personaKey: string, id: string): Promise<void> {
  removeLocal(new Set([id]));
  await withSession(auth, personaKey, (token) => api.deleteHistory(token, id));
}

export async function clearStored(auth: HistoryAuth): Promise<void> {
  clearLocal();
  await Promise.all(auth.tokenPersonas().map((personaKey) => withSession(auth, personaKey, (token) => api.clearHistoryRemote(token))));
}
