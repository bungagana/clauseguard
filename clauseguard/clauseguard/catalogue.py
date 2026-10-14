"""Plan catalogues and the deterministic plan recommender (Topic D: "plan recommendations").

Three catalogues, selected by jurisdiction:

* `recommend(gap_report, budget)` with no jurisdiction keeps the original six-plan MOCK catalogue
  and its fixed rules (below). EVERYTHING IN THAT CATALOGUE IS MOCK: the insurer is "MOCK INSURER",
  the prices and benefits are illustrative, and nothing names or endorses a real product.
* `jurisdiction="US"`: the CMS Health Insurance Exchange PUF plan-year-2026 extract
  (`data/real/cms_plans_py2026.csv`, see `plans/cms_loader.py`) solved by the set-cover selector in
  `plans/selector.py`. Falls back to the mock catalogue, labelled as such, when the file is missing.
* `jurisdiction="ID"`: `data/real/catalogue_id.json`, built by `build_catalogue_id()` from the
  extracted RIPLAY product summaries in `data/extracted/` (real Indonesian product summaries, LLM
  extraction, unverified tier), solved by the same selector; the mock catalogue when absent.

Mock-catalogue rules (`recommend` without jurisdiction) consume the output of `portfolio.gap_overlap`
(the `gap_analysis` tool result); no language model is involved:

1. A plan is only suggested if it closes at least one cover gap that is still open (set cover: each
   chosen plan removes the gaps it closes, so later plans must close something new). A plan that
   would only duplicate cover the customer already holds is never suggested - in particular an
   indemnity plan is never added on top of an active indemnity policy for the same peril, because
   indemnity cover does not stack.
2. Life: only the person with a quantified shortfall (`life_gap`) is offered term life; without a
   life-gap record a death gap counts only for a one-person household (no guessing about children).
3. The group top-up needs an enrolled group indemnity plan in the gap report; it is then preferred
   over the individual hospitalisation plan because it is cheaper and builds on the existing group cover.
4. With a budget the plans are chosen greedily by priority score and skipped when they would exceed it;
   the plans left out are named in the caveats of the first suggestion.
5. Every suggestion carries "indicative; consult a licensed agent".

The selector-backed catalogues apply rules 1, 2 and 5 inside the optimiser (weighted set cover with
an indemnity non-overlap constraint and a hard budget) and return the same `Recommendation` shape.
"""
from __future__ import annotations

import json
import re
from decimal import Decimal
from pathlib import Path
from typing import Optional

from pydantic import Field

from . import config
from .plans import selector
from .plans.cms_loader import load_cms_plans
from .schema import (
    Basis, ClauseTuple, Evidence, PeriodKind, PolicyRecord, Qualifiers, Relation, SourceTier, Strict,
)

MOCK_INSURER = "MOCK INSURER (demo catalogue, not a real company)"
MOCK_NOTE = "Mock catalogue: prices and benefits are illustrative and not an offer from any insurer."
AGENT_CAVEAT = "Indicative; consult a licensed agent before buying."
IDR = Decimal

# priority of a closed gap (higher = more important to close first); shared with the selector
EARNER_PERILS = selector.EARNER_PERILS
PERIL_WEIGHT = selector.PERIL_WEIGHT
REAL_DIR = config.DATA_DIR / "real"
CMS_PATH = REAL_DIR / "cms_plans_py2026.csv"
CATALOGUE_ID_PATH = REAL_DIR / "catalogue_id.json"
STATUTORY_PREFIXES = ("BPJS", "JASA-RAHARJA")  # sandbox ids of statutory cover (never counted as private indemnity)


def _t(pid: str, tid: str, rel: Relation, obj: str, q: Qualifiers, section: str, text: str) -> ClauseTuple:
    return ClauseTuple(
        id=tid, policy_id=pid, head=pid, relation=rel, object=obj, qualifiers=q,
        evidence=Evidence(doc_id=f"{pid}-mock", section=section, text=f"MOCK: {text}"[:1200]), source_tier=SourceTier.SYSTEM,
        extractor_version="mock-catalogue-1.0",
    )


def _plan(pid: str, name: str, ptype: str, basis: Basis, premium: int, covers: list[tuple[str, Qualifiers, str]], extra: Optional[list[ClauseTuple]] = None,
          waiting_days: int = 30, requires_group_base: bool = False) -> PolicyRecord:
    tuples: list[ClauseTuple] = []
    for i, (peril, q, text) in enumerate(covers):
        tuples.append(_t(pid, f"c_{peril.lower()}", Relation.COVERS, peril, q, "Benefits (mock)", text))
    tuples.append(_t(pid, "p_waiting", Relation.HAS_PERIOD, "WAITING", Qualifiers(period_kind=PeriodKind.WAITING, waiting_days=waiting_days),
                     "Waiting period (mock)", f"A waiting period of {waiting_days} days applies to illness; accidents are exempt."))
    tuples.append(_t(pid, "x_preexisting", Relation.EXCLUDES, "PRE_EXISTING_CONDITION", Qualifiers(), "Exclusions (mock)",
                     "Pre-existing conditions are excluded during the first 12 months."))
    tuples.append(_t(pid, "d_mock_premium", Relation.DEFINES, "MOCK_PREMIUM", Qualifiers(amount=IDR(premium), currency="IDR", formula=f"IDR {premium:,}/month per insured person (mock)"),
                     "Premium (mock)", f"Indicative premium IDR {premium:,} per month per insured person. Illustrative only."))
    if requires_group_base:
        tuples.append(_t(pid, "k_group_base", Relation.CONDITIONED_ON, "GROUP_BASE_PLAN", Qualifiers(),
                         "Eligibility (mock)", "Available only to members of an employer group health plan; pays above the base plan's room limit."))
    tuples.extend(extra or [])
    return PolicyRecord(
        id=pid, doc_id=f"{pid}-mock", insurer=MOCK_INSURER, product_name=f"{name} (MOCK)", product_type=ptype, basis=basis,
        effective_date=None, status="active", currency="IDR", tuples=tuples, verified=False,
    )


def build_catalogue() -> dict[str, PolicyRecord]:
    fx, ind = Basis.FIXED_BENEFIT, Basis.INDEMNITY
    plans = [
        _plan("CAT-HCASH-01", "Mock Hospital Cash Plan", "hospital_cash", fx, 150_000, [
            ("HOSPITALIZATION", Qualifiers(per_day_limit=IDR(300000), currency="IDR", max_days_per_year=60, basis=fx, other_insurance="STACKABLE"), "IDR 300,000 per day of hospitalisation, up to 60 days a year."),
            ("ICU", Qualifiers(per_day_limit=IDR(600000), currency="IDR", max_days_per_year=15, basis=fx, other_insurance="STACKABLE"), "IDR 600,000 per day in intensive care, up to 15 days a year."),
        ]),
        _plan("CAT-PA-01", "Mock Personal Accident Plan", "pa", fx, 90_000, [
            ("ACCIDENTAL_DEATH", Qualifiers(amount=IDR(100000000), currency="IDR", basis=fx, other_insurance="STACKABLE"), "IDR 100,000,000 on accidental death."),
            ("TPD", Qualifiers(amount=IDR(100000000), currency="IDR", basis=fx, other_insurance="STACKABLE"), "IDR 100,000,000 on total permanent disability caused by an accident."),
            ("TEMPORARY_DISABILITY", Qualifiers(per_week_amount=IDR(500000), max_weeks=52, currency="IDR", basis=fx, other_insurance="STACKABLE"), "IDR 500,000 per week of temporary total disability, up to 52 weeks."),
            ("ACCIDENT_MEDICAL", Qualifiers(per_case_limit=IDR(10000000), currency="IDR", basis=ind, other_insurance="EXCESS"), "Accident medical expenses up to IDR 10,000,000 per year."),
        ], waiting_days=0),
        _plan("CAT-TERM-01", "Mock Term Life Plan", "term_life", fx, 250_000, [
            ("DEATH", Qualifiers(amount=IDR(500000000), currency="IDR", basis=fx, other_insurance="STACKABLE"), "IDR 500,000,000 on death, level term 10 years."),
        ], waiting_days=0),
        _plan("CAT-CI-01", "Mock Critical Illness Plan", "ci", fx, 200_000, [
            ("CRITICAL_ILLNESS", Qualifiers(amount=IDR(100000000), currency="IDR", basis=fx, other_insurance="STACKABLE"), "IDR 100,000,000 lump sum on first diagnosis of a listed critical illness (30-day survival period)."),
        ], waiting_days=90),
        _plan("CAT-GTOPUP-01", "Mock Group Health Top-up", "group_health_topup", ind, 120_000, [
            ("HOSPITALIZATION", Qualifiers(per_day_limit=IDR(1000000), currency="IDR", max_days_per_year=60, basis=ind, other_insurance="EXCESS"), "Pays up to a further IDR 1,000,000 per day above the base group plan's room limit."),
            ("SURGERY", Qualifiers(per_case_limit=IDR(25000000), currency="IDR", basis=ind, other_insurance="EXCESS"), "Surgery costs above the base plan's limit, up to IDR 25,000,000 per case."),
        ], requires_group_base=True),
        _plan("CAT-HI-01", "Mock Individual Hospitalisation Plan", "health_indemnity", ind, 500_000, [
            ("HOSPITALIZATION", Qualifiers(per_day_limit=IDR(1000000), currency="IDR", max_days_per_year=120, basis=ind, other_insurance="EXCESS"), "Room and board up to IDR 1,000,000 per day, 120 days a year."),
            ("SURGERY", Qualifiers(per_case_limit=IDR(50000000), currency="IDR", basis=ind, other_insurance="EXCESS"), "Surgery up to IDR 50,000,000 per case."),
            ("ICU", Qualifiers(per_day_limit=IDR(2000000), currency="IDR", max_days_per_year=30, basis=ind, other_insurance="EXCESS"), "Intensive care up to IDR 2,000,000 per day, 30 days a year."),
        ], waiting_days=30),
    ]
    return {p.id: p for p in plans}


CATALOGUE: dict[str, PolicyRecord] = build_catalogue()


def monthly_premium(plan: PolicyRecord) -> int:
    t = next(x for x in plan.tuples if x.object == "MOCK_PREMIUM")
    return int(t.qualifiers.amount or 0)


def plan_perils(plan: PolicyRecord) -> list[str]:
    return [t.object for t in plan.tuples_by(Relation.COVERS)]


class Recommendation(Strict):
    plan_id: str
    product_name: str
    closes_gap_perils: list[str]
    monthly_premium_idr: int  # monthly cost in the catalogue's currency (IDR for the mock and RIPLAY catalogues, USD for CMS)
    rationale: str
    caveats: list[str] = Field(default_factory=list)
    mock: bool = True
    currency: str = "IDR"
    catalogue: str = "mock"  # mock | cms_puf_py2026 | riplay_id
    cost_basis: str = "premium"  # premium | oop | unknown (see plans.selector.plan_cost)


# --------------------------------------------------------------------------- gap interpretation
def closable_perils() -> set[str]:
    return {p for plan in CATALOGUE.values() for p in plan_perils(plan)}


def _open_gaps(gap_report: dict) -> tuple[dict[str, list[str]], Optional[dict]]:
    """peril -> persons with an open gap, after the life rule (see module docstring)."""
    persons = list((gap_report.get("matrix") or {}).keys())
    gaps: dict[str, list[str]] = {}
    for g in gap_report.get("gaps") or []:
        gaps.setdefault(g["peril"], []).append(g["person_id"])
    life = gap_report.get("life_gap")
    for peril in EARNER_PERILS:  # death and income-protection cover only for the earner (never guess for children or other members)
        if peril in gaps:
            if life and life.get("person_id"):
                gaps[peril] = [life["person_id"]] if life["person_id"] in gaps[peril] else []
            elif len(persons) != 1:
                gaps[peril] = []  # several people and no quantified earner: no guessing who needs it
    if life and life.get("person_id") and Decimal(str(life.get("gap", "0"))) > 0:
        gaps.setdefault("DEATH", [])
        if life["person_id"] not in gaps["DEATH"]:
            gaps["DEATH"].append(life["person_id"])
    return {k: v for k, v in gaps.items() if v and k in closable_perils()}, life


def _active_group_indemnity(gap_report: dict) -> bool:
    inactive = {n["policy_id"] for n in gap_report.get("notes") or [] if n.get("kind") == "INACTIVE"}
    for c in gap_report.get("cells") or []:
        if c.get("peril") == "HOSPITALIZATION" and c.get("basis") == "INDEMNITY" and c.get("policy_id") not in inactive and c.get("policy_id", "").startswith("GH-"):
            return True
    return False


def _score(plan: PolicyRecord, gaps: dict[str, list[str]]) -> tuple[int, list[str]]:
    closes = [p for p in plan_perils(plan) if p in gaps]
    return sum(PERIL_WEIGHT.get(p, 1) for p in closes), closes


def recommend(gap_report: dict, budget_idr_per_month: Optional[int] = None, jurisdiction: Optional[str] = None) -> list[Recommendation]:
    """Plan suggestions for a `gap_analysis` result. `jurisdiction` None -> mock catalogue and the
    fixed rules in the module docstring; "US" -> CMS PUF catalogue; "ID" -> RIPLAY catalogue; both
    real catalogues go through `plans.selector.select_from_gaps` and fall back to the mock catalogue
    (labelled) when their data file is absent. The budget is in the catalogue's currency per month."""
    if jurisdiction is not None:
        cat = catalogue_for(jurisdiction)
        if cat is not None:
            return _recommend_with_selector(gap_report, budget_idr_per_month, cat[0], cat[1], cat[2])
    gaps, life = _open_gaps(gap_report)
    group_base = _active_group_indemnity(gap_report)
    remaining = {k: list(v) for k, v in gaps.items()}
    chosen: list[Recommendation] = []
    spent = 0
    left_out: list[str] = []
    pool = [p for p in CATALOGUE.values() if not (p.id == "CAT-GTOPUP-01" and not group_base)]
    if group_base:
        pool = [p for p in pool if p.id != "CAT-HI-01"]  # the cheaper top-up builds on the group plan instead of duplicating its indemnity cover
    while True:
        ranked = []
        for p in pool:
            sc, closes = _score(p, remaining)
            if sc > 0:
                ranked.append((-sc, monthly_premium(p), p.id, p, closes))
        if not ranked:
            break
        ranked.sort(key=lambda r: r[:3])
        pick = None
        for _, price, pid, plan, closes in ranked:
            if budget_idr_per_month is not None and spent + price > budget_idr_per_month:
                if pid not in left_out:
                    left_out.append(pid)
                continue
            pick = (plan, closes, price)
            break
        if pick is None:
            break
        plan, closes, price = pick
        persons = sorted({pp for c in closes for pp in remaining.get(c, [])})
        chosen.append(_build(plan, closes, price, persons, life, gap_report))
        spent += price
        for c in closes:
            remaining.pop(c, None)
        pool = [p for p in pool if p.id != plan.id]
    if chosen and left_out:
        names = ", ".join(f"{pid} (IDR {monthly_premium(CATALOGUE[pid]):,}/month)" for pid in left_out if pid not in {c.plan_id for c in chosen})
        if names:
            chosen[0].caveats.append(f"Not suggested because they would exceed your budget of IDR {budget_idr_per_month:,}/month: {names}.")
    return chosen  # empty when nothing is needed or nothing fits the budget (render() explains which)


def _build(plan: PolicyRecord, closes: list[str], price: int, persons: list[str], life: Optional[dict], gap_report: Optional[dict] = None) -> Recommendation:
    readable = ", ".join(c.lower().replace("_", " ") for c in closes)
    who = ", ".join(persons)
    why = f"Closes cover gaps that are open in your portfolio today: {readable} (for {who})."
    caveats = [AGENT_CAVEAT, MOCK_NOTE, "Premium is per insured person per month; the figure shown is for one person."]
    if "DEATH" in closes and life and life.get("person_id") in persons and Decimal(str(life.get("gap", "0"))) > 0:
        why += (f" Existing death cover is IDR {Decimal(str(life['death_cover'])):,.0f} against liabilities of IDR {Decimal(str(life['liabilities'])):,.0f}, "
                f"a shortfall of IDR {Decimal(str(life['gap'])):,.0f}.")
        if life.get("conditional_on"):
            caveats.append("Part of your existing death cover ends if your employment ends; this plan does not depend on employment.")
    gap_report = gap_report or {}
    inactive = {n["policy_id"] for n in gap_report.get("notes") or [] if n.get("kind") == "INACTIVE"}
    lapsed_cover = sorted({c["policy_id"] for c in gap_report.get("cells") or [] if c.get("policy_id") in inactive and c.get("peril") in closes and c.get("person_id") in persons})
    if lapsed_cover:
        caveats.append(f"You hold {', '.join(lapsed_cover)} for this risk but it is not in force today; ask the insurer whether it can be reinstated, which may cost less than a new plan.")
    wait = next((t.qualifiers.waiting_days for t in plan.tuples_by(Relation.HAS_PERIOD) if t.qualifiers.waiting_days), None)
    if wait:
        caveats.append(f"A waiting period of {wait} days applies to illness (accidents are exempt).")
    caveats.append("Pre-existing conditions are excluded for the first 12 months.")
    if plan.id == "CAT-GTOPUP-01":
        caveats.append("Requires membership of an employer group health plan; it pays only the amount above that plan's limit, so it does not duplicate it.")
    if plan.basis == Basis.INDEMNITY and plan.id != "CAT-GTOPUP-01":
        caveats.append("Indemnity cover does not stack: it pays only what other cover leaves uncovered.")
    if any(c in EARNER_PERILS for c in closes):
        caveats.append("Death and income-protection cover is suggested for the household earner only; check each other adult's income before adding it, and children are not offered it.")
    return Recommendation(plan_id=plan.id, product_name=plan.product_name, closes_gap_perils=closes, monthly_premium_idr=price, rationale=why, caveats=caveats)


# --------------------------------------------------------------------------- real catalogues
_CACHE: dict[str, Optional[list[PolicyRecord]]] = {}


def cms_catalogue(path: Optional[Path] = None) -> list[PolicyRecord]:
    """CMS PUF plans (lazy, cached per path; default `CMS_PATH`); empty when the extract is not downloaded."""
    path = path or CMS_PATH
    key = f"cms:{path}"
    if key not in _CACHE:
        _CACHE[key] = load_cms_plans(path)
    return list(_CACHE[key] or [])


def riplay_catalogue(path: Optional[Path] = None) -> list[PolicyRecord]:
    """RIPLAY-derived Indonesian catalogue from `catalogue_id.json` (lazy, cached; default `CATALOGUE_ID_PATH`); empty when absent."""
    path = path or CATALOGUE_ID_PATH
    key = f"id:{path}"
    if key not in _CACHE:
        recs: list[PolicyRecord] = []
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            recs = [PolicyRecord.model_validate(r) for r in data.get("plans", [])]
        _CACHE[key] = recs
    return list(_CACHE[key] or [])


def build_catalogue_id(extracted_dir: Optional[Path] = None, out_path: Optional[Path] = None) -> int:
    """Write `catalogue_id.json` from the extracted RIPLAY records (`data/extracted/<ID>.json`, every
    record whose id is not a benchmark contract C1..C10 and whose currency is IDR). Each record is kept as extracted - real
    insurer and product names, tuples at the extractor's (unverified) tier - with status "active"
    and dates cleared so it reads as an offer, not a holding. Returns the number of plans written;
    writes nothing (and returns 0) when no RIPLAY record exists."""
    extracted_dir = extracted_dir or (config.DATA_DIR / "extracted")
    out_path = out_path or CATALOGUE_ID_PATH
    plans: list[dict] = []
    for f in sorted(extracted_dir.glob("*.json")):
        if f.name.endswith(".meta.json") or re.fullmatch(r"C\d+\.json", f.name):
            continue
        rec = PolicyRecord.model_validate(json.loads(f.read_text(encoding="utf-8")))
        if not rec.tuples_by(Relation.COVERS) or rec.currency != "IDR":
            continue  # the ID catalogue holds Indonesian (IDR) products only; other extracted RIPLAYs are foreign
        rec = rec.model_copy(update={"status": "active", "effective_date": None, "issue_date": None, "expiry_date": None, "reinstatement_date": None})
        plans.append(rec.model_dump(mode="json"))
    if not plans:
        return 0
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({"source": "data/extracted RIPLAY product summaries (LLM extraction, unverified tier); premiums not extracted",
                                    "plans": plans}, ensure_ascii=False, indent=1), encoding="utf-8")
    _CACHE.pop(f"id:{out_path}", None)
    return len(plans)


def catalogue_for(jurisdiction: str) -> Optional[tuple[list[PolicyRecord], str, str]]:
    """(plans, catalogue label, currency) for a jurisdiction, or None when only the mock is available."""
    j = jurisdiction.upper()
    if j == "US":
        plans = cms_catalogue()
        return (plans, "cms_puf_py2026", "USD") if plans else None
    if j == "ID":
        plans = riplay_catalogue()
        return (plans, "riplay_id", "IDR") if plans else None
    return None


def _report_context(gap_report: dict) -> tuple[list[dict], set[tuple[str, str]], bool, Optional[str]]:
    """Open gaps (after the earner rule), active private indemnity (peril, person) pairs, group-base
    flag and earner id, all read from the typed gap report."""
    inactive = {n["policy_id"] for n in gap_report.get("notes") or [] if n.get("kind") == "INACTIVE"}
    indemnified = {(c["peril"], c["person_id"]) for c in gap_report.get("cells") or []
                   if c.get("basis") == "INDEMNITY" and c.get("policy_id") not in inactive
                   and not str(c.get("policy_id", "")).upper().startswith(STATUTORY_PREFIXES)}
    life = gap_report.get("life_gap")
    earner = life.get("person_id") if life and life.get("person_id") else None
    persons = list((gap_report.get("matrix") or {}).keys())
    gaps: list[dict] = []
    for g in gap_report.get("gaps") or []:
        if g["peril"] in EARNER_PERILS:
            if earner is not None and g["person_id"] != earner:
                continue
            if earner is None and len(persons) != 1:
                continue
        gaps.append({"peril": g["peril"], "person_id": g["person_id"]})
    if earner and Decimal(str(life.get("gap", "0"))) > 0 and {"peril": "DEATH", "person_id": earner} not in gaps:
        gaps.append({"peril": "DEATH", "person_id": earner})
    return sorted(gaps, key=lambda g: (g["person_id"], g["peril"])), indemnified, _active_group_indemnity(gap_report), earner


def _recommend_with_selector(gap_report: dict, budget: Optional[int], plans: list[PolicyRecord], label: str, currency: str) -> list[Recommendation]:
    gaps, indemnified, group_base, earner = _report_context(gap_report)
    res = selector.select_from_gaps(gaps, plans, indemnified=indemnified, group_base=group_base, budget_monthly=budget)
    out: list[Recommendation] = []
    for i, c in enumerate(res.chosen):
        caveats = list(c.caveats)
        if label == "cms_puf_py2026":
            caveats.append("Source: CMS Health Insurance Exchange PUF, plan year 2026 (issuer filing, verified tier); cost sharing shown is in-network tier 1 for an individual.")
        else:
            caveats.append("Source: RIPLAY product summaries extracted automatically (unverified tier); check the figures against the insurer's document.")
        if i == 0:
            caveats.extend(x for x in res.caveats if x != selector.AGENT_CAVEAT)
            if res.alternatives:
                caveats.append("Alternatives: " + "; ".join(f"{' + '.join(a.plan_ids)} ({currency} {a.monthly_cost:,.0f}/month, closes {a.gaps_closed} gap cells)" for a in res.alternatives) + ".")
            if res.residual_gaps:
                caveats.append("Still open after these plans: " + ", ".join(f"{g['peril'].lower().replace('_', ' ')} ({g['person_id']})" for g in res.residual_gaps) + ".")
        out.append(Recommendation(plan_id=c.plan_id, product_name=c.product_name, closes_gap_perils=sorted({g["peril"] for g in c.closes}),
                                  monthly_premium_idr=int(c.monthly_cost), rationale=c.rationale, caveats=caveats, mock=False,
                                  currency=currency, catalogue=label, cost_basis=c.cost_basis))
    return out


def _render_real(recs: list[Recommendation], budget: Optional[int]) -> str:
    cur = recs[0].currency
    src = {"cms_puf_py2026": "CMS Exchange PUF plan year 2026", "riplay_id": "RIPLAY product summaries"}.get(recs[0].catalogue, recs[0].catalogue)
    head = f"Plan suggestions from your current cover gaps ({src}; indicative; consult a licensed agent)."
    if budget is not None:
        head += f" Budget used: {cur} {budget:,} per month."
    lines = [head]
    total = 0
    for i, r in enumerate(recs, 1):
        total += r.monthly_premium_idr
        cost = {"premium": "premium", "oop": "deductible + out-of-pocket maximum, per month", "unknown": "cost unknown"}[r.cost_basis]
        lines.append(f"{i}. {r.product_name} [{r.plan_id}] - {cur} {r.monthly_premium_idr:,} per month ({cost}). Closes: {', '.join(c.lower().replace('_', ' ') for c in r.closes_gap_perils)}.")
        lines.append(f"   Why: {r.rationale}")
        for c in r.caveats:
            lines.append(f"   - {c}")
    lines.append(f"Total: {cur} {total:,} per month. " + AGENT_CAVEAT)
    return "\n".join(lines)


def render(recs: list[Recommendation], gap_report: dict, budget: Optional[int]) -> str:
    """Plain-text answer used by the agent loop."""
    if recs and not recs[0].mock:
        return _render_real(recs, budget)
    head = "Plan suggestions from your current cover gaps (illustrative mock catalogue; indicative; consult a licensed agent)."
    if budget is not None:
        head += f" Budget used: IDR {budget:,} per month."
    if not recs:
        gaps, _ = _open_gaps(gap_report)
        if not gaps:
            return head + "\nI found no open cover gap that a plan in the catalogue would close, so I am not suggesting anything: adding more of the cover you already have would only duplicate it. " + AGENT_CAVEAT
        return head + "\nOpen gaps: " + ", ".join(k.lower().replace("_", " ") for k in gaps) + ".\nNo plan in the catalogue fits the budget; the cheapest plan that closes one of them costs more than IDR " + f"{(budget or 0):,}" + " per month. " + AGENT_CAVEAT
    lines = [head, "Open gaps: " + ", ".join(k.lower().replace("_", " ") for k in _open_gaps(gap_report)[0]) + "."]
    total = 0
    for i, r in enumerate(recs, 1):
        total += r.monthly_premium_idr
        lines.append(f"{i}. {r.product_name} [{r.plan_id}] - IDR {r.monthly_premium_idr:,} per month (mock price). Closes: {', '.join(c.lower().replace('_', ' ') for c in r.closes_gap_perils)}.")
        lines.append(f"   Why: {r.rationale}")
        for c in r.caveats:
            lines.append(f"   - {c}")
    lines.append(f"Total for one insured person: IDR {total:,} per month (mock). " + AGENT_CAVEAT)
    return "\n".join(lines)
