import { SCENES as RAW_SCENES, FIXTURE_POLICIES, type Scene as BaseScene, type SceneStep as BaseStep, type FixtureDoc } from "./fixtures.generated";
import { CLAIM_FLOW_SCENE } from "./fixtures.claimflow";
import { normalizeChatReply } from "./normalize";
import type { ClaimDraft, RecordedMeta } from "./replayTypes";

export { FIXTURE_POLICIES };
export type { FixtureDoc };

export interface SceneStep extends BaseStep {
  docs?: FixtureDoc[]; // several files attached before one message
  claimDraft?: ClaimDraft; // the claim form of the pending submission, so the card renders without a server
  followUpText?: string; // the insurer's decision, announced after the confirmation
}

export interface Scene extends Omit<BaseScene, "steps"> {
  steps: SceneStep[];
  // present only on a scene recorded from a real run: it replays in the browser even while the backend is up
  recorded?: RecordedMeta;
}

// Normalize every recorded reply once at module load (see normalize.ts for
// why this matters even for data captured from a real run).
export const SCENES: Scene[] = ([...RAW_SCENES, CLAIM_FLOW_SCENE] as Scene[]).map((scene) => ({
  ...scene,
  steps: scene.steps.map((step) => ({
    ...step,
    reply: step.reply ? normalizeChatReply(step.reply) : undefined,
    confirmReply: step.confirmReply ? normalizeChatReply(step.confirmReply) : undefined,
  })),
}));

export function sceneById(id: string): Scene | undefined {
  return SCENES.find((s) => s.id === id);
}

export function scenesForPersona(personaKey: string): Scene[] {
  return SCENES.filter((s) => s.personaKey === personaKey);
}
