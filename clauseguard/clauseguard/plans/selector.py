"""Plan Selection under Budget: weighted set cover over open cover gaps.

Inputs are typed `PolicyRecord`s (the household's current policies and the candidate plans) and
the household's persons. Open gaps are the (peril, person) cells that `portfolio.gap_overlap`
reports as uncovered by any active policy. The selector picks a set of candidate plans that
closes as much weighted gap as possible within the budget, then as cheaply, then with as few
plans, then with the lowest out-of-pocket maximum. No language model is involved; the result is
deterministic for the same inputs.

Formulation
-----------
Gaps g in G with weight w_g (peril priority, `PERIL_WEIGHT`), candidate plans j in P with
monthly cost c_j, out-of-pocket maximum m_j and the gap set S_j they close, budget B (monthly):

    maximise   sum_g w_g y_g                                  (lexicographic, first)
    then minimise sum_j c_j x_j, then sum_j x_j, then sum_j m_j x_j
    subject to y_g <= sum_{j : g in S_j} x_j        for all g   (a gap counts once it is covered)
               sum_j c_j x_j <= B                              (budget, when given)
               sum_{j indemnity : g in S_j} x_j <= 1          for all g   (chosen indemnity plans never overlap)
               x_j, y_g in {0, 1}

The lexicographic order is folded into one linear objective with separating scale factors, so a
single mixed-integer programme (scipy.optimize.milp, HiGHS) returns the optimum. Without scipy
the same objective is solved exactly by enumerating all plan subsets of size <= 3 and extended
greedily when more plans are needed. Alternatives are the two next-best solutions found by
re-solving with a "no-good" cut (sum_{j in S*} x_j <= |S*| - 1) excluding each earlier answer.

Cost c_j: `objective="premium"` uses the plan's monthly premium (`DEFINES PREMIUM`, Rate PUF);
`objective="oop"` - or a premium-less catalogue - uses (deductible + out-of-pocket maximum) / 12,
the member's worst-case annual cost sharing spread over the year. A budget is always compared
with the same c_j, which the rationale names.

Constraints that are not in the MILP but applied when the candidates are prepared:
* an INDEMNITY plan is never added when every peril it covers is already indemnified for every
  person by an active indemnity policy (indemnity cover does not stack; such a plan closes no gap);
* candidates that close no open gap are dropped (set cover never pays for duplicate cover);
* a plan that carries a `CONDITIONED_ON GROUP_BASE_PLAN` tuple is eligible only when an active
  group indemnity policy is held.
"""
from __future__ import annotations

from decimal import Decimal
from itertools import combinations
from typing import Optional

from pydantic import Field

from .. import portfolio
from ..schema import Basis, EventCode, PolicyRecord, Relation, Strict
from .cms_loader import deductible, metal_level, oop_max, premium_monthly

AGENT_CAVEAT = "Indicative; consult a licensed agent before buying."
EARNER_PERILS = ("DEATH", "TPD", "TEMPORARY_DISABILITY")
PERIL_WEIGHT: dict[str, int] = {
    "HOSPITALIZATION": 5, "DEATH": 5, "CRITICAL_ILLNESS": 4, "ACCIDENTAL_DEATH": 3, "ACCIDENT_MEDICAL": 3,
    "TPD": 2, "TEMPORARY_DISABILITY": 2, "SURGERY": 2, "ICU": 2, "OUTPATIENT": 2, "PREGNANCY": 1, "DENTAL": 1,
}
ENUM_LIMIT = 3  # exact enumeration depth of the scipy-free fallback
CANDIDATE_CAP = 60  # fallback: cheapest plans kept after dominance pruning


class PlanChoice(Strict):
    plan_id: str
    product_name: str
    insurer: str
    monthly_cost: Decimal
    cost_basis: str = Field(pattern=r"^(premium|oop|unknown)$")
    premium_monthly: Optional[Decimal] = None
    deductible: Optional[Decimal] = None
    oop_max: Optional[Decimal] = None
    metal_level: Optional[str] = None
    closes: list[dict] = Field(default_factory=list)  # {"peril", "person_id"}
    rationale: str
    fields_used: list[str] = Field(default_factory=list)  # PUF columns / tuple ids behind the numbers
    caveats: list[str] = Field(default_factory=list)


class Alternative(Strict):
    plan_ids: list[str]
    monthly_cost: Decimal
    gaps_closed: int
    weight_closed: int
    note: str


class SelectionResult(Strict):
    chosen: list[PlanChoice]
    perils_closed: list[str]
    gaps_closed: list[dict]
    residual_gaps: list[dict]
    open_gaps: list[dict]
    monthly_cost: Decimal
    cost_basis: str
    budget_monthly: Optional[Decimal] = None
    objective: str
    solver: str
    alternatives: list[Alternative] = Field(default_factory=list)
    excluded: list[dict] = Field(default_factory=list)  # {"plan_id", "reason"}
    caveats: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------- gaps and candidates
def _perils(policies: list[PolicyRecord], candidates: list[PolicyRecord]) -> list[EventCode]:
    out: list[EventCode] = []
    for p in list(candidates) + list(policies):
        for t in p.tuples_by(Relation.COVERS):
            try:
                e = EventCode(t.object)
            except ValueError:
                continue
            if e not in out:
                out.append(e)
    return out


def open_gaps(current_policies: list[PolicyRecord], candidate_plans: list[PolicyRecord], persons: list[str],
              insured: Optional[dict[str, list[str]]] = None, earner: Optional[str] = None) -> list[dict]:
    """(peril, person) cells with no active cover, restricted to perils some candidate closes.
    Death and income-protection gaps are kept only for `earner` (or a one-person household)."""
    perils = _perils(current_policies, candidate_plans)
    rep = portfolio.gap_overlap(current_policies, persons, perils, insured=insured)
    closable = {t.object for c in candidate_plans for t in c.tuples_by(Relation.COVERS)}
    gaps: list[dict] = []
    for g in rep["gaps"]:
        if g["peril"] not in closable:
            continue
        if g["peril"] in EARNER_PERILS:
            if earner is not None and g["person_id"] != earner:
                continue
            if earner is None and len(persons) != 1:
                continue
        gaps.append({"peril": g["peril"], "person_id": g["person_id"]})
    return sorted(gaps, key=lambda g: (g["person_id"], g["peril"]))


def _active_indemnity(current_policies: list[PolicyRecord], persons: list[str], insured: Optional[dict[str, list[str]]]) -> set[tuple[str, str]]:
    """(peril, person) pairs indemnified by an active private indemnity policy."""
    insured = insured or {}
    out: set[tuple[str, str]] = set()
    for p in current_policies:
        if p.status not in portfolio.ACTIVE_STATUSES or portfolio.is_statutory(p):
            continue
        for t in p.tuples_by(Relation.COVERS):
            if portfolio.cell_basis(t, p) == Basis.INDEMNITY:
                for person in insured.get(p.id, persons):
                    out.add((t.object, person))
    return out


def _has_group_base(current_policies: list[PolicyRecord]) -> bool:
    return any(p.status in portfolio.ACTIVE_STATUSES and portfolio.is_group(p) and p.basis == Basis.INDEMNITY and p.product_type.startswith("group_health")
               for p in current_policies)


def plan_cost(plan: PolicyRecord, objective: str) -> tuple[Optional[Decimal], str]:
    """(monthly cost, basis). 'premium' falls back to 'oop' when the plan has no premium, and to
    (0, 'unknown') when it has neither premium nor cost sharing on record (set cover then only
    minimises the number of plans and a budget cannot be checked, which the result says)."""
    prem = premium_monthly(plan)
    if objective == "premium" and prem is not None:
        return prem, "premium"
    d, m = deductible(plan), oop_max(plan)
    if d is None and m is None:
        return (prem, "premium") if prem is not None else (Decimal(0), "unknown")
    return ((d or Decimal(0)) + (m or Decimal(0))) / Decimal(12), "oop"


# --------------------------------------------------------------------------- solvers
def _score(sets: list[set[int]], costs: list[Decimal], oops: list[Decimal], weights: list[int], chosen: tuple[int, ...]) -> tuple:
    """Lexicographic key (higher weight closed, lower cost, fewer plans, lower OOP) as a sortable tuple."""
    covered: set[int] = set()
    for j in chosen:
        covered |= sets[j]
    return (-sum(weights[g] for g in covered), sum(costs[j] for j in chosen), len(chosen), sum(oops[j] for j in chosen), chosen)


def _solve_milp(sets, costs, oops, weights, budget, n_gaps, indem: list[bool], exclude: list[tuple[int, ...]]) -> Optional[tuple[int, ...]]:
    try:
        import numpy as np
        from scipy.optimize import Bounds, LinearConstraint, milp
    except Exception:  # noqa: BLE001
        return None
    n = len(sets)
    if n == 0:
        return ()
    # variables: x_0..x_{n-1}, y_0..y_{n_gaps-1}
    cost_scale = max([float(c) for c in costs] + [1.0])
    oop_scale = max([float(o) for o in oops] + [1.0])
    k_cost = 1.0 / (cost_scale * n + 1.0)  # cost term < 1 weight unit
    k_count = k_cost / (n + 1.0)
    k_oop = k_count / (oop_scale * n + 1.0)
    c = np.zeros(n + n_gaps)
    for j in range(n):
        c[j] = k_cost * float(costs[j]) + k_count + k_oop * float(oops[j])
    for g in range(n_gaps):
        c[n + g] = -float(weights[g])
    rows, lb, ub = [], [], []
    for g in range(n_gaps):
        row = np.zeros(n + n_gaps)
        row[n + g] = 1.0
        for j in range(n):
            if g in sets[j]:
                row[j] = -1.0
        rows.append(row)
        lb.append(-np.inf)
        ub.append(0.0)
    for g in range(n_gaps):  # indemnity plans do not stack: at most one chosen indemnity plan per gap
        js = [j for j in range(n) if indem[j] and g in sets[j]]
        if len(js) > 1:
            row = np.zeros(n + n_gaps)
            for j in js:
                row[j] = 1.0
            rows.append(row)
            lb.append(-np.inf)
            ub.append(1.0)
    if budget is not None:
        row = np.zeros(n + n_gaps)
        for j in range(n):
            row[j] = float(costs[j])
        rows.append(row)
        lb.append(-np.inf)
        ub.append(float(budget))
    for ex in exclude:
        row = np.zeros(n + n_gaps)
        for j in ex:
            row[j] = 1.0
        rows.append(row)
        lb.append(-np.inf)
        ub.append(len(ex) - 1.0)
    cons = LinearConstraint(np.array(rows), np.array(lb), np.array(ub)) if rows else []
    res = milp(c, constraints=cons, integrality=np.ones(n + n_gaps), bounds=Bounds(0, 1), options={"disp": False})
    if res.x is None:
        return None
    return tuple(j for j in range(n) if res.x[j] > 0.5)


def _indemnity_overlap(sets: list[set[int]], indem: list[bool], combo) -> bool:
    seen: set[int] = set()
    for j in combo:
        if indem[j]:
            if seen & sets[j]:
                return True
            seen |= sets[j]
    return False


def _solve_enum(sets, costs, oops, weights, budget, indem: list[bool], exclude: list[tuple[int, ...]]) -> tuple[int, ...]:
    """Exact over subsets of size <= ENUM_LIMIT of the pruned candidates, then greedy extension."""
    n = len(sets)
    if n == 0:
        return ()
    order = sorted(range(n), key=lambda j: (costs[j], oops[j], j))
    keep: list[int] = []
    seen_sets: dict[frozenset, int] = {}
    for j in order:  # dominance: identical gap sets keep the cheapest
        fs = frozenset(sets[j])
        if fs in seen_sets:
            continue
        seen_sets[fs] = j
        keep.append(j)
    keep = keep[:CANDIDATE_CAP]
    banned = {tuple(sorted(e)) for e in exclude}
    best: Optional[tuple] = None
    for r in range(0, min(ENUM_LIMIT, len(keep)) + 1):
        for combo in combinations(keep, r):
            if budget is not None and sum(costs[j] for j in combo) > budget:
                continue
            if tuple(sorted(combo)) in banned or _indemnity_overlap(sets, indem, combo):
                continue
            key = _score(sets, costs, oops, weights, tuple(sorted(combo)))
            if best is None or key < best:
                best = key
    chosen = list(best[-1]) if best else []
    while True:  # greedy extension when more than ENUM_LIMIT plans are useful
        covered = set().union(*[sets[j] for j in chosen]) if chosen else set()
        spent = sum(costs[j] for j in chosen)
        cands = []
        for j in keep:
            if j in chosen:
                continue
            gain = sum(weights[g] for g in sets[j] - covered)
            if gain <= 0 or (budget is not None and spent + costs[j] > budget) or _indemnity_overlap(sets, indem, chosen + [j]):
                continue
            cands.append((-gain, costs[j], oops[j], j))
        if not cands:
            break
        cands.sort()
        nxt = cands[0][3]
        if tuple(sorted(chosen + [nxt])) in banned:
            break
        chosen.append(nxt)
    return tuple(sorted(chosen))


# --------------------------------------------------------------------------- public API
def select_plans(current_policies: list[PolicyRecord], candidate_plans: list[PolicyRecord], persons: list[str],
                 budget_monthly: Optional[Decimal | int | float] = None, objective: str = "premium", *,
                 insured: Optional[dict[str, list[str]]] = None, earner: Optional[str] = None,
                 n_alternatives: int = 2, use_milp: Optional[bool] = None) -> SelectionResult:
    """Choose candidate plans that close the household's open gaps within `budget_monthly`.

    `objective` is "premium" (monthly premium) or "oop" (deductible + out-of-pocket maximum, per
    month); a premium-less catalogue is costed as "oop" whatever is asked. `insured` maps a
    current policy id to the persons it covers (default: everyone); `earner` is the person who
    receives death / income-protection suggestions. `use_milp=None` picks scipy when installed.
    """
    persons = list(persons)
    gaps = open_gaps(current_policies, candidate_plans, persons, insured=insured, earner=earner)
    return select_from_gaps(gaps, candidate_plans, persons=persons, indemnified=_active_indemnity(current_policies, persons, insured),
                            group_base=_has_group_base(current_policies), budget_monthly=budget_monthly, objective=objective,
                            n_alternatives=n_alternatives, use_milp=use_milp)


def select_from_gaps(gaps: list[dict], candidate_plans: list[PolicyRecord], *, persons: Optional[list[str]] = None,
                     indemnified: Optional[set[tuple[str, str]]] = None, group_base: bool = False,
                     budget_monthly: Optional[Decimal | int | float] = None, objective: str = "premium",
                     n_alternatives: int = 2, use_milp: Optional[bool] = None) -> SelectionResult:
    """Same optimisation from an already computed gap list (`{"peril", "person_id"}` cells, e.g. a
    `gap_analysis` report), the (peril, person) pairs an active private indemnity policy already
    covers, and whether an employer group health plan is held."""
    if objective not in ("premium", "oop"):
        raise ValueError("objective must be 'premium' or 'oop'")
    budget = Decimal(str(budget_monthly)) if budget_monthly is not None else None
    indemnified = set(indemnified or set())
    gaps = sorted(({"peril": g["peril"], "person_id": g["person_id"]} for g in gaps), key=lambda g: (g["person_id"], g["peril"]))
    persons = list(persons) if persons else sorted({g["person_id"] for g in gaps} | {p for _, p in indemnified})
    gap_index = {(g["peril"], g["person_id"]): i for i, g in enumerate(gaps)}

    excluded: list[dict] = []
    cands: list[PolicyRecord] = []
    sets: list[set[int]] = []
    costs: list[Decimal] = []
    oops: list[Decimal] = []
    indem: list[bool] = []
    bases: set[str] = set()
    for plan in sorted(candidate_plans, key=lambda p: p.id):
        perils = [t.object for t in plan.tuples_by(Relation.COVERS)]
        if any(t.relation == Relation.CONDITIONED_ON and t.object == "GROUP_BASE_PLAN" for t in plan.tuples) and not group_base:
            excluded.append({"plan_id": plan.id, "reason": "requires an active employer group health plan"})
            continue
        if plan.basis == Basis.INDEMNITY and perils and all((pe, person) in indemnified for pe in perils for person in persons):
            excluded.append({"plan_id": plan.id, "reason": "indemnity plan would only duplicate active indemnity cover on the same perils"})
            continue
        closes = {gap_index[(pe, person)] for pe in perils for person in persons if (pe, person) in gap_index}
        if not closes:
            excluded.append({"plan_id": plan.id, "reason": "closes no open gap"})
            continue
        cost, basis = plan_cost(plan, objective)
        cands.append(plan)
        sets.append(closes)
        costs.append(cost)
        oops.append(oop_max(plan) or Decimal(0))
        bases.add(basis)
        indem.append(plan.basis == Basis.INDEMNITY)
    if bases == {"unknown"}:
        cost_basis = "unknown"
    elif bases == {"oop"} or objective == "oop":
        cost_basis = "oop"
    else:
        cost_basis = "premium" if bases == {"premium"} else "mixed"
    weights = [PERIL_WEIGHT.get(g["peril"], 1) for g in gaps]

    solver = "none"
    solutions: list[tuple[int, ...]] = []
    want_milp = use_milp if use_milp is not None else True
    for _ in range(1 + n_alternatives):
        sol: Optional[tuple[int, ...]] = None
        if want_milp:
            sol = _solve_milp(sets, costs, oops, weights, budget, len(gaps), indem, solutions)
            if sol is not None:
                solver = "scipy.optimize.milp"
        if sol is None:
            sol = _solve_enum(sets, costs, oops, weights, budget, indem, solutions)
            solver = "enumeration<=3+greedy" if solver == "none" else solver
        if not sol and solutions:
            break
        if sol in solutions:
            break
        solutions.append(sol)
        if not sol:
            break

    best = solutions[0] if solutions else ()
    chosen: list[PlanChoice] = []
    closed_idx: set[int] = set()
    for j in best:
        plan = cands[j]
        new = sorted(sets[j] - closed_idx)
        closed_idx |= sets[j]
        chosen.append(_choice(plan, [gaps[g] for g in new], costs[j], "oop" if cost_basis == "oop" else plan_cost(plan, objective)[1]))
    chosen.sort(key=lambda c: (-sum(PERIL_WEIGHT.get(x["peril"], 1) for x in c.closes), c.monthly_cost, c.plan_id))
    alternatives: list[Alternative] = []
    for sol in solutions[1:]:
        cov = set().union(*[sets[j] for j in sol]) if sol else set()
        alternatives.append(Alternative(
            plan_ids=[cands[j].id for j in sol], monthly_cost=sum((costs[j] for j in sol), Decimal(0)), gaps_closed=len(cov),
            weight_closed=sum(weights[g] for g in cov),
            note="next-best feasible set under the same objective (no-good cut on the chosen set)"))
    residual = [g for i, g in enumerate(gaps) if i not in closed_idx]
    caveats = [AGENT_CAVEAT]
    if cost_basis == "oop":
        caveats.append("No premium on record for these plans: cost is (deductible + out-of-pocket maximum) / 12, the member's worst-case annual cost sharing per month, and the budget is compared with that figure.")
    if cost_basis == "unknown":
        caveats.append("No premium or cost-sharing figures on record for these plans: the selection minimises the number of plans only and the budget could not be checked; ask the insurer for a quotation.")
    if cost_basis == "mixed":
        caveats.append("Some candidates have no premium on record and are costed by (deductible + out-of-pocket maximum) / 12; the totals mix the two.")
    if budget is not None and residual and any(sets[j] & {gaps.index(g) for g in residual} for j in range(len(cands))):
        caveats.append(f"Gaps remain that a plan outside the budget of {budget:,.2f}/month would close.")
    return SelectionResult(
        chosen=chosen, perils_closed=sorted({g["peril"] for i, g in enumerate(gaps) if i in closed_idx}),
        gaps_closed=[gaps[i] for i in sorted(closed_idx)], residual_gaps=residual, open_gaps=gaps,
        monthly_cost=sum((c.monthly_cost for c in chosen), Decimal(0)), cost_basis=cost_basis, budget_monthly=budget,
        objective=objective, solver=solver, alternatives=alternatives, excluded=excluded, caveats=caveats,
    )


def _choice(plan: PolicyRecord, closes: list[dict], cost: Decimal, basis: str) -> PlanChoice:
    perils = sorted({g["peril"] for g in closes})
    persons = sorted({g["person_id"] for g in closes})
    prem, d, m, metal = premium_monthly(plan), deductible(plan), oop_max(plan), metal_level(plan)
    fields: list[str] = []
    for t in plan.tuples:
        if t.relation == Relation.COVERS and t.object in perils:
            fields.append(f"{t.id}: {t.evidence.text}")
        elif t.relation == Relation.DEFINES and t.object in ("PREMIUM", "MOCK_PREMIUM", "OOP_MAX", "DEDUCTIBLE", "METAL_LEVEL"):
            fields.append(f"{t.id}: {t.evidence.text}")
    why = f"Closes open gaps for {', '.join(p.lower().replace('_', ' ') for p in perils)} ({', '.join(persons)})."
    if basis == "premium" and prem is not None:
        why += f" Monthly premium {plan.currency} {prem:,.2f}."
    elif basis == "unknown":
        why += " Premium not stated in the extracted document; cost treated as unknown."
    else:
        why += f" Costed at {plan.currency} {cost:,.2f}/month = (deductible {d or 0:,.0f} + out-of-pocket maximum {m or 0:,.0f}) / 12; no premium on record."
    if metal:
        why += f" Metal level {metal}."
    if d is not None or m is not None:
        why += f" Member cost sharing: deductible {plan.currency} {d or 0:,.0f}, out-of-pocket maximum {plan.currency} {m or 0:,.0f} per year."
    caveats = [AGENT_CAVEAT]
    if plan.basis == Basis.INDEMNITY:
        caveats.append("Indemnity cover does not stack: it pays only what other cover leaves uncovered.")
    return PlanChoice(plan_id=plan.id, product_name=plan.product_name, insurer=plan.insurer, monthly_cost=cost, cost_basis=basis,
                      premium_monthly=prem, deductible=d, oop_max=m, metal_level=metal, closes=closes, rationale=why,
                      fields_used=fields[:40], caveats=caveats)
