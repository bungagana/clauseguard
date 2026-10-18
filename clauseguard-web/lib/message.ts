import type { ClaimDraft } from "./replayTypes";
import type { AllocationResponse, ChatReply, PendingAction, PolicyUploadResult, TimelineResponse, TwinResponse } from "./types";

export interface MessageDoc {
  filename: string;
  doc_id?: string; // the customer's own upload, when it can be reopened from the server
  suspicious?: boolean;
  findings?: string[];
}

export interface PolicyUploadCard {
  filename: string;
  status: "extracting" | "done" | "error";
  result?: PolicyUploadResult;
  error?: string;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "system";
  text?: string;
  doc?: MessageDoc;
  replayed?: boolean; // part of a recorded scene: actions that need a server (PDF export) are not offered
  claimDraft?: ClaimDraft; // set only on a recorded scene's reply: the form is shown from the recording, not fetched
  policyUpload?: PolicyUploadCard;
  reply?: ChatReply;
  typing?: boolean;
  offlineNotice?: boolean;
  entitlement?: {
    timeline?: TimelineResponse;
    allocation?: AllocationResponse;
    twin?: TwinResponse;
  };
  // "superseded": a later reply carried a fresh version of the same pending action (e.g. the form was rebuilt after a correction)
  pendingResolved?: "confirmed" | "cancelled" | "expired" | "superseded";
  confirmBusy?: boolean;
  // Set only on a reply that just arrived live (not from history, a scene, or an offline
  // replay) — gates the streaming reveal (so a reloaded conversation renders instantly) and
  // regenerate eligibility (so stale sessions can't be resent).
  liveReply?: boolean;
  forText?: string;
  usedUploads?: string[];
}

let counter = 0;
export function nextId(): string {
  counter += 1;
  return `m${Date.now()}_${counter}`;
}

export function firstTier2Pending(reply: ChatReply | undefined): PendingAction | undefined {
  return reply?.actions_pending?.find((a) => a.tier === 2 && a.requires_confirmation);
}
