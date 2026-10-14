import { SCENES as RAW_SCENES, FIXTURE_POLICIES, type Scene } from "./fixtures.generated";
import { normalizeChatReply } from "./normalize";

export { FIXTURE_POLICIES };
export type { Scene, SceneStep, FixtureDoc } from "./fixtures.generated";

// Normalize every recorded reply once at module load (see normalize.ts for
// why this matters even for data captured from a real run).
export const SCENES: Scene[] = RAW_SCENES.map((scene) => ({
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
