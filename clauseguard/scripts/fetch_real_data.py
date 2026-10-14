"""Download and derive the real public datasets kept under ``data/real/``.

Every step is idempotent and resumable: raw downloads are kept under
``data/real/raw/`` (ignored by git) and skipped when already present, and derived
files are rebuilt only when missing or when ``--force`` is given. Network access is
polite: one request per second to any single host and an explicit User-Agent.

Sections (select with ``--only``):

``cms``
    CMS Health Insurance Exchange Public Use Files, plan year 2026 (Plan Attributes
    PUF and Benefits and Cost Sharing PUF). Produces ``cms_plans_py2026.csv``, a
    compact per-plan table for the state with the most individual medical plans.
``rates``
    CMS Rate PUF, plan year 2026. Produces ``cms_rates_py2026.csv``: monthly
    non-tobacco premiums at ages 21, 30, 40 and 50 per rating area, same state as ``cms``.
``insuranceqa``
    InsuranceQA V2 (Feng et al., 2015). Produces ``insuranceqa_questions.jsonl`` and a
    200-question keyword-stratified sample ``insuranceqa_sample200.jsonl``.
``fos``
    UK Financial Ombudsman Service published decisions (insurance sector). Produces
    ``fos_decisions.jsonl`` with decision text and the policy wording quoted in it.
``riplay``
    Indonesian product summaries (RIPLAY Umum) published by insurers. Produces
    ``riplay/<insurer>_<product>.pdf`` and ``riplay/manifest.json``.
``kff``
    CMS Transparency in Coverage PUF (PY2025 release, 2023 claims), the data behind
    the KFF analysis of Marketplace claim denials. Produces ``kff_denials_2023.csv``
    and ``kff_denials_2023_published.csv``.
``icd10cm``
    ICD-10-CM code descriptions (CMS/NCHS, FY2027 release, public domain). Produces
    ``icd10cm_codes.txt``: one line per billable code, code then description.

Usage::

    python scripts/fetch_real_data.py                 # everything
    python scripts/fetch_real_data.py --only cms,kff  # a subset
    python scripts/fetch_real_data.py --force         # rebuild derived files
    python scripts/fetch_real_data.py --fos-target 50 # fewer ombudsman decisions

Only the Python standard library plus ``httpx`` and ``pymupdf`` (both already in
``requirements.txt``) are needed.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import logging
import random
import re
import sys
import time
import zipfile
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterable, Iterator
from urllib.parse import quote, urlencode

import httpx

ROOT = Path(__file__).resolve().parents[1]
REAL_DIR = ROOT / "data" / "real"
RAW_DIR = REAL_DIR / "raw"
RIPLAY_DIR = REAL_DIR / "riplay"
MANIFEST_PATH = REAL_DIR / "manifest.json"

USER_AGENT = "clauseguard-data-fetch/1.0 (research use; polite, 1 request/s per host)"
MIN_INTERVAL_S = 1.0
LOG = logging.getLogger("fetch_real_data")


# --------------------------------------------------------------------------- #
# HTTP helpers
# --------------------------------------------------------------------------- #
class PoliteClient:
    """Thin wrapper around ``httpx.Client`` that rate-limits per host."""

    def __init__(self, min_interval_s: float = MIN_INTERVAL_S, timeout_s: float = 120.0) -> None:
        self._client = httpx.Client(
            headers={"User-Agent": USER_AGENT, "Accept": "*/*"},
            follow_redirects=True,
            timeout=timeout_s,
        )
        self._min_interval = min_interval_s
        self._last_hit: dict[str, float] = {}

    def _wait(self, url: str) -> None:
        host = httpx.URL(url).host
        elapsed = time.monotonic() - self._last_hit.get(host, 0.0)
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_hit[host] = time.monotonic()

    def get_text(self, url: str) -> str:
        self._wait(url)
        response = self._client.get(url)
        response.raise_for_status()
        return response.text

    def download(self, url: str, dest: Path, force: bool = False) -> Path:
        """Stream ``url`` to ``dest`` unless it already exists; returns ``dest``."""
        if dest.exists() and dest.stat().st_size > 0 and not force:
            LOG.debug("exists, skipping download: %s", dest.name)
            return dest
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(dest.suffix + ".part")
        self._wait(url)
        with self._client.stream("GET", url) as response:
            response.raise_for_status()
            with tmp.open("wb") as fh:
                for chunk in response.iter_bytes(1 << 16):
                    fh.write(chunk)
        tmp.replace(dest)
        LOG.info("downloaded %s (%.1f MB)", dest.name, dest.stat().st_size / 1e6)
        return dest

    def close(self) -> None:
        self._client.close()


def sha256_of(path: Path) -> str:
    """Return the hex SHA-256 digest of a file."""
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_manifest() -> dict:
    if MANIFEST_PATH.exists():
        return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    return {"generated_by": "scripts/fetch_real_data.py", "sources": {}}


def record_source(manifest: dict, key: str, url: str, path: Path, **extra: object) -> None:
    """Record provenance (URL, download date, size, hash) of a raw or derived file."""
    manifest["sources"][key] = {
        "url": url,
        "path": str(path.relative_to(ROOT)).replace("\\", "/"),
        "downloaded_on": date.today().isoformat(),
        "bytes": path.stat().st_size,
        "sha256": sha256_of(path),
        **extra,
    }


def save_manifest(manifest: dict) -> None:
    manifest["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: Iterable[dict]) -> int:
    count = 0
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            count += 1
    return count


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


# --------------------------------------------------------------------------- #
# 1. CMS Exchange PUFs, plan year 2026
# --------------------------------------------------------------------------- #
CMS_PLAN_ATTR_URL = "https://download.cms.gov/marketplace-puf/2026/plan-attributes-puf.zip"
CMS_BENEFITS_URL = "https://download.cms.gov/marketplace-puf/2026/benefits-and-cost-sharing-puf.zip"
CMS_OUT = REAL_DIR / "cms_plans_py2026.csv"
CMS_RATE_URL = "https://download.cms.gov/marketplace-puf/2026/rate-puf.zip"
CMS_RATES_OUT = REAL_DIR / "cms_rates_py2026.csv"
CMS_RATE_AGES = ("21", "30", "40", "50")

# Benefit label used in the derived table -> exact ``BenefitName`` in the Benefits PUF.
CMS_BENEFITS: dict[str, str] = {
    "inpatient_hospital": "Inpatient Hospital Services (e.g., Hospital Stay)",
    "emergency_room": "Emergency Room Services",
    "primary_care": "Primary Care Visit to Treat an Injury or Illness",
    "specialist": "Specialist Visit",
    "generic_drugs": "Generic Drugs",
    "mental_health_inpatient": "Mental/Behavioral Health Inpatient Services",
    "maternity_delivery": "Delivery and All Inpatient Services for Maternity Care",
}
# Plan Attributes columns copied verbatim (see data/real/README.md for meaning).
CMS_PLAN_COLUMNS: list[str] = [
    "StateCode",
    "IssuerId",
    "IssuerMarketPlaceMarketingName",
    "StandardComponentId",
    "PlanId",
    "PlanMarketingName",
    "PlanType",
    "MetalLevel",
    "CSRVariationType",
    "QHPNonQHPTypeId",
    "IsHSAEligible",
    "MedicalDrugDeductiblesIntegrated",
    "MedicalDrugMaximumOutofPocketIntegrated",
    "MEHBDedInnTier1Individual",
    "TEHBDedInnTier1Individual",
    "MEHBInnTier1IndividualMOOP",
    "TEHBInnTier1IndividualMOOP",
]


def _open_zip_csv(zip_path: Path) -> Iterator[dict[str, str]]:
    """Stream rows of the single CSV inside a CMS PUF zip without extracting it."""
    with zipfile.ZipFile(zip_path) as zf:
        csv_names = [n for n in zf.namelist() if n.lower().endswith(".csv")]
        if len(csv_names) != 1:
            raise RuntimeError(f"expected one CSV in {zip_path.name}, found {csv_names}")
        with zf.open(csv_names[0]) as raw:
            text = io.TextIOWrapper(raw, encoding="utf-8-sig", errors="replace", newline="")
            yield from csv.DictReader(text)


def _individual_medical_plans(plan_zip: Path) -> list[dict[str, str]]:
    """Return Plan Attributes rows for individual-market, non-dental-only plans."""
    return [
        r for r in _open_zip_csv(plan_zip)
        if r["DentalOnlyPlan"] == "No" and r["MarketCoverage"] == "Individual"
    ]


def _pick_state(plan_rows: list[dict[str, str]]) -> str:
    """Return the state with the most individual-market medical plan variants."""
    counts = Counter(r["StateCode"] for r in plan_rows)
    state, _ = counts.most_common(1)[0]
    LOG.info("state with most individual medical plans: %s (%s)", state, counts.most_common(5))
    return state


def build_cms_table(client: PoliteClient, manifest: dict, force: bool) -> None:
    """Build ``cms_plans_py2026.csv`` for the state with the most plans."""
    raw_dir = RAW_DIR / "cms"
    plan_zip = client.download(CMS_PLAN_ATTR_URL, raw_dir / "plan-attributes-puf.zip")
    benefits_zip = client.download(CMS_BENEFITS_URL, raw_dir / "benefits-and-cost-sharing-puf.zip")
    record_source(manifest, "cms_plan_attributes_py2026", CMS_PLAN_ATTR_URL, plan_zip, license="US public domain")
    record_source(manifest, "cms_benefits_cost_sharing_py2026", CMS_BENEFITS_URL, benefits_zip, license="US public domain")
    if CMS_OUT.exists() and not force:
        LOG.info("exists, skipping derive: %s", CMS_OUT.name)
        return

    plan_rows = _individual_medical_plans(plan_zip)
    state = _pick_state(plan_rows)
    plans: dict[str, dict[str, str]] = {}
    for r in plan_rows:
        if r["StateCode"] != state:
            continue
        plans[r["PlanId"]] = {col: r.get(col, "") for col in CMS_PLAN_COLUMNS}
    LOG.info("%s: %d plan variants", state, len(plans))

    wanted = {name: label for label, name in CMS_BENEFITS.items()}
    benefit_cells: dict[str, dict[str, str]] = defaultdict(dict)
    seen_state = False
    for r in _open_zip_csv(benefits_zip):
        if r["StateCode"] != state:
            if seen_state:
                break  # the file is sorted by state; nothing more to read
            continue
        seen_state = True
        label = wanted.get(r["BenefitName"])
        if label is None or r["PlanId"] not in plans:
            continue
        cells = benefit_cells[r["PlanId"]]
        cells[f"{label}_covered"] = r["IsCovered"]
        cells[f"{label}_copay_inn"] = r["CopayInnTier1"]
        cells[f"{label}_coins_inn"] = r["CoinsInnTier1"]
        cells[f"{label}_quant_limit"] = r["QuantLimitOnSvc"]
        cells[f"{label}_limit_qty"] = r["LimitQty"]
        cells[f"{label}_limit_unit"] = r["LimitUnit"]

    benefit_columns = [
        f"{label}_{suffix}"
        for label in CMS_BENEFITS
        for suffix in ("covered", "copay_inn", "coins_inn", "quant_limit", "limit_qty", "limit_unit")
    ]
    derived_columns = ["deductible_individual_inn", "oop_max_individual_inn", "premium_note"]
    header = CMS_PLAN_COLUMNS + derived_columns + benefit_columns
    with CMS_OUT.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=header)
        writer.writeheader()
        for plan_id in sorted(plans):
            row = dict(plans[plan_id])
            integrated_ded = row["MedicalDrugDeductiblesIntegrated"] == "Yes"
            integrated_moop = row["MedicalDrugMaximumOutofPocketIntegrated"] == "Yes"
            row["deductible_individual_inn"] = (
                row["TEHBDedInnTier1Individual"] if integrated_ded else row["MEHBDedInnTier1Individual"]
            )
            row["oop_max_individual_inn"] = (
                row["TEHBInnTier1IndividualMOOP"] if integrated_moop else row["MEHBInnTier1IndividualMOOP"]
            )
            row["premium_note"] = "premiums are not in these PUFs; see the separate Rate PUF"
            for col in benefit_columns:
                row[col] = benefit_cells.get(plan_id, {}).get(col, "")
            writer.writerow(row)
    record_source(manifest, "cms_plans_py2026_csv", "derived", CMS_OUT, state=state, rows=len(plans))
    LOG.info("wrote %s (%d rows, %.2f MB)", CMS_OUT.name, len(plans), CMS_OUT.stat().st_size / 1e6)


def build_cms_rates(client: PoliteClient, manifest: dict, force: bool) -> None:
    """Build ``cms_rates_py2026.csv`` (monthly non-tobacco premiums) for the same state."""
    raw_dir = RAW_DIR / "cms"
    plan_zip = client.download(CMS_PLAN_ATTR_URL, raw_dir / "plan-attributes-puf.zip")
    rate_zip = client.download(CMS_RATE_URL, raw_dir / "rate-puf.zip")
    record_source(manifest, "cms_rate_py2026", CMS_RATE_URL, rate_zip, license="US public domain")
    if CMS_RATES_OUT.exists() and not force:
        LOG.info("exists, skipping derive: %s", CMS_RATES_OUT.name)
        return

    state = _pick_state(_individual_medical_plans(plan_zip))
    standard_ids = {r["StandardComponentId"] for r in _individual_medical_plans(plan_zip) if r["StateCode"] == state}
    header = ["PlanId", "Age", "RatingAreaId", "IndividualRate", "Tobacco", "RateEffectiveDate", "RateExpirationDate"]
    rows: list[dict[str, str]] = []
    seen_state = False
    for r in _open_zip_csv(rate_zip):
        if r["StateCode"] != state:
            if seen_state:
                break  # the file is sorted by state
            continue
        seen_state = True
        # ``PlanId`` in the Rate PUF is the 14-character standard component id; rates apply
        # to every cost-sharing variant of that plan. ``IndividualRate`` is the non-tobacco
        # premium under both tobacco settings.
        if r["Age"] not in CMS_RATE_AGES or r["PlanId"] not in standard_ids:
            continue
        rows.append({col: r[col] for col in header})
    rows.sort(key=lambda r: (r["PlanId"], r["RatingAreaId"], int(r["Age"])))
    with CMS_RATES_OUT.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=header)
        writer.writeheader()
        writer.writerows(rows)
    record_source(manifest, "cms_rates_py2026_csv", "derived", CMS_RATES_OUT, state=state, rows=len(rows), ages=list(CMS_RATE_AGES))
    LOG.info("wrote %s (%d rows, %.2f MB)", CMS_RATES_OUT.name, len(rows), CMS_RATES_OUT.stat().st_size / 1e6)


# --------------------------------------------------------------------------- #
# 2. InsuranceQA V2
# --------------------------------------------------------------------------- #
IQA_BASE = "https://raw.githubusercontent.com/shuzi/insuranceQA/master/V2/"
IQA_VOCAB_URL = IQA_BASE + "vocabulary"
IQA_QUESTIONS_URL = IQA_BASE + "InsuranceQA.question.anslabel.raw.encoded.gz"
IQA_OUT = REAL_DIR / "insuranceqa_questions.jsonl"
IQA_SAMPLE_OUT = REAL_DIR / "insuranceqa_sample200.jsonl"
IQA_SAMPLE_SIZE = 200
IQA_SEED = 20260101

# Ordered keyword buckets used for ``topic_guess`` and for stratified sampling.
IQA_TOPICS: list[tuple[str, tuple[str, ...]]] = [
    ("claims", ("claim", "payout", "pay out", "paid out", "denied", "deny", "reimburse")),
    ("exclusions_waiting", ("exclusion", "exclude", "waiting period", "pre-existing", "preexisting", "elimination period")),
    ("premiums_cost", ("premium", "cost", "price", "expensive", "cheap", "rate", "afford", "how much")),
    ("cancellation_lapse", ("cancel", "lapse", "terminate", "surrender", "refund", "grace period")),
    ("beneficiary_payout", ("beneficiary", "death benefit", "payable", "estate")),
    ("hospital_medical", ("hospital", "surgery", "doctor", "prescription", "medical", "dental", "maternity", "pregnan")),
    ("accident_disability", ("accident", "disability", "disabled", "injury", "injured")),
    ("critical_illness", ("critical illness", "cancer", "heart attack", "stroke", "terminal")),
    ("eligibility_underwriting", ("qualify", "eligib", "underwrit", "medical exam", "age limit", "too old")),
    ("coverage_scope", ("cover", "coverage", "protect", "include")),
    ("tax_regulation", ("tax", "deductible", "irs", "law", "legal", "required by")),
]


def guess_topic(question: str) -> str:
    """Return the first keyword bucket matching ``question`` (``general`` if none)."""
    text = question.lower()
    for topic, keywords in IQA_TOPICS:
        if any(k in text for k in keywords):
            return topic
    return "general"


def _is_english(text: str) -> bool:
    """Cheap language filter: mostly ASCII letters, at least two words."""
    letters = [c for c in text if c.isalpha()]
    if len(letters) < 6 or len(text.split()) < 2:
        return False
    ascii_letters = sum(1 for c in letters if c.isascii())
    return ascii_letters / len(letters) > 0.95


def build_insuranceqa(client: PoliteClient, manifest: dict, force: bool) -> None:
    """Decode InsuranceQA V2 questions and write the full and sampled JSONL files."""
    raw_dir = RAW_DIR / "insuranceqa"
    vocab_path = client.download(IQA_VOCAB_URL, raw_dir / "vocabulary")
    questions_path = client.download(IQA_QUESTIONS_URL, raw_dir / "InsuranceQA.question.anslabel.raw.encoded.gz")
    license_note = "research use only; cite Feng et al., ASRU 2015"
    record_source(manifest, "insuranceqa_vocabulary", IQA_VOCAB_URL, vocab_path, license=license_note)
    record_source(manifest, "insuranceqa_questions_raw", IQA_QUESTIONS_URL, questions_path, license=license_note)
    if IQA_OUT.exists() and IQA_SAMPLE_OUT.exists() and not force:
        LOG.info("exists, skipping derive: %s", IQA_OUT.name)
        return

    vocab: dict[str, str] = {}
    with vocab_path.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            key, _, word = line.rstrip("\n").partition("\t")
            vocab[key] = word

    rows: list[dict] = []
    seen: set[str] = set()
    dropped_dup = dropped_lang = 0
    with gzip.open(questions_path, "rt", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 2:
                continue
            domain, encoded = parts[0], parts[1]
            question = " ".join(vocab.get(tok, tok) for tok in encoded.split()).strip()
            question = re.sub(r"\s+", " ", question)
            key = re.sub(r"[^a-z0-9 ]", "", question.lower()).strip()
            if key in seen:
                dropped_dup += 1
                continue
            if not _is_english(question):
                dropped_lang += 1
                continue
            seen.add(key)
            rows.append(
                {
                    "id": f"iqa-{len(rows) + 1:05d}",
                    "question": question,
                    "topic_guess": guess_topic(question),
                    "dataset_domain": domain,
                }
            )
    n_all = write_jsonl(IQA_OUT, rows)
    LOG.info("wrote %s (%d questions; dropped %d duplicates, %d non-English)", IQA_OUT.name, n_all, dropped_dup, dropped_lang)

    # Stratified sample: equal share per topic bucket, remainder filled from the pool.
    rng = random.Random(IQA_SEED)
    by_topic: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_topic[row["topic_guess"]].append(row)
    topics = sorted(by_topic)
    per_topic = IQA_SAMPLE_SIZE // len(topics)
    sample: list[dict] = []
    for topic in topics:
        pool = by_topic[topic]
        rng.shuffle(pool)
        sample.extend(pool[:per_topic])
    chosen = {r["id"] for r in sample}
    remainder = [r for r in rows if r["id"] not in chosen]
    rng.shuffle(remainder)
    sample.extend(remainder[: IQA_SAMPLE_SIZE - len(sample)])
    sample.sort(key=lambda r: r["id"])
    n_sample = write_jsonl(IQA_SAMPLE_OUT, sample)
    record_source(manifest, "insuranceqa_questions_jsonl", "derived", IQA_OUT, rows=n_all)
    record_source(manifest, "insuranceqa_sample200_jsonl", "derived", IQA_SAMPLE_OUT, rows=n_sample, seed=IQA_SEED)
    LOG.info("wrote %s (%d questions, %s)", IQA_SAMPLE_OUT.name, n_sample, dict(Counter(r["topic_guess"] for r in sample)))


# --------------------------------------------------------------------------- #
# 3. UK Financial Ombudsman Service decisions
# --------------------------------------------------------------------------- #
FOS_SEARCH_URL = "https://www.financial-ombudsman.org.uk/businesses/resolving-complaint/ombudsman-decisions/search"
FOS_PDF_URL = "https://www.financial-ombudsman.org.uk/decision/{ref}.pdf"
FOS_INSURANCE_SECTOR_ID = 3  # "Insurance (excluding PPI)" in the search form
FOS_PAGE_SIZE = 10
FOS_OUT = REAL_DIR / "fos_decisions.jsonl"
FOS_CLAUSE_TERMS = ["waiting period", "pre-existing", "exclusion", "late notification", "coordination"]
FOS_PRODUCT_TERMS = ["private medical", "life", "income protection", "personal accident", "travel"]
# Product label -> phrases that identify it in the decision text (first match wins).
FOS_PRODUCTS: list[tuple[str, tuple[str, ...]]] = [
    ("income_protection", ("income protection", "permanent health insurance", "phi policy")),
    ("personal_accident", ("personal accident", "accident policy", "accidental death")),
    ("travel", ("travel insurance", "travel policy", "holiday", "trip")),
    ("health_medical", ("private medical", "medical insurance", "health insurance", "health cash plan", "dental plan", "treatment")),
    ("life", ("life insurance", "life assurance", "life policy", "life cover", "critical illness", "terminal illness", "over 50", "funeral")),
]
FOS_RESULT_RE = re.compile(
    r'href="decision/(?P<ref>DRN-?\d+)\.pdf".*?<em>(?P<date>[^<]+)</em>'
    r'(?:.*?<span class="search-result__separator"></span>\s*(?P<business>[^<]+?)\s*)?'
    r'<span class="search-result__separator"></span>\s*(?P<outcome>Upheld|Not upheld)',
    re.S,
)
# Decisions quote policy wording in double or single typographic quotes; an apostrophe
# inside a single-quoted passage (e.g. "insurer's") is a U+2019 followed by a letter.
_LDQ, _RDQ, _LSQ, _RSQ = chr(0x201C), chr(0x201D), chr(0x2018), chr(0x2019)
FOS_QUOTE_RE = re.compile(
    f"[{_LDQ}\"]([^{_RDQ}\"]{{40,600}})[{_RDQ}\"]"
    f"|{_LSQ}((?:[^{_LSQ}{_RSQ}]|{_RSQ}(?=[A-Za-z])){{40,600}}){_RSQ}(?![A-Za-z])"
)


@dataclass
class FosHit:
    """One row of the ombudsman decision search listing."""

    ref: str
    date: str
    business: str
    outcome: str
    query: str
    product_hint: str


def _fos_search(client: PoliteClient, keyword: str, start: int) -> tuple[list[FosHit], int]:
    """Return (hits on this page, total result count) for a keyword search."""
    params = {
        "Keyword": keyword,
        f"IndustrySectorID[{FOS_INSURANCE_SECTOR_ID}]": str(FOS_INSURANCE_SECTOR_ID),
        "IsUpheld[0]": "0",
        "IsUpheld[1]": "1",
        "Sort": "relevance",
        "Start": str(start),
    }
    html = client.get_text(f"{FOS_SEARCH_URL}?{urlencode(params, quote_via=quote)}")
    total_match = re.search(r"returned\s+([\d,]+)\s+results", html)
    total = int(total_match.group(1).replace(",", "")) if total_match else 0
    hits: list[FosHit] = []
    for block in html.split('<li>')[1:]:
        m = FOS_RESULT_RE.search(block)
        if not m:
            continue
        hits.append(
            FosHit(
                ref=m.group("ref"),
                date=_parse_fos_date(m.group("date").strip()),
                business=re.sub(r"\s+", " ", (m.group("business") or "").replace("&amp;", "&")).strip(),
                outcome="upheld" if m.group("outcome") == "Upheld" else "not upheld",
                query=keyword,
                product_hint="",
            )
        )
    return hits, total


def _parse_fos_date(text: str) -> str:
    for fmt in ("%d %b %Y", "%d %B %Y"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return text


def _pdf_text(path: Path) -> str:
    import pymupdf  # imported lazily so the other sections do not need it

    with pymupdf.open(path) as doc:
        return "\n".join(page.get_text() for page in doc)


def _classify_product(text: str) -> str:
    lowered = text.lower()
    scores = {label: sum(lowered.count(p) for p in phrases) for label, phrases in FOS_PRODUCTS}
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "other"


def _quoted_clauses(text: str) -> list[str]:
    """Return de-duplicated passages quoted in the decision (policy wording cited verbatim)."""
    flat = re.sub(r"\s+", " ", text)
    out: list[str] = []
    for m in FOS_QUOTE_RE.finditer(flat):
        clause = (m.group(1) or m.group(2) or "").strip()
        if clause not in out:
            out.append(clause)
    return out


def build_fos(client: PoliteClient, manifest: dict, force: bool, target: int) -> None:
    """Collect ``target`` insurance decisions that quote policy wording."""
    raw_dir = RAW_DIR / "fos"
    raw_dir.mkdir(parents=True, exist_ok=True)
    existing = {} if force else {r["decision_id"]: r for r in read_jsonl(FOS_OUT)}
    kept: list[dict] = list(existing.values())
    rejected_path = raw_dir / "rejected.json"
    rejected: set[str] = set(json.loads(rejected_path.read_text()) if rejected_path.exists() and not force else [])
    if len(kept) >= target:
        LOG.info("%s already has %d decisions (target %d)", FOS_OUT.name, len(kept), target)
        return

    queries = [f'"{clause}" {product}' for clause in FOS_CLAUSE_TERMS for product in FOS_PRODUCT_TERMS]
    queue: list[FosHit] = []
    queued: set[str] = set()
    pages_per_query = 3
    for keyword in queries:
        for page in range(pages_per_query):
            try:
                hits, total = _fos_search(client, keyword, page * FOS_PAGE_SIZE)
            except httpx.HTTPError as exc:
                LOG.warning("search failed for %r: %s", keyword, exc)
                break
            LOG.info("search %r page %d: %d hits (total %d)", keyword, page, len(hits), total)
            for hit in hits:
                if hit.ref in queued or hit.ref in existing or hit.ref in rejected:
                    continue
                hit.product_hint = keyword
                queue.append(hit)
                queued.add(hit.ref)
            if (page + 1) * FOS_PAGE_SIZE >= total or not hits:
                break
        if len(queue) >= 3 * target:
            break
    LOG.info("%d candidate decisions queued", len(queue))

    for hit in queue:
        if len(kept) >= target:
            break
        pdf_path = raw_dir / f"{hit.ref}.pdf"
        try:
            client.download(FOS_PDF_URL.format(ref=hit.ref), pdf_path)
            text = _pdf_text(pdf_path)
        except (httpx.HTTPError, RuntimeError, ValueError) as exc:
            LOG.warning("%s: fetch/parse failed: %s", hit.ref, exc)
            rejected.add(hit.ref)
            continue
        product = _classify_product(text)
        clauses = _quoted_clauses(text)
        lowered = text.lower()
        if product == "other" or not clauses or not any(t in lowered for t in FOS_CLAUSE_TERMS):
            rejected.add(hit.ref)
            continue
        kept.append(
            {
                "decision_id": hit.ref,
                "date": hit.date,
                "business": hit.business,
                "product": product,
                "outcome": hit.outcome,
                "search_query": hit.query,
                "source_url": FOS_PDF_URL.format(ref=hit.ref),
                "text": text.strip(),
                "quoted_clauses": clauses,
            }
        )
        write_jsonl(FOS_OUT, kept)
        rejected_path.write_text(json.dumps(sorted(rejected)))
        LOG.info("kept %s (%s, %s, %d quotes) -> %d/%d", hit.ref, product, hit.outcome, len(clauses), len(kept), target)

    kept.sort(key=lambda r: r["decision_id"])
    n = write_jsonl(FOS_OUT, kept)
    rejected_path.write_text(json.dumps(sorted(rejected)))
    record_source(
        manifest,
        "fos_decisions_jsonl",
        FOS_SEARCH_URL,
        FOS_OUT,
        rows=n,
        products=dict(Counter(r["product"] for r in kept)),
        outcomes=dict(Counter(r["outcome"] for r in kept)),
        license="Crown copyright; Open Government Licence v3.0 (financial-ombudsman.org.uk)",
    )
    LOG.info("wrote %s (%d decisions)", FOS_OUT.name, n)


# --------------------------------------------------------------------------- #
# 4. Indonesian RIPLAY product summaries
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class RiplayDoc:
    """A publicly downloadable RIPLAY Umum (general product summary)."""

    insurer: str
    product: str
    product_type: str
    language: str
    url: str
    issuer_legal_name: str
    host_note: str = ""

    @property
    def filename(self) -> str:
        return f"{self.insurer}_{self.product}.pdf"


RIPLAY_DOCS: list[RiplayDoc] = [
    # hospital cash
    RiplayDoc("chubb", "hospital_cash_protection", "hospital_cash", "id",
              "https://www.chubb.com/content/dam/chubb-sites/chubb-com/id-id/lei-new-assets/riplay/pdf/asuransi-kesehatan-riplay-umum-hospital-cash-protection-rider.pdf",
              "PT Chubb Life Insurance Indonesia"),
    RiplayDoc("astra", "hospital_cash_plan", "hospital_cash", "id",
              "https://www.astralife.co.id/wp-content/uploads/2023/03/RIPLAY-Umum-Hospital-Cash-Plan-071223.pdf",
              "PT Asuransi Jiwa Astra"),
    RiplayDoc("sompo", "hospital_cash_plan_id", "hospital_cash", "id",
              "https://www.roojai.co.id/wp-content/uploads/2024/03/roojai-riplay-HCP-id-20230405.pdf",
              "PT Sompo Insurance Indonesia", "distributed via Roojai (roojai.co.id)"),
    RiplayDoc("sompo", "hospital_cash_plan_en", "hospital_cash", "en",
              "https://www.roojai.co.id/wp-content/uploads/2024/03/roojai-riplay-HCP-en-20230405.pdf",
              "PT Sompo Insurance Indonesia", "distributed via Roojai (roojai.co.id)"),
    RiplayDoc("axa_mandiri", "proteksi_ekstra_hospital_cash", "hospital_cash", "id",
              "https://www.axa-mandiri.co.id/documents/1415637/1443288/RIPLAY%20Umum%20Asuransi%20Kesehatan%20Proteksi%20Ekstra.pdf",
              "PT AXA Mandiri Financial Services"),
    # hospitalisation / medical
    RiplayDoc("chubb", "medical_pro", "hospitalisation", "id",
              "https://www.chubb.com/content/dam/chubb-sites/chubb-com/id-id/lei-new-assets/riplay/pdf/asuransi-kesehatan-riplay-umum-asuransi-medical-pro.pdf",
              "PT Chubb Life Insurance Indonesia"),
    RiplayDoc("astra", "medis_dan_bedah", "hospitalisation", "id",
              "https://www.astralife.co.id/wp-content/uploads/2023/03/RIPLAY_Umum_Asuransi_Tambahan_Medis_dan_Bedah_010426.pdf",
              "PT Asuransi Jiwa Astra"),
    RiplayDoc("axa", "his_plus_hospital_income_surgical", "hospitalisation", "id",
              "https://www.axa.co.id/documents/1127000/0/2026+Asuransi+Tambahan+HIS+Plus+-+RIPLAY+Umum_v1.6-Clean.pdf/a3505db4-7c93-2274-ad59-fbae54843ab1?t=1780389491121",
              "PT AXA Financial Indonesia"),
    RiplayDoc("sequis", "m_protection_health", "hospitalisation", "id",
              "https://sequis.co.id/Products/MiProtection/RIPLay%20Umum%20M-Protection_27062022.pdf",
              "PT Asuransi Jiwa Sequis Life"),
    RiplayDoc("sinarmas", "simas_sehat_executive", "hospitalisation", "id",
              "https://www.sinarmas.co.id/property/9564570/RIPLAY-UMUM-SIMAS-SEHAT-EXECUTIVE.pdf",
              "PT Asuransi Sinar Mas", "general insurer of the Sinar Mas group (not Sinarmas MSIG Life)"),
    # personal accident
    RiplayDoc("chubb", "personal_accident", "personal_accident", "id",
              "https://www.chubb.com/content/dam/chubb-sites/chubb/id-id/documents/riplay-chubb-general/riplay-versi-umum-personal-accident-insurance-dbs.pdf",
              "PT Chubb General Insurance Indonesia"),
    RiplayDoc("chubb", "proteksi_diri_extra", "personal_accident", "id",
              "https://www.chubb.com/content/dam/chubb-sites/chubb-com/id-id/lei-new-assets/riplay/pdf/asuransi-berjangka-riplay-umum-proteksi-diri-extra.pdf",
              "PT Chubb Life Insurance Indonesia"),
    RiplayDoc("astra", "kecelakaan_diri", "personal_accident", "id",
              "https://www.astralife.co.id/wp-content/uploads/2023/03/RIPLAY_Umum_Asuransi_Tambahan_Kecelakaan_Diri_010426.pdf",
              "PT Asuransi Jiwa Astra"),
    RiplayDoc("sompo", "personal_accident", "personal_accident", "id",
              "https://www.roojai.co.id/wp-content/uploads/2025/12/roojai-sompo-pa-riplay-id-20250604.pdf",
              "PT Sompo Insurance Indonesia", "distributed via Roojai (roojai.co.id)"),
    RiplayDoc("great_eastern", "personal_accident_en", "personal_accident", "en",
              "https://www.greateasterngeneral.com/content/dam/ge-general/id/homepage/customer-service/riplay/en/gegi-prod-riplay-personal-accident-en.pdf",
              "PT Great Eastern General Insurance Indonesia"),
    # term life
    RiplayDoc("chubb", "term_life_protection_plus", "term_life", "id",
              "https://www.chubb.com/content/dam/chubb-sites/chubb-com/id-id/lei-new-assets/riplay/pdf/rip-term-life-protection-plus-052926.pdf",
              "PT Chubb Life Insurance Indonesia"),
    RiplayDoc("chubb", "my_prime_term_protection_essential", "term_life", "id",
              "https://www.chubb.com/content/dam/chubb-sites/chubb-com/id-id/lei-new-assets/riplay/pdf/asuransi-berjangka-riplay-umum-mptp-essential-v2.pdf",
              "PT Chubb Life Insurance Indonesia"),
    RiplayDoc("fwd", "bebas_hidup", "term_life", "id",
              "https://www.fwd.co.id/files/v3/assets/blt0c90459332411c22/blta141f2cbe1a6affd/64d5d0affe2ccc76c5a2e625/RIPLAY_Umum_Bebas_Hidup.pdf",
              "PT FWD Insurance Indonesia"),
    RiplayDoc("fwd", "asuransi_jiwa_kredit_multiguna", "term_life", "id",
              "https://www.fwd.co.id/files/v3/assets/blt0c90459332411c22/blt6ef89cfa24a6efe6/64bf9ea975211b6f48f340fb/RIPLAY_Umum_Asuransi_Jiwa_Kredit_Multiguna.pdf",
              "PT FWD Insurance Indonesia", "credit life (term) product"),
    RiplayDoc("manulife", "mifirst_life_protector", "term_life", "id",
              "https://www.dbs.com/id/iwov-resources/flp/pdf/RIPLAY-Umum-MiFirst-Life-Protector.pdf",
              "PT Asuransi Jiwa Manulife Indonesia", "hosted by distribution partner DBS Indonesia (manulife.co.id blocks automated downloads)"),
    RiplayDoc("astra", "ava_group_life", "term_life", "id",
              "https://www.astralife.co.id/wp-content/uploads/2022/11/RIPLAY-Umum-AVA-Group-Life-030623.pdf",
              "PT Asuransi Jiwa Astra", "group term life"),
    RiplayDoc("sequis", "sofi_basic_100_rop", "term_life", "id",
              "https://www.sequis.co.id/Products/SOFI/RIPLAY%20UMUM_SOFI_Basic_100-%20ROP_27062022.pdf",
              "PT Asuransi Jiwa Sequis Life", "term life with return of premium"),
    # critical illness
    RiplayDoc("chubb", "critical_illness_protection", "critical_illness", "id",
              "https://www.chubb.com/content/dam/chubb-sites/chubb-com/id-id/lei-new-assets/riplay/pdf/asuransi-kesehatan-riplay-umum-critical-illness-protection-v2.pdf",
              "PT Chubb Life Insurance Indonesia"),
    RiplayDoc("astra", "penyakit_kritis", "critical_illness", "id",
              "https://www.astralife.co.id/wp-content/uploads/2023/03/RIPLAY_Umum_Asuransi_Tambahan_Penyakit_Kritis_070426.pdf",
              "PT Asuransi Jiwa Astra"),
    RiplayDoc("astra", "critical_care_protector", "critical_illness", "id",
              "https://www.astralife.co.id/wp-content/uploads/2026/04/RIPLAY_Umum_ASLI_Critical_Care_Protector_120326.pdf",
              "PT Asuransi Jiwa Astra"),
    RiplayDoc("sequis", "ci_coverage_insurance", "critical_illness", "id",
              "https://sequis.co.id/Products/CI%20Coverage-%20Insurance/RIPLay%20Umum%20CI%20Coverage-%20Insurance_V2_11032026.pdf",
              "PT Asuransi Jiwa Sequis Life"),
    RiplayDoc("sequis", "critical_care_plus", "critical_illness", "id",
              "https://sequis.co.id/Products/Asuransi%20Sequis%20Critical%20Care%20Plus/RIPLAY%20Umum%20Sequis%20Critical%20Care%20Plus_SQL_V2.pdf",
              "PT Asuransi Jiwa Sequis Life"),
    RiplayDoc("sequis", "sofi_critical_infinity", "critical_illness", "id",
              "https://www.sequis.co.id/PDF/id/RIP/SOFI%20Series/RIPLay%20Umum%20SOFI%20Critical%20Infinity_V1.1.pdf",
              "PT Asuransi Jiwa Sequis Life"),
    RiplayDoc("prudential", "prucritical_benefit_88", "critical_illness", "id",
              "https://www.prudential.co.id/content/dam/prudential-aem-lbu/plai/pdf/product-summary-prucritical-benefit-88-v2.pdf",
              "PT Prudential Life Assurance"),
    RiplayDoc("great_eastern", "great_pro_assurance", "whole_life", "id",
              "https://cdn2.ocbc.id/asset/media/Feature/individu/riplay/wm-asuransi/riplay-great-pro-assurance.pdf",
              "PT Great Eastern Life Indonesia", "hosted by distribution partner OCBC Indonesia"),
]
RIPLAY_MANIFEST = RIPLAY_DIR / "manifest.json"


def build_riplay(client: PoliteClient, manifest: dict, force: bool) -> None:
    """Download the RIPLAY PDFs and write ``riplay/manifest.json``."""
    RIPLAY_DIR.mkdir(parents=True, exist_ok=True)
    entries: list[dict] = []
    for doc in RIPLAY_DOCS:
        dest = RIPLAY_DIR / doc.filename
        status = "ok"
        try:
            client.download(doc.url, dest, force=force)
            with dest.open("rb") as fh:
                if fh.read(5) != b"%PDF-":
                    raise ValueError("response is not a PDF")
        except (httpx.HTTPError, ValueError) as exc:
            status = f"failed: {exc}"
            LOG.warning("%s: %s", doc.filename, status)
            if dest.exists():
                dest.unlink()
        entry = {
            "file": doc.filename,
            "insurer": doc.insurer,
            "issuer_legal_name": doc.issuer_legal_name,
            "product": doc.product,
            "product_type": doc.product_type,
            "language": doc.language,
            "url": doc.url,
            "downloaded_on": date.today().isoformat(),
            "status": status,
        }
        if status == "ok":
            entry["bytes"] = dest.stat().st_size
            entry["sha256"] = sha256_of(dest)
        if doc.host_note:
            entry["note"] = doc.host_note
        entries.append(entry)
    RIPLAY_MANIFEST.write_text(json.dumps(entries, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    ok = [e for e in entries if e["status"] == "ok"]
    manifest["sources"]["riplay_manifest"] = {
        "path": "data/real/riplay/manifest.json",
        "documents_ok": len(ok),
        "documents_failed": len(entries) - len(ok),
        "by_product_type": dict(Counter(e["product_type"] for e in ok)),
        "license": "publicly distributed product summaries; copyright remains with each insurer",
    }
    LOG.info("riplay: %d/%d documents downloaded", len(ok), len(entries))


# --------------------------------------------------------------------------- #
# 5. Claim denial rates (CMS Transparency in Coverage PUF, 2023 claims)
# --------------------------------------------------------------------------- #
TIC_URL = "https://data.healthcare.gov/datafile/py2025/transparency_in_coverage_PUF.xlsx"
TIC_SHEET = "Transparency 2025 - Ind QHP"
KFF_OUT = REAL_DIR / "kff_denials_2023.csv"
KFF_PUBLISHED_OUT = REAL_DIR / "kff_denials_2023_published.csv"
KFF_ARTICLE_URL = (
    "https://www.kff.org/private-insurance/issue-brief/"
    "claims-denials-and-appeals-in-aca-marketplace-plans-in-2023/"
)
# Figures as published in the KFF issue brief (Lo, Long, Wallace, Salaga, Pestaina;
# 27 Jan 2025, updated 24 Mar 2026 for corrected CMS data). Transcribed by hand.
KFF_PUBLISHED_ROWS: list[tuple[str, str, str, str]] = [
    ("headline", "in_network_denial_rate_all_healthcare_gov_insurers", "20%", "share of in-network claims denied, 2023"),
    ("headline", "out_of_network_denial_rate", "36%", "share of out-of-network claims denied, 2023"),
    ("headline", "in_network_denial_rate_range_across_insurers", "1% to 54%", "insurer-level range"),
    ("headline", "in_network_denials_count", "86 million", "approximate number of in-network denials"),
    ("state", "highest_state_average_in_network", "34% (Alabama)", "state average"),
    ("state", "lowest_state_average_in_network", "6% (South Dakota)", "state average"),
    ("metal_level", "bronze", "20%", "in-network denial rate"),
    ("metal_level", "silver", "19%", "in-network denial rate"),
    ("metal_level", "gold", "18%", "in-network denial rate"),
    ("metal_level", "platinum", "19%", "in-network denial rate"),
    ("metal_level", "catastrophic", "26%", "in-network denial rate"),
    ("denial_reason", "other", "34%", "share of in-network denials, among insurers reporting reasons"),
    ("denial_reason", "administrative", "21%", "share of in-network denials"),
    ("denial_reason", "excluded_service", "14%", "share of in-network denials"),
    ("denial_reason", "lack_of_prior_authorization_or_referral", "9%", "share of in-network denials"),
    ("denial_reason", "medical_necessity", "6%", "share of in-network denials"),
    ("appeals", "internal_appeals_filed", "376,508", "less than 1% of in-network denials"),
    ("appeals", "internal_appeals_upheld_by_insurer", "211,383 (56%)", "share of decided internal appeals"),
    ("appeals", "external_appeals_filed", "about 5,000", "about 3% of upheld internal appeals"),
]


def _read_xlsx_sheet(path: Path, sheet_name: str) -> list[list[str | None]]:
    """Read one worksheet of an .xlsx file with the standard library only."""
    main_ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    rel_ns = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    ns = {"m": main_ns}
    with zipfile.ZipFile(path) as zf:
        workbook = ET.fromstring(zf.read("xl/workbook.xml"))
        rels = {r.get("Id"): r.get("Target") for r in ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))}
        target = None
        for sheet in workbook.find("m:sheets", ns):
            if sheet.get("name") == sheet_name:
                target = rels[sheet.get(f"{{{rel_ns}}}id")]
        if target is None:
            raise RuntimeError(f"sheet {sheet_name!r} not found in {path.name}")
        shared: list[str] = []
        if "xl/sharedStrings.xml" in zf.namelist():
            for si in ET.fromstring(zf.read("xl/sharedStrings.xml")).findall("m:si", ns):
                shared.append("".join(t.text or "" for t in si.iter(f"{{{main_ns}}}t")))
        sheet_path = target.lstrip("/") if target.startswith("/") else "xl/" + target
        root = ET.fromstring(zf.read(sheet_path))
        rows: list[list[str | None]] = []
        for row in root.find("m:sheetData", ns):
            values: list[str | None] = []
            for cell in row:
                v = cell.find("m:v", ns)
                if v is None:
                    values.append(None)
                elif cell.get("t") == "s":
                    values.append(shared[int(v.text)])
                else:
                    values.append(v.text)
            rows.append(values)
    return rows


def _to_int(value: str | None) -> int | None:
    """Parse a count cell; CMS marks suppressed cells with ``**``."""
    if value is None or value.strip() in {"", "*", "**", "***"}:
        return None
    try:
        return int(float(value))
    except ValueError:
        return None


def _rate(numer: int | None, denom: int | None) -> str:
    if numer is None or not denom:
        return ""
    return f"{numer / denom:.4f}"


def build_kff(client: PoliteClient, manifest: dict, force: bool) -> None:
    """Derive 2023 claim denial rates from the CMS Transparency in Coverage PUF."""
    raw_path = client.download(TIC_URL, RAW_DIR / "kff" / "transparency_in_coverage_PUF_py2025.xlsx")
    record_source(manifest, "cms_transparency_in_coverage_py2025", TIC_URL, raw_path, license="US public domain")
    if KFF_OUT.exists() and KFF_PUBLISHED_OUT.exists() and not force:
        LOG.info("exists, skipping derive: %s", KFF_OUT.name)
        return

    rows = _read_xlsx_sheet(raw_path, TIC_SHEET)
    header_idx = next(i for i, r in enumerate(rows) if r and r[0] == "Individual/SHOP")
    header = [h or "" for h in rows[header_idx]]
    col = {name: i for i, name in enumerate(header)}
    records = [dict(zip(header, r + [None] * (len(header) - len(r)))) for r in rows[header_idx + 1 :]]
    records = [r for r in records if r.get("Plan_ID") and r.get("QHP or SADP?") == "QHP"]

    # Issuer-level counts repeat on every plan row; de-duplicate on (state, issuer).
    issuers: dict[tuple[str, str], dict] = {}
    for r in records:
        key = (r["State"], r["Issuer_ID"])
        if key in issuers:
            continue
        issuers[key] = {
            "state": r["State"],
            "issuer_id": r["Issuer_ID"],
            "issuer_name": r["Issuer_Name"],
            "exchange_type": r["Exchange_Type"],
            "claims_received_in_network": _to_int(r["Issuer_Claims_Received_In_Network"]),
            "claims_denied_in_network": _to_int(r["Issuer_Claims_Denied_In_Network"]),
            "claims_received_out_of_network": _to_int(r["Issuer_Claims_Received_Out_of_Network"]),
            "claims_denied_out_of_network": _to_int(r["Issuer_Claims_Denied_Out_of_Network"]),
            "internal_appeals_filed": _to_int(r["Issuer_Internal_Appeals_Filed"]),
            "internal_appeals_overturned": _to_int(r["Issuer_Number_Internal_Appeals_Overturned"]),
            "external_appeals_filed": _to_int(r["Issuer_External_Appeals_Filed"]),
            "external_appeals_overturned": _to_int(r["Issuer_Number_External_Appeals_Overturned"]),
        }

    count_fields = [
        "claims_received_in_network",
        "claims_denied_in_network",
        "claims_received_out_of_network",
        "claims_denied_out_of_network",
        "internal_appeals_filed",
        "internal_appeals_overturned",
        "external_appeals_filed",
        "external_appeals_overturned",
    ]

    def aggregate(group: Iterable[dict]) -> dict[str, int | None]:
        totals: dict[str, int | None] = {f: 0 for f in count_fields}
        for item in group:
            for f in count_fields:
                if totals[f] is None:
                    continue
                totals[f] = None if item[f] is None else totals[f] + item[f]
        return totals

    def finish(row: dict) -> dict:
        row["in_network_denial_rate"] = _rate(row["claims_denied_in_network"], row["claims_received_in_network"])
        row["out_of_network_denial_rate"] = _rate(row["claims_denied_out_of_network"], row["claims_received_out_of_network"])
        row["internal_appeal_overturn_rate"] = _rate(row["internal_appeals_overturned"], row["internal_appeals_filed"])
        row["source"] = TIC_URL
        return row

    out_rows: list[dict] = []
    national = aggregate(i for i in issuers.values() if i["claims_received_in_network"] is not None)
    out_rows.append(finish({"level": "national", "state": "", "issuer_id": "", "issuer_name": "", "exchange_type": "", **national}))
    by_state: dict[str, list[dict]] = defaultdict(list)
    for item in issuers.values():
        by_state[item["state"]].append(item)
    for state in sorted(by_state):
        totals = aggregate(i for i in by_state[state] if i["claims_received_in_network"] is not None)
        out_rows.append(finish({"level": "state", "state": state, "issuer_id": "", "issuer_name": "", "exchange_type": "", **totals}))
    for key in sorted(issuers):
        out_rows.append(finish({"level": "issuer", **issuers[key]}))

    header_out = [
        "level", "state", "issuer_id", "issuer_name", "exchange_type", *count_fields,
        "in_network_denial_rate", "out_of_network_denial_rate", "internal_appeal_overturn_rate", "source",
    ]
    with KFF_OUT.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=header_out)
        writer.writeheader()
        writer.writerows(out_rows)
    with KFF_PUBLISHED_OUT.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["category", "item", "value", "note", "source"])
        for category, item, value, note in KFF_PUBLISHED_ROWS:
            writer.writerow([category, item, value, note, KFF_ARTICLE_URL])
    record_source(manifest, "kff_denials_2023_csv", "derived", KFF_OUT, rows=len(out_rows), issuers=len(issuers), states=len(by_state))
    record_source(manifest, "kff_denials_2023_published_csv", KFF_ARTICLE_URL, KFF_PUBLISHED_OUT, rows=len(KFF_PUBLISHED_ROWS))
    LOG.info("wrote %s (%d rows: 1 national, %d states, %d issuers)", KFF_OUT.name, len(out_rows), len(by_state), len(issuers))


# --------------------------------------------------------------------------- #
# 6. ICD-10-CM code descriptions
# --------------------------------------------------------------------------- #
ICD10CM_YEAR = 2027
ICD10CM_URL = f"https://www.cms.gov/files/zip/{ICD10CM_YEAR}-code-descriptions-tabular-order.zip"
ICD10CM_OUT = REAL_DIR / "icd10cm_codes.txt"
ICD10CM_LINE_RE = re.compile(r"^([A-Z][0-9A-Z][0-9A-Z]{1,5})\s+(.+?)\s*$")


def build_icd10cm(client: PoliteClient, manifest: dict, force: bool) -> None:
    """Extract ``icd10cm_codes_<year>.txt`` from the CMS zip into ``icd10cm_codes.txt``."""
    raw_path = client.download(ICD10CM_URL, RAW_DIR / "icd10cm" / f"{ICD10CM_YEAR}-code-descriptions-tabular-order.zip")
    record_source(manifest, f"icd10cm_code_descriptions_fy{ICD10CM_YEAR}", ICD10CM_URL, raw_path, license="US public domain (CMS/CDC-NCHS)")
    if ICD10CM_OUT.exists() and not force:
        LOG.info("exists, skipping derive: %s", ICD10CM_OUT.name)
        return
    with zipfile.ZipFile(raw_path) as zf:
        names = [n for n in zf.namelist() if re.search(r"icd10cm[_-]codes[_-]\d{4}\.txt$", n, re.I)]
        if len(names) != 1:
            raise RuntimeError(f"expected one icd10cm_codes_<year>.txt in {raw_path.name}, found {names}")
        text = zf.read(names[0]).decode("utf-8", errors="replace")
    rows: list[str] = []
    bad = 0
    for line in text.splitlines():
        if not line.strip():
            continue
        m = ICD10CM_LINE_RE.match(line)
        if not m:
            bad += 1
            continue
        rows.append(f"{m.group(1)} {m.group(2)}")
    if bad > 10 or len(rows) < 50000:
        raise RuntimeError(f"{names[0]}: unexpected format ({len(rows)} parsed rows, {bad} rejected lines)")
    ICD10CM_OUT.write_text("\n".join(rows) + "\n", encoding="utf-8")
    record_source(manifest, "icd10cm_codes_txt", "derived", ICD10CM_OUT, rows=len(rows), source_member=names[0], fiscal_year=ICD10CM_YEAR)
    LOG.info("wrote %s (%d codes, %.2f MB)", ICD10CM_OUT.name, len(rows), ICD10CM_OUT.stat().st_size / 1e6)


# --------------------------------------------------------------------------- #
# 7. Optional: ICD retrieval embeddings (local multilingual-e5-small ONNX model, cached category vectors)
# --------------------------------------------------------------------------- #
E5_REPO = "Xenova/multilingual-e5-small"
E5_REVISION = "main"
E5_FILES = {"onnx/model_int8.onnx": "model_int8.onnx", "tokenizer.json": "tokenizer.json"}
E5_DIR = ROOT / "data" / "cache" / "models" / "multilingual-e5-small"


def build_e5onnx(client: PoliteClient, manifest: dict, force: bool) -> None:
    """Download the int8 ONNX export of intfloat/multilingual-e5-small (Xenova conversion) and its tokenizer.

    The files are untrusted data: they are only ever parsed (onnxruntime, tokenizers), never executed.
    Stored under data/cache/ (gitignored); provenance goes into manifest.json.
    """
    for remote, local in E5_FILES.items():
        url = f"https://huggingface.co/{E5_REPO}/resolve/{E5_REVISION}/{remote}"
        path = client.download(url, E5_DIR / local, force=force)
        record_source(manifest, f"e5_small_onnx_{local}", url, path, license="MIT (intfloat/multilingual-e5-small); ONNX export by Xenova")


def build_icdembed(client: PoliteClient, manifest: dict, force: bool) -> None:
    """Embed every ICD-10-CM 3-character category once per backend and cache the vectors in data/cache/."""
    sys.path.insert(0, str(ROOT))
    from clauseguard import icd10_coder, icd10_embed

    cl = icd10_coder.code_list()
    docs = icd10_embed.category_documents(cl.codes, cl.category_label)
    for name in icd10_embed.BACKENDS:
        backend = icd10_embed.get_backend(name)
        try:
            index = icd10_embed.build_index(backend, docs, force=force)
        except icd10_embed.EmbeddingUnavailable as e:
            LOG.warning("skipped %s embeddings: %s", name, e)
            continue
        path = icd10_embed.index_path(backend, docs)
        record_source(manifest, f"icd10_category_embeddings_{name}", "derived", path, model=backend.model, categories=len(index.ids), dim=int(index.matrix.shape[1]))
        LOG.info("%s: %d category vectors (%s)", name, len(index.ids), path.name)


# --------------------------------------------------------------------------- #
# entry point
# --------------------------------------------------------------------------- #
SECTIONS = ("cms", "rates", "insuranceqa", "fos", "riplay", "kff", "icd10cm")
OPTIONAL_SECTIONS = ("e5onnx", "icdembed")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--only", default=",".join(SECTIONS), help="comma-separated subset of: " + ", ".join(SECTIONS + OPTIONAL_SECTIONS) + " (the last two are opt-in)")
    parser.add_argument("--force", action="store_true", help="rebuild derived files even if they exist")
    parser.add_argument("--fos-target", type=int, default=150, help="number of ombudsman decisions to collect")
    parser.add_argument("--rate", type=float, default=MIN_INTERVAL_S, help="minimum seconds between requests to one host")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)

    selected = [s.strip() for s in args.only.split(",") if s.strip()]
    unknown = sorted(set(selected) - set(SECTIONS + OPTIONAL_SECTIONS))
    if unknown:
        parser.error(f"unknown section(s): {unknown}")

    REAL_DIR.mkdir(parents=True, exist_ok=True)
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    manifest = load_manifest()
    client = PoliteClient(min_interval_s=args.rate)
    try:
        if "cms" in selected:
            build_cms_table(client, manifest, args.force)
        if "rates" in selected:
            build_cms_rates(client, manifest, args.force)
        if "insuranceqa" in selected:
            build_insuranceqa(client, manifest, args.force)
        if "fos" in selected:
            build_fos(client, manifest, args.force, args.fos_target)
        if "riplay" in selected:
            build_riplay(client, manifest, args.force)
        if "kff" in selected:
            build_kff(client, manifest, args.force)
        if "icd10cm" in selected:
            build_icd10cm(client, manifest, args.force)
        if "e5onnx" in selected:
            build_e5onnx(client, manifest, args.force)
        if "icdembed" in selected:
            build_icdembed(client, manifest, args.force)
    finally:
        client.close()
        save_manifest(manifest)
    return 0


if __name__ == "__main__":
    sys.exit(main())
