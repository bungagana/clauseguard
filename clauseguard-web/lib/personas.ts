import type { Persona } from "./types";

export interface PersonaMeta {
  key: string;
  name: string;
  tagline: string;
  initials: string;
  accent: string; // tailwind class suffix for a small color accent on the avatar ring
}

// Static display metadata for the three sandbox personas. The live label/
// description still comes from GET /personas; this just adds friendlier
// names, initials and a color accent for the switcher UI.
export const PERSONA_META: Record<string, PersonaMeta> = {
  rizky: {
    key: "rizky",
    name: "Rizky",
    tagline: "Grad student with a hospital-cash claim in progress",
    initials: "RP",
    accent: "bg-primary/10 text-primary",
  },
  santoso: {
    key: "santoso",
    name: "Santoso family",
    tagline: "A family of four juggling employer and individual cover",
    initials: "SF",
    accent: "bg-warning/15 text-warning-foreground",
  },
  dewi: {
    key: "dewi",
    name: "Dewi",
    tagline: "Delivery rider with platform and personal-accident cover",
    initials: "DL",
    accent: "bg-success/10 text-success",
  },
};

// production mode signs in as a fresh account with no policies on file
PERSONA_META.guest = { key: "guest", name: "Your account", tagline: "Policies you upload stay in this session", initials: "ME", accent: "bg-primary/10 text-primary" };

export const FALLBACK_PERSONAS: Persona[] = [
  {
    key: "rizky",
    label: "Rizky Pratama (24, graduate student)",
    user_id: "C-RIZKY",
    description:
      "24, graduate student. Hospital cash plan, term life (premium overdue), BPJS class 2. Open dengue claim.",
  },
  {
    key: "santoso",
    label: "Santoso family (Budi, Sari, Aditya, Nadia)",
    user_id: "C-BUDI",
    description:
      "Budi, Sari, Aditya, Nadia. Employer group health and life, family hospital-cash rider, Sari's individual plan, BPJS class 1.",
  },
  {
    key: "dewi",
    label: "Dewi Lestari (29, ojek/courier)",
    user_id: "C-DEWI",
    description:
      "29, ojek courier. Personal accident, platform on-trip cover, BPJS class 3 (3 months arrears), Jasa Raharja statutory.",
  },
];

export function personaMeta(key: string): PersonaMeta {
  return PERSONA_META[key] ?? { key, name: key, tagline: "", initials: key.slice(0, 2).toUpperCase(), accent: "bg-muted text-muted-foreground" };
}
