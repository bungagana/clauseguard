"""Evaluation of the claim allocation optimizer on real plan terms.

Usage: python -m bench.allocation_eval [--households 500] [--seed 20261011] [--plans 200] [--out evidence/allocation_report.md]

Three studies, all deterministic (seeded), no language model:

1. Persona demo cases: the three sandbox claims (Rizky dengue, Santoso/Aditya asthma, Dewi traffic
   accident) on the persona policies of `clauseguard/sandbox/persona_policies.py`, whose tuples
   quote real public wordings (Sompo/Roojai HCP, Astra HCP rider, Astra Flexi Life, Chubb PA) or
   sandbox wordings marked "(mock)". Reported step by step with clause ids.
2. Persona households (rule pack ID): households holding 2-3 of the persona hospitalisation
   covers (group plan, individual plan, BPJS Kesehatan, the two hospital-cash plans) with sampled
   illness admissions. Plan terms are the persona tuples; bill amounts, days and facility are
   sampled from the distribution stated in the report.
3. CMS households (rule pack GENERIC): PolicyRecords built by `clauseguard.plans.cms_loader` from
   `data/real/cms_plans_py2026.csv` (CMS Marketplace PUF plan year 2026, one-state extract); the
   first `--plans` plans with inpatient cover, households of 2-3 distinct plans, inpatient bills
   sampled from a log-normal distribution. Plan terms (deductible, coinsurance, out-of-pocket
   maximum, copay) are real; bill amounts are sampled. The PUF carries no coordination clause,
   so households are evaluated twice: as loaded (every plan tagged EXCESS by the loader, which
   makes them circular and pro rata) and as co-primary (the order search). The file is loaded
   lazily and the study is skipped with a note when it is missing.

For every household the report compares the optimizer with the two baselines of
`allocation.optimize_allocation`: greedy (claim in the order held) and the best single policy.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import statistics
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Optional

from clauseguard import config
from clauseguard.agent.demo_fixtures import bpjs_kes, gh_nusa, hcp_rider_b, hcp_sompo, hi_indiv_s, jasa_raharja, pa_chubb, platform_acc
from clauseguard.allocation import AllocationResult, BillBreakdown, optimize_allocation
from clauseguard.schema import Basis, PolicyRecord, Relation, ScenarioFacts, Slot

AS_OF = date(2026, 10, 11)
CMS_PATH = config.DATA_DIR / "real" / "cms_plans_py2026.csv"
MANIFEST = config.DATA_DIR / "real" / "manifest.json"
OUT = config.EVIDENCE_DIR / "allocation_report.md"


# --------------------------------------------------------------------------- helpers
def money(v: Optional[Decimal], cur: str) -> str:
    return "n/a" if v is None else f"{cur} {int(v):,}"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def steps_table(res: AllocationResult) -> list[str]:
    cur = res.currency
    L = ["| # | policy | type | amount | clause ids | note |", "|---|---|---|---|---|---|"]
    for s in res.steps:
        L.append(f"| {s.order} | {s.policy_id} | {s.payer_type} | {money(s.amount, cur)} | {', '.join(s.clause_ids)} | {(s.note or '')[:200]} |")
    for u in res.uncertain:
        L.append(f"| - | {u.policy_id} | UNCERTAIN ({', '.join(x.value for x in u.slots)}) | up to {money(u.potential_amount, cur)} | {', '.join(u.clause_ids)} | {(u.note or '')[:200]} |")
    for e in res.excluded:
        if e.code in ("NOT_APPLICABLE", "NOT_SPECIFIED") and not e.rule_id:
            continue
        L.append(f"| - | {e.policy_id} | EXCLUDED {e.code} | - | {', '.join(e.clause_ids)} | {(e.note or '')[:200]} |")
    L.append(f"| | **total** | | **{money(res.total_recovered, cur)}** (indemnity {money(res.indemnity_total, cur)} + fixed {money(res.fixed_benefit_total, cur)}) | out of pocket {money(res.out_of_pocket, cur)} | greedy {money(res.greedy_total, cur)}, best single {money(res.single_policy_total, cur)}, circular excess: {res.circular_excess} |")
    return L


class Study:
    """Accumulates optimizer / greedy / single totals over households."""

    def __init__(self, name: str, currency: str):
        self.name, self.currency = name, currency
        self.rows: list[dict] = []

    def add(self, label: str, res: AllocationResult, policies: list[PolicyRecord], bill: BillBreakdown, facts: ScenarioFacts) -> None:
        self.rows.append({"label": label, "res": res, "policies": policies, "bill": bill, "facts": facts,
                          "opt": res.total_recovered, "greedy": res.greedy_total or Decimal(0), "single": res.single_policy_total or Decimal(0)})

    def summary(self) -> list[str]:
        if not self.rows:
            return [f"_{self.name}: no households._"]
        n = len(self.rows)
        opt = [float(r["opt"]) for r in self.rows]
        gr = [float(r["greedy"]) for r in self.rows]
        sg = [float(r["single"]) for r in self.rows]
        bills = [float(r["bill"].total) for r in self.rows]
        sub = [r for r in self.rows if r["greedy"] < r["opt"]]
        breach = [r for r in self.rows if r["greedy"] > r["opt"]]
        gains = [float(r["opt"] - r["greedy"]) for r in sub]
        circ = sum(1 for r in self.rows if r["res"].circular_excess)
        cur = self.currency
        L = [f"| metric | optimizer | greedy (holdings order) | best single policy |", "|---|---|---|---|",
             f"| mean recovery | {cur} {statistics.mean(opt):,.0f} | {cur} {statistics.mean(gr):,.0f} | {cur} {statistics.mean(sg):,.0f} |",
             f"| median recovery | {cur} {statistics.median(opt):,.0f} | {cur} {statistics.median(gr):,.0f} | {cur} {statistics.median(sg):,.0f} |",
             f"| mean recovery / bill | {100 * statistics.mean(o / b for o, b in zip(opt, bills)):.1f}% | {100 * statistics.mean(g / b for g, b in zip(gr, bills)):.1f}% | {100 * statistics.mean(s / b for s, b in zip(sg, bills)):.1f}% |",
             "",
             f"- households: {n}; mean bill {cur} {statistics.mean(bills):,.0f} (median {cur} {statistics.median(bills):,.0f})",
             f"- greedy suboptimal (greedy < optimizer): {len(sub)} / {n} = {100 * len(sub) / n:.1f}%",
             f"- mean gain over greedy where suboptimal: {cur} {statistics.mean(gains):,.0f} (mean over all households {cur} {statistics.mean(float(r['opt'] - r['greedy']) for r in self.rows):,.0f})" if sub else "- mean gain over greedy: 0",
             f"- greedy above the rule-bound optimum (holdings order breaches a coordination rule): {len(breach)} / {n}",
             f"- optimizer >= best single policy in {sum(1 for r in self.rows if r['opt'] >= r['single'])} / {n}",
             f"- circular excess flagged: {circ} / {n}",
             f"- solver labels: {dict(sorted(_count(r['res'].solver for r in self.rows).items()))}"]
        return L

    def worked_examples(self, k: int) -> list[str]:
        """The k households with the largest optimizer gain over greedy, then the most payers."""
        rows = sorted(self.rows, key=lambda r: (-(r["opt"] - r["greedy"]), -len(r["res"].steps), r["label"]))[:k]
        L: list[str] = []
        for r in rows:
            res = r["res"]
            L.append(f"#### {r['label']}")
            L.append(f"Bill {money(r['bill'].total, res.currency)}" + (f" (room {money(r['bill'].room, res.currency)}, other {money(r['bill'].total - (r['bill'].room or 0), res.currency)})" if r["bill"].room is not None else "")
                     + f", {r['facts'].get(Slot.DAYS_HOSPITALIZED)} days; policies: " + ", ".join(f"{p.id} ({p.insurer[:40]}, {p.product_name[:40]})" for p in r["policies"]))
            L += steps_table(res)
            L.append("")
        return L


def _count(items) -> dict:
    out: dict = {}
    for x in items:
        out[x] = out.get(x, 0) + 1
    return out


# --------------------------------------------------------------------------- study 1: persona demo cases
def rizky_facts() -> ScenarioFacts:
    return ScenarioFacts(values={
        Slot.EVENT: "HOSPITALIZATION", Slot.CAUSE: "ILLNESS", Slot.IS_ACCIDENT: False, Slot.IS_EMERGENCY: False, Slot.DAYS_SINCE_EFFECTIVE: 44,
        Slot.MONTHS_SINCE_ISSUE: 1, Slot.DISEASE_IN_SPECIFIED_LIST: False, Slot.DIAGNOSIS_BEFORE_EFFECTIVE: False, Slot.DAYS_HOSPITALIZED: 5,
        Slot.DAYS_SINCE_DISCHARGE: 4, Slot.FACILITY_BPJS_PARTNER: True, Slot.BILLED_AMOUNT: 9200000, Slot.PREMIUM_STATUS: "PAID"}, as_of=AS_OF)


def aditya_facts() -> ScenarioFacts:
    return ScenarioFacts(values={
        Slot.EVENT: "HOSPITALIZATION", Slot.CAUSE: "ILLNESS", Slot.IS_ACCIDENT: False, Slot.IS_EMERGENCY: False, Slot.DAYS_HOSPITALIZED: 4,
        Slot.DAYS_SINCE_DISCHARGE: 1, Slot.BILLED_AMOUNT: 18000000, Slot.FACILITY_BPJS_PARTNER: False, Slot.EMPLOYMENT_ACTIVE: True,
        Slot.PREMIUM_STATUS: "PAID", Slot.DISEASE_IN_SPECIFIED_LIST: False, Slot.DIAGNOSIS_BEFORE_EFFECTIVE: True, Slot.MONTHS_SINCE_ISSUE: 11,
        Slot.DAYS_SINCE_EFFECTIVE: 339}, as_of=AS_OF)


def dewi_facts(license_valid: Optional[bool]) -> ScenarioFacts:
    v = {Slot.EVENT: "HOSPITALIZATION", Slot.CAUSE: "ACCIDENT_TRAFFIC", Slot.IS_ACCIDENT: True, Slot.VEHICLES_INVOLVED: 2, Slot.WORK_RELATED: True,
         Slot.DAYS_HOSPITALIZED: 6, Slot.DAYS_SINCE_EVENT: 6, Slot.DAYS_SINCE_DISCHARGE: 0, Slot.BILLED_AMOUNT: 22000000, Slot.FACILITY_BPJS_PARTNER: True,
         Slot.DAYS_SINCE_EFFECTIVE: 204, Slot.MONTHS_SINCE_ISSUE: 6, Slot.INTOXICATED: False, Slot.OCCUPATION_CLASS: 1}
    if license_valid is not None:
        v[Slot.LICENSE_VALID] = license_valid
    return ScenarioFacts(values=v, as_of=AS_OF)


def persona_cases() -> list[tuple[str, AllocationResult]]:
    out = []
    out.append(("Rizky: dengue admission, 5 days, BPJS partner hospital, bill IDR 9,200,000 (HCP-SOMPO-01, BPJS Kesehatan)",
                optimize_allocation([hcp_sompo(), bpjs_kes("BPJS-KES-RIZKY", "active")], rizky_facts(), BillBreakdown(total=Decimal(9_200_000)), rule_pack="ID", as_of=AS_OF)))
    pols = [gh_nusa(), hi_indiv_s(), hcp_rider_b(), bpjs_kes("BPJS-KES-SANTOSO", "active")]
    bill = BillBreakdown(total=Decimal(18_000_000), room=Decimal(8_000_000), drugs=Decimal(7_000_000), doctor=Decimal(3_000_000))
    out.append(("Santoso/Aditya: asthma admission (pre-existing for the individual plan), 4 days, non-partner hospital, bill IDR 18,000,000 itemised",
                optimize_allocation(pols, aditya_facts(), bill, rule_pack="ID", as_of=AS_OF, facts_by_policy={"HCP-RIDER-B": aditya_facts().bind(Slot.DIAGNOSIS_BEFORE_EFFECTIVE, False)})))
    pols = [pa_chubb(), platform_acc(), bpjs_kes("BPJS-KES-DEWI", "lapsed"), jasa_raharja()]
    out.append(("Dewi: two-vehicle traffic accident on an active order, 6 days, bill IDR 22,000,000, licence validity unknown",
                optimize_allocation(pols, dewi_facts(None), BillBreakdown(total=Decimal(22_000_000)), rule_pack="ID", as_of=AS_OF)))
    out.append(("Dewi: the same claim once the licence is confirmed valid (two EXCESS policies become circular)",
                optimize_allocation(pols, dewi_facts(True), BillBreakdown(total=Decimal(22_000_000)), rule_pack="ID", as_of=AS_OF)))
    return out


# --------------------------------------------------------------------------- study 2: persona households
PERSONA_POOL = {
    "GH-NUSA-GRP": gh_nusa, "HI-INDIV-S": hi_indiv_s, "HCP-SOMPO-01": hcp_sompo, "HCP-RIDER-B": hcp_rider_b,
    "BPJS-KES": lambda: bpjs_kes("BPJS-KES", "active"),
}


def persona_households(n: int, rng: random.Random) -> Study:
    study = Study("persona households (ID pack)", "IDR")
    ids = sorted(PERSONA_POOL)
    for k in range(n):
        chosen = rng.sample(ids, rng.choice([2, 3]))
        policies = [PERSONA_POOL[i]() for i in chosen]
        total = int(min(250_000_000, max(1_500_000, math.exp(rng.gauss(math.log(15_000_000), 0.8)))))
        total -= total % 1000
        days = rng.choice([2, 3, 3, 4, 4, 5, 6, 8])
        room_share = rng.uniform(0.25, 0.5)
        room = int(total * room_share) - int(total * room_share) % 1000
        bill = BillBreakdown(total=Decimal(total), room=Decimal(room), drugs=Decimal(total - room))
        facts = ScenarioFacts(values={
            Slot.EVENT: "HOSPITALIZATION", Slot.CAUSE: "ILLNESS", Slot.IS_ACCIDENT: False, Slot.IS_EMERGENCY: False, Slot.DAYS_HOSPITALIZED: days,
            Slot.DAYS_SINCE_DISCHARGE: 2, Slot.BILLED_AMOUNT: total, Slot.FACILITY_BPJS_PARTNER: rng.random() < 0.5, Slot.EMPLOYMENT_ACTIVE: True,
            Slot.PREMIUM_STATUS: "PAID", Slot.DISEASE_IN_SPECIFIED_LIST: False, Slot.DIAGNOSIS_BEFORE_EFFECTIVE: False, Slot.MONTHS_SINCE_ISSUE: 14,
            Slot.DAYS_SINCE_EFFECTIVE: 420}, as_of=AS_OF)
        res = optimize_allocation(policies, facts, bill, rule_pack="ID", as_of=AS_OF)
        study.add(f"persona household {k + 1}: {' + '.join(chosen)}", res, policies, bill, facts)
    return study


# --------------------------------------------------------------------------- study 3: CMS households
def load_cms(limit: int) -> tuple[list[PolicyRecord], dict]:
    if not CMS_PATH.exists():
        return [], {"missing": True}
    from clauseguard.plans.cms_loader import load_cms_plans

    plans = [p for p in load_cms_plans(CMS_PATH) if any(t.object == "HOSPITALIZATION" for t in p.tuples_by(Relation.COVERS))]
    meta = {"missing": False, "path": str(CMS_PATH.relative_to(config.ROOT)), "sha256": sha256(CMS_PATH), "plans_with_inpatient": len(plans), "plans_used": min(limit, len(plans))}
    if MANIFEST.exists():
        try:
            m = json.loads(MANIFEST.read_text(encoding="utf-8")).get("sources", {})
            for key in ("cms_plans_py2026_csv", "cms_plan_attributes_py2026", "cms_benefits_cost_sharing_py2026"):
                if key in m:
                    meta[key] = {k: m[key].get(k) for k in ("url", "downloaded_on", "sha256", "state", "rows", "license") if k in m[key]}
        except (OSError, ValueError):
            pass
    return plans[:limit], meta


def co_primary(plan: PolicyRecord) -> PolicyRecord:
    """The same plan without the loader's EXCESS tag (the PUF states no coordination clause)."""
    tuples = [t.model_copy(update={"qualifiers": t.qualifiers.model_copy(update={"other_insurance": None})}) if t.qualifiers.other_insurance else t for t in plan.tuples]
    return plan.model_copy(update={"tuples": tuples})


def cms_households(plans: list[PolicyRecord], n: int, rng: random.Random) -> tuple[Study, Study]:
    primary = Study("CMS households, co-primary (GENERIC pack)", "USD")
    filed = Study("CMS households, as loaded (every plan EXCESS)", "USD")
    for k in range(n):
        chosen = rng.sample(plans, rng.choice([2, 3]))
        total = int(min(250_000, max(500, math.exp(rng.gauss(math.log(12_000), 0.9)))))
        days = rng.choice([1, 2, 2, 3, 3, 4, 5, 7])
        bill = BillBreakdown(total=Decimal(total), currency="USD")
        facts = ScenarioFacts(values={
            Slot.EVENT: "HOSPITALIZATION", Slot.CAUSE: "ILLNESS", Slot.IS_ACCIDENT: False, Slot.IS_EMERGENCY: False, Slot.DAYS_HOSPITALIZED: days,
            Slot.DAYS_SINCE_DISCHARGE: 3, Slot.BILLED_AMOUNT: total, Slot.PREMIUM_STATUS: "PAID", Slot.DISEASE_IN_SPECIFIED_LIST: False,
            Slot.DIAGNOSIS_BEFORE_EFFECTIVE: False, Slot.MONTHS_SINCE_ISSUE: 9, Slot.DAYS_SINCE_EFFECTIVE: 280}, as_of=AS_OF)
        label = f"CMS household {k + 1}: {' + '.join(p.id for p in chosen)}"
        cp = [co_primary(p) for p in chosen]
        primary.add(label, optimize_allocation(cp, facts, bill, rule_pack="GENERIC", as_of=AS_OF), cp, bill, facts)
        filed.add(label, optimize_allocation(chosen, facts, bill, rule_pack="GENERIC", as_of=AS_OF), chosen, bill, facts)
    return primary, filed


# --------------------------------------------------------------------------- report
def render(households: int, seed: int, plans_limit: int) -> str:
    rng = random.Random(seed)
    L: list[str] = ["# Claim allocation optimizer: evaluation report", "",
                    f"Generated by `python -m bench.allocation_eval --households {households} --seed {seed} --plans {plans_limit}`; as-of date {AS_OF.isoformat()}; no language model involved.", "",
                    "The optimizer (`clauseguard/allocation.py`) decides which policy of a household pays what share of one bill under the",
                    "coordination rules of a rule pack (`clauseguard/rulepacks.py`): statutory schemes first, then employer group before individual,",
                    "then primary / pro-rata / excess, fixed benefits stacked. Within a layer of co-primary policies it searches the claiming order",
                    "exactly; every later payer is presented what is still unpaid. Baselines: **greedy** = claim in the order the policies are held;",
                    "**single** = the best single policy on the whole bill.", ""]

    L += ["## 1. Persona demo cases", "", "Policies from `clauseguard/sandbox/persona_policies.py`; tuples quote real public wordings where the product is modelled on one (doc ids `roojai_hcp_en`, `astra_hcp`, `astra_flexi_life`, `chubb_my_pa`) and sandbox wordings marked `(mock)` otherwise. Statutory amounts are sandbox stubs (\"verify\").", ""]
    for title, res in persona_cases():
        L.append(f"### {title}")
        L += steps_table(res)
        L.append("")

    L += ["## 2. Persona households (rule pack ID)", "",
          f"Households of 2-3 covers drawn from {{{', '.join(sorted(PERSONA_POOL))}}} (plan terms = the persona tuples). Admission: illness, days in {{2,3,4,5,6,8}} (weighted), "
          "BPJS partner facility with probability 0.5, bill total log-normal with median IDR 15,000,000 and sigma 0.8 clipped to [1.5M, 250M], room share uniform in [0.25, 0.5]. "
          "**Bill amounts sampled; plan terms real (persona wordings).**", ""]
    s2 = persona_households(households, rng)
    L += s2.summary()
    L.append("")

    plans, meta = load_cms(plans_limit)
    L += ["## 3. CMS Marketplace households (rule pack GENERIC)", ""]
    if meta.get("missing"):
        L += [f"_Skipped: `{CMS_PATH.relative_to(config.ROOT)}` is not present. Re-run after `scripts/fetch_real_data.py` has produced it._", ""]
        s3 = s3f = None
    else:
        L += [f"{meta['plans_used']} plans (the first {meta['plans_used']} by plan id of {meta['plans_with_inpatient']} with inpatient cover) loaded by `clauseguard.plans.cms_loader` from `{meta['path']}` "
              "(deductible, coinsurance, out-of-pocket maximum and copay per plan as COVERS qualifiers, basis INDEMNITY, currency USD). Households of 2-3 distinct plans; "
              "inpatient bill log-normal with median USD 12,000 and sigma 0.9 clipped to [500, 250,000]; days in {1,2,3,4,5,7} (weighted). **Bill amounts sampled; plan terms real.**", "",
              "The PUF states no coordination-of-benefits clause. The loader tags every plan EXCESS, which makes any two plans circular; the households are therefore evaluated "
              "twice: as co-primary (claiming order searched) and as loaded (circular, flagged, resolved as a rateable proportion: charges split by limit, each plan applying its own deductible and coinsurance to its share). "
              "The rateable resolution leaves more unpaid than sequential claiming, which is why greedy exceeds it there: the pro-rata clause, not the optimizer, is what costs the member.", "",
              "### 3a. Co-primary", ""]
        s3, s3f = cms_households(plans, households, rng)
        L += s3.summary()
        L += ["", "### 3b. As loaded (every plan EXCESS)", ""]
        L += s3f.summary()
        L.append("")

    L += ["## 4. Worked examples (largest optimizer gain over greedy)", ""]
    examples = s2.worked_examples(2) + (s3.worked_examples(3) if s3 else s2.worked_examples(5)[2:])
    L += examples

    L += ["## 5. Reading the numbers", "",
          "- The indemnity principle holds in every household: the indemnity steps never add up to more than the bill (asserted in `tests/test_allocation.py`).",
          "- Greedy is suboptimal when the first policy held is not the one to claim first: a plan whose deductible or out-of-pocket maximum binds on the full bill "
          "leaves a remainder that the second plan pays better than the other way round. The gain is the difference in cost sharing, not extra money.",
          "- Greedy can exceed the optimizer only by breaching a coordination rule (claiming an excess or individual policy ahead of the statutory or group payer); the count is reported per study.",
          "- Fixed-benefit covers (hospital cash) stack and are identical in all three strategies; the comparison is driven by the indemnity layer.", ""]

    L += ["## 6. Data provenance", "",
          "| source | what | role in this report |", "|---|---|---|",
          "| `clauseguard/sandbox/persona_policies.py` | hand-verified PolicyRecords; verbatim clauses from public wordings (public insurer PDFs, extracted to text) for Sompo/Roojai HCP, Astra HCP rider, Astra Flexi Life, Chubb Essential Plus PA; sandbox wordings marked `(mock)` for the group plan, the individual plan, the platform cover, BPJS Kesehatan and Jasa Raharja | studies 1 and 2 |"]
    if meta.get("missing"):
        L.append(f"| `{CMS_PATH.relative_to(config.ROOT)}` | CMS Marketplace PUF plan year 2026 extract | not present at run time; study 3 skipped |")
    else:
        L.append(f"| `{meta['path']}` | CMS Health Insurance Exchange PUF, plan year 2026, one-state extract (sha256 `{meta['sha256'][:16]}...`) | study 3; {meta['plans_used']} of {meta['plans_with_inpatient']} plans |")
        for key in ("cms_plans_py2026_csv", "cms_plan_attributes_py2026", "cms_benefits_cost_sharing_py2026"):
            if key in meta:
                m = meta[key]
                L.append(f"| manifest `{key}` | {m.get('url', '')}; downloaded {m.get('downloaded_on', '')}; state {m.get('state', '-')}; rows {m.get('rows', '-')}; {m.get('license', '')} | {('sha256 ' + m['sha256'][:16] + '...') if m.get('sha256') else ''} |")
    L += ["| bill amounts, days, facility flags | sampled with `random.Random(seed)` from the distributions stated in each study | synthetic inputs, stated as such |",
          "", "Nothing else is synthetic: no plan, limit, deductible, copay or clause text was invented for this report.", ""]
    return "\n".join(L)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--households", type=int, default=500)
    ap.add_argument("--seed", type=int, default=20261011)
    ap.add_argument("--plans", type=int, default=200)
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args()
    text = render(args.households, args.seed, args.plans)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text, encoding="utf-8")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
