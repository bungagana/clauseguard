import type { Verdict } from "./types";
import { humanize } from "./format";

// Plain-language names for the facts the engine can ask about, used wherever a slot name
// would otherwise leak into the interface ("facility_bpjs_partner = True").
const SLOT_PHRASES: Record<string, { label: string; yes: string; no: string }> = {
  facility_bpjs_partner: { label: "the hospital", yes: "is a BPJS partner", no: "is not a BPJS partner" },
  facility_in_network: { label: "the hospital", yes: "is in the insurer's network", no: "is out of network" },
  license_valid: { label: "your licence", yes: "was valid", no: "had expired" },
  is_accident: { label: "the cause", yes: "was an accident", no: "was an illness" },
  is_emergency: { label: "the admission", yes: "was an emergency", no: "was planned" },
  work_related: { label: "it", yes: "happened while working", no: "happened off duty" },
  intoxicated: { label: "you", yes: "were under the influence", no: "were sober" },
  employment_active: { label: "you", yes: "are still employed there", no: "have left the employer" },
  rider_attached: { label: "the rider", yes: "is attached", no: "is not attached" },
  vehicles_involved: { label: "vehicles involved", yes: "", no: "" },
  days_hospitalized: { label: "days in hospital", yes: "", no: "" },
  occupation_class: { label: "occupation class", yes: "", no: "" },
};

const VERDICT_WORD: Record<string, string> = {
  COVERED: "covered",
  DENIED: "not covered",
  NOT_APPLICABLE: "the policy does not apply",
  NOT_SPECIFIED: "not specified",
  CLARIFY: "still depends on another fact",
};

/** "If the hospital is a BPJS partner → not covered" */
export function branchSentence(slot: string, value: string, verdict: Verdict | string): string {
  const key = slot.toLowerCase();
  const p = SLOT_PHRASES[key];
  const v = value.toLowerCase();
  let condition: string;
  if (p && (v === "true" || v === "false")) condition = `${p.label} ${v === "true" ? p.yes : p.no}`;
  else if (p) condition = `${p.label} = ${v.replace(/_/g, " ")}`;
  else condition = `${humanize(key).toLowerCase()} = ${v.replace(/_/g, " ")}`;
  return `If ${condition} → ${VERDICT_WORD[verdict] ?? String(verdict).toLowerCase()}`;
}
