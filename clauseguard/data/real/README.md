# Real public data

Everything in this directory is downloaded or derived from public sources by
`scripts/fetch_real_data.py`. Raw downloads live in `data/real/raw/` (ignored by git);
the derived files below are committed. `manifest.json` records URL, download date,
size and SHA-256 of every raw and derived file.

Download date for all sources: **2026-10-11**.

## Reproduce

```bash
pip install -r requirements.txt            # httpx and pymupdf are the only runtime needs
python scripts/fetch_real_data.py          # all sections, resumable
python scripts/fetch_real_data.py --only cms,rates,kff
python scripts/fetch_real_data.py --only fos --fos-target 150
python scripts/fetch_real_data.py --force  # rebuild derived files from the raw downloads
```

The script is idempotent: existing raw files are not re-downloaded, existing derived
files are kept unless `--force` is given, and the ombudsman collection resumes from the
decisions already stored. All HTTP traffic identifies itself with a User-Agent and is
limited to one request per second per host.

## Files

| File | Rows / count | Used for |
|---|---|---|
| `cms_plans_py2026.csv` | 4,183 plan variants (Texas) | Realistic US health-plan cost-sharing terms (deductible, OOP max, per-benefit copay/coinsurance) for the coverage calculator and benchmark scenarios |
| `cms_rates_py2026.csv` | 9,052 rows (834 standard plans x 27 rating areas x 4 ages) | Monthly premiums for the plan selector; joins to `cms_plans_py2026.csv` on `StandardComponentId` |
| `insuranceqa_questions.jsonl` | 16,860 questions | Real consumer insurance questions for intent and off-script robustness testing |
| `insuranceqa_sample200.jsonl` | 200 questions | Fixed, keyword-stratified subset for off-script evaluation runs |
| `fos_decisions.jsonl` | 150 decisions | Real dispute narratives that quote policy wording, for clause-interpretation and adversarial evaluation |
| `riplay/*.pdf` + `riplay/manifest.json` | 30 documents | Real Indonesian product summaries for the policy extractor |
| `kff_denials_2023.csv` | 238 rows (1 national, 31 states, 206 issuers) | Base rates of claim denial for calibrating risk messaging |
| `kff_denials_2023_published.csv` | 19 rows | Headline, metal-level, reason and appeal figures as published by KFF |

## 1. CMS Exchange Public Use Files, plan year 2026

* Source: Centers for Medicare & Medicaid Services, Health Insurance Exchange Public
  Use Files (Exchange PUFs), <https://www.cms.gov/marketplace/resources/data/public-use-files>.
  Data.gov entries "Plan Attributes PUF - PY2026" and "Benefits and Cost Sharing PUF - PY2026".
* Raw files (streamed to `raw/cms/`, not committed):
  * `https://download.cms.gov/marketplace-puf/2026/plan-attributes-puf.zip` (1.0 MB zip, 32 MB CSV)
  * `https://download.cms.gov/marketplace-puf/2026/benefits-and-cost-sharing-puf.zip` (12.5 MB zip, 375 MB CSV)
  * Data dictionaries: `https://www.cms.gov/files/document/planattributes-datadictionary-py26.pdf`,
    `https://www.cms.gov/files/document/benefitscostsharing-datadictionary-py26.pdf`
* License: US Government work, public domain (<https://www.usa.gov/publicdomain/label/1.0/>).
* State choice: the script picks the state with the most individual-market medical plan
  variants (`DentalOnlyPlan == "No"`, `MarketCoverage == "Individual"`). For PY2026 that is
  **Texas (4,183 variants; Florida is second with 2,119)**. Every cost-sharing-reduction
  variant (`CSRVariationType`) is kept as its own row.
* **Premiums are not in these two files.** They are published separately in the Rate PUF,
  handled in section 1b below; the column `premium_note` states this on every row.

Columns of `cms_plans_py2026.csv` (2.5 MB):

| Column | Origin |
|---|---|
| `StateCode`, `IssuerId`, `IssuerMarketPlaceMarketingName`, `StandardComponentId`, `PlanId`, `PlanMarketingName`, `PlanType`, `MetalLevel`, `CSRVariationType`, `QHPNonQHPTypeId`, `IsHSAEligible` | Plan Attributes PUF, verbatim |
| `MedicalDrugDeductiblesIntegrated`, `MedicalDrugMaximumOutofPocketIntegrated` | Plan Attributes PUF, verbatim; decide which deductible / MOOP column applies |
| `MEHBDedInnTier1Individual`, `TEHBDedInnTier1Individual` | Plan Attributes PUF, verbatim (medical-EHB and total-EHB in-network tier-1 individual deductible) |
| `MEHBInnTier1IndividualMOOP`, `TEHBInnTier1IndividualMOOP` | Plan Attributes PUF, verbatim (in-network tier-1 individual maximum out-of-pocket) |
| `deductible_individual_inn` | `TEHBDedInnTier1Individual` when deductibles are integrated, else `MEHBDedInnTier1Individual` |
| `oop_max_individual_inn` | `TEHBInnTier1IndividualMOOP` when MOOPs are integrated, else `MEHBInnTier1IndividualMOOP` |
| `premium_note` | constant text, see above |
| `<benefit>_covered` | Benefits PUF `IsCovered` |
| `<benefit>_copay_inn` | Benefits PUF `CopayInnTier1` |
| `<benefit>_coins_inn` | Benefits PUF `CoinsInnTier1` |
| `<benefit>_quant_limit`, `<benefit>_limit_qty`, `<benefit>_limit_unit` | Benefits PUF `QuantLimitOnSvc`, `LimitQty`, `LimitUnit` |

Benefit prefixes and the exact `BenefitName` matched in the Benefits PUF:

| Prefix | `BenefitName` |
|---|---|
| `inpatient_hospital` | `Inpatient Hospital Services (e.g., Hospital Stay)` |
| `emergency_room` | `Emergency Room Services` |
| `primary_care` | `Primary Care Visit to Treat an Injury or Illness` |
| `specialist` | `Specialist Visit` |
| `generic_drugs` | `Generic Drugs` |
| `mental_health_inpatient` | `Mental/Behavioral Health Inpatient Services` |
| `maternity_delivery` | `Delivery and All Inpatient Services for Maternity Care` |

Values are kept as published (for example `$35.00`, `50.00% Coinsurance after deductible`,
`Not Applicable`); no numeric parsing is done at this stage.

## 1b. CMS Rate PUF, plan year 2026 (`cms_rates_py2026.csv`)

* Source: same Exchange PUF page; data.gov entry "Rate PUF - PY2026".
  Raw file `https://download.cms.gov/marketplace-puf/2026/rate-puf.zip` (16 MB zip,
  281 MB CSV), streamed to `raw/cms/`, not committed. Public domain.
  Data dictionary: `https://www.cms.gov/files/document/rate-datadictionary-py26.pdf`.
* Rows kept: the same state as section 1 (Texas), `Age` in {21, 30, 40, 50}, every
  rating area. `IndividualRate` is the monthly non-tobacco premium (it is identical under
  both `Tobacco` settings; `IndividualTobaccoRate` is not kept). Rows are sorted by
  `PlanId`, `RatingAreaId`, `Age`.
* Columns (verbatim Rate PUF names): `PlanId`, `Age`, `RatingAreaId`, `IndividualRate`,
  `Tobacco`, `RateEffectiveDate`, `RateExpirationDate`.
* Join key: `PlanId` here is the 14-character standard component id, so it matches
  `cms_plans_py2026.csv.StandardComponentId` (not `PlanId`, which carries the `-NN`
  cost-sharing-variant suffix). All 834 standard plans, hence all 4,183 variants, have a
  rate in each of Texas's 27 rating areas: 834 x 27 x 4 = 9,052 rows.

## 2. InsuranceQA V2

* Source: Minwei Feng, Bing Xiang, Michael R. Glass, Lidan Wang, Bowen Zhou,
  "Applying Deep Learning to Answer Selection: A Study and An Open Task", ASRU 2015.
  Repository <https://github.com/shuzi/insuranceQA>, folder `V2`. The questions are real
  consumer questions collected from Insurance Library. (The Hugging Face mirror
  `deccan-ai/insuranceQA-v2` is derived from the same files but drops the domain label,
  so the original repository is used.)
* Raw files: `V2/vocabulary` and `V2/InsuranceQA.question.anslabel.raw.encoded.gz`
  (questions are stored as vocabulary indices and decoded by the script).
* License: the repository states "This dataset is provided as is and for research purpose
  only. If you publish anything using this data, please cite our paper." It is used here for
  research evaluation only, and the citation above must accompany any publication.
* Processing: all 16,889 train/valid/test questions are decoded, normalised
  (whitespace), de-duplicated case-insensitively (29 duplicates removed) and passed
  through a simple English filter (none removed). Result: 16,860 questions.
* `insuranceqa_questions.jsonl` fields:
  * `id`: `iqa-00001` ... in file order
  * `question`: the decoded question text
  * `topic_guess`: first matching keyword bucket (`claims`, `exclusions_waiting`,
    `premiums_cost`, `cancellation_lapse`, `beneficiary_payout`, `hospital_medical`,
    `accident_disability`, `critical_illness`, `eligibility_underwriting`,
    `coverage_scope`, `tax_regulation`, or `general`)
  * `dataset_domain`: the product category label shipped with the corpus
    (`life-insurance`, `health-insurance`, `disability-insurance`, ...)
* `insuranceqa_sample200.jsonl`: 200 questions, 16 per `topic_guess` bucket (12 buckets)
  plus 8 filled at random from the remainder, seed `20260101`.

## 3. UK Financial Ombudsman Service decisions

* Source: Financial Ombudsman Service, published ombudsman decisions,
  <https://www.financial-ombudsman.org.uk/decisions-case-studies/ombudsman-decisions>.
  Search endpoint used:
  `https://www.financial-ombudsman.org.uk/businesses/resolving-complaint/ombudsman-decisions/search`
  with `Keyword`, `IndustrySectorID[3]=3` (Insurance excluding PPI), `IsUpheld[0]`,
  `IsUpheld[1]`, `Sort=relevance`, `Start`. Decision PDFs are at
  `https://www.financial-ombudsman.org.uk/decision/<DRN>.pdf`.
* License: Crown copyright, Open Government Licence v3.0
  (<https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/>).
  Decisions are anonymised by the ombudsman; the complainant is never named.
* Queries: every combination of the clause terms `"waiting period"`, `"pre-existing"`,
  `"exclusion"`, `"late notification"`, `"coordination"` with the product words
  `private medical`, `life`, `income protection`, `personal accident`, `travel`
  (25 queries, up to 3 result pages each). The search form has no product filter, so
  the product is classified from the decision text by keyword counts
  (`health_medical`, `life`, `income_protection`, `personal_accident`, `travel`).
* Kept only when the text (a) classifies into one of those products, (b) contains at
  least one of the clause terms, and (c) quotes at least one passage of 40 to 600
  characters inside double or single typographic quotation marks (how the ombudsman
  cites policy wording). About one in three downloaded decisions passes.
* Access note: the site served every request normally at one request per second with an
  identifying User-Agent; no scraping service or account was used. Raw PDFs are kept
  under `raw/fos/` and are not committed; `raw/fos/rejected.json` lists decisions that
  were downloaded but filtered out, so re-runs do not refetch them.
* `fos_decisions.jsonl` fields: `decision_id` (DRN reference), `date` (ISO),
  `business` (respondent firm, as listed), `product`, `outcome` (`upheld` /
  `not upheld`), `search_query`, `source_url`, `text` (full extracted text),
  `quoted_clauses` (list of quoted passages, de-duplicated, in order of appearance).
* Counts: **150 of 150** decisions collected (health_medical 64, travel 31,
  income_protection 27, personal_accident 18, life 10; not upheld 110, upheld 40;
  dated 2013-04-19 to 2026-08-25). See `manifest.json` under `fos_decisions_jsonl`
  for the same breakdown plus the file's size and hash.

## 4. Indonesian RIPLAY product summaries

RIPLAY Umum ("Ringkasan Informasi Produk dan Layanan", general version) is the
OJK-mandated product summary every Indonesian insurer must publish. All 30 documents
were downloaded without login from the URLs listed in `riplay/manifest.json`
(fields: `file`, `insurer`, `issuer_legal_name`, `product`, `product_type`, `language`,
`url`, `downloaded_on`, `bytes`, `sha256`, `status`, optional `note`). Copyright stays
with each insurer; the files are used only as test inputs for the policy extractor.

| Product type | Count | Insurers |
|---|---|---|
| hospital_cash | 5 | Chubb Life, Astra Life, Sompo (id + en), AXA Mandiri |
| hospitalisation | 5 | Chubb Life, Astra Life, AXA Financial Indonesia, Sequis, Asuransi Sinar Mas |
| personal_accident | 5 | Chubb General, Chubb Life, Astra Life, Sompo, Great Eastern General |
| term_life | 7 | Chubb Life (2), FWD (2), Manulife, Astra Life, Sequis |
| critical_illness | 7 | Chubb Life, Astra Life (2), Sequis (3), Prudential |
| whole_life | 1 | Great Eastern Life |

Notes on coverage of the requested insurer list:

* **Allianz Indonesia** and **Manulife Indonesia** return HTTP 403 to non-browser
  clients for their PDF assets, so nothing was taken from `allianz.co.id` or
  `manulife.co.id`. The Manulife MiFirst Life Protector summary is the identical
  document published by its bank distribution partner DBS Indonesia.
* **Sinarmas MSIG Life** does not expose RIPLAY PDFs to search engines; the
  Sinar Mas document included is from the group's general insurer, PT Asuransi Sinar Mas.
* **Great Eastern Life Indonesia** publishes its RIPLAY files through its bank partner
  OCBC Indonesia; the personal accident document is from Great Eastern General Insurance
  Indonesia's own site.
* **Prudential Indonesia**: the only RIPLAY asset that resolved (older URLs now 404) is
  PRUCritical Benefit 88, whose first page carries the RIPLAY Umum heading.
* Sompo's retail products are distributed through Roojai; the documents are issued by
  PT Sompo Insurance Indonesia and hosted on `roojai.co.id`.
* Two documents are in English (`language: en`); all others are Indonesian.

## 5. Claim denial rates, 2023 (KFF / CMS Transparency in Coverage)

* KFF analysis: Justin Lo, Michelle Long, Rayna Wallace, Meghan Salaga, Kaye Pestaina,
  "Claims Denials and Appeals in ACA Marketplace Plans in 2023", KFF, 27 January 2025
  (updated 24 March 2026 for corrected CMS data),
  <https://www.kff.org/private-insurance/issue-brief/claims-denials-and-appeals-in-aca-marketplace-plans-in-2023/>.
* Underlying data: CMS Transparency in Coverage PUF, PY2025 release, which reports
  plan-year-2023 claims for issuers on HealthCare.gov,
  `https://data.healthcare.gov/datafile/py2025/transparency_in_coverage_PUF.xlsx`
  (sheet `Transparency 2025 - Ind QHP`). Public domain.
* `kff_denials_2023.csv` is computed by the script from the issuer-level columns
  (`Issuer_Claims_Received_In_Network`, `Issuer_Claims_Denied_In_Network`,
  `Issuer_Claims_Received_Out_of_Network`, `Issuer_Claims_Denied_Out_of_Network`,
  `Issuer_Internal_Appeals_Filed`, `Issuer_Number_Internal_Appeals_Overturned`,
  `Issuer_External_Appeals_Filed`, `Issuer_Number_External_Appeals_Overturned`),
  de-duplicated on (state, issuer) and aggregated to state and national level.
  CMS suppresses small cells with `**`; those are blank, and any aggregate that would
  include a suppressed cell is also blank. The derived national in-network denial rate
  is 0.1970 and the out-of-network rate 0.3613, matching KFF's published 20% and 36%.
* `kff_denials_2023_published.csv` transcribes the figures KFF publishes only as text or
  figures (metal-level rates, denial reasons, appeal counts), each row citing the article.
  KFF's state map and per-parent-company table are images and are not transcribed;
  the state-level rates in `kff_denials_2023.csv` are the equivalent computed values.
