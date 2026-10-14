import type { PoliciesResponse, PolicyTuple, PolicyView } from "./types";

export function findPolicy(policies: PoliciesResponse | null, policyId: string): PolicyView | undefined {
  return policies?.policies.find((p) => p.id === policyId || p.record_id === policyId);
}

export function policyName(policies: PoliciesResponse | null, policyId: string): string {
  const p = findPolicy(policies, policyId);
  return p ? p.product_name : policyId;
}

export function findTuple(
  policies: PoliciesResponse | null,
  policyId: string,
  tupleId: string | null | undefined
): PolicyTuple | undefined {
  if (!tupleId) return undefined;
  const p = findPolicy(policies, policyId);
  if (p) {
    const t = p.tuples.find((t) => t.id === tupleId);
    if (t) return t;
  }
  // Tuple ids are usually unique sandbox-wide (e.g. a clarification's
  // why_tuple_id may sit on a policy not named in the current call), so fall
  // back to a search across every policy on the account.
  for (const pol of policies?.policies ?? []) {
    const t = pol.tuples.find((t) => t.id === tupleId);
    if (t) return t;
  }
  return undefined;
}

/** First clause tuple for a policy_id among a list of candidate tuple ids. */
export function firstClause(
  policies: PoliciesResponse | null,
  policyId: string,
  tupleIds: string[]
): PolicyTuple | undefined {
  for (const id of tupleIds) {
    const t = findTuple(policies, policyId, id);
    if (t) return t;
  }
  return undefined;
}

export function clauseCitation(t: PolicyTuple | undefined, policyId: string): string {
  if (!t) return policyId;
  return `${policyId} ${t.section || t.id}`;
}
