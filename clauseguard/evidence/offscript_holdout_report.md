# ClauseGuard second off-script batch (a dev set: probed before it was fixed)

## How to read this report

This second batch of 10 questions is a **development set, not a hold-out**: nine of the ten were probed once before being written down and their failures were fixed first; only H09 (cosmetic surgery) is new. Result at the first probe: 5 of 10 passed (H01, H04, H05, H07, H08); after fixing the defects they exposed: 10 of 10. For an out-of-sample figure see `evidence/offscript_blind_report.md` (3 of 14).


Generated 2026-10-11 - LLM: mocked / deterministic fallbacks - policy source: sandbox

**10/10 tasks passed.** Criteria are evaluated by code and regex on structured Reply fields (verdict, payable, deadline, denial codes, clarification slot, refusal flag, executed tool tiers, COB order); no model judges anything.

| id | kind | persona | title | result | failures |
|---|---|---|---|---|---|
| H01 | holdout | rizky | Indonesian: dengue payout for a 6-day stay | PASS |  |
| H02 | holdout | rizky | Wording question containing the word claim: annual limit | PASS |  |
| H03 | holdout | santoso | Who is insured under the group plan | PASS |  |
| H04 | holdout | dewi | Expired licence, hypothetical crash | PASS |  |
| H05 | holdout | rizky | Late premium on the life policy | PASS |  |
| H06 | holdout | rizky | Named critical illness without an admission | PASS |  |
| H07 | holdout | santoso | Typo-free but unusual phrasing: max room rate | PASS |  |
| H08 | holdout | dewi | Full Indonesian crash claim with expired SIM | PASS |  |
| H09 | holdout | santoso | Cosmetic surgery on the group plan | PASS |  |
| H10 | holdout | rizky | Administrative question with no policy clause | PASS |  |

holdout: 10/10 passed

## Failure details

None.

## Transcripts (all tasks)

### H01 - Indonesian: dengue payout for a 6-day stay (PASS)

**User:** kalo aku kena demam berdarah dan opname 6 hari mulai 1 okt 2026, berapa yg dibayar asuransi?

**Tools:** get_my_policies, get_payment_status, get_payment_status, get_payment_status, get_payment_status, get_payment_status, check_coverage, claim_readiness

```
Sompo Health Insurance Hospital Care Plan (Hospital Cash Plan) (HCP-SOMPO-01): Covered (indicative). Indicative benefit: IDR 3,000,000.
- Clause [HCP-SOMPO-01 Benefits, Art. 1, c_hosp_daily]: "This Policy provide daily cash compensation to Participants as stated in the Policy Summary if during the Insurance period, the Participant is affected by an illness or has an accident and requires Hospitalization in the Hospital. For this benefit, it is"
Jaminan Kesehatan Nasional (JKN) (BPJS-KES-RIZKY): depends on one fact - if facility bpjs partner = yes: covered.
Documents required for HCP-SOMPO-01: original claim form; receipt original or legalised; receipt details; medical resume inpatient; prescription copy; diagnostic results.
Readiness flags: INCOMPLETE_DOCS.
One question before I can answer: Is the hospital a BPJS Kesehatan partner facility? It matters because the answer changes the outcome (yes: covered). The clause that makes this matter (BPJS-KES-RIZKY, Manfaat 1 (modelled)) says: "Inpatient care is guaranteed at a BPJS Kesehatan partner facility (FKRTL) according to the INA-CBG package tariff for the participant's class, on referral from the first-level facility or through the emergency unit. Services at non-partner facilities are not reimbursed except in an emergency."
Indicative only, based on the wording in your documents; the insurer makes the claim decision and the policy wording prevails.
Alert: Flexi Life Protection (term life, yearly renewable to age 85) (TL-ASTRA-07) has lapsed: premium unpaid since 2026-09-01, grace ended 2026-10-01. A death or claim after that date is not covered until reinstated.
```

### H02 - Wording question containing the word claim: annual limit (PASS)

**User:** Is there any limit on how many times a year i can claim the hospital cash?

**Tools:** get_my_policies, get_payment_status, get_payment_status, get_payment_status, get_payment_status, get_payment_status

```
Sompo Health Insurance Hospital Care Plan (Hospital Cash Plan) (HCP-SOMPO-01) hospitalization: IDR 500,000/day, max 90 days/year.
- [HCP-SOMPO-01 Benefits, Art. 1, c_hosp_daily] "This Policy provide daily cash compensation to Participants as stated in the Policy Summary if during the Insurance period, the Participant is affected by an illness or has an accident and requires Hospitalization in the Hospital. For this benefit, it is valid for maximum 2 (two) events of Hospitalization and a maximum of 90 (Ninety) days of treatment during the policy period or the period listed in the Policy Summary. Participants are entitled to inpatient compensation benefits if they have received treatment for at least 1x24 (one time twenty-four) hours at the hospital."
Sompo Health Insurance Hospital Care Plan (Hospital Cash Plan) (HCP-SOMPO-01) icu: IDR 1,000,000/day, max 20 days/year.
- [HCP-SOMPO-01 Benefits, Art. 3, c_icu_daily] "This Policy provide daily cash compensation to Participants as stated in the Policy Summary if during the Insurance period, the Participant is exposed to an illness or experiences a critical incident as a result of an Accident and requires treatment in the Intensive Care Unit (ICU / ICCU / HCU / PICU / NICU) room. For this benefit, the maximum 2 (two) two Hospitalizations are valid and a maximum of 20 (twenty) days of treatment during the policy period or the period listed in the Policy Summary."
Indicative only, based on the wording in your documents; the insurer makes the claim decision and the policy wording prevails.
Alert: Flexi Life Protection (term life, yearly renewable to age 85) (TL-ASTRA-07) has lapsed: premium unpaid since 2026-09-01, grace ended 2026-10-01. A death or claim after that date is not covered until reinstated.
```

### H03 - Who is insured under the group plan (PASS)

**User:** can my wife and kids use the company health insurance too?

**Tools:** get_my_policies, get_payment_status, get_payment_status, get_payment_status, get_payment_status, get_payment_status, get_payment_status

```
Nusantara Group Health (employer plan, cashless network N1) (GH-NUSA-GRP) insures: Budi Santoso, Sari Santoso, Aditya Santoso, Nadia Santoso.
Indicative only, based on the wording in your documents; the insurer makes the claim decision and the policy wording prevails.
```

### H04 - Expired licence, hypothetical crash (PASS)

**User:** my driving licence expired last month, am I still covered by my PA if I crash?

**Tools:** get_my_policies, get_payment_status, get_payment_status, get_payment_status, get_payment_status, check_coverage

```
No event date was given, so I evaluated the policies as of 2026-10-11.
Essential Plus Personal Accident (PA-CHUBB-03): Not covered (indicative). Reason: riding without a valid driving licence is excluded [NO_VALID_LICENSE].
- Clause [PA-CHUBB-03 General Exclusions (d), k_valid_license]: "driving/riding without a valid license; or"
Driver-partner on-trip accident protection (PLATFORM-ACC): depends on one fact - if work related = yes: covered; if work related = no: not addressed by the policy.
Jaminan Kesehatan Nasional (JKN) (BPJS-KES-DEWI): depends on one fact - if facility bpjs partner = yes: not covered.
Road traffic accident compensation (UU 33/34 1964) (JASA-RAHARJA): depends on one fact - if vehicles involved = 1: not covered; if vehicles involved = 2: covered.
Disclosure issue: the occupation declared on the PA policy is 'administrative staff (class 1)' while your actual work is 'motorcycle courier (class 3)'. This is an occupation mismatch (non-disclosure) that the insurer can treat as grounds to reduce or void the cover. I cannot advise you to leave it undisclosed; contact the insurer or your agent to declare the correct occupation and ask what loading applies.
One question before I can answer: Did this happen while you were working (for example on an active delivery order)? It matters because the answer changes the outcome (yes: covered; no: not addressed by the policy). The clause that makes this matter (PLATFORM-ACC, Benefits, 1) says: "Accidental death while the driver-partner is on an active order (from order acceptance to completion as recorded by the app): IDR 50,000,000 paid to the registered heir."
Indicative only, based on the wording in your documents; the insurer makes the claim decision and the policy wording prevails.
Alert: BPJS Kesehatan (BPJS-KE
```

### H05 - Late premium on the life policy (PASS)

**User:** my premium for the life policy is 40 days late, is it dead?

**Tools:** get_my_policies, get_payment_status, get_payment_status, get_payment_status, get_payment_status, get_payment_status

```
Sompo Health Insurance Hospital Care Plan (Hospital Cash Plan) (HCP-SOMPO-01): active, in force.
Flexi Life Protection (term life, yearly renewable to age 85) (TL-ASTRA-07): NOT in force (grace ended 2026-10-01).
Essential Critical Care (critical illness, modelled) (CI-CHUBB-05): active, in force.
Jaminan Kesehatan Nasional (JKN) (BPJS-KES-RIZKY): active, in force.
Road traffic accident compensation (UU 33/34 1964) (JASA-RAHARJA): active, in force.
Indicative only, based on the wording in your documents; the insurer makes the claim decision and the policy wording prevails.
```

### H06 - Named critical illness without an admission (PASS)

**User:** Which of my policies pay out if I get cancer?

**Tools:** get_my_policies, get_payment_status, get_payment_status, get_payment_status, get_payment_status, get_payment_status, check_coverage

```
No event date was given, so I evaluated the policies as of 2026-10-11.
Essential Critical Care (critical illness, modelled) (CI-CHUBB-05): depends on one fact - if survival days = 0-29: not covered; if survival days = 30-31: covered.
One question before I can answer: How many days did the insured survive after the diagnosis? It matters because the answer changes the outcome (0-29: not covered; 30-31: covered). The clause that makes this matter (CI-CHUBB-05, Survival Period) says: "The Insured must survive for at least 30 days after the date of diagnosis of the critical illness; no benefit is payable if the Insured dies within this survival period."
Indicative only, based on the wording in your documents; the insurer makes the claim decision and the policy wording prevails.
Alert: Flexi Life Protection (term life, yearly renewable to age 85) (TL-ASTRA-07) has lapsed: premium unpaid since 2026-09-01, grace ended 2026-10-01. A death or claim after that date is not covered until reinstated.
```

### H07 - Typo-free but unusual phrasing: max room rate (PASS)

**User:** whats the max my group plan pays per day for a hospital room

**Tools:** get_my_policies, get_payment_status, get_payment_status, get_payment_status, get_payment_status, get_payment_status, get_payment_status

```
Nusantara Group Health (employer plan, cashless network N1) (GH-NUSA-GRP) covers hospitalization: IDR 1,500,000/day, max 60 days/year; annual cap IDR 150,000,000 [c_room].
Nusantara Group Health (employer plan, cashless network N1) (GH-NUSA-GRP) covers hospitalization: IDR 7,700,000/case [pays_other_inpatient].
Nusantara Group Health (employer plan, cashless network N1) (GH-NUSA-GRP) covers surgery: IDR 25,000,000/case; annual cap IDR 150,000,000 [c_surgery].
Nusantara Group Health (employer plan, cashless network N1) (GH-NUSA-GRP) covers icu: IDR 3,000,000/day, max 15 days/year [c_icu].
Indicative only, based on the wording in your documents; the insurer makes the claim decision and the policy wording prevails.
```

### H08 - Full Indonesian crash claim with expired SIM (PASS)

**User:** tolong bantu klaim kecelakaan 5 Oktober 2026, tabrakan sama mobil, saya lagi order, SIM saya mati

**Tools:** get_my_policies, get_payment_status, get_payment_status, get_payment_status, get_payment_status, check_coverage, claim_readiness, cob_plan

```
Essential Plus Personal Accident (PA-CHUBB-03): Not covered (indicative). Reason: riding without a valid driving licence is excluded [NO_VALID_LICENSE].
- Clause [PA-CHUBB-03 General Exclusions (d), k_valid_license]: "driving/riding without a valid license; or"
Driver-partner on-trip accident protection (PLATFORM-ACC): Covered (indicative). Indicative benefit: IDR 5,000,000.
- Clause [PLATFORM-ACC Benefits, 2, c_medical_on_trip]: "Medical expenses from an accident while on an active order: actual expenses up to IDR 5,000,000 per accident, in excess of any amount recoverable from Jasa Raharja or other insurance."
Jaminan Kesehatan Nasional (JKN) (BPJS-KES-DEWI): Not covered (indicative). Reason: the policy was not in force (premium unpaid beyond the grace period) [LAPSED].
- Clause [BPJS-KES-DEWI Kepesertaan (modelled), k_premium_active]: "Membership status becomes inactive from the 1st of the month following a missed contribution. Benefits are suspended until all arrears are paid; after reactivation, inpatient care within 45 days is subject to a service fee."
- Note: is_emergency does not change the verdict.
Road traffic accident compensation (UU 33/34 1964) (JASA-RAHARJA): Covered (indicative). Indicative benefit: IDR 20,000,000.
- Clause [JASA-RAHARJA Santunan (modelled on PMK 15/16 2017), c_medical]: "Victims of a traffic accident involving two or more motor vehicles are entitled to compensation for medical treatment costs up to IDR 20,000,000, paid directly to the hospital or reimbursed."
Filing deadline for PLATFORM-ACC: 2026-10-12 (counted from 2026-10-05), 1 days left; a late claim is rejected [p_filing_7d].
Documents required for PLATFORM-ACC: app claim form; trip log screenshot; medical report; itemised bill and receipts (original); id copy; police report (BAP)
```

### H09 - Cosmetic surgery on the group plan (PASS)

**User:** does my company plan pay for a nose job (cosmetic surgery)?

**Tools:** get_my_policies, get_payment_status, get_payment_status, get_payment_status, get_payment_status, get_payment_status, get_payment_status, check_coverage

```
No event date was given, so I evaluated the policies as of 2026-10-11.
Nusantara Group Health (employer plan, cashless network N1) (GH-NUSA-GRP): Not covered (indicative). Reason: exclusion cosmetic [EXCLUSION_COSMETIC].
- Clause [GH-NUSA-GRP Exclusions 3, x_cosmetic]: "Cosmetic or plastic surgery except reconstructive surgery necessitated by an accident."
Indicative only, based on the wording in your documents; the insurer makes the claim decision and the policy wording prevails.
```

### H10 - Administrative question with no policy clause (PASS)

**User:** Do I need to tell the insurer if I move to another city?

**Tools:** get_my_policies, get_payment_status, get_payment_status, get_payment_status, get_payment_status, get_payment_status

```
Not determinable from your documents: no extracted clause addresses this. I can schedule a call-back with the insurer (this needs your confirmation).
Indicative only, based on the wording in your documents; the insurer makes the claim decision and the policy wording prevails.
```
