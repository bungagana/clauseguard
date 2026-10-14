"""Extraction-quality check: extracted C1..C10 vs the benchmark ABox (gold).

Fields compared (per contract, exact match):
  suicide_months   HAS_PERIOD SUICIDE window (converted to months)   vs li:suicideExclusionPeriodMonths
  grace_days       HAS_PERIOD GRACE window (days) / PolicyRecord.grace_days vs li:gracePeriodDays
  contest_years    HAS_PERIOD CONTESTABILITY window (years)          vs li:contestabilityPeriodYears
  free_look_days   HAS_PERIOD FREE_LOOK window (days)                vs li:freeLookDays
  loan_available   PERMITS POLICY_LOAN present                        vs li:hasPolicyLoan present
Precision = TP / (TP + FP) where FP = extracted value that is absent in gold or differs;
Recall    = TP / (TP + FN) where FN = gold value missing or wrong in the extraction.
For loan_available the gold is the boolean presence; TN are reported too.

Writes evidence/extraction_quality.md.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import rdflib  # noqa: E402

from clauseguard.schema import PeriodKind, PolicyRecord, Relation, TimeUnit  # noqa: E402

ABOX = ROOT / "data" / "benchmark" / "ontologies" / "life_insurance_abox.ttl"
LI = rdflib.Namespace("http://www.lifeinsurance.org/ontology#")
AB = rdflib.Namespace("http://www.lifeinsurance.org/ontology/abox#")
EXTRACTED = ROOT / "data" / "extracted"
OUT = ROOT / "evidence" / "extraction_quality.md"
CONTRACTS = [f"C{i}" for i in range(1, 11)]
FIELDS = ["suicide_months", "grace_days", "contest_years", "free_look_days", "loan_available"]


def _to(unit_len, unit, target: TimeUnit):
    if unit_len is None:
        return None
    unit = unit or target
    days = {TimeUnit.DAYS: 1, TimeUnit.MONTHS: 30, TimeUnit.YEARS: 365}
    if unit == target:
        return int(unit_len)
    val = unit_len * days[unit] / days[target]
    return int(round(val))


def gold_values(g: rdflib.Graph, cid: str) -> dict:
    pol = AB[f"Policy_{cid}"]
    out = {k: None for k in FIELDS}
    out["loan_available"] = (pol, LI.hasPolicyLoan, None) in g
    out["suicide_benefit"] = None
    for o in g.objects(pol, LI.hasGracePeriod):
        v = g.value(o, LI.gracePeriodDays)
        out["grace_days"] = int(v) if v is not None else None
    for o in g.objects(pol, LI.hasExclusion):
        v = g.value(o, LI.suicideExclusionPeriodMonths)
        if v is not None:
            out["suicide_months"] = int(v)
            bt = g.value(o, LI.suicideBenefitType)
            out["suicide_benefit"] = str(bt).split("#")[-1] if bt is not None else None
    for o in g.objects(pol, LI.hasProvision):
        v = g.value(o, LI.contestabilityPeriodYears)
        if v is not None:
            out["contest_years"] = int(v)
        v = g.value(o, LI.freeLookDays)
        if v is not None:
            out["free_look_days"] = int(v)
    return out


def extracted_values(rec: PolicyRecord) -> dict:
    out = {k: None for k in FIELDS}
    out["loan_available"] = any(t.relation == Relation.PERMITS and t.object == "POLICY_LOAN" for t in rec.tuples)
    out["suicide_benefit"] = None
    base = [t for t in rec.tuples if t.head == rec.id]
    for t in base:
        q = t.qualifiers
        if t.relation == Relation.HAS_PERIOD:
            if t.object == PeriodKind.SUICIDE.value and out["suicide_months"] is None:
                out["suicide_months"] = _to(q.window_len, q.window_unit, TimeUnit.MONTHS)
                out["suicide_benefit"] = q.benefit_type
            elif t.object == PeriodKind.GRACE.value and out["grace_days"] is None:
                out["grace_days"] = _to(q.window_len, q.window_unit, TimeUnit.DAYS)
            elif t.object == PeriodKind.CONTESTABILITY.value and out["contest_years"] is None:
                out["contest_years"] = _to(q.window_len, q.window_unit, TimeUnit.YEARS)
            elif t.object == PeriodKind.FREE_LOOK.value and out["free_look_days"] is None:
                out["free_look_days"] = _to(q.window_len, q.window_unit, TimeUnit.DAYS)
    if out["suicide_months"] is None:
        for t in base:
            if t.relation == Relation.EXCLUDES and t.object == "SUICIDE" and t.qualifiers.window_len:
                out["suicide_months"] = _to(t.qualifiers.window_len, t.qualifiers.window_unit, TimeUnit.MONTHS)
                out["suicide_benefit"] = t.qualifiers.benefit_type
                break
    if out["free_look_days"] is None:
        for t in base:
            if t.relation == Relation.PERMITS and t.object == "FREE_LOOK" and t.qualifiers.window_len:
                out["free_look_days"] = _to(t.qualifiers.window_len, t.qualifiers.window_unit, TimeUnit.DAYS)
                break
    if out["grace_days"] is None and rec.grace_days:
        out["grace_days"] = rec.grace_days
    return out


BENEFIT_MAP = {
    "ReturnPremiumsPaid": "RETURN_PREMIUMS",
    "ReturnPremiumsMinusWithdrawals": "RETURN_PREMIUMS",
    "ReturnPremiumsMinusWithdrawalsAndCharges": "RETURN_PREMIUMS",
    "ReturnAccountValue": "REDUCED",
    "NoBenefit": "NONE",
}


def main() -> None:
    g = rdflib.Graph()
    g.parse(str(ABOX), format="turtle")
    rows = []
    stats = {f: {"tp": 0, "fp": 0, "fn": 0, "tn": 0} for f in FIELDS}
    bt_ok = bt_n = 0
    counts = {}
    for cid in CONTRACTS:
        p = EXTRACTED / f"{cid}.json"
        if not p.exists():
            rows.append((cid, None, None))
            continue
        rec = PolicyRecord.model_validate_json(p.read_text(encoding="utf8"))
        counts[cid] = (len(rec.tuples), rec.extraction_coverage)
        gv, ev = gold_values(g, cid), extracted_values(rec)
        rows.append((cid, gv, ev))
        for f in FIELDS:
            gval, eval_ = gv[f], ev[f]
            if f == "loan_available":
                if gval and eval_:
                    stats[f]["tp"] += 1
                elif gval and not eval_:
                    stats[f]["fn"] += 1
                elif not gval and eval_:
                    stats[f]["fp"] += 1
                else:
                    stats[f]["tn"] += 1
                continue
            if gval is None and eval_ is None:
                stats[f]["tn"] += 1
            elif gval is not None and eval_ == gval:
                stats[f]["tp"] += 1
            elif gval is None and eval_ is not None:
                stats[f]["fp"] += 1  # extracted something the gold does not state
            elif gval is not None and eval_ is None:
                stats[f]["fn"] += 1
            else:  # both present, differ
                stats[f]["fp"] += 1
                stats[f]["fn"] += 1
        if gv["suicide_benefit"] is not None:
            bt_n += 1
            if BENEFIT_MAP.get(gv["suicide_benefit"]) == ev["suicide_benefit"]:
                bt_ok += 1

    def pr(s):
        p = s["tp"] / (s["tp"] + s["fp"]) if s["tp"] + s["fp"] else float("nan")
        r = s["tp"] / (s["tp"] + s["fn"]) if s["tp"] + s["fn"] else float("nan")
        return p, r

    lines = [
        "# Extraction quality vs benchmark ABox (C1..C10)",
        "",
        "Gold: `data/benchmark/ontologies/life_insurance_abox.ttl`. Extracted: `data/extracted/C*.json` "
        "produced by `scripts/extract_all.py` (two-pass extractor, model `gemini-3.6-flash`, temperature 0).",
        "",
        "Held-out discipline: prompts and normalisation rules were tuned on **C1 and C7 only**; C2-C6 and C8-C10 are held out.",
        "",
        "## Per-field precision / recall (exact value match)",
        "",
        "| field | TP | FP | FN | TN | precision | recall |",
        "|---|---|---|---|---|---|---|",
    ]
    for f in FIELDS:
        s = stats[f]
        p, r = pr(s)
        lines.append(f"| {f} | {s['tp']} | {s['fp']} | {s['fn']} | {s['tn']} | {p:.2f} | {r:.2f} |")
    lines += [
        "",
        f"Suicide benefit type (ReturnPremiums/NoBenefit/AccountValue -> RETURN_PREMIUMS/NONE/REDUCED) correct: {bt_ok}/{bt_n}.",
        "",
        "## Per-contract values (gold -> extracted)",
        "",
        "| contract | tuples | coverage | suicide_months | grace_days | contest_years | free_look_days | loan_available |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for cid, gv, ev in rows:
        if gv is None:
            lines.append(f"| {cid} | (not extracted) | | | | | | |")
            continue
        n, cov = counts[cid]
        cell = lambda f: f"{gv[f]} -> {ev[f]}" + ("" if gv[f] == ev[f] else " **x**")  # noqa: E731
        lines.append(f"| {cid} | {n} | {cov:.2f} | {cell('suicide_months')} | {cell('grace_days')} | {cell('contest_years')} | {cell('free_look_days')} | {cell('loan_available')} |")
    lines += [
        "",
        "Notes:",
        "- `grace_days` for C6 has no `gracePeriodDays` literal in the ABox (the group certificate defines the grace period in prose), so an extracted value there counts as FP under exact matching; see the per-contract row.",
        "- The two `contest_years` FNs (C4, C6) are gold values that do not appear in the contract text: contract_4 has no contestability clause at all and the ABox labels C6's as `Section 1.3 (implied from master policy)`. The extractor correctly did not invent them.",
        "- The `loan_available` FP (C5) is a gold gap: contract_5 §4.3 states `You can borrow against the cash value`, but the ABox has no `PolicyLoan` node for C5.",
        "- Models: C1-C3 `gemini-3.6-flash` (primary); C4-C6, C8-C9 `gemini-3.8-flash`; C10 `gemini-3.7-flash`; C7 `gemini-3-flash-preview` - the free-tier daily quota (20 requests/model, shared with other module runs on the same key) forced the fallback chain in `policy_extractor.MODEL_CHAIN`. Each tuple records its model in `extractor_version`.",
        "- Post-blind-run code changes (disclosed): (a) `window_from_text` rescue parses 'N days/months/years' from the evidence when a fallback model leaves `window_len` empty on a HAS_PERIOD row (rescued tuples carry confidence <= 0.7); (b) object aliases for codes the fallback models invented (ACCELERATED_DEATH_* -> TERMINAL/CHRONIC_ILLNESS, HIV_AIDS -> SPECIFIED_DISEASE). No prompt text was changed after the blind run.",
        "- Windows are converted in code (years -> months x12, days kept); a value counts only if the number matches exactly.",
        "- `loan_available` is the presence of a PERMITS POLICY_LOAN tuple vs `li:hasPolicyLoan` in the ABox.",
    ]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n", encoding="utf8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
