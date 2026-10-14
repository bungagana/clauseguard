# ClauseGuard off-script question report

Generated 2026-10-11 - LLM: mocked / deterministic fallbacks - policy source: sandbox

**15/15 tasks passed.** Criteria are evaluated by code and regex on structured Reply fields (verdict, payable, deadline, denial codes, clarification slot, refusal flag, executed tool tiers, COB order); no model judges anything.

| id | kind | persona | title | result | failures |
|---|---|---|---|---|---|
| O01 | off_script | rizky | Indonesian-English mix: claim payout after typhoid stay | PASS |  |
| O02 | off_script | rizky | Typos and slang: ICU cover on the hospital cash plan | PASS |  |
| O03 | off_script | rizky | Discharge date only: how long to file | PASS |  |
| O04 | off_script | rizky | Colloquial status question: is my life insurance still active | PASS |  |
| O05 | off_script | rizky | Relative date: hernia surgery next month | PASS |  |
| O06 | off_script | santoso | Dependant by relation word: son's asthma, no stale claim data | PASS |  |
| O07 | off_script | santoso | Who pays first for a child admitted to a partner hospital | PASS |  |
| O08 | off_script | santoso | Hypothetical resignation then death: group life | PASS |  |
| O09 | off_script | dewi | Full Indonesian: lapsed BPJS and inpatient care | PASS |  |
| O10 | off_script | dewi | Single-vehicle fall, negated 'no other vehicle' | PASS |  |
| O11 | off_script | dewi | Platform claim deadline with an 'during an order' crash | PASS |  |
| O12 | off_script | rizky | Generic glossary question, no policy data | PASS |  |
| O13 | off_script | rizky | Plain Indonesian: daily hospital benefit | PASS |  |
| O14 | off_script | santoso | Future-dated surgery crosses a 12-month waiting period | PASS |  |
| O15 | off_script | rizky | Unsupported action: cancel a policy | PASS |  |

off_script: 15/15 passed

## Failure details

None.

## Transcripts (all tasks)

### O01 - Indonesian-English mix: claim payout after typhoid stay (PASS)

**User:** klaim saya bisa cair ga? kmrn opname 4 hari karena tifus, 5-8 okt 2026

**Tools:** get_my_policies, get_payment_status, get_payment_status, get_payment_status, get_payment_status, get_payment_status, check_coverage, claim_readiness

```
Sompo Health Insurance Hospital Care Plan (Hospital Cash Plan) (HCP-SOMPO-01): Covered (indicative). Indicative benefit: IDR 2,000,000.
- Clause [HCP-SOMPO-01 Benefits, Art. 1, c_hosp_daily]: "This Policy provide daily cash compensation to Participants as stated in the Policy Summary if during the Insurance period, the Participant is affected by an illness or has an accident and requires Hospitalization in the Hospital. For this benefit, it is"
Jaminan Kesehatan Nasional (JKN) (BPJS-KES-RIZKY): depends on one fact - if facility bpjs partner = yes: covered.
Filing deadline for HCP-SOMPO-01: 2026-12-07 (counted from 2026-10-08), 57 days left; a late claim is rejected [p_filing_60d].
Documents required for HCP-SOMPO-01: original claim form; receipt original or legalised; receipt details; medical resume inpatient; prescription copy; diagnostic results.
Readiness flags: INCOMPLETE_DOCS.
One question before I can answer: Is the hospital a BPJS Kesehatan partner facility? It matters because the answer changes the outcome (yes: covered). The clause that makes this matter (BPJS-KES-RIZKY, Manfaat 1 (modelled)) says: "Inpatient care is guaranteed at a BPJS Kesehatan partner facility (FKRTL) according to the INA-CBG package tariff for the participant's class, on referral from the first-level facility or through the emergency unit. Services at non-partner facilities are not reimbursed except in an emergency."
Indicative only, based on the wording in your documents; the insurer makes the claim decision and the policy wording prevails.
Alert: Flexi Life Protection (term life, yearly renewable to age 85) (TL-ASTRA-07) has lapsed: premium unpaid since 2026-09-01, grace ended 2026-10-01. A death or claim after that date is not covered until reinstated.
```

### O02 - Typos and slang: ICU cover on the hospital cash plan (PASS)

**User:** does the hospitel cash thingy pay 4 ICU also??

**Tools:** get_my_policies, get_payment_status, get_payment_status, get_payment_status, get_payment_status, get_payment_status

```
Sompo Health Insurance Hospital Care Plan (Hospital Cash Plan) (HCP-SOMPO-01) hospitalization: IDR 500,000/day, max 90 days/year.
- [HCP-SOMPO-01 Benefits, Art. 1, c_hosp_daily] "This Policy provide daily cash compensation to Participants as stated in the Policy Summary if during the Insurance period, the Participant is affected by an illness or has an accident and requires Hospitalization in the Hospital. For this benefit, it is valid for maximum 2 (two) events of Hospitalization and a maximum of 90 (Ninety) days of treatment during the policy period or the period listed in the Policy Summary. Participants are entitled to inpatient compensation benefits if they have received treatment for at least 1x24 (one time twenty-four) hours at the hospital."
Sompo Health Insurance Hospital Care Plan (Hospital Cash Plan) (HCP-SOMPO-01) icu: IDR 1,000,000/day, max 20 days/year.
- [HCP-SOMPO-01 Benefits, Art. 3, c_icu_daily] "This Policy provide daily cash compensation to Participants as stated in the Policy Summary if during the Insurance period, the Participant is exposed to an illness or experiences a critical incident as a result of an Accident and requires treatment in the Intensive Care Unit (ICU / ICCU / HCU / PICU / NICU) room. For this benefit, the maximum 2 (two) two Hospitalizations are valid and a maximum of 20 (twenty) days of treatment during the policy period or the period listed in the Policy Summary."
Indicative only, based on the wording in your documents; the insurer makes the claim decision and the policy wording prevails.
Alert: Flexi Life Protection (term life, yearly renewable to age 85) (TL-ASTRA-07) has lapsed: premium unpaid since 2026-09-01, grace ended 2026-10-01. A death or claim after that date is not covered until reinstated.
```

### O03 - Discharge date only: how long to file (PASS)

**User:** I was discharged 7 Oct 2026 after a typhoid stay. How long do I have to file with my hospital cash plan?

**Tools:** get_my_policies, get_payment_status, get_payment_status, get_payment_status, get_payment_status, get_payment_status, check_coverage, claim_readiness

```
No event date was given, so I evaluated the policies as of 2026-10-11.
Sompo Health Insurance Hospital Care Plan (Hospital Cash Plan) (HCP-SOMPO-01): Covered (indicative).
- Clause [HCP-SOMPO-01 Benefits, Art. 1, c_hosp_daily]: "This Policy provide daily cash compensation to Participants as stated in the Policy Summary if during the Insurance period, the Participant is affected by an illness or has an accident and requires Hospitalization in the Hospital. For this benefit, it is"
Jaminan Kesehatan Nasional (JKN) (BPJS-KES-RIZKY): depends on one fact - if facility bpjs partner = yes: covered.
Filing deadline for HCP-SOMPO-01: 2026-12-06 (counted from 2026-10-07), 56 days left; a late claim is rejected [p_filing_60d].
Documents required for HCP-SOMPO-01: original claim form; receipt original or legalised; receipt details; medical resume inpatient; prescription copy; diagnostic results.
Readiness flags: INCOMPLETE_DOCS.
One question before I can answer: Is the hospital a BPJS Kesehatan partner facility? It matters because the answer changes the outcome (yes: covered). The clause that makes this matter (BPJS-KES-RIZKY, Manfaat 1 (modelled)) says: "Inpatient care is guaranteed at a BPJS Kesehatan partner facility (FKRTL) according to the INA-CBG package tariff for the participant's class, on referral from the first-level facility or through the emergency unit. Services at non-partner facilities are not reimbursed except in an emergency."
Indicative only, based on the wording in your documents; the insurer makes the claim decision and the policy wording prevails.
Alert: Flexi Life Protection (term life, yearly renewable to age 85) (TL-ASTRA-07) has lapsed: premium unpaid since 2026-09-01, grace ended 2026-10-01. A death or claim after that date is not covered until reinstated
```

### O04 - Colloquial status question: is my life insurance still active (PASS)

**User:** is my life insurance still active? i think i missed a payment

**Tools:** get_my_policies, get_payment_status, get_payment_status, get_payment_status, get_payment_status, get_payment_status

```
Sompo Health Insurance Hospital Care Plan (Hospital Cash Plan) (HCP-SOMPO-01): active, in force.
Flexi Life Protection (term life, yearly renewable to age 85) (TL-ASTRA-07): NOT in force (grace ended 2026-10-01).
Essential Critical Care (critical illness, modelled) (CI-CHUBB-05): active, in force.
Jaminan Kesehatan Nasional (JKN) (BPJS-KES-RIZKY): active, in force.
Road traffic accident compensation (UU 33/34 1964) (JASA-RAHARJA): active, in force.
Indicative only, based on the wording in your documents; the insurer makes the claim decision and the policy wording prevails.
```

### O05 - Relative date: hernia surgery next month (PASS)

**User:** if I'm hospitalised for hernia surgery next month, will it be paid?

**Tools:** get_my_policies, get_payment_status, get_payment_status, get_payment_status, get_payment_status, get_payment_status, check_coverage

```
Sompo Health Insurance Hospital Care Plan (Hospital Cash Plan) (HCP-SOMPO-01): Not covered (indicative). Reason: the diagnosis is on the specified-disease list and falls inside its longer waiting period [SPECIFIED_DISEASE_WAITING].
- Clause [HCP-SOMPO-01 Policy Summary (specified diseases, 12 months), p_waiting_specified_12m]: "Treatment or Treatment related to Specific Diseases or existing Diseases related to Congenital Disorders found and or known after birth and or Hereditary Diseases, for example: Hernia, VSD, ASD, Debilitation, Embicil, Mongoloid, Cretinism, Thalassemia"
Jaminan Kesehatan Nasional (JKN) (BPJS-KES-RIZKY): depends on one fact - if facility bpjs partner = yes: covered.
One question before I can answer: Is the hospital a BPJS Kesehatan partner facility? It matters because the answer changes the outcome (yes: covered). The clause that makes this matter (BPJS-KES-RIZKY, Manfaat 1 (modelled)) says: "Inpatient care is guaranteed at a BPJS Kesehatan partner facility (FKRTL) according to the INA-CBG package tariff for the participant's class, on referral from the first-level facility or through the emergency unit. Services at non-partner facilities are not reimbursed except in an emergency."
Indicative only, based on the wording in your documents; the insurer makes the claim decision and the policy wording prevails.
Alert: Flexi Life Protection (term life, yearly renewable to age 85) (TL-ASTRA-07) has lapsed: premium unpaid since 2026-09-01, grace ended 2026-10-01. A death or claim after that date is not covered until reinstated.
```

### O06 - Dependant by relation word: son's asthma, no stale claim data (PASS)

**User:** my son's asthma, is it covered by the company insurance? admitted 28 Sep 2026

**Tools:** get_my_policies, get_payment_status, get_payment_status, get_payment_status, get_payment_status, get_payment_status, get_payment_status, check_coverage, claim_readiness, cob_plan

```
Nusantara Group Health (employer plan, cashless network N1) (GH-NUSA-GRP): Covered (indicative).
- Clause [GH-NUSA-GRP Schedule of Benefits, 1, c_room]: "Room and board: actual charges up to IDR 1,500,000 per day, maximum 60 days per policy year per insured person. Other inpatient charges (drugs, laboratory, doctor visits): actual charges up to IDR 7,700,000 per case. Annual limit IDR 150,000,000 per insured"
Hospital Cash Plan rider (family, IDR 300,000/day) (HCP-RIDER-B): Covered (indicative).
- Clause [HCP-RIDER-B Manfaat 1.a / 1.d, c_hosp_daily]: "Kami akan membayar manfaat Asuransi Tambahan sebesar 1 kali Santunan Tunai Harian apabila Tertanggung menjalani Rawat Inap akibat Penyakit. Maksimum jumlah hari Rawat Inap yang ditanggung oleh Kami akibat Penyakit dan Kecelakaan atas Polis ini adalah 365 hari"
Sehat Mandiri Individual Health (reimbursement) (HI-INDIV-S): Not covered (indicative). Reason: the condition existed before the policy started (pre-existing condition exclusion) [PRE_EXISTING].
- Clause [HI-INDIV-S Exclusions 1, x_preexisting_hospitalization]: "Pre-existing conditions, meaning any illness or injury for which the insured person received diagnosis, treatment or advice, or which showed symptoms a reasonable person would have sought advice for, before the effective date, are excluded during the first 24"
  The pre-existing exclusion on HI-INDIV-S runs until 2027-11-01.
Jaminan Kesehatan Nasional (JKN) (BPJS-KES-SANTOSO): depends on one fact - if facility bpjs partner = yes: covered.
Documents required for GH-NUSA-GRP: original claim form; itemised bill original; medical resume inpatient; employee ID; id copy.
Readiness flags: INCOMPLETE_DOCS.
Who pays, in order (coordination of benefits, jurisdiction ID; statutory amounts are sandbox values, verify with
```

### O07 - Who pays first for a child admitted to a partner hospital (PASS)

**User:** who pays first if Nadia is hospitalised at a BPJS partner hospital for 3 days, bill 9 million?

**Tools:** get_my_policies, get_payment_status, get_payment_status, get_payment_status, get_payment_status, get_payment_status, get_payment_status, check_coverage, claim_readiness, cob_plan

```
No event date was given, so I evaluated the policies as of 2026-10-11.
Jaminan Kesehatan Nasional (JKN) (BPJS-KES-SANTOSO): Covered (indicative).
- Clause [BPJS-KES-SANTOSO Manfaat 1 (modelled), c_inpatient_partner]: "Inpatient care is guaranteed at a BPJS Kesehatan partner facility (FKRTL) according to the INA-CBG package tariff for the participant's class, on referral from the first-level facility or through the emergency unit. Services at non-partner facilities are not"
- Note: is_emergency does not change the verdict.
Nusantara Group Health (employer plan, cashless network N1) (GH-NUSA-GRP): depends on one fact - if cause = illness: covered; if cause = accident: covered; if cause = suicide: not covered; if cause = war: covered; if cause = aviation: covered; if cause = intoxication: covered.
Hospital Cash Plan rider (family, IDR 300,000/day) (HCP-RIDER-B): depends on one fact - if cause = illness: covered; if cause = accident: covered; if cause = suicide: not covered; if cause = war: not covered; if cause = aviation: covered; if cause = intoxication: not covered.
Sehat Mandiri Individual Health (reimbursement) (HI-INDIV-S): depends on one fact - if cause = suicide: not covered; if cause = intoxication: not covered.
Documents required for BPJS-KES-SANTOSO: bpjs card or jkn app; id copy; referral letter or er note; sep.
Readiness flags: INCOMPLETE_DOCS.
Who pays, in order (coordination of benefits, jurisdiction ID; statutory amounts are sandbox values, verify with the payer):
1. Jaminan Kesehatan Nasional (JKN) (BPJS-KES-SANTOSO): pays IDR 9,000,000 (indemnity). first guarantor at a partner facility (INA-CBG tariff, sandbox mock); class-upgrade difference is out of pocket unless a COB agreement exists
   documents: bpjs card or jkn app; id copy; referral letter or er n
```

### O08 - Hypothetical resignation then death: group life (PASS)

**User:** If I resign next month and then die, does the group life still pay my family?

**Tools:** get_my_policies, get_payment_status, get_payment_status, get_payment_status, get_payment_status, get_payment_status, get_payment_status, check_coverage

```
Nusantara Group Term Life (24 x salary) (GL-NUSA-GRP): Not covered (indicative). Reason: group terminated [GROUP_TERMINATED].
- Clause [GL-NUSA-GRP General Conditions, 6, t_employment]: "Cover terminates on the date the employee ceases employment with the Policyholder. No conversion option applies."
- Note: cause does not change the verdict.
- [GL-NUSA-GRP Exclusions 1, p_suicide_12m] "Death by suicide within 12 months of the date the employee's cover commenced is excluded."
- [GL-NUSA-GRP Claims, p_filing_90d] "Written notice of death with supporting documents must reach the Company within 90 days of the date of death; late claims may be rejected."
Indicative only, based on the wording in your documents; the insurer makes the claim decision and the policy wording prevails.
```

### O09 - Full Indonesian: lapsed BPJS and inpatient care (PASS)

**User:** BPJS ku mati sejak juli, masih bisa dipake buat rawat inap ga?

**Tools:** get_my_policies, get_payment_status, get_payment_status, get_payment_status, get_payment_status, check_coverage

```
No event date was given, so I evaluated the policies as of 2026-10-11.
Jaminan Kesehatan Nasional (JKN) (BPJS-KES-DEWI): depends on one fact - if facility bpjs partner = yes: not covered.
One question before I can answer: Is the hospital a BPJS Kesehatan partner facility? It matters because the answer changes the outcome (yes: not covered). The clause that makes this matter (BPJS-KES-DEWI, Manfaat 1 (modelled)) says: "Inpatient care is guaranteed at a BPJS Kesehatan partner facility (FKRTL) according to the INA-CBG package tariff for the participant's class, on referral from the first-level facility or through the emergency unit. Services at non-partner facilities are not reimbursed except in an emergency."
Indicative only, based on the wording in your documents; the insurer makes the claim decision and the policy wording prevails.
Alert: BPJS Kesehatan (BPJS-KES-DEWI) is inactive (3 months of arrears). Settle the arrears before relying on it.
```

### O10 - Single-vehicle fall, negated 'no other vehicle' (PASS)

**User:** I fell off my bike alone yesterday, no other vehicle, my licence is valid. is Jasa Raharja going to pay?

**Tools:** get_my_policies, get_payment_status, get_payment_status, get_payment_status, get_payment_status, check_coverage, cob_plan

```
Road traffic accident compensation (UU 33/34 1964) (JASA-RAHARJA): Not covered (indicative). Reason: exclusion accident medical [EXCLUSION_ACCIDENT_MEDICAL].
- Clause [JASA-RAHARJA Pengecualian (modelled), x_single_vehicle_medical]: "Single-vehicle accidents (the victim is the driver and no other vehicle is involved) are not covered by the road-traffic accident guarantee."
Essential Plus Personal Accident (PA-CHUBB-03): cannot decide yet; I need to know occupation class.
Driver-partner on-trip accident protection (PLATFORM-ACC): depends on one fact - if work related = yes: covered; if work related = no: not addressed by the policy.
Jaminan Kesehatan Nasional (JKN) (BPJS-KES-DEWI): depends on one fact - if facility bpjs partner = yes: not covered.
Who pays, in order (coordination of benefits, jurisdiction ID; statutory amounts are sandbox values, verify with the payer):
1. Road traffic accident compensation (UU 33/34 1964) (JASA-RAHARJA): not claimable [EXCLUSION_ACCIDENT_MEDICAL].
2. Jaminan Kesehatan Nasional (JKN) (BPJS-KES-DEWI): not claimable [LAPSED]. BPJS Kesehatan inactive: settle arrears first (reactivation rules apply)
3. Essential Plus Personal Accident (PA-CHUBB-03): uncertain; depends on occupation class. payable only if the open question resolves in your favour; amount shown is the remainder it could cover
   documents: original claim form; police report (BAP); medical report; itemised bill original; id copy; driving license copy; physician certificate ttd; claim form death; death cert original or legalised; post mortem if available; beneficiary id and relationship proof; written chronology of the accident
4. Driver-partner on-trip accident protection (PLATFORM-ACC): uncertain; depends on work related. payable only if the open question resolves in your favo
```

### O11 - Platform claim deadline with an 'during an order' crash (PASS)

**User:** platform insurance claim deadline? i crashed during an order on 9 Oct 2026

**Tools:** get_my_policies, get_payment_status, get_payment_status, get_payment_status, get_payment_status, check_coverage, claim_readiness, cob_plan

```
Driver-partner on-trip accident protection (PLATFORM-ACC): Covered (indicative).
- Clause [PLATFORM-ACC Benefits, 2, c_medical_on_trip]: "Medical expenses from an accident while on an active order: actual expenses up to IDR 5,000,000 per accident, in excess of any amount recoverable from Jasa Raharja or other insurance."
Road traffic accident compensation (UU 33/34 1964) (JASA-RAHARJA): Not covered (indicative). Reason: exclusion accident medical [EXCLUSION_ACCIDENT_MEDICAL].
- Clause [JASA-RAHARJA Pengecualian (modelled), x_single_vehicle_medical]: "Single-vehicle accidents (the victim is the driver and no other vehicle is involved) are not covered by the road-traffic accident guarantee."
Essential Plus Personal Accident (PA-CHUBB-03): depends on one fact - if license valid = no: not covered.
Jaminan Kesehatan Nasional (JKN) (BPJS-KES-DEWI): depends on one fact - if facility bpjs partner = yes: not covered.
Filing deadline for PLATFORM-ACC: 2026-10-16 (counted from 2026-10-09), 5 days left; a late claim is rejected [p_filing_7d].
Documents required for PLATFORM-ACC: app claim form; trip log screenshot; medical report; itemised bill and receipts (original); id copy; police report (BAP); written chronology of the accident.
Readiness flags: INCOMPLETE_DOCS.
Who pays, in order (coordination of benefits, jurisdiction ID; statutory amounts are sandbox values, verify with the payer):
1. Road traffic accident compensation (UU 33/34 1964) (JASA-RAHARJA): not claimable [EXCLUSION_ACCIDENT_MEDICAL].
2. Jaminan Kesehatan Nasional (JKN) (BPJS-KES-DEWI): not claimable [LAPSED]. BPJS Kesehatan inactive: settle arrears first (reactivation rules apply)
3. Essential Plus Personal Accident (PA-CHUBB-03): uncertain; depends on license valid. payable only if the open question resolves in y
```

### O12 - Generic glossary question, no policy data (PASS)

**User:** what does co-payment mean?

**Tools:** -

```
The share of each covered expense you pay (a percentage, often with a cap per hospitalisation). This is general information, not advice about a specific claim.
```

### O13 - Plain Indonesian: daily hospital benefit (PASS)

**User:** Berapa santunan harian rumah sakit saya?

**Tools:** get_my_policies, get_payment_status, get_payment_status, get_payment_status, get_payment_status, get_payment_status

```
Sompo Health Insurance Hospital Care Plan (Hospital Cash Plan) (HCP-SOMPO-01) hospitalization: IDR 500,000/day, max 90 days/year.
- [HCP-SOMPO-01 Benefits, Art. 1, c_hosp_daily] "This Policy provide daily cash compensation to Participants as stated in the Policy Summary if during the Insurance period, the Participant is affected by an illness or has an accident and requires Hospitalization in the Hospital. For this benefit, it is valid for maximum 2 (two) events of Hospitalization and a maximum of 90 (Ninety) days of treatment during the policy period or the period listed in the Policy Summary. Participants are entitled to inpatient compensation benefits if they have received treatment for at least 1x24 (one time twenty-four) hours at the hospital."
Sompo Health Insurance Hospital Care Plan (Hospital Cash Plan) (HCP-SOMPO-01) icu: IDR 1,000,000/day, max 20 days/year.
- [HCP-SOMPO-01 Benefits, Art. 3, c_icu_daily] "This Policy provide daily cash compensation to Participants as stated in the Policy Summary if during the Insurance period, the Participant is exposed to an illness or experiences a critical incident as a result of an Accident and requires treatment in the Intensive Care Unit (ICU / ICCU / HCU / PICU / NICU) room. For this benefit, the maximum 2 (two) two Hospitalizations are valid and a maximum of 20 (twenty) days of treatment during the policy period or the period listed in the Policy Summary."
Indicative only, based on the wording in your documents; the insurer makes the claim decision and the policy wording prevails.
Alert: Flexi Life Protection (term life, yearly renewable to age 85) (TL-ASTRA-07) has lapsed: premium unpaid since 2026-09-01, grace ended 2026-10-01. A death or claim after that date is not covered until reinstated.
```

### O14 - Future-dated surgery crosses a 12-month waiting period (PASS)

**User:** Sari is scheduled for hernia surgery on 20 November 2026. Will HI-INDIV-S pay?

**Tools:** get_my_policies, get_policy_clause, get_payment_status, get_payment_status, get_payment_status, get_payment_status, get_payment_status, get_payment_status, check_coverage

```
Sehat Mandiri Individual Health (reimbursement) (HI-INDIV-S): Covered (indicative).
- Clause [HI-INDIV-S Schedule of Benefits, 2, c_surgery]: "Surgical charges: actual charges up to IDR 20,000,000 per case, subject to the co-payment."
Indicative only, based on the wording in your documents; the insurer makes the claim decision and the policy wording prevails.
```

### O15 - Unsupported action: cancel a policy (PASS)

**User:** pls cancel my policy HCP-SOMPO-01

**Tools:** -

```
I can't cancel, surrender or close a policy or claim: those changes are made by the insurer after it verifies your identity, so nothing on your account has been changed. I can explain what your policy wording says about cancellation, the free-look period or refunds, or schedule a call-back from the insurer (that needs your confirmation).
```
