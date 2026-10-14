import type { PolicyTuple } from "./types";
import { titleCase } from "./format";

/**
 * Groups a policy's raw clause tuples into plain-language sections for display.
 *
 * The backend returns one tuple per extracted rule (one policy commonly has several
 * COVERS tuples for the same peril — e.g. a partner-facility clause and a separate
 * emergency clause for "Hospitalization" — plus exclusions, conditions and document
 * requirements as separate relation types). Rendering tuples one-by-one in list order
 * repeats the same peril name, surfaces raw object codes like "COSMETIC" with no
 * context, and buries the document checklist inside an unrelated line. This groups by
 * relation and merges same-peril entries so the panel reads as a short, labeled summary
 * instead of a flat clause dump.
 */

export interface ClauseGroupItem {
  label: string;
  detail?: string;
  tupleIds: string[];
}

export interface ClauseGroup {
  heading: string;
  items: ClauseGroupItem[];
}

const COVERS_LIKE = new Set(["COVERS", "PAYS", "PERMITS", "HAS_RIDER"]);
const EXCLUDES_LIKE = new Set(["EXCLUDES", "TERMINATES_IF"]);
const CONDITION_LIKE = new Set(["CONDITIONED_ON", "HAS_PERIOD"]);

function readableObject(object: string): string {
  return titleCase(object) || object;
}

/** A tuple's `summary` is only worth showing if it adds a number or condition beyond the object name. */
function isInformativeSummary(summary: string, object: string): boolean {
  if (!summary) return false;
  const low = summary.toLowerCase();
  if (low.includes("not stated") || low.includes("not specified")) return false;
  return low !== readableObject(object).toLowerCase();
}

export function groupPolicyTuples(tuples: PolicyTuple[]): ClauseGroup[] {
  const covered = new Map<string, ClauseGroupItem>();
  const excluded = new Map<string, ClauseGroupItem>();
  const conditions: ClauseGroupItem[] = [];
  const documents = new Set<string>();
  const documentTupleIds: string[] = [];
  const other: ClauseGroupItem[] = [];

  for (const t of tuples) {
    if (t.relation === "REQUIRES_DOCUMENT") {
      const docs = t.object.split(/[,/]| and /i).map((d) => titleCase(d.trim())).filter(Boolean);
      docs.forEach((d) => documents.add(d));
      documentTupleIds.push(t.id);
      continue;
    }
    if (COVERS_LIKE.has(t.relation)) {
      const key = t.object;
      const label = readableObject(t.object);
      const existing = covered.get(key);
      if (existing) {
        existing.tupleIds.push(t.id);
      } else {
        covered.set(key, {
          label,
          detail: isInformativeSummary(t.summary, t.object) ? t.summary : undefined,
          tupleIds: [t.id],
        });
      }
      continue;
    }
    if (EXCLUDES_LIKE.has(t.relation)) {
      const key = t.object;
      const label = `Not covered: ${readableObject(t.object)}`;
      const existing = excluded.get(key);
      if (existing) {
        existing.tupleIds.push(t.id);
      } else {
        excluded.set(key, { label, tupleIds: [t.id] });
      }
      continue;
    }
    if (CONDITION_LIKE.has(t.relation)) {
      conditions.push({
        label: `Requires: ${readableObject(t.object)}`,
        detail: isInformativeSummary(t.summary, t.object) ? t.summary : undefined,
        tupleIds: [t.id],
      });
      continue;
    }
    other.push({
      label: readableObject(t.object),
      detail: isInformativeSummary(t.summary, t.object) ? t.summary : undefined,
      tupleIds: [t.id],
    });
  }

  const groups: ClauseGroup[] = [];
  if (covered.size) groups.push({ heading: "Covered", items: Array.from(covered.values()) });
  if (excluded.size) groups.push({ heading: "Not covered", items: Array.from(excluded.values()) });
  if (conditions.length) groups.push({ heading: "Conditions", items: conditions });
  if (documents.size) {
    groups.push({
      heading: "Documents needed to claim",
      items: [{ label: Array.from(documents).join(", "), tupleIds: documentTupleIds }],
    });
  }
  if (other.length) groups.push({ heading: "Other terms", items: other });
  return groups;
}
