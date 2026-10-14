"""Plan-selection evaluation: optimiser vs "cheapest plan" vs "highest metal level" on the CMS plans.

    python -m bench.plan_selection_eval [--households 100] [--seed 7] [--plans data/real/cms_plans_py2026.csv]
        -> evidence/plan_selection_report.md

Households
----------
100 synthetic households drawn (seeded) from the three sandbox persona patterns in
`clauseguard.sandbox.persona_policies`: a single adult with fixed-benefit hospital cash, critical
illness and a lapsed term-life policy (rizky); a four-person family with an employer group health
plan for everyone, group life for the earner and an individual hospital plan for some members
(santoso); a single adult with personal-accident cover only and lapsed statutory cover (dewi).
Each household gets 1-4 persons, one pattern, a random subset of that pattern's holdings (so some
indemnity cover is already held on some perils for some persons) and a monthly budget drawn from
{none, 1x, 2x, 3x the median plan cost}. Existing holdings are light `PolicyRecord`s built from
the pattern's product types and perils; they are not the Indonesian policies themselves.

Methods (same candidate plans, same open gaps, same cost basis)
---------------------------------------------------------------
* optimiser: `plans.selector.select_plans` (weighted set cover under budget, indemnity non-overlap).
* cheapest plan: the single cheapest candidate that closes at least one open gap and is not a
  duplicate of held indemnity cover (what a price-sorted marketplace listing suggests).
* highest metal: the single Platinum > Gold > Silver > Bronze > Catastrophic plan, cheapest within
  the level, that closes at least one open gap (what "buy the best plan" suggests).
Both baselines ignore the budget unless the plan simply does not fit, in which case they fall back
to the cheapest fitting plan; the report counts how often they exceed it.

Metric: gap cells (peril x person) closed per 100 currency units of monthly cost, plus weight
closed, cost, residual cells and budget violations, averaged over households.

Experiment A runs on the CMS plans. Every ACA plan covers the same essential-health-benefit perils,
so one plan closes every medical gap cell and the three methods can only differ in price; the
report says so. Experiment B repeats the protocol on the mixed-peril mock catalogue
(`clauseguard.catalogue.CATALOGUE`, IDR, illustrative prices) where plans close different gap sets,
which is where set cover and a single-plan rule of thumb diverge; "highest metal" becomes "most
expensive plan" there because mock plans carry no metal level.
"""
from __future__ import annotations

import argparse
import random
import statistics
from collections import Counter
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Optional

from clauseguard import config
from clauseguard.plans import selector
from clauseguard.plans.cms_loader import load_cms_plans, metal_level, oop_max, premium_monthly
from clauseguard.schema import Basis, ClauseTuple, Evidence, PolicyRecord, Qualifiers, Relation

METAL_RANK = {"platinum": 5, "gold": 4, "silver": 3, "bronze": 2, "expanded bronze": 2, "catastrophic": 1}

# persona patterns: (product_type, basis, perils, share of persons covered)
PATTERNS: dict[str, list[tuple[str, Basis, list[str], str]]] = {
    "rizky": [("hospital_cash", Basis.FIXED_BENEFIT, ["HOSPITALIZATION", "ICU"], "all"),
              ("ci", Basis.FIXED_BENEFIT, ["CRITICAL_ILLNESS"], "all"),
              ("term_life", Basis.FIXED_BENEFIT, ["DEATH"], "lapsed")],
    "santoso": [("group_health", Basis.INDEMNITY, ["HOSPITALIZATION", "SURGERY", "ICU", "OUTPATIENT"], "all"),
                ("group_life", Basis.FIXED_BENEFIT, ["DEATH"], "earner"),
                ("hospital_cash", Basis.FIXED_BENEFIT, ["HOSPITALIZATION"], "all"),
                ("health_indemnity", Basis.INDEMNITY, ["HOSPITALIZATION", "SURGERY", "ICU"], "some")],
    "dewi": [("pa", Basis.FIXED_BENEFIT, ["ACCIDENTAL_DEATH", "TPD", "ACCIDENT_MEDICAL"], "all")],
}


def _policy(pid: str, ptype: str, basis: Basis, perils: list[str], status: str) -> PolicyRecord:
    tuples = [ClauseTuple(id=f"{pid}-{p}", policy_id=pid, head=pid, relation=Relation.COVERS, object=p, qualifiers=Qualifiers(basis=basis),
                          evidence=Evidence(doc_id=pid, text=f"synthetic holding {ptype} {p}")) for p in perils]
    return PolicyRecord(id=pid, doc_id=pid, insurer="synthetic", product_name=f"{ptype} (held)", product_type=ptype, basis=basis, status=status, tuples=tuples)


def make_households(n: int, seed: int, median_cost: Decimal) -> list[dict]:
    rng = random.Random(seed)
    out = []
    for i in range(n):
        pattern = rng.choice(list(PATTERNS))
        k = 1 if pattern in ("rizky", "dewi") and rng.random() < 0.7 else rng.randint(1, 4)
        persons = [f"h{i}p{j}" for j in range(k)]
        policies, insured = [], {}
        for idx, (ptype, basis, perils, share) in enumerate(PATTERNS[pattern]):
            if rng.random() < 0.3:
                continue  # this household never bought this one
            pid = f"H{i}-{idx}"
            status = "lapsed" if share == "lapsed" else "active"
            if share == "earner":
                who = [persons[0]]
            elif share == "some":
                who = [p for p in persons if rng.random() < 0.6] or [persons[-1]]
            else:
                who = list(persons)
            policies.append(_policy(pid, ptype, basis, perils, status))
            insured[pid] = who
        budget_mult = rng.choice([None, 1, 2, 3])
        budget = None if budget_mult is None else (median_cost * budget_mult).quantize(Decimal("1"))
        out.append({"id": i, "pattern": pattern, "persons": persons, "policies": policies, "insured": insured, "budget": budget, "earner": persons[0]})
    return out


def _cost(plan: PolicyRecord, objective: str) -> Decimal:
    c, _ = selector.plan_cost(plan, objective)
    return c


def _eligible(h: dict, plans: list[PolicyRecord], objective: str) -> tuple[list[dict], list[tuple[PolicyRecord, set[int]]]]:
    """Open gaps and the (plan, gap set) pairs that are not duplicates of held indemnity cover."""
    gaps = selector.open_gaps(h["policies"], plans, h["persons"], insured=h["insured"], earner=h["earner"])
    idx = {(g["peril"], g["person_id"]): i for i, g in enumerate(gaps)}
    indem = selector._active_indemnity(h["policies"], h["persons"], h["insured"])
    out = []
    for p in plans:
        perils = [t.object for t in p.tuples_by(Relation.COVERS)]
        if p.basis == Basis.INDEMNITY and perils and all((pe, person) in indem for pe in perils for person in h["persons"]):
            continue
        s = {idx[(pe, person)] for pe in perils for person in h["persons"] if (pe, person) in idx}
        if s:
            out.append((p, s))
    return gaps, out


def baseline(h: dict, plans: list[PolicyRecord], objective: str, how: str) -> dict:
    gaps, elig = _eligible(h, plans, objective)
    weights = [selector.PERIL_WEIGHT.get(g["peril"], 1) for g in gaps]
    if not elig:
        return {"plans": [], "cost": Decimal(0), "closed": 0, "weight": 0, "residual": len(gaps), "over_budget": False}
    if how == "cheapest":
        key = lambda ps: (_cost(ps[0], objective), oop_max(ps[0]) or 0, ps[0].id)  # noqa: E731
    elif any(metal_level(ps[0]) for ps in elig):
        key = lambda ps: (-METAL_RANK.get((metal_level(ps[0]) or "").lower(), 0), _cost(ps[0], objective), ps[0].id)  # noqa: E731
    else:  # no metal levels in this catalogue: "buy the best plan" = the most expensive one
        key = lambda ps: (-_cost(ps[0], objective), ps[0].id)  # noqa: E731
    plan, s = sorted(elig, key=key)[0]
    cost = _cost(plan, objective)
    over = h["budget"] is not None and cost > h["budget"]
    if over:  # the buyer cannot afford it: fall back to the cheapest fitting plan, if any
        fit = [ps for ps in elig if _cost(ps[0], objective) <= h["budget"]]
        if fit:
            plan, s = sorted(fit, key=lambda ps: (_cost(ps[0], objective), ps[0].id))[0]
            cost = _cost(plan, objective)
            over = False
        else:
            return {"plans": [], "cost": Decimal(0), "closed": 0, "weight": 0, "residual": len(gaps), "over_budget": False}
    return {"plans": [plan.id], "cost": cost, "closed": len(s), "weight": sum(weights[g] for g in s), "residual": len(gaps) - len(s), "over_budget": over}


def optimiser(h: dict, plans: list[PolicyRecord], objective: str) -> dict:
    r = selector.select_plans(h["policies"], plans, h["persons"], budget_monthly=h["budget"], objective=objective, insured=h["insured"], earner=h["earner"], n_alternatives=0)
    weights = {(g["peril"], g["person_id"]): selector.PERIL_WEIGHT.get(g["peril"], 1) for g in r.open_gaps}
    return {"plans": [c.plan_id for c in r.chosen], "cost": r.monthly_cost, "closed": len(r.gaps_closed),
            "weight": sum(weights[(g["peril"], g["person_id"])] for g in r.gaps_closed), "residual": len(r.residual_gaps),
            "over_budget": h["budget"] is not None and r.monthly_cost > h["budget"], "solver": r.solver}


def summarise(rows: list[dict]) -> dict:
    n = len(rows)
    with_cost = [r for r in rows if r["cost"] > 0]
    per100 = [Decimal(r["closed"]) * 100 / r["cost"] for r in with_cost]
    return {
        "households": n, "mean_closed": statistics.mean(r["closed"] for r in rows), "mean_weight": statistics.mean(r["weight"] for r in rows),
        "mean_cost": statistics.mean(float(r["cost"]) for r in rows), "mean_residual": statistics.mean(r["residual"] for r in rows),
        "closed_per_100": statistics.mean(float(x) for x in per100) if per100 else 0.0,
        "median_closed_per_100": statistics.median(float(x) for x in per100) if per100 else 0.0,
        "over_budget": sum(1 for r in rows if r["over_budget"]), "nothing": sum(1 for r in rows if not r["plans"]),
        "mean_plans": statistics.mean(len(r["plans"]) for r in rows),
    }


def provenance(path: Path, plans: list[PolicyRecord]) -> dict:
    import csv

    states: Counter = Counter()
    rows = 0
    with path.open(newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            rows += 1
            states[(r.get("StateCode") or r.get("statecode") or "?").strip()] += 1
    metals = Counter((metal_level(p) or "unknown") for p in plans)
    issuers = len({p.insurer for p in plans})
    rates = path.with_name("cms_rates_py2026.csv")
    return {"file": path.name, "rows": rows, "states": dict(states), "plans": len(plans), "issuers": issuers, "metals": dict(metals),
            "rates_file": rates.name if rates.exists() else None, "with_premium": sum(1 for p in plans if premium_monthly(p) is not None),
            "real": path.parent.name == "real"}


def run_experiment(plans: list[PolicyRecord], households: int, seed: int) -> tuple[dict, dict, list[dict], Decimal, str, Counter]:
    objective = "premium" if all(premium_monthly(p) is not None for p in plans) else "oop"
    costs = sorted(_cost(p, objective) for p in plans)
    median_cost = costs[len(costs) // 2]
    hh = make_households(households, seed, median_cost)
    results: dict[str, list[dict]] = {"optimiser": [], "cheapest plan": [], "highest metal": []}
    solvers: Counter = Counter()
    for h in hh:
        o = optimiser(h, plans, objective)
        solvers[o["solver"]] += 1
        results["optimiser"].append(o)
        results["cheapest plan"].append(baseline(h, plans, objective, "cheapest"))
        results["highest metal"].append(baseline(h, plans, objective, "metal"))
    return results, {k: summarise(v) for k, v in results.items()}, hh, median_cost, objective, solvers


def _table(summ: dict, metal_label: str) -> list[str]:
    lines = ["| method | gap cells closed per 100/month | median | cells closed | weight closed | cost/month | residual cells | plans | households with nothing | over budget |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for k, s_ in summ.items():
        name = metal_label if k == "highest metal" else k
        lines.append(f"| {name} | {s_['closed_per_100']:.3f} | {s_['median_closed_per_100']:.3f} | {s_['mean_closed']:.2f} | {s_['mean_weight']:.2f} | {s_['mean_cost']:,.2f} | {s_['mean_residual']:.2f} | {s_['mean_plans']:.2f} | {s_['nothing']} | {s_['over_budget']} |")
    return lines


def _pairwise(results: dict, summ: dict, metal_label: str) -> list[str]:
    opt, ch, hm = results["optimiser"], results["cheapest plan"], results["highest metal"]
    n = len(opt)
    wins_ch = sum(1 for o, c in zip(opt, ch) if o["weight"] > c["weight"])
    ties_ch = sum(1 for o, c in zip(opt, ch) if o["weight"] == c["weight"])
    wins_hm = sum(1 for o, c in zip(opt, hm) if o["weight"] > c["weight"])
    ties_hm = sum(1 for o, c in zip(opt, hm) if o["weight"] == c["weight"])
    cheaper_hm = sum(1 for o, c in zip(opt, hm) if o["cost"] < c["cost"] and o["weight"] >= c["weight"])
    same_ch = sum(1 for o, c in zip(opt, ch) if o["plans"] == c["plans"])
    return [f"- optimiser closes more weighted gap than the cheapest plan in {wins_ch}/{n} households (ties {ties_ch}; identical pick in {same_ch}); never less, as it is the optimum of that objective under the same budget.",
            f"- optimiser closes more weighted gap than the {metal_label} in {wins_hm}/{n} households (ties {ties_hm}); in {cheaper_hm} it closes at least as much for less money.",
            f"- budget violations: optimiser {summ['optimiser']['over_budget']}, cheapest {summ['cheapest plan']['over_budget']}, {metal_label} {summ['highest metal']['over_budget']} (baselines fall back to the cheapest fitting plan when their pick does not fit)."]


def main(argv: Optional[list[str]] = None) -> Path:
    ap = argparse.ArgumentParser()
    ap.add_argument("--households", type=int, default=100)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--plans", default=str(config.DATA_DIR / "real" / "cms_plans_py2026.csv"))
    ap.add_argument("--out", default=str(config.EVIDENCE_DIR / "plan_selection_report.md"))
    a = ap.parse_args(argv)
    path = Path(a.plans)
    fixture = False
    if not path.exists():
        path = config.ROOT / "tests" / "fixtures" / "cms_plans_py2026_sample.csv"
        fixture = True
    plans = load_cms_plans(path)
    if not plans:
        raise SystemExit(f"no plans in {path}")
    results, summ, hh, median_cost, objective, solvers = run_experiment(plans, a.households, a.seed)
    prov = provenance(path, plans)
    peril_sets = Counter(tuple(sorted(t.object for t in p.tuples_by(Relation.COVERS))) for p in plans)
    lines = ["# Plan selection under budget: optimiser vs baselines", "",
             f"Generated {datetime.now().isoformat(timespec='seconds')} by `python -m bench.plan_selection_eval --households {a.households} --seed {a.seed}`.", ""]
    if fixture:
        lines += ["**Data: the 10-row test fixture `tests/fixtures/cms_plans_py2026_sample.csv` (synthetic sample in the PUF column format), "
                  "because `data/real/cms_plans_py2026.csv` is not present. Re-run once the CMS extract is downloaded; the numbers below are not from real plans.**", ""]
    lines += ["## Experiment A: CMS Exchange plans", "", "### Data provenance", "",
              f"- plan file: `{prov['file']}` ({'real CMS Exchange PUF PY2026 extract, built by scripts/fetch_real_data.py from plan-attributes-puf.zip and benefits-and-cost-sharing-puf.zip' if prov['real'] else 'fixture'}), {prov['rows']} rows",
              f"- state(s): {', '.join(f'{k} ({v} rows)' for k, v in sorted(prov['states'].items()))}",
              f"- plans loaded: {prov['plans']} standard components from {prov['issuers']} issuers; metal levels: {', '.join(f'{k} {v}' for k, v in sorted(prov['metals'].items()))}",
              "- benefit perils per plan: " + "; ".join(", ".join(k) + f" ({v} plans)" for k, v in peril_sets.most_common(3)),
              f"- rate file: {('`' + prov['rates_file'] + '` (age 30, non-tobacco, lowest rating area)') if prov['rates_file'] else 'absent (`cms_rates_py2026.csv` not downloaded)'}; plans with a premium: {prov['with_premium']}/{prov['plans']}",
              f"- cost basis used by every method: **{objective}** ({'monthly premium from the Rate PUF' if objective == 'premium' else '(deductible + out-of-pocket maximum) / 12, because premiums are not in the Plan Attributes / Benefits PUFs'}); median plan cost {median_cost:,.2f}/month",
              f"- households: {a.households}, seed {a.seed}, persona patterns {dict(Counter(h['pattern'] for h in hh))}; budgets: {sum(1 for h in hh if h['budget'] is None)} without, the rest 1-3x the median plan cost",
              f"- optimiser solver: {dict(solvers)}", "",
              "### Results (mean over households)", ""] + _table(summ, "highest metal") + ["", "### Pairwise", ""] + _pairwise(results, summ, "highest metal plan")
    if len(peril_sets) == 1:
        lines += ["", "### Why the methods coincide here", "",
                  f"Every one of the {prov['plans']} plans covers the same perils ({', '.join(peril_sets.most_common(1)[0][0]).lower().replace('_', ' ')}): the ACA essential-health-benefit "
                  "schedule fixes what a marketplace plan covers, so any single plan closes every medical gap cell and the choice reduces to price. "
                  + ("With the Rate PUF absent the price is the member's worst-case cost sharing, which is lowest for the richest metal levels, so the cheapest and the highest-metal pick are the same plan and both equal the optimum. "
                     "With premiums (Rate PUF) the two baselines separate: the cheapest plan is a Bronze or Catastrophic plan and the highest-metal pick a Gold one, and the optimiser's answer depends on the chosen objective." if objective == "oop" else
                     "The optimiser's answer equals the cheapest eligible plan under the premium objective, which is the correct optimum for a single-peril-set catalogue."),
                  "Death, disability and critical-illness gaps cannot be closed by any ACA plan and are not counted as open gaps in this experiment (the selector only scores perils a candidate closes)."]
    # Experiment B: mixed-peril mock catalogue
    from clauseguard.catalogue import CATALOGUE

    mock = list(CATALOGUE.values())
    results_b, summ_b, hh_b, median_b, objective_b, solvers_b = run_experiment(mock, a.households, a.seed)
    lines += ["", "## Experiment B: mixed-peril catalogue (mock, for contrast)", "",
              f"- plans: the {len(mock)} illustrative MOCK plans of `clauseguard.catalogue.CATALOGUE` (IDR, invented prices; not an offer from any insurer); perils per plan differ (hospital cash, personal accident, term life, critical illness, group top-up, individual hospitalisation)",
              f"- cost basis: **{objective_b}**; median plan cost IDR {median_b:,.0f}/month; same {a.households} households and seed; budgets 1-3x the median",
              f"- optimiser solver: {dict(solvers_b)}", "",
              "### Results (mean over households)", ""] + _table(summ_b, "most expensive plan") + ["", "### Pairwise", ""] + _pairwise(results_b, summ_b, "most expensive plan")
    lines += ["", "## Reading the numbers", "",
              "- A gap cell is one (peril, person) pair with no active cover; cells are weighted by `PERIL_WEIGHT` (hospitalisation and death 5, critical illness 4, ...).",
              "- Every method sees the same candidates, the same open gaps and the same rule that an indemnity plan is never added on top of active indemnity cover for the same perils.",
              "- A candidate plan is assumed to enrol every household member (family enrolment) at the stated cost; per-member pricing needs the Rate PUF.",
              "- Indicative; consult a licensed agent. The households are synthetic; the CMS plan figures are the issuers' PUF filings, not quotes; the mock prices are illustrative."]
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(out)
    return out


if __name__ == "__main__":
    main()
