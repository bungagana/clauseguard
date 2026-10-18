"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import * as api from "@/lib/api";
import { FALLBACK_PERSONAS } from "@/lib/personas";
import type { RecordedMeta } from "@/lib/replayTypes";
import { FIXTURE_POLICIES, SCENES, type Scene, type SceneStep } from "@/lib/fixtures";
import { firstTier2Pending, nextId, type ChatMessage } from "@/lib/message";
import {
  clearStored,
  deleteStored,
  deriveTitle,
  fetchConversation,
  loadHistory,
  loadLocalSummaries,
  newConversationId,
  renameStored,
  reviveFromStorage,
  sanitizeForStorage,
  saveConversation,
  type ConversationSummary,
  type HistoryAuth,
  type HistoryMode,
  type StoredConversation,
} from "@/lib/history";
import type { ChatReply, DigestResponse, SessionState, AutonomyMode, PoliciesResponse, Persona } from "@/lib/types";
import { digestItemQuestion } from "@/lib/digestQuestion";
import type { AppMode } from "@/lib/appMode";

const DEFAULT_PERSONA = "rizky";
const PRODUCTION_PERSONA = "guest"; // a blank account on the backend: no seeded policies
const THINKING_DELAY_MS = 550;
const SAVE_DEBOUNCE_MS = 600;

function sortByRecency(list: ConversationSummary[]): ConversationSummary[] {
  return [...list].sort((a, b) => b.updatedAt - a.updatedAt);
}

function summarize(c: StoredConversation): ConversationSummary {
  return {
    id: c.id,
    personaKey: c.personaKey,
    title: c.title,
    createdAt: c.createdAt,
    updatedAt: c.updatedAt,
    messageCount: c.messages.filter((m) => m.role !== "system" && !m.typing).length,
  };
}

function greetingFor(personaKey: string, mode: AppMode): string {
  if (mode === "production") {
    return "Welcome. Upload your policy (PDF) and I will read it live and tell you what it covers, with the clause that decides. You can also ask a general insurance question first.";
  }
  switch (personaKey) {
    case "dewi":
      return "Hi Dewi — I can see your personal accident, platform and BPJS cover. Ask me about a claim, or try a demo scene below.";
    case "santoso":
      return "Hi — I can see the Santoso family's employer, individual and BPJS cover. Ask about any of the family's policies, or try a demo scene below.";
    default:
      return "Hi Rizky — I can see your hospital cash plan, term life and BPJS cover. Ask me what's covered, or try a demo scene below.";
  }
}

function findOfflineStep(personaKey: string, text: string): SceneStep | undefined {
  for (const scene of SCENES) {
    if (scene.personaKey !== personaKey || scene.recorded) continue;
    for (const step of scene.steps) {
      if (step.kind === "chat" && step.userText === text) return step;
    }
  }
  return undefined;
}

export function useChatEngine(mode: AppMode) {
  const [online, setOnline] = useState<boolean | null>(null);
  const [personas, setPersonas] = useState<Persona[]>(FALLBACK_PERSONAS);
  const [personaKey, setPersonaKey] = useState(mode === "production" ? PRODUCTION_PERSONA : DEFAULT_PERSONA);
  const [policies, setPolicies] = useState<PoliciesResponse | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [followUps, setFollowUps] = useState<string[]>([]);
  const [sending, setSending] = useState(false);
  const [isDemo, setIsDemo] = useState(false);
  const [policiesPanelOpen, setPoliciesPanelOpen] = useState(false);
  const [focusPolicyId, setFocusPolicyId] = useState<string | null>(null);
  const [devPanelOpen, setDevPanelOpen] = useState(false);
  const [securityPanelOpen, setSecurityPanelOpen] = useState(false);
  const [demoSheetOpen, setDemoSheetOpen] = useState(false);
  // several files can be attached before one message; they travel together as `uploads`
  const [uploadedDocs, setUploadedDocs] = useState<Array<{ doc_id: string; filename: string }>>([]);
  const uploadedDoc = uploadedDocs.length === 0 ? null : { doc_id: uploadedDocs[uploadedDocs.length - 1].doc_id, filename: uploadedDocs.length === 1 ? uploadedDocs[0].filename : `${uploadedDocs.length} files attached` };
  const [digest, setDigest] = useState<DigestResponse | null>(null);
  const [digestDismissed, setDigestDismissed] = useState(false);
  const [uploadBusy, setUploadBusy] = useState(false);
  const [historyPanelOpen, setHistoryPanelOpen] = useState(false);
  const [history, setHistory] = useState<ConversationSummary[]>([]);
  const [historyMode, setHistoryMode] = useState<HistoryMode>("local");
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [fromHistory, setFromHistory] = useState(false);
  const [sessionState, setSessionState] = useState<SessionState | null>(null);
  const [insurerPanelOpen, setInsurerPanelOpen] = useState(false);
  const [controlsOpen, setControlsOpen] = useState(false);

  const tokenRef = useRef<Record<string, string>>({});
  const activeSceneRef = useRef<Scene | null>(null);
  // set while a recorded scene is on screen: the label is shown, live digest and polling stay out of the picture
  const [replay, setReplay] = useState<RecordedMeta | null>(null);
  const replayRef = useRef(false);
  const loadingPersonaRef = useRef<string | null>(null);
  const historyRef = useRef<ConversationSummary[]>([]);
  const historyModeRef = useRef<HistoryMode>("local");
  const convCacheRef = useRef<Record<string, StoredConversation>>({});
  const pendingSaveRef = useRef<Map<string, StoredConversation>>(new Map());
  const unsettledRef = useRef<Set<string>>(new Set());
  const saveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const refreshSeqRef = useRef(0);
  const activeByPersonaRef = useRef<Record<string, string>>({});
  const createdAtRef = useRef<number>(Date.now());
  const titleOverrideRef = useRef<string | null>(null);

  const beginConversation = useCallback((key: string, initial: ChatMessage[]) => {
    const id = newConversationId();
    activeByPersonaRef.current[key] = id;
    createdAtRef.current = Date.now();
    titleOverrideRef.current = null;
    setConversationId(id);
    setFromHistory(false);
    setMessages(initial);
    setFollowUps([]);
    setUploadedDocs([]);
    activeSceneRef.current = null;
    replayRef.current = false;
    setReplay(null);
    return id;
  }, []);

  const patchMessage = useCallback((id: string, patch: Partial<ChatMessage>) => {
    setMessages((prev) => prev.map((m) => (m.id === id ? { ...m, ...patch } : m)));
  }, []);

  const pushMessage = useCallback((msg: Omit<ChatMessage, "id">) => {
    const id = nextId();
    setMessages((prev) => [...prev, { id, ...msg }]);
    return id;
  }, []);

  const applyHistory = useCallback((next: ConversationSummary[]) => {
    historyRef.current = next;
    setHistory(next);
  }, []);

  const applyMode = useCallback((mode: HistoryMode) => {
    historyModeRef.current = mode;
    setHistoryMode(mode);
  }, []);

  const historyAuth = useMemo<HistoryAuth>(
    () => ({
      tokenFor: (key) => tokenRef.current[key],
      tokenPersonas: () => Object.keys(tokenRef.current),
      renew: async (key) => {
        try {
          const fresh = await api.login(key);
          tokenRef.current[key] = fresh.session_token;
          return fresh.session_token;
        } catch {
          return null;
        }
      },
    }),
    []
  );

  const refreshHistory = useCallback(async () => {
    const seq = (refreshSeqRef.current += 1);
    const { items, mode } = await loadHistory(historyAuth);
    if (seq !== refreshSeqRef.current) return;
    const unsettled = unsettledRef.current;
    const merged = new Map(items.map((c) => [c.id, c]));
    for (const c of historyRef.current) {
      if (unsettled.has(c.id)) merged.set(c.id, c);
    }
    applyHistory(sortByRecency(Array.from(merged.values())));
    applyMode(mode);
  }, [historyAuth, applyHistory, applyMode]);

  const flushPendingSaves = useCallback(async () => {
    if (saveTimerRef.current) {
      clearTimeout(saveTimerRef.current);
      saveTimerRef.current = null;
    }
    const batch = Array.from(pendingSaveRef.current.values());
    pendingSaveRef.current.clear();
    for (const record of batch) {
      const mode = await saveConversation(historyAuth, record);
      if (!pendingSaveRef.current.has(record.id)) unsettledRef.current.delete(record.id);
      const wasLocal = historyModeRef.current === "local";
      applyMode(mode);
      if (mode === "backend" && wasLocal) void refreshHistory();
    }
  }, [historyAuth, applyMode, refreshHistory]);

  const scheduleSave = useCallback(
    (record: StoredConversation) => {
      convCacheRef.current[record.id] = record;
      pendingSaveRef.current.set(record.id, record);
      unsettledRef.current.add(record.id);
      if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
      saveTimerRef.current = setTimeout(() => void flushPendingSaves(), SAVE_DEBOUNCE_MS);
    },
    [flushPendingSaves]
  );

  // ------------------------------------------------------------ bootstrap
  useEffect(() => {
    applyHistory(loadLocalSummaries());
    const flushOnHide = () => {
      if (document.visibilityState === "hidden" && pendingSaveRef.current.size) void flushPendingSaves();
    };
    document.addEventListener("visibilitychange", flushOnHide);
    return () => document.removeEventListener("visibilitychange", flushOnHide);
  }, [applyHistory, flushPendingSaves]);

  useEffect(() => {
    let mounted = true;
    (async () => {
      const ok = await api.checkBackendOnline();
      if (!mounted) return;
      setOnline(ok);
      if (ok) {
        try {
          const list = await api.getPersonas();
          if (mounted && list.length) setPersonas(list);
        } catch {
          /* keep fallback persona list */
        }
      }
    })();
    return () => {
      mounted = false;
    };
  }, []);

  const loadPersona = useCallback(
    async (key: string, backendOnline: boolean) => {
      loadingPersonaRef.current = key;
      setDigest(null);
      setDigestDismissed(false);
      if (backendOnline) {
        try {
          const res = await api.login(key);
          tokenRef.current[key] = res.session_token;
          void refreshHistory();
          const pol = await api.getPolicies(res.session_token);
          if (loadingPersonaRef.current === key) setPolicies(pol);
          api.getSession(res.session_token).then((st) => { if (loadingPersonaRef.current === key) setSessionState(st); }).catch(() => undefined);
          // Demo mode: the persona switch itself is "opening a chat", so the digest is worth
          // fetching right away. Production mode has no persona of its own to switch into —
          // its digest is fetched after the user's first upload instead (see uploadPolicy).
          if (mode === "demo") {
            api
              .getDigest(res.session_token)
              .then((d) => {
                if (loadingPersonaRef.current === key && d.available && d.items.length) setDigest(d);
              })
              .catch(() => undefined);
          }
          return;
        } catch {
          // fall through to fixture data if the live call failed mid-session
        }
      }
      setPolicies(FIXTURE_POLICIES[key] ?? null);
    },
    [refreshHistory, mode]
  );

  // load the default persona once we know whether the backend is reachable
  useEffect(() => {
    if (online === null) return;
    const first = mode === "production" ? PRODUCTION_PERSONA : DEFAULT_PERSONA;
    loadPersona(first, online);
    beginConversation(first, [{ id: nextId(), role: "assistant", text: greetingFor(first, mode) }]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [online]);

  // ------------------------------------------------------------ persistence
  useEffect(() => {
    if (!conversationId || sending) return;
    if (messages.some((m) => m.typing || m.policyUpload?.status === "extracting")) return;
    const title = deriveTitle(messages);
    if (!title) return;
    const previous = convCacheRef.current[conversationId];
    const snapshot = sanitizeForStorage(messages);
    if (previous && JSON.stringify(previous.messages) === JSON.stringify(snapshot)) return;
    const record: StoredConversation = {
      id: conversationId,
      personaKey,
      title: previous?.title ?? titleOverrideRef.current ?? title,
      createdAt: previous?.createdAt ?? createdAtRef.current,
      updatedAt: Date.now(),
      messages: snapshot,
    };
    scheduleSave(record);
    applyHistory(sortByRecency([summarize(record), ...historyRef.current.filter((c) => c.id !== record.id)]));
  }, [messages, sending, conversationId, personaKey, scheduleSave, applyHistory]);

  const switchPersona = useCallback(
    async (key: string) => {
      if (key === personaKey) return;
      setPersonaKey(key);
      setIsDemo(false);
      const resumeId = activeByPersonaRef.current[key];
      const resume = resumeId ? convCacheRef.current[resumeId] : undefined;
      if (resume) {
        setConversationId(resume.id);
        createdAtRef.current = resume.createdAt;
        setFromHistory(false);
        setMessages(reviveFromStorage(resume.messages));
        setFollowUps([]);
        setUploadedDocs([]);
        activeSceneRef.current = null;
      } else {
        beginConversation(key, [{ id: nextId(), role: "assistant", text: greetingFor(key, mode) }]);
      }
      if (!tokenRef.current[key] || resume === undefined) {
        await loadPersona(key, Boolean(online));
      } else {
        setPolicies(FIXTURE_POLICIES[key] ?? null);
        api.getPolicies(tokenRef.current[key]).then(setPolicies).catch(() => undefined);
      }
    },
    [personaKey, online, loadPersona, beginConversation, mode]
  );

  const newConversation = useCallback(() => {
    setIsDemo(false);
    beginConversation(personaKey, [{ id: nextId(), role: "assistant", text: greetingFor(personaKey, mode) }]);
  }, [personaKey, beginConversation, mode]);

  const loadConversation = useCallback(
    async (id: string) => {
      const summary = historyRef.current.find((c) => c.id === id);
      if (!summary) return;
      setHistoryPanelOpen(false);
      const target = convCacheRef.current[id] ?? (await fetchConversation(historyAuth, summary));
      if (!target) return;
      convCacheRef.current[id] = target;
      const key = target.personaKey;
      activeByPersonaRef.current[key] = target.id;
      createdAtRef.current = target.createdAt;
      setConversationId(target.id);
      setFromHistory(true);
      setIsDemo(false);
      setFollowUps([]);
      setUploadedDocs([]);
      activeSceneRef.current = null;
      setMessages(reviveFromStorage(target.messages));
      if (key !== personaKey) setPersonaKey(key);
      if (key !== personaKey || !tokenRef.current[key]) {
        await loadPersona(key, Boolean(online));
      }
    },
    [personaKey, online, loadPersona, historyAuth]
  );

  const deleteConversation = useCallback(
    (id: string) => {
      const target = historyRef.current.find((c) => c.id === id);
      pendingSaveRef.current.delete(id);
      unsettledRef.current.delete(id);
      delete convCacheRef.current[id];
      applyHistory(historyRef.current.filter((c) => c.id !== id));
      if (target) void deleteStored(historyAuth, target.personaKey, id);
      if (id === conversationId) {
        setIsDemo(false);
        beginConversation(personaKey, [{ id: nextId(), role: "assistant", text: greetingFor(personaKey, mode) }]);
      }
    },
    [conversationId, personaKey, beginConversation, historyAuth, applyHistory, mode]
  );

  const clearHistory = useCallback(() => {
    if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
    pendingSaveRef.current.clear();
    unsettledRef.current.clear();
    convCacheRef.current = {};
    void clearStored(historyAuth);
    applyHistory([]);
    activeByPersonaRef.current = {};
    setIsDemo(false);
    beginConversation(personaKey, [{ id: nextId(), role: "assistant", text: greetingFor(personaKey, mode) }]);
  }, [personaKey, beginConversation, historyAuth, applyHistory, mode]);

  // ------------------------------------------------------------ enrichment
  const enrichReply = useCallback(async (messageId: string, reply: ChatReply, token: string) => {
    const entitlement: NonNullable<ChatMessage["entitlement"]> = {};
    const jobs: Promise<void>[] = [];
    if (reply.readiness?.verdict?.policy_id) {
      jobs.push(
        api
          .getTwin(token, "draft", reply.readiness.verdict.policy_id)
          .then((t) => {
            if (t.available) entitlement.twin = t;
          })
          .catch(() => undefined)
      );
    }
    if (reply.cob && reply.cob.length >= 2) {
      jobs.push(
        api
          .getAllocation(token, "draft")
          .then((a) => {
            if (a.available && a.steps.length) entitlement.allocation = a;
          })
          .catch(() => undefined)
      );
    }
    if (reply.deadline) {
      jobs.push(
        api
          .getTimeline(token)
          .then((t) => {
            if (t.available && t.events.length) entitlement.timeline = t;
          })
          .catch(() => undefined)
      );
    }
    if (!jobs.length) return;
    await Promise.all(jobs);
    if (Object.keys(entitlement).length) patchMessage(messageId, { entitlement });
  }, [patchMessage]);

  // ------------------------------------------------------------ chat send (with 401 auto-recovery)
  // The backend keeps sessions in memory and wipes them on every restart, which happens often in
  // dev. A tab holding a now-stale token gets a 401 on its next /chat call even though the backend
  // itself is perfectly healthy. Re-login once and retry transparently before surfacing anything.
  type SendChatResult =
    | { ok: true; reply: ChatReply; token: string }
    | { ok: false; reason: "session_expired" | "network" | "aborted" };

  const abortRef = useRef<AbortController | null>(null);

  const sendChatWithRetry = useCallback(
    async (forPersonaKey: string, text: string, uploads: string[], signal?: AbortSignal): Promise<SendChatResult> => {
      const token = tokenRef.current[forPersonaKey];
      try {
        const reply = await api.sendChat(token, text, uploads, signal);
        return { ok: true, reply, token };
      } catch (err) {
        if (err instanceof DOMException && err.name === "AbortError") {
          return { ok: false, reason: "aborted" };
        }
        if (err instanceof api.ApiError && err.status === 401) {
          try {
            const fresh = await api.login(forPersonaKey);
            tokenRef.current[forPersonaKey] = fresh.session_token;
            api.getPolicies(fresh.session_token).then(setPolicies).catch(() => undefined);
            const reply = await api.sendChat(fresh.session_token, text, uploads, signal);
            return { ok: true, reply, token: fresh.session_token };
          } catch (retryErr) {
            if (retryErr instanceof DOMException && retryErr.name === "AbortError") {
              return { ok: false, reason: "aborted" };
            }
            return { ok: false, reason: "session_expired" };
          }
        }
        return { ok: false, reason: "network" };
      }
    },
    []
  );

  const stopSending = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  // ------------------------------------------------------------ send
  const sendMessage = useCallback(
    async (text: string, uploadsOverride?: string[]) => {
      const trimmed = text.trim();
      if (!trimmed || sending) return;
      // only drop the chip that was just used (if any) — a scene can queue
      // several follow-ups, and using one shouldn't discard the rest
      setFollowUps((prev) => prev.filter((f) => f !== trimmed));
      if (!uploadsOverride) for (const d of uploadedDocs) pushMessage({ role: "user", doc: { filename: d.filename } });
      pushMessage({ role: "user", text: trimmed });
      setSending(true);

      if (online) {
        const typingId = pushMessage({ role: "assistant", typing: true });
        const uploads = uploadsOverride ?? uploadedDocs.map((d) => d.doc_id);
        const controller = new AbortController();
        abortRef.current = controller;
        try {
          const result = await sendChatWithRetry(personaKey, trimmed, uploads, controller.signal);
          if (result.ok) {
            setUploadedDocs([]);
            const fresh = firstTier2Pending(result.reply)?.tool;
            if (fresh) {
              // the backend keeps one pending action per tool: an older unresolved card for the same tool is now stale
              setMessages((prev) =>
                prev.map((m) =>
                  m.id !== typingId && m.reply && !m.pendingResolved && firstTier2Pending(m.reply)?.tool === fresh ? { ...m, pendingResolved: "superseded" } : m
                )
              );
            }
            patchMessage(typingId, { typing: false, reply: result.reply, liveReply: true, forText: trimmed, usedUploads: uploads });
            void enrichReply(typingId, result.reply, result.token);
          } else if (result.reason === "aborted") {
            patchMessage(typingId, {
              typing: false,
              text: "Stopped. The backend may still finish that turn in the background — its answer just won't show here.",
            });
          } else if (result.reason === "session_expired") {
            patchMessage(typingId, {
              typing: false,
              text: "Your session expired and couldn't be renewed automatically. Try switching persona (or back) to start a fresh session.",
            });
          } else {
            patchMessage(typingId, {
              typing: false,
              text: "I couldn't reach the backend just now. It may have gone offline mid-session — try again in a moment.",
            });
            api.checkBackendOnline(true).then(setOnline);
          }
        } finally {
          if (abortRef.current === controller) abortRef.current = null;
          setSending(false);
        }
        return;
      }

      // offline: replay a recorded exchange if this exact question is one we captured (demo only —
      // production mode has no recorded scenes to fall back to)
      await new Promise((r) => setTimeout(r, THINKING_DELAY_MS));
      const step = mode === "demo" ? findOfflineStep(personaKey, trimmed) : undefined;
      if (step?.reply) {
        pushMessage({ role: "assistant", reply: step.reply, entitlement: step.entitlement, offlineNotice: true });
      } else if (mode === "demo") {
        pushMessage({
          role: "assistant",
          offlineNotice: true,
          text:
            "The demo backend is offline right now, so I can only replay a few recorded examples here. Try one of the demo scenes below, or run the backend locally to chat freely.",
        });
        setFollowUps(SCENES.filter((s) => s.personaKey === personaKey && !s.recorded).map((s) => s.steps.find((st) => st.kind === "chat")?.userText ?? "").filter(Boolean));
      } else {
        pushMessage({
          role: "assistant",
          offlineNotice: true,
          text: "The backend is offline right now, so I can't read your policy. Please try again in a moment.",
        });
      }
      setSending(false);
    },
    [online, personaKey, sending, uploadedDocs, pushMessage, patchMessage, enrichReply, sendChatWithRetry, mode]
  );

  // ------------------------------------------------------------ confirm / cancel
  const confirmPending = useCallback(
    async (messageId: string, reply: ChatReply) => {
      patchMessage(messageId, { confirmBusy: true });
      const scene = activeSceneRef.current;
      if ((!online || scene?.recorded) && scene) {
        const step = scene.steps.find((s) => s.reply === reply);
        if (step?.confirmReply) {
          await new Promise((r) => setTimeout(r, 400));
          pushMessage({ role: "assistant", reply: step.confirmReply, replayed: Boolean(scene.recorded) });
          patchMessage(messageId, { pendingResolved: "confirmed", confirmBusy: false });
          if (step.followUpText) {
            await new Promise((r) => setTimeout(r, 1200));
            pushMessage({ role: "assistant", text: `News from the insurer: ${step.followUpText}` });
          }
          return;
        }
      }
      if (!online) {
        patchMessage(messageId, { confirmBusy: false });
        pushMessage({
          role: "assistant",
          text: "Confirming a submission needs the live backend; this recorded example doesn't have one wired up for this message.",
        });
        return;
      }
      const token = tokenRef.current[personaKey];
      const wanted = reply.actions_pending.find((a) => a.tier === 2 && a.requires_confirmation);
      try {
        const pending = await api.getChatPending(token);
        const idx = pending.pending.findIndex((p) => p.tool === wanted?.tool);
        const confirmed = await api.confirmChat(token, idx >= 0 ? idx : 0);
        pushMessage({ role: "assistant", reply: confirmed });
        patchMessage(messageId, { pendingResolved: "confirmed", confirmBusy: false });
      } catch {
        patchMessage(messageId, { confirmBusy: false });
        pushMessage({ role: "assistant", text: "The confirmation didn't go through. Nothing was submitted; you can try again." });
      }
    },
    [online, personaKey, pushMessage, patchMessage]
  );

  const cancelPending = useCallback(
    (messageId: string) => {
      patchMessage(messageId, { pendingResolved: "cancelled" });
      pushMessage({ role: "system", text: "Cancelled — nothing was sent." });
    },
    [patchMessage, pushMessage]
  );

  // ------------------------------------------------------------ regenerate
  // Resends the user turn that produced a reply, in place — only ever offered for the most
  // recent reply, and only when it's `liveReply` (so a reloaded/scene/offline message, whose
  // session or recorded fixture no longer matches, never shows the option).
  const regenerate = useCallback(
    async (messageId: string) => {
      if (sending) return;
      const msg = messages.find((m) => m.id === messageId);
      if (!msg || msg.role !== "assistant" || !msg.liveReply || !msg.forText) return;
      setSending(true);
      patchMessage(messageId, {
        typing: true,
        reply: undefined,
        text: undefined,
        entitlement: undefined,
        pendingResolved: undefined,
        confirmBusy: undefined,
      });
      const controller = new AbortController();
      abortRef.current = controller;
      try {
        const result = await sendChatWithRetry(personaKey, msg.forText, msg.usedUploads ?? [], controller.signal);
        if (result.ok) {
          patchMessage(messageId, {
            typing: false,
            reply: result.reply,
            liveReply: true,
            forText: msg.forText,
            usedUploads: msg.usedUploads,
          });
          void enrichReply(messageId, result.reply, result.token);
        } else if (result.reason === "aborted") {
          patchMessage(messageId, {
            typing: false,
            text: "Stopped. The backend may still finish that turn in the background — its answer just won't show here.",
          });
        } else if (result.reason === "session_expired") {
          patchMessage(messageId, {
            typing: false,
            text: "Your session expired and couldn't be renewed automatically. Try switching persona (or back) to start a fresh session.",
          });
        } else {
          patchMessage(messageId, {
            typing: false,
            text: "I couldn't reach the backend just now. It may have gone offline mid-session — try again in a moment.",
          });
          api.checkBackendOnline(true).then(setOnline);
        }
      } finally {
        if (abortRef.current === controller) abortRef.current = null;
        setSending(false);
      }
    },
    [messages, sending, personaKey, patchMessage, sendChatWithRetry, enrichReply]
  );

  // ------------------------------------------------------------ uploads
  const attachDocument = useCallback(
    async (file: File) => {
      if (!online) {
        pushMessage({
          role: "assistant",
          text: "Attaching a document needs the live backend. Try the \"Hidden-text invoice\" demo scene instead to see how this works.",
        });
        return;
      }
      setUploadBusy(true);
      try {
        const token = tokenRef.current[personaKey];
        const res = await api.uploadDocument(token, file);
        // the file waits in the composer; it enters the conversation only when the customer sends a message
        setUploadedDocs((prev) => [...prev, { doc_id: res.doc_id, filename: file.name }]);
      } catch {
        pushMessage({ role: "assistant", text: "That upload didn't go through. Please try again." });
      } finally {
        setUploadBusy(false);
      }
    },
    [online, personaKey, pushMessage]
  );

  // ------------------------------------------------------------ upload my own policy (live extraction demo)
  const uploadPolicy = useCallback(
    async (file: File) => {
      if (!online) {
        pushMessage({
          role: "assistant",
          text: "Uploading your own policy needs the live backend (it runs the real extractor). Try again once the backend is reachable.",
        });
        return;
      }
      const token = tokenRef.current[personaKey];
      const id = pushMessage({ role: "user", policyUpload: { filename: file.name, status: "extracting" } });
      try {
        const result = await api.uploadPolicy(token, file);
        patchMessage(id, { policyUpload: { filename: file.name, status: "done", result } });
        // merge immediately so the panel shows it without waiting on a round trip, then
        // refetch to prove it is real server-side state, not just a client-side merge.
        setPolicies((prev) =>
          prev
            ? { ...prev, policies: [...prev.policies.filter((p) => p.id !== result.policy.id), result.policy] }
            : prev
        );
        api.getPolicies(token).then(setPolicies).catch(() => undefined);
        // Production mode's "chat open" moment is the first completed upload, not a persona
        // switch (there is no persona picker to switch in that mode) — fetch the digest here.
        if (mode === "production") {
          setDigestDismissed(false);
          api
            .getDigest(token)
            .then((d) => {
              if (d.available && d.items.length) setDigest(d);
            })
            .catch(() => undefined);
        }
      } catch (err) {
        const message = err instanceof api.ApiError ? err.message : "That upload didn't go through. Please try again.";
        patchMessage(id, { policyUpload: { filename: file.name, status: "error", error: message } });
      }
    },
    [online, personaKey, pushMessage, patchMessage, mode]
  );

  const viewUploadedPolicy = useCallback((policyId: string) => {
    setFocusPolicyId(policyId);
    setPoliciesPanelOpen(true);
  }, []);

  const dismissDigest = useCallback(() => setDigestDismissed(true), []);

  // Session notes (mode, clock) replace their predecessor instead of piling up in the thread.
  const noteSession = useCallback(
    (kind: "mode" | "clock", text: string) => {
      const prefix = kind === "mode" ? /^(Observe|Draft|Act) mode:/ : /^Sandbox clock/;
      setMessages((prev) => [...prev.filter((m) => !(m.role === "system" && m.text && prefix.test(m.text))), { id: nextId(), role: "system", text }]);
    },
    []
  );

  // claim-status lines already shown, so a change at the insurer's desk becomes one proactive message, not a repeat
  const claimStatusSeen = useRef<Map<string, string> | null>(null);

  const refreshDigest = useCallback(async (quiet = false) => {
    const token = tokenRef.current[personaKey];
    if (!token || replayRef.current) return;
    try {
      const d = await api.getDigest(token);
      const statuses = new Map((d.items ?? []).filter((i) => i.kind === "CLAIM_STATUS" && i.claim_id).map((i) => [i.claim_id as string, i.message_en]));
      if (claimStatusSeen.current) {
        statuses.forEach((text, claimId) => {
          if (claimStatusSeen.current?.get(claimId) !== text) {
            pushMessage({ role: "assistant", text: `News from the insurer: ${text}` });
          }
        });
      }
      claimStatusSeen.current = statuses;
      setDigest(d.available && d.items.length ? d : null);
      if (!quiet) setDigestDismissed(false);
    } catch {
      /* digest is best effort */
    }
  }, [personaKey, pushMessage]);

  // while the chat is open the desk may decide: poll quietly so the decision reaches the customer without a reload
  useEffect(() => {
    if (online !== true) return;
    const id = setInterval(() => void refreshDigest(true), 30000);
    return () => clearInterval(id);
  }, [online, refreshDigest]);

  useEffect(() => {
    claimStatusSeen.current = null; // a new persona or session starts the comparison afresh
  }, [personaKey]);

  const setAutonomy = useCallback(
    async (m: AutonomyMode) => {
      const token = tokenRef.current[personaKey];
      if (!token) return;
      try {
        const st = await api.setAutonomy(token, m);
        setSessionState(st);
        const note = m === "observe" ? "Observe mode: the agent answers and explains only." : m === "draft" ? "Draft mode: the agent prepares drafts but cannot submit." : "Act mode: the agent may submit, but only after you tap Confirm.";
        noteSession("mode", note);
      } catch {
        pushMessage({ role: "system", text: "Could not change the autonomy mode." });
      }
    },
    [personaKey, pushMessage, noteSession]
  );

  const moveClock = useCallback(
    async (days: number, reset = false) => {
      const token = tokenRef.current[personaKey];
      if (!token) return;
      try {
        const st = await api.moveClock(token, days, reset);
        setSessionState(st);
        noteSession("clock", reset ? `Sandbox clock reset: today is ${st.as_of}.` : `Sandbox clock: today is now ${st.as_of} (${st.as_of_offset_days > 0 ? "+" : ""}${st.as_of_offset_days} days).`);
        await refreshDigest();
      } catch {
        pushMessage({ role: "system", text: "Could not move the sandbox clock." });
      }
    },
    [personaKey, pushMessage, refreshDigest, noteSession]
  );

  const askAboutDigestItem = useCallback(
    (item: DigestResponse["items"][number]) => {
      setDigestDismissed(true);
      void sendMessage(digestItemQuestion(item));
    },
    [sendMessage]
  );

  // ------------------------------------------------------------ demo scenes
  const startScene = useCallback(
    async (scene: Scene) => {
      setDemoSheetOpen(false);
      if (scene.personaKey !== personaKey) {
        setPersonaKey(scene.personaKey);
        if (!tokenRef.current[scene.personaKey]) {
          await loadPersona(scene.personaKey, Boolean(online));
        } else {
          api.getPolicies(tokenRef.current[scene.personaKey]).then(setPolicies).catch(() => undefined);
        }
      }
      beginConversation(scene.personaKey, []);
      titleOverrideRef.current = scene.title;
      activeSceneRef.current = scene;
      if (scene.recorded) {
        replayRef.current = true;
        setReplay(scene.recorded);
      }
      setIsDemo(true);
      setSending(true);

      const token = tokenRef.current[scene.personaKey];
      let stepIndex = 0;
      let pendingUploadId: string | null = null;

      // step 0: run an upload action immediately when the scene opens with one
      if (scene.steps[0]?.kind === "upload") {
        const doc = scene.steps[0].doc;
        if (online && token) {
          try {
            const res = await api.runDemoAttack(token, "hidden_text_invoice");
            const docId = res.doc_id ?? doc?.doc_id ?? "";
            const filename = res.filename ?? doc?.filename ?? "document.pdf";
            pendingUploadId = docId || null;
            setUploadedDocs(docId ? [{ doc_id: docId, filename }] : []);
            pushMessage({ role: "user", doc: { filename } });
            // the hidden-text scan runs server-side inside the *next* /chat
            // call (extract_document only runs once the doc is referenced in
            // a message), so the DOC_SUSPICIOUS audit check happens after
            // that reply comes back, not here.
          } catch {
            if (doc) {
              pendingUploadId = doc.doc_id;
              setUploadedDocs([{ doc_id: doc.doc_id, filename: doc.filename }]);
              pushMessage({ role: "user", doc: { filename: doc.filename } });
            }
          }
        } else if (doc) {
          await new Promise((r) => setTimeout(r, 300));
          pendingUploadId = doc.doc_id;
          setUploadedDocs([{ doc_id: doc.doc_id, filename: doc.filename }]);
          pushMessage({ role: "user", doc: { filename: doc.filename, suspicious: doc.suspicious, findings: doc.findings } });
          if (doc.suspicious) {
            pushMessage({
              role: "assistant",
              offlineNotice: true,
              text:
                "This file contained hidden, instruction-like text aimed at me, not at you. It was flagged and ignored — nothing it said was followed.",
            });
          }
        }
        stepIndex = 1;
      }

      const first = scene.steps[stepIndex];
      if (first?.kind === "chat" && first.userText) {
        if (online && token && !scene.recorded) {
          pushMessage({ role: "user", text: first.userText });
          const typingId = pushMessage({ role: "assistant", typing: true });
          const uploads = pendingUploadId ? [pendingUploadId] : [];
          const result = await sendChatWithRetry(scene.personaKey, first.userText, uploads);
          if (result.ok) {
            setUploadedDocs([]);
            patchMessage(typingId, { typing: false, reply: result.reply });
            void enrichReply(typingId, result.reply, result.token);
            if (uploads.length) {
              // the hidden-text scan (extract_document) just ran as part of
              // this turn; check whether it flagged anything
              api
                .getAudit(result.token)
                .then((audit) => {
                  const found = audit.events.find((e) => e.event_type === "DOC_SUSPICIOUS");
                  if (found?.findings?.length) {
                    pushMessage({
                      role: "assistant",
                      text:
                        "That file contained hidden, instruction-like text aimed at me, not at you. It was flagged and ignored — nothing it said was followed.",
                      doc: { filename: "the file you attached", suspicious: true, findings: found.findings as string[] },
                    });
                  }
                })
                .catch(() => undefined);
            }
          } else if (result.reason === "session_expired") {
            patchMessage(typingId, {
              typing: false,
              text: "Your session expired and couldn't be renewed automatically. Try switching persona (or back) to start a fresh session.",
            });
          } else {
            patchMessage(typingId, { typing: false, text: "I couldn't reach the backend just now." });
          }
        } else {
          for (const d of first.docs ?? []) pushMessage({ role: "user", doc: { filename: d.filename } });
          pushMessage({ role: "user", text: first.userText });
          await new Promise((r) => setTimeout(r, scene.recorded ? THINKING_DELAY_MS * 2 : THINKING_DELAY_MS));
          pushMessage({ role: "assistant", reply: first.reply, entitlement: first.entitlement, offlineNotice: !online && !scene.recorded, claimDraft: first.claimDraft, replayed: Boolean(scene.recorded) });
        }
        stepIndex += 1;
      }

      const remaining = scene.steps.slice(stepIndex).filter((s): s is SceneStep & { userText: string } => s.kind === "chat" && Boolean(s.userText));
      setFollowUps(remaining.map((s) => s.userText));
      setSending(false);
    },
    [online, personaKey, loadPersona, beginConversation, pushMessage, patchMessage, enrichReply, sendChatWithRetry]
  );

  const renameConversation = useCallback((id: string, title: string) => {
    const trimmed = title.replace(/\s+/g, " ").trim();
    if (!trimmed) return;
    const target = historyRef.current.find((c) => c.id === id);
    if (!target) return;
    const nextTitle = trimmed.slice(0, 200);
    const cached = convCacheRef.current[id];
    if (cached) convCacheRef.current[id] = { ...cached, title: nextTitle };
    const queued = pendingSaveRef.current.get(id);
    if (queued) pendingSaveRef.current.set(id, { ...queued, title: nextTitle });
    applyHistory(historyRef.current.map((c) => (c.id === id ? { ...c, title: nextTitle } : c)));
    if (queued) return;
    void renameStored(historyAuth, target.personaKey, id, nextTitle, cached).then((ok) => {
      if (ok) return;
      applyHistory(historyRef.current.map((c) => (c.id === id ? { ...c, title: target.title } : c)));
    });
  }, [historyAuth, applyHistory]);

  return {
    history,
    historyMode,
    conversationId,
    fromHistory,
    historyPanelOpen,
    setHistoryPanelOpen,
    newConversation,
    loadConversation,
    deleteConversation,
    renameConversation,
    clearHistory,
    online,
    personas,
    personaKey,
    policies,
    messages,
    followUps,
    sending,
    isDemo,
    replay,
    scenes: SCENES,
    policiesPanelOpen,
    setPoliciesPanelOpen,
    focusPolicyId,
    setFocusPolicyId,
    devPanelOpen,
    setDevPanelOpen,
    securityPanelOpen,
    setSecurityPanelOpen,
    demoSheetOpen,
    setDemoSheetOpen,
    uploadedDoc,
    uploadBusy,
    switchPersona,
    sendMessage,
    confirmPending,
    cancelPending,
    stopSending,
    regenerate,
    attachDocument,
    uploadPolicy,
    viewUploadedPolicy,
    digest,
    digestDismissed,
    dismissDigest,
    askAboutDigestItem,
    startScene,
    clearUpload: () => setUploadedDocs([]),
    sessionToken: () => tokenRef.current[personaKey],
    sessionState,
    setAutonomy,
    moveClock,
    refreshDigest,
    insurerPanelOpen,
    setInsurerPanelOpen,
    controlsOpen,
    setControlsOpen,
  };
}
