# RIPLAY provenance for sandbox persona policies

This note records, for each sandbox `PolicyRecord` in
`clauseguard/sandbox/persona_policies.py`, whether its clause wording now cites a real
Indonesian RIPLAY (Ringkasan Informasi Produk dan/atau Layanan) PDF downloaded into this
directory, and why, as of the 2026-10-11 pass that reviewed every `(mock)`-labelled
policy against `data/real/riplay/manifest.json` (30 RIPLAY PDFs).

## Changed

- **GH-NUSA-GRP** (Santoso family's employer group health). No Indonesian insurer
  publishes a RIPLAY for a *group* health product (RIPLAY is a retail-product
  disclosure requirement under POJK/SEOJK rules; group master policies are not sold
  as a named retail product and have no RIPLAY). The closest available real
  substitute is an individual hospitalisation RIPLAY of the same clause shape:
  `chubb_medical_pro.pdf` (PT Chubb Life Insurance Indonesia, "Asuransi Medical Pro",
  product_type `hospitalisation`). The qualitative clauses -- cosmetic exclusion,
  suicide exclusion, the 30-day reimbursement filing deadline, and the claim-document
  checklist -- were replaced with verbatim quotes from that PDF (verified by direct
  substring match against the extracted PDF text; see "Verification method" below).
  The dental exclusion/exception pair was **left on the original mock wording**
  because the scripted task `data/scripted_tasks/T05.yaml` asserts the literal phrase
  "natural teeth" in the agent's answer, which Chubb's real dental exclusion wording
  does not contain; swapping it would have required rewriting a task assertion to
  chase a cosmetic wording change, which was not worth the risk. The benefit amounts
  (room/day limit IDR 1,500,000, per-case limit IDR 7,700,000, surgery limit IDR
  25,000,000, annual cap IDR 150,000,000) and the "no waiting period for members
  enrolled within 30 days" feature are sandbox-engineered to produce the exact
  IDR 13,700,000 claim walkthrough used throughout the test suite and scripted
  tasks; they are not literally Chubb's Plan 3000 schedule (which uses IDR 3,000,000
  room/day and an IDR 1.5bn annual cap) and keep the `GH-NUSA-GRP-wording(mock)` doc
  id on those specific tuples.

- **HI-INDIV-S** (Sari's individual health). Real substitute: `astra_medis_dan_bedah.pdf`
  (PT Asuransi Jiwa Astra, "Asuransi Tambahan Perawatan Medis & Bedah", an individual
  hospitalisation/surgery rider, product_type `hospitalisation`). Replaced with
  verbatim quotes: the 30-day waiting-period exclusion (Astra's own worked illustration
  uses the identical "30 hari ... kecuali karena kecelakaan" shape already coded in the
  sandbox), the pre-existing-condition exclusion heading, the sex-change-surgery
  (cosmetic-adjacent) exclusion, the suicide exclusion, the hazardous-activity
  exclusion, the pregnancy-complications benefit line, and the coordination-of-benefits
  exclusion (Astra's own clause 29). The dental exclusion was left on mock wording
  because Astra's rider has no standalone dental benefit to exclude from (there is
  nothing to quote). The 24-month pre-existing window, the specified-illness waiting
  list, the benefit amounts and the 30-day claim-filing deadline (Astra's RIPLAY states
  no numeric filing deadline for this rider) remain sandbox values and keep the
  `HI-INDIV-S-wording(mock)` doc id on those tuples.

## Checked, found already real (no change)

- **HCP-SOMPO-01** (Rizky's hospital cash plan) and **HCP-RIDER-B** (the Santoso
  family's Astra hospital-cash rider) were suspected `(mock)` candidates per the task
  brief, but their `doc_id` fields (`roojai_hcp_en`, `astra_hcp`) already point to real
  documents in `data/policies/real/` (a pre-existing hand-verification pass, separate
  from the `data/real/riplay/` download done on 2026-10-11). Spot-checking one quoted
  sentence from each tuple set against the cited PDF with an exact substring match
  confirmed both are genuinely verbatim:
  - `data/policies/real/roojai_hcp_en.pdf` contains the HCP-SOMPO-01 hospitalisation
    clause verbatim.
  - `data/policies/real/astra_hcp.pdf` contains the HCP-RIDER-B illness-hospitalisation
    clause verbatim.
  Note: `data/real/riplay/sompo_hospital_cash_plan_en.pdf` and
  `data/real/riplay/astra_hospital_cash_plan.pdf` (the newly downloaded RIPLAY PDFs for
  the same two products) use *different* wording from the older `data/policies/real/`
  copies -- these are different editions/versions of the same rider, not the same text.
  No change was made since the cited documents are already correct and real.

## Left intentionally mock / modelled (no RIPLAY exists)

- **PLATFORM-ACC** (gig-platform driver accident cover): genuinely synthetic. No
  Indonesian ride-hailing platform publishes a RIPLAY (platform driver-partner
  accident cover is an unpublished group policy, not a licensed retail product with
  its own disclosure document). Every clause in this record turns on the
  platform-specific "on trip" condition (app-logged trip window, 7-day app-only filing
  deadline) that has no counterpart in a retail personal-accident RIPLAY, so
  substituting a real PA RIPLAY's wording would misrepresent the product rather than
  clarify it. See the comment above `platform_acc()` in `persona_policies.py`.
- **BPJS-KES** and **JASA-RAHARJA**: statutory/social schemes. RIPLAY is a disclosure
  requirement for licensed private insurers' retail products; it does not apply to
  BPJS Kesehatan (JKN) or Jasa Raharja, which are modelled on public regulatory
  sources (POJK/PMK, the JKN member handbook) as already documented in their `doc_id`
  strings. Unchanged.
- **GL-NUSA-GRP** (Santoso family group term life): out of scope for this pass (not
  named in the task brief). A real candidate exists
  (`data/real/riplay/astra_ava_group_life.pdf`) for a future pass but was not touched
  here to keep the change set scoped to the five named products.

## Verification method

Each real quote above was checked by extracting the cited PDF's text with `pypdf`
(`PdfReader.extract_text()` per page, joined and whitespace-normalised) and confirming
the quote is an exact substring of the extracted text, run ad hoc from the repo root.
No `clauseguard.extractor.policy_extractor` / Gemini calls were made: the clause
shapes needed (standard exclusions, waiting-period wording, filing deadlines, claim
documents) were short and unambiguous enough to pick by direct reading, so no LLM
locator pass was needed, and this kept the Gemini key pool untouched for other work.
`source_tier` stays `POLICY_DOC_VERIFIED` on every tuple, consistent with
`tests/test_persona_policies.py` and `tests/test_bench.py`, which assert every tuple
in every policy record carries that tier -- the quotes above are genuinely verbatim,
and the still-mock tuples were already `POLICY_DOC_VERIFIED` by the file's existing
convention (hand-written sandbox wording, reviewed by a human, just not from a public
document).
