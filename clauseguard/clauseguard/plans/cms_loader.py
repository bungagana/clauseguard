"""Load CMS Health Insurance Exchange Public Use Files (PUF) into typed `PolicyRecord`s.

Source
------
CMS publishes, for every plan year, the *Plan Attributes PUF* (one row per plan: metal level,
deductible, out-of-pocket maximum, ...), the *Benefits and Cost Sharing PUF* (one row per plan
and benefit: copay, coinsurance, quantity limits, exclusions) and the *Rate PUF* (one row per
plan, rating area, age and tobacco status). This loader reads a one-state extract of the plan
year 2026 files (see `data/real/README.md`):

* `data/real/cms_plans_py2026.csv` in one of two layouts, both with the PUF column names:
  - *wide* (what `scripts/fetch_real_data.py` writes): one row per plan variant, Plan Attributes
    columns (`StateCode, IssuerId, IssuerMarketPlaceMarketingName, StandardComponentId, PlanId,
    PlanMarketingName, PlanType, MetalLevel, CSRVariationType, TEHBDedInnTier1Individual,
    TEHBInnTier1IndividualMOOP, ...`) followed, for each benefit group `<g>` in `WIDE_BENEFITS`,
    by `<g>_covered, <g>_copay_inn, <g>_coins_inn, <g>_quant_limit, <g>_limit_qty, <g>_limit_unit`
    (the Benefits and Cost Sharing PUF columns `IsCovered, CopayInnTier1, CoinsInnTier1,
    QuantLimitOnSvc, LimitQty, LimitUnit` of that benefit's row);
  - *long*: one row per plan x benefit with `BenefitName, IsCovered, CopayInnTier1, CoinsInnTier1,
    QuantLimitOnSvc, LimitQty, LimitUnit` next to the Plan Attributes columns. A plain Plan
    Attributes extract (no `BenefitName`) is also accepted when a sibling `cms_benefits_py2026.csv`
    holds the benefit rows; the two are joined on `PlanId`.
  Cost-sharing-reduction variants (`PlanId` suffix -02..-06) are folded away: one record per
  standard component, from the standard on-exchange variant (-01) or else the off-exchange one (-00).
* `data/real/cms_rates_py2026.csv` (optional) - Rate PUF columns `PlanId, RatingAreaId, Age,
  Tobacco, IndividualRate`. The monthly premium of a plan is the age-30, non-tobacco
  `IndividualRate` in the lowest-numbered rating area of the extract (one state has several
  rating areas; the lowest is used so the choice is deterministic and documented).

Typed mapping (no free text reaches a decision)
----------------------------------------------
Each plan becomes one `PolicyRecord(product_type="health_indemnity", basis=INDEMNITY,
currency="USD", verified=True)`. Every covered benefit row whose `BenefitName` maps to a closed
`EventCode` becomes a `COVERS` tuple whose qualifiers hold the parsed cost sharing:

* `copay_amount`    <- `CopayInnTier1` dollar amount ("$30", "$250 Copay after deductible")
* `copay_pct`       <- `CoinsInnTier1` percentage ("20% Coinsurance after deductible")
* `deductible_amount` <- `TEHBDedInnTier1Individual` (plan-level in-network individual deductible)
* `copay_cap`       <- `TEHBInnTier1IndividualMOOP`: the annual out-of-pocket maximum is a cap
  on the *member's* cost sharing, which is exactly the schema's `copay_cap`. `annual_cap`
  (a cap on what the insurer pays) is deliberately left empty: ACA-compliant plans carry no
  annual dollar limit on essential health benefits, and putting the MOOP there would make the
  coordination-of-benefits engine stop paying at the member's limit instead of the insurer's.
* `max_days_per_year` / `max_days` <- `LimitQty` when `LimitUnit` is days per year / days
* `other_insurance="EXCESS"`, `basis=INDEMNITY`

Benefit rows with `IsCovered != "Covered"` become `EXCLUDES` tuples. The out-of-pocket maximum
and the deductible are also recorded once as `DEFINES OOP_MAX` / `DEFINES DEDUCTIBLE` tuples;
the premium, when the Rate PUF is present, as `DEFINES PREMIUM` (amount USD per month).
Without the Rate PUF `premium_monthly(plan)` is `None` and the selector minimises
deductible + out-of-pocket maximum instead (`objective="oop"`), which it states in its rationale.

Evidence is the PUF row reference, never prose: `Evidence(doc_id=<file name>,
section=<PlanId>, text="<file>:<PlanId>:<column>=<raw value>")`. Source tier is
`POLICY_DOC_VERIFIED` because the PUF is the issuer's own regulatory filing.

Formulation of the cost sharing per benefit b of plan p, for a billed amount B:
    member pays  min(MOOP_p, D_p + copay_b + coins_b * max(0, B - D_p))
    insurer pays B - member pays
which is what `allocation.policy_terms` / `PolicyTerms.pay` compute from the same qualifiers
(deductible -> co-payment -> inner limits -> caps).
"""
from __future__ import annotations

import csv
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterable, Optional

from ..schema import Basis, ClauseTuple, Evidence, PolicyRecord, Qualifiers, Relation, SourceTier

PUF_FILE = "cms_plans_py2026.csv"
BENEFITS_FILE = "cms_benefits_py2026.csv"
RATES_FILE = "cms_rates_py2026.csv"
EXTRACTOR_VERSION = "cms-puf-loader-1.0"
PREMIUM_AGE = 30

# CMS `BenefitName` -> closed EventCode. ICU care is part of "Inpatient Hospital Services" under
# the essential-health-benefit definition, so the inpatient row yields both HOSPITALIZATION and ICU.
BENEFIT_EVENTS: dict[str, tuple[str, ...]] = {
    "inpatient hospital services (e.g., hospital stay)": ("HOSPITALIZATION", "ICU"),
    "inpatient physician and surgical services": ("SURGERY",),
    "outpatient surgery physician/surgical services": ("SURGERY",),
    "outpatient facility fee (e.g., ambulatory surgery center)": ("OUTPATIENT",),
    "primary care visit to treat an injury or illness": ("OUTPATIENT",),
    "specialist visit": ("OUTPATIENT",),
    "emergency room services": ("ACCIDENT_MEDICAL",),
    "urgent care centers or facilities": ("ACCIDENT_MEDICAL",),
    "prenatal and postnatal care": ("PREGNANCY",),
    "delivery and all inpatient services for maternity care": ("PREGNANCY",),
    "dental check-up for children": ("DENTAL",),
    "basic dental care - child": ("DENTAL",),
    "basic dental care - adult": ("DENTAL",),
    "major dental care - adult": ("DENTAL",),
    "major dental care - child": ("DENTAL",),
    "routine dental services (adult)": ("DENTAL",),
}

# wide layout: column prefix -> (PUF BenefitName, events)
WIDE_BENEFITS: dict[str, tuple[str, tuple[str, ...]]] = {
    "inpatient_hospital": ("Inpatient Hospital Services (e.g., Hospital Stay)", ("HOSPITALIZATION", "ICU")),
    "emergency_room": ("Emergency Room Services", ("ACCIDENT_MEDICAL",)),
    "primary_care": ("Primary Care Visit to Treat an Injury or Illness", ("OUTPATIENT",)),
    "specialist": ("Specialist Visit", ("OUTPATIENT",)),
    "maternity_delivery": ("Delivery and All Inpatient Services for Maternity Care", ("PREGNANCY",)),
}
STANDARD_VARIANTS = ("01", "00", "")  # on-exchange standard first, then off-exchange standard

_MONEY = re.compile(r"\$\s*([\d,]+(?:\.\d+)?)")
_PCT = re.compile(r"(\d+(?:\.\d+)?)\s*%")


def parse_money(raw: Optional[str]) -> Optional[Decimal]:
    """'$3,000' / '$250 Copay after deductible' -> Decimal; 'No Charge' -> 0; 'Not Applicable' / '' -> None."""
    if raw is None:
        return None
    s = raw.strip()
    if not s or s.lower().startswith("not applicable"):
        return None
    if s.lower().startswith("no charge"):
        return Decimal(0)
    m = _MONEY.search(s)
    if not m:
        return None
    try:
        return Decimal(m.group(1).replace(",", ""))
    except InvalidOperation:
        return None


def parse_pct(raw: Optional[str]) -> Optional[float]:
    """'20% Coinsurance after deductible' -> 20.0; 'No Charge' -> 0.0; 'Not Applicable' -> None."""
    if raw is None:
        return None
    s = raw.strip()
    if not s or s.lower().startswith("not applicable"):
        return None
    if s.lower().startswith("no charge"):
        return 0.0
    m = _PCT.search(s)
    return float(m.group(1)) if m else None


def _col(row: dict, name: str) -> Optional[str]:
    """Case-insensitive column lookup (PUF headers vary in case between years)."""
    if name in row:
        return row[name]
    low = name.lower()
    for k, v in row.items():
        if k and k.lower() == low:
            return v
    return None


def standard_id(plan_id: str) -> str:
    """'12345AZ0010001-01' -> '12345AZ0010001' (cost-sharing-reduction variants share one standard component)."""
    return (plan_id or "").split("-")[0].strip()


def _read_csv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8-sig") as f:
        return [dict(r) for r in csv.DictReader(f)]


def load_rates(path: Path, age: int = PREMIUM_AGE) -> dict[str, Decimal]:
    """Standard component id -> monthly premium (age `age`, non-tobacco, lowest rating area)."""
    if not path.exists():
        return {}
    best: dict[str, tuple[str, Decimal]] = {}
    for r in _read_csv(path):
        if str(_col(r, "Age") or "").strip() != str(age):
            continue
        # The Rate PUF's Tobacco column is a rating-rule label, not a per-row tobacco status:
        # "No Preference" means the issuer charges one rate regardless of tobacco use, and
        # "Tobacco User/Non-Tobacco User" means the published IndividualRate is the non-tobacco
        # rate (tobacco surcharges are applied separately and are not in this column). Both
        # cases give the non-tobacco premium we want; no row needs to be excluded on this basis.
        rate = parse_money("$" + (_col(r, "IndividualRate") or "").replace("$", "").strip())
        if rate is None or rate <= 0:
            continue
        sid = standard_id(_col(r, "PlanId") or "")
        area = (_col(r, "RatingAreaId") or "").strip()
        key = (area.replace("Rating Area ", "").zfill(3), area)
        if sid not in best or key[0] < best[sid][0]:
            best[sid] = (key[0], rate)
    return {k: v[1] for k, v in best.items()}


def _evidence(file_name: str, plan_id: str, column: str, raw: Optional[str]) -> Evidence:
    return Evidence(doc_id=file_name, section=plan_id[:80], text=f"{file_name}:{plan_id}:{column}={(raw or '').strip()}"[:1200])


def _tuple(pid: str, tid: str, rel: Relation, obj: str, q: Qualifiers, ev: Evidence) -> ClauseTuple:
    return ClauseTuple(id=tid, policy_id=pid, head=pid, relation=rel, object=obj, qualifiers=q, evidence=ev,
                       source_tier=SourceTier.POLICY_DOC_VERIFIED, extractor_version=EXTRACTOR_VERSION)


def _plan_record(sid: str, attrs: dict, benefit_rows: Iterable[dict], file_name: str, premium: Optional[Decimal]) -> Optional[PolicyRecord]:
    if (_col(attrs, "DentalOnlyPlan") or "No").strip().lower() == "yes":
        return None
    deductible = parse_money(_col(attrs, "TEHBDedInnTier1Individual"))
    moop = parse_money(_col(attrs, "TEHBInnTier1IndividualMOOP"))
    tuples: list[ClauseTuple] = []
    seen: set[str] = set()
    for r in sorted(benefit_rows, key=lambda x: (_col(x, "BenefitName") or "")):
        bname = (_col(r, "BenefitName") or "").strip()
        events = BENEFIT_EVENTS.get(bname.lower())
        if not events:
            continue
        covered = (_col(r, "IsCovered") or "").strip().lower() == "covered"
        col = r.get("_column") or "BenefitName"  # wide layout: the actual column group
        ev = _evidence(file_name, sid, col, f"{bname}; copay={(_col(r, 'CopayInnTier1') or '').strip()}; coins={(_col(r, 'CoinsInnTier1') or '').strip()}")
        for e in events:
            if e in seen:
                continue
            seen.add(e)
            if not covered:
                tuples.append(_tuple(sid, f"x_{e.lower()}", Relation.EXCLUDES, e, Qualifiers(basis=Basis.INDEMNITY),
                                     _evidence(file_name, sid, col if col != "BenefitName" else "IsCovered", _col(r, "IsCovered"))))
                continue
            q = Qualifiers(
                basis=Basis.INDEMNITY, currency="USD", other_insurance="EXCESS",
                copay_amount=parse_money(_col(r, "CopayInnTier1")), copay_pct=parse_pct(_col(r, "CoinsInnTier1")),
                deductible_amount=deductible, copay_cap=moop,
            )
            if (_col(r, "QuantLimitOnSvc") or "").strip().lower() == "yes":
                unit = (_col(r, "LimitUnit") or "").strip().lower()
                try:
                    qty = int(Decimal((_col(r, "LimitQty") or "").strip() or "0"))
                except InvalidOperation:
                    qty = 0
                if qty and "day" in unit:
                    if "year" in unit:
                        q.max_days_per_year = qty
                    else:
                        q.max_days = qty
            tuples.append(_tuple(sid, f"c_{e.lower()}", Relation.COVERS, e, q, ev))
    if not any(t.relation == Relation.COVERS for t in tuples):
        return None
    if moop is not None:
        tuples.append(_tuple(sid, "d_oop_max", Relation.DEFINES, "OOP_MAX", Qualifiers(amount=moop, currency="USD", formula=f"in-network individual out-of-pocket maximum USD {moop:,.0f}/year"),
                             _evidence(file_name, sid, "TEHBInnTier1IndividualMOOP", _col(attrs, "TEHBInnTier1IndividualMOOP"))))
    if deductible is not None:
        tuples.append(_tuple(sid, "d_deductible", Relation.DEFINES, "DEDUCTIBLE", Qualifiers(amount=deductible, currency="USD", formula=f"in-network individual deductible USD {deductible:,.0f}/year"),
                             _evidence(file_name, sid, "TEHBDedInnTier1Individual", _col(attrs, "TEHBDedInnTier1Individual"))))
    if premium is not None:
        tuples.append(_tuple(sid, "d_premium", Relation.DEFINES, "PREMIUM", Qualifiers(amount=premium, currency="USD", formula=f"USD {premium:,.2f}/month, age {PREMIUM_AGE}, non-tobacco (Rate PUF)"),
                             _evidence(RATES_FILE, sid, "IndividualRate", str(premium))))
    metal = (_col(attrs, "MetalLevel") or "").strip()
    tuples.append(_tuple(sid, "d_metal", Relation.DEFINES, "METAL_LEVEL", Qualifiers(plan=metal[:40] or None, formula=f"{metal} / {(_col(attrs, 'PlanType') or '').strip()}"[:200]),
                         _evidence(file_name, sid, "MetalLevel", metal)))
    insurer = (_col(attrs, "IssuerMarketPlaceMarketingName") or _col(attrs, "IssuerId") or "unknown issuer").strip()
    name = (_col(attrs, "PlanMarketingName") or sid).strip()
    return PolicyRecord(
        id=sid, doc_id=file_name, insurer=insurer[:80], product_name=name[:120], product_type="health_indemnity",
        basis=Basis.INDEMNITY, status="active", currency="USD", tuples=tuples, verified=True, extraction_coverage=1.0,
    )


def _variant(plan_id: str) -> str:
    parts = (plan_id or "").split("-")
    return parts[1].strip() if len(parts) > 1 else ""


def _wide_benefits(row: dict) -> list[dict]:
    """Benefit rows synthesised from a wide-layout plan row (see module docstring)."""
    out = []
    for prefix, (bname, _events) in WIDE_BENEFITS.items():
        if _col(row, f"{prefix}_covered") is None:
            continue
        out.append({"BenefitName": bname, "IsCovered": _col(row, f"{prefix}_covered"), "CopayInnTier1": _col(row, f"{prefix}_copay_inn"),
                    "CoinsInnTier1": _col(row, f"{prefix}_coins_inn"), "QuantLimitOnSvc": _col(row, f"{prefix}_quant_limit"),
                    "LimitQty": _col(row, f"{prefix}_limit_qty"), "LimitUnit": _col(row, f"{prefix}_limit_unit"), "_column": f"{prefix}_*"})
    return out


def load_cms_plans(path: str | Path, benefits_path: Optional[str | Path] = None, rates_path: Optional[str | Path] = None) -> list[PolicyRecord]:
    """Read the one-state PUF extract at `path` into `PolicyRecord`s (sorted by plan id).

    Accepts the wide and the long layout (module docstring). `benefits_path` defaults to
    `cms_benefits_py2026.csv` next to `path` and is only used for a long layout without
    `BenefitName`; `rates_path` defaults to `cms_rates_py2026.csv` next to `path` and is optional.
    Missing `path` -> empty list.
    """
    path = Path(path)
    if not path.exists():
        return []
    rows = _read_csv(path)
    if not rows:
        return []
    wide = any(_col(rows[0], f"{p}_covered") is not None for p in WIDE_BENEFITS)
    has_benefits = _col(rows[0], "BenefitName") is not None
    attrs: dict[str, dict] = {}
    rank: dict[str, int] = {}
    benefits: dict[str, list[dict]] = {}
    for r in rows:
        sid = standard_id(_col(r, "PlanId") or _col(r, "StandardComponentId") or "")
        if not sid:
            continue
        var = _variant(_col(r, "PlanId") or "")
        if var not in STANDARD_VARIANTS:
            continue  # cost-sharing-reduction variants
        if (_col(r, "MarketCoverage") or "Individual").strip().lower().startswith("shop"):
            continue
        rk = STANDARD_VARIANTS.index(var)
        if wide:
            if sid not in attrs or rk < rank[sid]:
                attrs[sid], rank[sid] = r, rk
                benefits[sid] = _wide_benefits(r)
        else:
            attrs.setdefault(sid, r)
            if has_benefits:
                benefits.setdefault(sid, []).append(r)
    if not wide and not has_benefits:
        bpath = Path(benefits_path) if benefits_path else path.with_name(BENEFITS_FILE)
        if bpath.exists():
            for r in _read_csv(bpath):
                sid = standard_id(_col(r, "PlanId") or "")
                if _variant(_col(r, "PlanId") or "") not in STANDARD_VARIANTS:
                    continue
                if sid in attrs:
                    benefits.setdefault(sid, []).append(r)
    rates = load_rates(Path(rates_path) if rates_path else path.with_name(RATES_FILE))
    out: list[PolicyRecord] = []
    for sid in sorted(attrs):
        rec = _plan_record(sid, attrs[sid], benefits.get(sid, []), path.name, rates.get(sid))
        if rec is not None:
            out.append(rec)
    return out


def premium_monthly(plan: PolicyRecord) -> Optional[Decimal]:
    """Monthly premium from a `DEFINES PREMIUM` (Rate PUF) or `DEFINES MOCK_PREMIUM` tuple; None when unknown."""
    for t in plan.tuples:
        if t.relation == Relation.DEFINES and t.object in ("PREMIUM", "MOCK_PREMIUM") and t.qualifiers.amount is not None:
            return Decimal(t.qualifiers.amount)
    return None


def defined_amount(plan: PolicyRecord, obj: str) -> Optional[Decimal]:
    for t in plan.tuples:
        if t.relation == Relation.DEFINES and t.object == obj and t.qualifiers.amount is not None:
            return Decimal(t.qualifiers.amount)
    return None


def oop_max(plan: PolicyRecord) -> Optional[Decimal]:
    """Annual out-of-pocket maximum (`DEFINES OOP_MAX`, else the largest `copay_cap` of a COVERS tuple)."""
    v = defined_amount(plan, "OOP_MAX")
    if v is not None:
        return v
    caps = [t.qualifiers.copay_cap for t in plan.tuples_by(Relation.COVERS) if t.qualifiers.copay_cap is not None]
    return max(caps) if caps else None


def deductible(plan: PolicyRecord) -> Optional[Decimal]:
    v = defined_amount(plan, "DEDUCTIBLE")
    if v is not None:
        return v
    ds = [t.qualifiers.deductible_amount for t in plan.tuples_by(Relation.COVERS) if t.qualifiers.deductible_amount is not None]
    return max(ds) if ds else None


def metal_level(plan: PolicyRecord) -> Optional[str]:
    for t in plan.tuples:
        if t.relation == Relation.DEFINES and t.object == "METAL_LEVEL":
            return t.qualifiers.plan
    return None
