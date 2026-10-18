"use client";

import { useEffect, useState } from "react";
import { useChatEngine } from "./useChatEngine";
import { TopBar } from "./TopBar";
import { MessageList } from "./MessageList";
import { Composer } from "./Composer";
import { OfflineBanner } from "./OfflineBanner";
import { DemoSceneSheet } from "./DemoSceneSheet";
import { PoliciesPanel } from "./PoliciesPanel";
import { DeveloperPanel } from "./DeveloperPanel";
import { HistorySidebar } from "./HistorySidebar";
import { DigestCard } from "./DigestCard";
import { InsurerPanel } from "./InsurerPanel";
import { SessionControls } from "./SessionControls";
import { personaMeta } from "@/lib/personas";
import { ClaimStageStrip } from "./ClaimStageStrip";
import { ReplayStrip } from "./ReplayStrip";
import { ProcessPanel } from "./ProcessPanel";
import { SecurityInfoDialog } from "./SecurityInfoDialog";
import { ApiKeyDialog } from "./ApiKeyDialog";
import { defaultAppMode, readStoredAppMode, setStoredAppMode, type AppMode } from "@/lib/appMode";

export function ChatApp({ initialModeOverride }: { initialModeOverride?: AppMode }) {
  const [mode, setMode] = useState<AppMode>(initialModeOverride ?? defaultAppMode());

  // The query param (set by the landing page's two CTAs) wins and is remembered for this
  // browser; otherwise fall back to whatever was remembered last, then the env default. This
  // mirrors ThemeToggle's own localStorage pattern and runs before useChatEngine's bootstrap
  // effect below (same render, earlier hook), so the persona/greeting it picks already sees
  // the right mode.
  useEffect(() => {
    if (initialModeOverride) {
      setStoredAppMode(initialModeOverride);
      return;
    }
    const stored = readStoredAppMode();
    if (stored && stored !== mode) setMode(stored);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const engine = useChatEngine(mode);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [processOpen, setProcessOpen] = useState(true);

  const awaitingFirstUpload =
    mode === "production" &&
    !engine.uploadedDoc &&
    !engine.messages.some((m) => m.policyUpload && m.policyUpload.status !== "error");

  return (
    <div className="flex h-dvh flex-col bg-background">
      <TopBar
        mode={mode}
        personas={engine.personas}
        activePersona={engine.personaKey}
        onSwitchPersona={engine.switchPersona}
        fromHistory={engine.fromHistory}
        onOpenPolicies={() => engine.setPoliciesPanelOpen(true)}
        onOpenControls={() => engine.setControlsOpen(true)}
        onToggleProcess={mode === "demo" ? () => setProcessOpen((o) => !o) : undefined}
        processOpen={processOpen}
        onToggleSidebar={() => setSidebarOpen((o) => !o)}
        onOpenHistory={() => engine.setHistoryPanelOpen(true)}
        onNewConversation={engine.newConversation}
        backendOnline={engine.online === true}
        sessionState={engine.sessionState}
        onAutonomyChange={(m) => void engine.setAutonomy(m)}
      />

      <div className="flex min-h-0 flex-1">
        <HistorySidebar
          desktopOpen={sidebarOpen}
          mobileOpen={engine.historyPanelOpen}
          onMobileOpenChange={engine.setHistoryPanelOpen}
          conversations={engine.history}
          mode={engine.historyMode}
          activeId={engine.conversationId}
          onSelect={(id) => void engine.loadConversation(id)}
          onNew={engine.newConversation}
          onRename={engine.renameConversation}
          onDelete={engine.deleteConversation}
          onClearAll={engine.clearHistory}
          profile={(() => {
            const m = personaMeta(engine.personaKey);
            return { name: m.name, subtitle: m.tagline, initials: m.initials, accent: m.accent, demo: mode === "demo" };
          })()}
        />

        <div className="flex min-w-0 flex-1 flex-col">
          {engine.online === false && !engine.replay && <OfflineBanner />}

          {engine.replay && <ReplayStrip meta={engine.replay} />}

          <ClaimStageStrip messages={engine.messages} digest={engine.replay ? null : engine.digest} />

          {!engine.replay && !engine.digestDismissed && engine.digest?.items.length ? (
            <DigestCard items={engine.digest.items} onAsk={engine.askAboutDigestItem} onDismiss={engine.dismissDigest} />
          ) : null}

          <MessageList
            messages={engine.messages}
            policies={engine.policies}
            onConfirm={(id) => {
              const msg = engine.messages.find((m) => m.id === id);
              if (msg?.reply) void engine.confirmPending(id, msg.reply);
            }}
            onCancel={(id) => engine.cancelPending(id)}
            onViewPolicy={engine.viewUploadedPolicy}
            onRegenerate={(id) => void engine.regenerate(id)}
            onQuickReply={(text) => void engine.sendMessage(text)}
            sessionToken={engine.sessionToken}
            autonomy={engine.sessionState?.autonomy}
          />

          <Composer
            mode={mode}
            awaitingUpload={awaitingFirstUpload}
            onSend={(text) => void engine.sendMessage(text)}
            onAttach={(file) => void engine.attachDocument(file)}
            onUploadPolicy={(file) => void engine.uploadPolicy(file)}
            onOpenDemo={() => engine.setDemoSheetOpen(true)}
            onStop={engine.stopSending}
            followUps={engine.followUps}
            uploadedFilename={engine.uploadedDoc?.filename}
            onClearUpload={engine.clearUpload}
            uploadBusy={engine.uploadBusy}
            sending={engine.sending}
            disabled={engine.online === null}
          />
        </div>

        {mode === "demo" && (
          <ProcessPanel
            open={processOpen}
            onClose={() => setProcessOpen(false)}
            messages={engine.messages}
            policies={engine.policies}
            sessionState={engine.sessionState}
            online={engine.online === true}
            onMoveClock={(d, r) => void engine.moveClock(d, r)}
            onOpenInsurer={() => engine.setInsurerPanelOpen(true)}
            onOpenDeveloper={() => engine.setDevPanelOpen(true)}
          />
        )}
      </div>

      {mode === "demo" && (
        <DemoSceneSheet
          open={engine.demoSheetOpen}
          onOpenChange={engine.setDemoSheetOpen}
          scenes={engine.scenes}
          onPick={(scene) => void engine.startScene(scene)}
        />
      )}

      <PoliciesPanel
        open={engine.policiesPanelOpen}
        onOpenChange={(open) => {
          engine.setPoliciesPanelOpen(open);
          if (!open) engine.setFocusPolicyId(null);
        }}
        policies={engine.policies}
        focusPolicyId={engine.focusPolicyId}
      />

      <SessionControls
        open={engine.controlsOpen}
        onOpenChange={engine.setControlsOpen}
        sessionState={engine.sessionState}
      >
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <SecurityInfoDialog /> How ClauseGuard keeps you in control
        </div>
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <ApiKeyDialog /> Use your own Gemini key
        </div>
      </SessionControls>

      {mode === "demo" && <InsurerPanel open={engine.insurerPanelOpen} onOpenChange={engine.setInsurerPanelOpen} />}

      <DeveloperPanel
        open={engine.devPanelOpen}
        onOpenChange={engine.setDevPanelOpen}
        policies={engine.policies}
        messages={engine.messages}
      />
    </div>
  );
}
