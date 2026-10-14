// The Reply.text field is a server-rendered transcript that already contains
// everything (per-policy reasoning, raw clause ids, "Clauses:" lines, COB
// steps as text, alerts...). Verdict cards show a one-line, human reasoning
// pulled out of that transcript instead of the whole block, so the chat
// stays uncluttered; the verbatim clause quote for "show clause" always
// comes from the policies endpoint, never from this text.

const STOP_PATTERNS: RegExp[] = [
  /^Clauses:/,
  /^Filing deadline/,
  /^Documents required/,
  /^Readiness flags/,
  /^Who pays/,
  /^Disclosure issue/,
  /^One question/,
  /^Alert:/,
  /^Indicative only/,
  /^Request legalised copies/,
  /^\s*The pre-existing/,
  /^\s*Exception to this exclusion/,
  /^Not determinable/,
  /^Next step:/,
];

const POLICY_HEADER = /\(([A-Z][A-Z0-9-]+)\):/;

// A deterministic reply that is ordinary prose (an action outcome, a gated submission) rather
// than the per-policy transcript the cards parse; such text is shown to the user as-is.
export function isPlainTranscript(text: string): boolean {
  const lines = text.split("\n").map((l) => l.trim()).filter(Boolean);
  return lines.length > 0 && !lines.some((l) => POLICY_HEADER.test(l) || STOP_PATTERNS.some((p) => p.test(l)));
}

export function reasoningFor(text: string, policyId: string): string | null {
  const marker = `(${policyId}):`;
  const lines = text.split("\n");
  const idx = lines.findIndex((l) => l.includes(marker));
  if (idx === -1) return null;

  const afterColon = lines[idx].split(marker).slice(1).join(marker).trim();
  if (/^depends on one fact/i.test(afterColon)) {
    return afterColon.replace(/^depends on one fact\s*-\s*/i, "").replace(/\.$/, "").trim();
  }

  const out: string[] = [];
  for (let i = idx + 1; i < lines.length; i++) {
    const line = lines[i];
    if (line.trim() === "") break;
    if (STOP_PATTERNS.some((re) => re.test(line))) break;
    const m = line.match(POLICY_HEADER);
    if (m && m[1] !== policyId) break;
    out.push(line.trim());
  }
  // the backend's own template occasionally leaves a stray brace at a quote's
  // end (a known quirk of its f-string wording); drop it rather than show it
  return out.join(" ").trim().replace(/"\}+$/, '"').replace(/\}+$/, "") || null;
}

/** Strips the leading "{Name} (ID): Covered (indicative)." style preamble, for
 * when the one-liner itself still carries the verdict word. */
export function stripVerdictPreamble(line: string): string {
  return line.replace(/^(Covered|Not covered|Denied)\s*\(indicative\)\.?\s*(Indicative benefit:[^.]*\.)?\s*/i, "").trim();
}

/** The clarifier's own phrasing of the one verdict-changing question, when the
 * reply also decided other policies (clarifier.phrase's "One question before
 * I can answer: ..." line). Returns null for a pure-clarification turn, where
 * the whole reply text already *is* the question. */
export function extractClarificationLine(text: string): string | null {
  const line = text.split("\n").find((l) => l.startsWith("One question before I can answer:"));
  return line ? line.replace(/^One question before I can answer:\s*/, "").trim() : null;
}
