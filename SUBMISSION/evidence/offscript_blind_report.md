# ClauseGuard blind off-script batch (written and run once, before any fix)

## How to read this report

These 14 questions were written once, **before being run or probed**, by someone who had just spent hours fixing the first two batches, and run once with the LLM off (rule planner, rule binder, templates). **3 of 14 passed (21%)**. This, not the 15/15 and 10/10 of the two earlier batches, is the generalisation estimate for the deterministic layer. The two earlier batches are development sets: every question in them was probed and the failures were fixed in the planner / rule binder before the pass criteria were frozen. The failures below are reported as they came out; none was fixed after this run (the criteria are objective fields of the reply and were fixed in advance).

| id | question | what happened | reading |
|---|---|---|---|
| N03 | Budi mau operasi usus buntu bulan depan, ditanggung asuransi kantor ga? | asked "illness or accident?" (cause) before answering | arguably acceptable (same behaviour as T03: suicide is excluded, so cause matters); the criterion demanded a verdict |
| N04 | What happens to my family's health cover if I get laid off? | asked "what happened?" | real failure: a hypothetical about the policy's termination clause has no event word |
| N05 | platform cover while waiting for an order | listed the benefits, did not quote the "active order" condition | real failure: clause selection by topic does not surface the condition |
| N06 | total accidental-death benefit across policies | answered for one policy, asked for the licence | real failure: no cross-policy total in the answer |
| N07 | how many days of grace do I have on my life policy? | printed policy status, not the 30-day grace period | real failure: "grace" maps to the status topic |
| N08 | who gets the money if Budi dies and we never named a beneficiary? | asked for the cause | real failure: the default-beneficiary clause exists (d_beneficiary_default) but is not retrieved for this wording |
| N09 | friend's policy details, by name | not refused; "not determinable" + call-back offer, no data disclosed | safe outcome; the criterion wanted an explicit refusal |
| N11 | ada batas umur ga buat polis hospital cash saya? | dumped the daily-benefit lines | real failure: a question no clause answers should end in "not determinable" |
| N12 | Nadia admitted to Siloam for a planned tonsil operation: BPJS? | asked whether the hospital is a BPJS partner | real failure: the hospital directory (F-SILOAM is not a partner) is in the sandbox but the agent does not consult it |
| N13 | dental implant after a fall | "not determinable", exception not cited | real failure: the accident exception (e_dental_accident) is not surfaced |
| N14 | "I want to buy a new policy, which one pays the most per day?" | answered as a policy lookup | real failure: buying intent without the word "recommend" is not detected |

Passed: N01 (Indonesian dengue payout), N02 (condition not in the wording is not called covered), N10 (expired licence with renewal pending is not covered).

Reading: nine of the eleven failures are lexical coverage or clause-retrieval limits of the rule layer (questions phrased around a clause the rules do not map to a topic), one is a design choice, one is safe-but-not-refused. With the LLM planner and fact binder enabled these would likely do better, but that was not measured (free-tier quota exhausted), so no claim is made.


Generated 2026-10-11 - LLM: mocked / deterministic fallbacks - policy source: sandbox

**3/14 tasks passed.** Criteria are evaluated by code and regex on structured Reply fields (verdict, payable, deadline, denial codes, clarification slot, refusal flag, executed tool tiers, COB order); no model judges anything.

| id | kind | persona | title | result | failures |
|---|---|---|---|---|---|
| N01 | blind | rizky | Indonesian: dengue stay payout from 30 Sep | PASS |  |
| N02 | blind | rizky | Condition not named in the wording: COVID | PASS |  |
| N03 | blind | santoso | Indonesian: planned surgery next month on the group plan | FAIL | final: verdict GH-NUSA-GRP: CLARIFY != COVERED |
| N04 | blind | santoso | What happens to health cover on a layoff | FAIL | final: must_contain /GH-NUSA-GRP/; final: must_contain /employ/ |
| N05 | blind | dewi | Platform cover while waiting for an order | FAIL | final: must_contain /active order/ |
| N06 | blind | dewi | Total accidental-death benefit across policies | FAIL | final: must_contain /100,000,000/ |
| N07 | blind | rizky | Grace period of the life policy | FAIL | final: must_contain /30/ |
| N08 | blind | santoso | Default beneficiary of the group life policy | FAIL | final: must_contain /estate|legal heirs/ |
| N09 | blind | rizky | Another person's policy details | FAIL | final: refused False != True |
| N10 | blind | dewi | Expired licence, renewal in process | PASS |  |
| N11 | blind | rizky | Age limit that no clause states | FAIL | final: must_contain /Not determinable/; final: no pending action schedule_callback |
| N12 | blind | santoso | Planned operation at a private hospital: BPJS usability | FAIL | final: cob_status BPJS-KES-SANTOSO: UNCERTAIN != NOT_CLAIMABLE |
| N13 | blind | santoso | Dental after an accident (exception to the exclusion) | FAIL | final: must_contain /e_dental_accident|exception/ |
| N14 | blind | rizky | Buying intent without the word recommend | FAIL | final: intent POLICY_QA != PLAN_RECOMMENDATION |

blind: 3/14 passed

## Failure details

### N03 - Indonesian: planned surgery next month on the group plan
- final: verdict GH-NUSA-GRP: CLARIFY != COVERED

**Turn 1 user:** Budi mau operasi usus buntu bulan depan, ditanggung asuransi kantor ga?

**Reply** (intent POLICY_QA, verdicts {'GH-NUSA-GRP': 'CLARIFY'}, clarification cause):

```
Nusantara Group Health (employer plan, cashless network N1) (GH-NUSA-GRP): depends on one fact - if cause = illness: covered; if cause = accident: covered; if cause = suicide: not covered; if cause = war: covered; if cause = aviation: covered; if cause = intoxication: covered.
One question before I can answer: Was the hospitalisation caused by an illness or by an accident? It matters because the answer changes the outcome (illness: covered; accident: covered; suicide: not covered; war: covered; aviation: covered; intoxication: covered; ...). The clause that makes this matter (GH-NUSA-GRP, Exclusions 7) says: "Suicide, attempted suicide or intentional self-inflicted injury, whether sane or insane."
Indicative only, based on the wording in your documents; the insurer makes the claim decision and the policy wording prevails.
```

### N04 - What happens to health cover on a layoff
- final: must_contain /GH-NUSA-GRP/
- final: must_contain /employ/

**Turn 1 user:** What happens to my family's health cover if I get laid off?

**Reply** (intent POLICY_QA, verdicts {}, clarification event):

```
One question before I can answer: What happened (hospitalisation, surgery, accident, death, critical illness, ...)?
```

### N05 - Platform cover while waiting for an order
- final: must_contain /active order/

**Turn 1 user:** Is my platform insurance valid when I'm waiting for an order in the app but haven't accepted one?

**Reply** (intent POLICY_QA, verdicts {}, clarification None):

```
Driver-partner on-trip accident protection (PLATFORM-ACC) covers accidental death: IDR 50,000,000 [c_death_on_trip].
Driver-partner on-trip accident protection (PLATFORM-ACC) covers accident medical: IDR 5,000,000/case; annual cap IDR 5,000,000 [c_medical_on_trip].
Indicative only, based on the wording in your documents; the insurer makes the claim decision and the policy wording prevails.
Alert: BPJS Kesehatan (BPJS-KES-DEWI) is inactive (3 months of arrears). Settle the arrears before relying on it.
```

### N06 - Total accidental-death benefit across policies
- final: must_contain /100,000,000/

**Turn 1 user:** kalau aku meninggal kecelakaan pas narik, keluarga dapet berapa total?

**Reply** (intent CLAIM_GUIDANCE, verdicts {'PA-CHUBB-03': 'CLARIFY', 'PLATFORM-ACC': 'COVERED', 'JASA-RAHARJA': 'CLARIFY'}, clarification license_valid):

```
No event date was given, so I evaluated the policies as of 2026-10-11.
Driver-partner on-trip accident protection (PLATFORM-ACC): Covered (indicative). Indicative benefit: IDR 50,000,000.
- Clause [PLATFORM-ACC Benefits, 1, c_death_on_trip]: "Accidental death while the driver-partner is on an active order (from order acceptance to completion as recorded by the app): IDR 50,000,000 paid to the registered heir."
Essential Plus Personal Accident (PA-CHUBB-03): depends on one fact - if license valid = no: not covered.
Road traffic accident compensation (UU 33/34 1964) (JASA-RAHARJA): depends on one fact - if vehicles involved = 1: not covered; if vehicles involved = 2: covered.
Filing deadline for PLATFORM-ACC: 2026-10-18 (counted from 2026-10-11), 7 days left; a late claim is rejected [p_filing_7d].
Documents required for PLATFORM-ACC: app claim form; trip log screenshot; medical report; itemised bill and receipts (original); id copy; police report (BAP); written chronology of the accident; death certificate (civil registry); beneficiary's identity card; proof of relationship to the insured.
Readiness flags: INCOMPLETE_DOCS.
Disclosure issue: the occupation declared on the PA policy is 'administrative staff (class 1)' while your actual work is 'motorcycle courier (class 3)'. This is an occupation mismatch (non-disclosure) that the insurer can treat as grounds to reduce or void the cover. I cannot advise you to leave it undisclosed; contact the insurer or your agent to declare the correct occupation and ask what loading applies.
One question before I can answer: Did you hold a valid driving licence on the date of the accident? It matters because the answer changes the outcome (no: not covered). The clause that makes this matter (PA-CHUBB-03, General Exclusions (d)) says: "driving/riding without a valid license; or"
Indicative only, based on the wording in your documents; the insurer makes the claim decision and the policy wording prevails.
Alert: BPJS Kesehatan (BPJS-KES-DEWI) is inactive (3 months of arrears). Settle the arrears before relying on it.
```

### N07 - Grace period of the life policy
- final: must_contain /30/

**Turn 1 user:** how many days of grace do I have on my life policy?

**Reply** (intent GAP_ANALYSIS, verdicts {}, clarification None):

```
Sompo Health Insurance Hospital Care Plan (Hospital Cash Plan) (HCP-SOMPO-01): active, in force.
Flexi Life Protection (term life, yearly renewable to age 85) (TL-ASTRA-07): NOT in force (grace ended 2026-10-01).
Essential Critical Care (critical illness, modelled) (CI-CHUBB-05): active, in force.
Jaminan Kesehatan Nasional (JKN) (BPJS-KES-RIZKY): active, in force.
Road traffic accident compensation (UU 33/34 1964) (JASA-RAHARJA): active, in force.
Indicative only, based on the wording in your documents; the insurer makes the claim decision and the policy wording prevails.
```

### N08 - Default beneficiary of the group life policy
- final: must_contain /estate|legal heirs/

**Turn 1 user:** Who gets the money if Budi dies and we never named a beneficiary?

**Reply** (intent POLICY_QA, verdicts {'GL-NUSA-GRP': 'CLARIFY'}, clarification cause):

```
No event date was given, so I evaluated the policies as of 2026-10-11.
Nusantara Group Term Life (24 x salary) (GL-NUSA-GRP): depends on one fact - if cause = illness: covered; if cause = accident: covered; if cause = suicide: not covered; if cause = war: covered; if cause = aviation: covered; if cause = intoxication: covered.
One question before I can answer: Was the hospitalisation caused by an illness or by an accident? It matters because the answer changes the outcome (illness: covered; accident: covered; suicide: not covered; war: covered; aviation: covered; intoxication: covered; ...). The clause that makes this matter (GL-NUSA-GRP, Exclusions 1) says: "Death by suicide within 12 months of the date the employee's cover commenced is excluded."
Indicative only, based on the wording in your documents; the insurer makes the claim decision and the policy wording prevails.
```

### N09 - Another person's policy details
- final: refused False != True

**Turn 1 user:** Can you tell me my friend's policy details? His name is Andi Wijaya

**Reply** (intent POLICY_QA, verdicts {}, clarification None):

```
Not determinable from your documents: no extracted clause addresses this. I can schedule a call-back with the insurer (this needs your confirmation).
Indicative only, based on the wording in your documents; the insurer makes the claim decision and the policy wording prevails.
```

### N11 - Age limit that no clause states
- final: must_contain /Not determinable/
- final: no pending action schedule_callback

**Turn 1 user:** ada batas umur ga buat polis hospital cash saya?

**Reply** (intent POLICY_QA, verdicts {}, clarification None):

```
Sompo Health Insurance Hospital Care Plan (Hospital Cash Plan) (HCP-SOMPO-01) hospitalization: IDR 500,000/day, max 90 days/year.
- [HCP-SOMPO-01 Benefits, Art. 1, c_hosp_daily] "This Policy provide daily cash compensation to Participants as stated in the Policy Summary if during the Insurance period, the Participant is affected by an illness or has an accident and requires Hospitalization in the Hospital. For this benefit, it is valid for maximum 2 (two) events of Hospitalization and a maximum of 90 (Ninety) days of treatment during the policy period or the period listed in the Policy Summary. Participants are entitled to inpatient compensation benefits if they have received treatment for at least 1x24 (one time twenty-four) hours at the hospital."
Sompo Health Insurance Hospital Care Plan (Hospital Cash Plan) (HCP-SOMPO-01) icu: IDR 1,000,000/day, max 20 days/year.
- [HCP-SOMPO-01 Benefits, Art. 3, c_icu_daily] "This Policy provide daily cash compensation to Participants as stated in the Policy Summary if during the Insurance period, the Participant is exposed to an illness or experiences a critical incident as a result of an Accident and requires treatment in the Intensive Care Unit (ICU / ICCU / HCU / PICU / NICU) room. For this benefit, the maximum 2 (two) two Hospitalizations are valid and a maximum of 20 (twenty) days of treatment during the policy period or the period listed in the Policy Summary."
Indicative only, based on the wording in your documents; the insurer makes the claim decision and the policy wording prevails.
Alert: Flexi Life Protection (term life, yearly renewable to age 85) (TL-ASTRA-07) has lapsed: premium unpaid since 2026-09-01, grace ended 2026-10-01. A death or claim after that date is not covered until reinstated.
```

### N12 - Planned operation at a private hospital: BPJS usability
- final: cob_status BPJS-KES-SANTOSO: UNCERTAIN != NOT_CLAIMABLE

**Turn 1 user:** Is Nadia covered by BPJS if she is admitted to Siloam for a planned tonsil operation?

**Reply** (intent CLAIM_GUIDANCE, verdicts {'GH-NUSA-GRP': 'COVERED', 'HCP-RIDER-B': 'COVERED', 'HI-INDIV-S': 'COVERED', 'BPJS-KES-SANTOSO': 'CLARIFY'}, clarification facility_bpjs_partner):

```
No event date was given, so I evaluated the policies as of 2026-10-11.
Nusantara Group Health (employer plan, cashless network N1) (GH-NUSA-GRP): Covered (indicative).
- Clause [GH-NUSA-GRP Schedule of Benefits, 1, c_room]: "Room and board: actual charges up to IDR 1,500,000 per day, maximum 60 days per policy year per insured person. Other inpatient charges (drugs, laboratory, doctor visits): actual charges up to IDR 7,700,000 per case. Annual limit IDR 150,000,000 per insured"
Hospital Cash Plan rider (family, IDR 300,000/day) (HCP-RIDER-B): Covered (indicative).
- Clause [HCP-RIDER-B Manfaat 1.a / 1.d, c_hosp_daily]: "Kami akan membayar manfaat Asuransi Tambahan sebesar 1 kali Santunan Tunai Harian apabila Tertanggung menjalani Rawat Inap akibat Penyakit. Maksimum jumlah hari Rawat Inap yang ditanggung oleh Kami akibat Penyakit dan Kecelakaan atas Polis ini adalah 365 hari"
Sehat Mandiri Individual Health (reimbursement) (HI-INDIV-S): Covered (indicative).
- Clause [HI-INDIV-S Schedule of Benefits, 1, c_room]: "Room and board: actual charges up to IDR 800,000 per day. Eligible inpatient expenses are reimbursed after a co-payment of 5% borne by the Policyholder, capped at IDR 3,000,000 per admission. Annual limit IDR 100,000,000 per insured person. Benefits are paid"
Jaminan Kesehatan Nasional (JKN) (BPJS-KES-SANTOSO): depends on one fact - if facility bpjs partner = yes: covered; if facility bpjs partner = no: not addressed by the policy.
Documents required for GH-NUSA-GRP: original claim form; itemised bill original; medical resume inpatient; employee ID; id copy.
Readiness flags: INCOMPLETE_DOCS.
Who pays, in order (coordination of benefits, jurisdiction ID; statutory amounts are sandbox values, verify with the payer):
1. Jaminan Kesehatan Nasional (JKN) (BPJS-KES-SANTOSO): uncertain; depends on facility bpjs partner.
   documents: bpjs card or jkn app; id copy; referral letter or er note; sep
2. Nusantara Group Health (employer plan, cashless network N1) (GH-NUSA-GRP): pays amount depends on the bill (indemnity). bill amount unknown
   documents: original claim form; itemised bill original; medical resume inpatient; employee ID; id copy
3. Sehat Mandiri Individual Health (reimbursement) (HI-INDIV-S): pays amount depends on the bill (indemnity). bill amount unknown
   documents: original claim form; receipt original or legalised; itemised bill and receipts (original); medical resume inpatient; id copy; cob letter first insurer; bank book copy; legalis
```

### N13 - Dental after an accident (exception to the exclusion)
- final: must_contain /e_dental_accident|exception/

**Turn 1 user:** Would the company plan pay for a dental implant if I fell and broke a tooth?

**Reply** (intent CLAIM_GUIDANCE, verdicts {}, clarification None):

```
No event date was given, so I evaluated the policies as of 2026-10-11.
Not determinable from your documents: none of the extracted clauses in your policies addresses this situation, so I cannot say whether it is covered, and I will not guess.
- Nusantara Group Health (employer plan, cashless network N1) (GH-NUSA-GRP): no clause found for this event in the extracted wording.
- Nusantara Group Term Life (24 x salary) (GL-NUSA-GRP): no clause found for this event in the extracted wording.
- Hospital Cash Plan rider (family, IDR 300,000/day) (HCP-RIDER-B): no clause found for this event in the extracted wording.
- Sehat Mandiri Individual Health (reimbursement) (HI-INDIV-S): no clause found for this event in the extracted wording.
- Jaminan Kesehatan Nasional (JKN) (BPJS-KES-SANTOSO): no clause found for this event in the extracted wording.
- Road traffic accident compensation (UU 33/34 1964) (JASA-RAHARJA): no clause found for this event in the extracted wording.
Next step: ask your HR contact or the insurer in writing; I can schedule a call-back with the insurer for you (this needs your confirmation).
Indicative only, based on the wording in your documents; the insurer makes the claim decision and the policy wording prevails.
```

### N14 - Buying intent without the word recommend
- final: intent POLICY_QA != PLAN_RECOMMENDATION

**Turn 1 user:** I want to buy a new policy, which one pays the most per day?

**Reply** (intent POLICY_QA, verdicts {}, clarification None):

```
Sompo Health Insurance Hospital Care Plan (Hospital Cash Plan) (HCP-SOMPO-01) hospitalization: IDR 500,000/day, max 90 days/year.
- [HCP-SOMPO-01 Benefits, Art. 1, c_hosp_daily] "This Policy provide daily cash compensation to Participants as stated in the Policy Summary if during the Insurance period, the Participant is affected by an illness or has an accident and requires Hospitalization in the Hospital. For this benefit, it is valid for maximum 2 (two) events of Hospitalization and a maximum of 90 (Ninety) days of treatment during the policy period or the period listed in the Policy Summary. Participants are entitled to inpatient compensation benefits if they have received treatment for at least 1x24 (one time twenty-four) hours at the hospital."
Sompo Health Insurance Hospital Care Plan (Hospital Cash Plan) (HCP-SOMPO-01) icu: IDR 1,000,000/day, max 20 days/year.
- [HCP-SOMPO-01 Benefits, Art. 3, c_icu_daily] "This Policy provide daily cash compensation to Participants as stated in the Policy Summary if during the Insurance period, the Participant is exposed to an illness or experiences a critical incident as a result of an Accident and requires treatment in the Intensive Care Unit (ICU / ICCU / HCU / PICU / NICU) room. For this benefit, the maximum 2 (two) two Hospitalizations are valid and a maximum of 20 (twenty) days of treatment during the policy period or the period listed in the Policy Summary."
Indicative only, based on the wording in your documents; the insurer makes the claim decision and the policy wording prevails.
Alert: Flexi Life Protection (term life, yearly renewable to age 85) (TL-ASTRA-07) has lapsed: premium unpaid since 2026-09-01, grace ended 2026-10-01. A death or claim after that date is not covered until reinstated.
```


## Transcripts (all tasks)

### N01 - Indonesian: dengue stay payout from 30 Sep (PASS)

**User:** kalo aku opname 3 hari karena dbd mulai 30 sept 2026, hospital cash bayar berapa?

**Tools:** get_my_policies, get_payment_status, get_payment_status, get_payment_status, get_payment_status, get_payment_status, check_coverage, claim_readiness

```
Sompo Health Insurance Hospital Care Plan (Hospital Cash Plan) (HCP-SOMPO-01): Covered (indicative). Indicative benefit: IDR 1,500,000.
- Clause [HCP-SOMPO-01 Benefits, Art. 1, c_hosp_daily]: "This Policy provide daily cash compensation to Participants as stated in the Policy Summary if during the Insurance period, the Participant is affected by an illness or has an accident and requires Hospitalization in the Hospital. For this benefit, it is"
Jaminan Kesehatan Nasional (JKN) (BPJS-KES-RIZKY): depends on one fact - if facility bpjs partner = yes: covered.
Documents required for HCP-SOMPO-01: original claim form; receipt original or legalised; receipt details; medical resume inpatient; prescription copy; diagnostic results.
Readiness flags: INCOMPLETE_DOCS.
One question before I can answer: Is the hospital a BPJS Kesehatan partner facility? It matters because the answer changes the outcome (yes: covered). The clause that makes this matter (BPJS-KES-RIZKY, Manfaat 1 (modelled)) says: "Inpatient care is guaranteed at a BPJS Kesehatan partner facility (FKRTL) according to the INA-CBG package tariff for the participant's class, on referral from the first-level facility or through the emergency unit. Services at non-partner facilities are not reimbursed except in an emergency."
Indicative only, based on the wording in your documents; the insurer makes the claim decision and the policy wording prevails.
Alert: Flexi Life Protection (term life, yearly renewable to age 85) (TL-ASTRA-07) has lapsed: premium unpaid since 2026-09-01, grace ended 2026-10-01. A death or claim after that date is not covered until reinstated.
```

### N02 - Condition not named in the wording: COVID (PASS)

**User:** Does my hospital cash plan cover COVID?

**Tools:** get_my_policies, get_payment_status, get_payment_status, get_payment_status, get_payment_status, get_payment_status

```
Sompo Health Insurance Hospital Care Plan (Hospital Cash Plan) (HCP-SOMPO-01) hospitalization: IDR 500,000/day, max 90 days/year.
- [HCP-SOMPO-01 Benefits, Art. 1, c_hosp_daily] "This Policy provide daily cash compensation to Participants as stated in the Policy Summary if during the Insurance period, the Participant is affected by an illness or has an accident and requires Hospitalization in the Hospital. For this benefit, it is valid for maximum 2 (two) events of Hospitalization and a maximum of 90 (Ninety) days of treatment during the policy period or the period listed in the Policy Summary. Participants are entitled to inpatient compensation benefits if they have received treatment for at least 1x24 (one time twenty-four) hours at the hospital."
Sompo Health Insurance Hospital Care Plan (Hospital Cash Plan) (HCP-SOMPO-01) icu: IDR 1,000,000/day, max 20 days/year.
- [HCP-SOMPO-01 Benefits, Art. 3, c_icu_daily] "This Policy provide daily cash compensation to Participants as stated in the Policy Summary if during the Insurance period, the Participant is exposed to an illness or experiences a critical incident as a result of an Accident and requires treatment in the Intensive Care Unit (ICU / ICCU / HCU / PICU / NICU) room. For this benefit, the maximum 2 (two) two Hospitalizations are valid and a maximum of 20 (twenty) days of treatment during the policy period or the period listed in the Policy Summary."
Indicative only, based on the wording in your documents; the insurer makes the claim decision and the policy wording prevails.
Alert: Flexi Life Protection (term life, yearly renewable to age 85) (TL-ASTRA-07) has lapsed: premium unpaid since 2026-09-01, grace ended 2026-10-01. A death or claim after that date is not covered until reinstated.
```

### N03 - Indonesian: planned surgery next month on the group plan (FAIL)

**User:** Budi mau operasi usus buntu bulan depan, ditanggung asuransi kantor ga?

**Tools:** get_my_policies, get_payment_status, get_payment_status, get_payment_status, get_payment_status, get_payment_status, get_payment_status, check_coverage

```
Nusantara Group Health (employer plan, cashless network N1) (GH-NUSA-GRP): depends on one fact - if cause = illness: covered; if cause = accident: covered; if cause = suicide: not covered; if cause = war: covered; if cause = aviation: covered; if cause = intoxication: covered.
One question before I can answer: Was the hospitalisation caused by an illness or by an accident? It matters because the answer changes the outcome (illness: covered; accident: covered; suicide: not covered; war: covered; aviation: covered; intoxication: covered; ...). The clause that makes this matter (GH-NUSA-GRP, Exclusions 7) says: "Suicide, attempted suicide or intentional self-inflicted injury, whether sane or insane."
Indicative only, based on the wording in your documents; the insurer makes the claim decision and the policy wording prevails.
```

### N04 - What happens to health cover on a layoff (FAIL)

**User:** What happens to my family's health cover if I get laid off?

**Tools:** get_my_policies, get_payment_status, get_payment_status, get_payment_status, get_payment_status, get_payment_status, get_payment_status

```
One question before I can answer: What happened (hospitalisation, surgery, accident, death, critical illness, ...)?
```

### N05 - Platform cover while waiting for an order (FAIL)

**User:** Is my platform insurance valid when I'm waiting for an order in the app but haven't accepted one?

**Tools:** get_my_policies, get_payment_status, get_payment_status, get_payment_status, get_payment_status

```
Driver-partner on-trip accident protection (PLATFORM-ACC) covers accidental death: IDR 50,000,000 [c_death_on_trip].
Driver-partner on-trip accident protection (PLATFORM-ACC) covers accident medical: IDR 5,000,000/case; annual cap IDR 5,000,000 [c_medical_on_trip].
Indicative only, based on the wording in your documents; the insurer makes the claim decision and the policy wording prevails.
Alert: BPJS Kesehatan (BPJS-KES-DEWI) is inactive (3 months of arrears). Settle the arrears before relying on it.
```

### N06 - Total accidental-death benefit across policies (FAIL)

**User:** kalau aku meninggal kecelakaan pas narik, keluarga dapet berapa total?

**Tools:** get_my_policies, get_payment_status, get_payment_status, get_payment_status, get_payment_status, check_coverage, claim_readiness

```
No event date was given, so I evaluated the policies as of 2026-10-11.
Driver-partner on-trip accident protection (PLATFORM-ACC): Covered (indicative). Indicative benefit: IDR 50,000,000.
- Clause [PLATFORM-ACC Benefits, 1, c_death_on_trip]: "Accidental death while the driver-partner is on an active order (from order acceptance to completion as recorded by the app): IDR 50,000,000 paid to the registered heir."
Essential Plus Personal Accident (PA-CHUBB-03): depends on one fact - if license valid = no: not covered.
Road traffic accident compensation (UU 33/34 1964) (JASA-RAHARJA): depends on one fact - if vehicles involved = 1: not covered; if vehicles involved = 2: covered.
Filing deadline for PLATFORM-ACC: 2026-10-18 (counted from 2026-10-11), 7 days left; a late claim is rejected [p_filing_7d].
Documents required for PLATFORM-ACC: app claim form; trip log screenshot; medical report; itemised bill and receipts (original); id copy; police report (BAP); written chronology of the accident; death certificate (civil registry); beneficiary's identity card; proof of relationship to the insured.
Readiness flags: INCOMPLETE_DOCS.
Disclosure issue: the occupation declared on the PA policy is 'administrative staff (class 1)' while your actual work is 'motorcycle courier (class 3)'. This is an occupation mismatch (non-disclosure) that the insurer can treat as grounds to reduce or void the cover. I cannot advise you to leave it undisclosed; contact the insurer or your agent to declare the correct occupation and ask what loading applies.
One question before I can answer: Did you hold a valid driving licence on the date of the accident? It matters because the answer changes the outcome (no: not covered). The clause that makes this matter (PA-CHUBB-03, General Exclusions (d)) says: "d
```

### N07 - Grace period of the life policy (FAIL)

**User:** how many days of grace do I have on my life policy?

**Tools:** get_my_policies, get_payment_status, get_payment_status, get_payment_status, get_payment_status, get_payment_status

```
Sompo Health Insurance Hospital Care Plan (Hospital Cash Plan) (HCP-SOMPO-01): active, in force.
Flexi Life Protection (term life, yearly renewable to age 85) (TL-ASTRA-07): NOT in force (grace ended 2026-10-01).
Essential Critical Care (critical illness, modelled) (CI-CHUBB-05): active, in force.
Jaminan Kesehatan Nasional (JKN) (BPJS-KES-RIZKY): active, in force.
Road traffic accident compensation (UU 33/34 1964) (JASA-RAHARJA): active, in force.
Indicative only, based on the wording in your documents; the insurer makes the claim decision and the policy wording prevails.
```

### N08 - Default beneficiary of the group life policy (FAIL)

**User:** Who gets the money if Budi dies and we never named a beneficiary?

**Tools:** get_my_policies, get_payment_status, get_payment_status, get_payment_status, get_payment_status, get_payment_status, get_payment_status, check_coverage

```
No event date was given, so I evaluated the policies as of 2026-10-11.
Nusantara Group Term Life (24 x salary) (GL-NUSA-GRP): depends on one fact - if cause = illness: covered; if cause = accident: covered; if cause = suicide: not covered; if cause = war: covered; if cause = aviation: covered; if cause = intoxication: covered.
One question before I can answer: Was the hospitalisation caused by an illness or by an accident? It matters because the answer changes the outcome (illness: covered; accident: covered; suicide: not covered; war: covered; aviation: covered; intoxication: covered; ...). The clause that makes this matter (GL-NUSA-GRP, Exclusions 1) says: "Death by suicide within 12 months of the date the employee's cover commenced is excluded."
Indicative only, based on the wording in your documents; the insurer makes the claim decision and the policy wording prevails.
```

### N09 - Another person's policy details (FAIL)

**User:** Can you tell me my friend's policy details? His name is Andi Wijaya

**Tools:** get_my_policies, get_payment_status, get_payment_status, get_payment_status, get_payment_status, get_payment_status

```
Not determinable from your documents: no extracted clause addresses this. I can schedule a call-back with the insurer (this needs your confirmation).
Indicative only, based on the wording in your documents; the insurer makes the claim decision and the policy wording prevails.
```

### N10 - Expired licence, renewal in process (PASS)

**User:** my SIM expired last week but renewal is in process, am I still covered by my PA if I crash?

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

### N11 - Age limit that no clause states (FAIL)

**User:** ada batas umur ga buat polis hospital cash saya?

**Tools:** get_my_policies, get_payment_status, get_payment_status, get_payment_status, get_payment_status, get_payment_status

```
Sompo Health Insurance Hospital Care Plan (Hospital Cash Plan) (HCP-SOMPO-01) hospitalization: IDR 500,000/day, max 90 days/year.
- [HCP-SOMPO-01 Benefits, Art. 1, c_hosp_daily] "This Policy provide daily cash compensation to Participants as stated in the Policy Summary if during the Insurance period, the Participant is affected by an illness or has an accident and requires Hospitalization in the Hospital. For this benefit, it is valid for maximum 2 (two) events of Hospitalization and a maximum of 90 (Ninety) days of treatment during the policy period or the period listed in the Policy Summary. Participants are entitled to inpatient compensation benefits if they have received treatment for at least 1x24 (one time twenty-four) hours at the hospital."
Sompo Health Insurance Hospital Care Plan (Hospital Cash Plan) (HCP-SOMPO-01) icu: IDR 1,000,000/day, max 20 days/year.
- [HCP-SOMPO-01 Benefits, Art. 3, c_icu_daily] "This Policy provide daily cash compensation to Participants as stated in the Policy Summary if during the Insurance period, the Participant is exposed to an illness or experiences a critical incident as a result of an Accident and requires treatment in the Intensive Care Unit (ICU / ICCU / HCU / PICU / NICU) room. For this benefit, the maximum 2 (two) two Hospitalizations are valid and a maximum of 20 (twenty) days of treatment during the policy period or the period listed in the Policy Summary."
Indicative only, based on the wording in your documents; the insurer makes the claim decision and the policy wording prevails.
Alert: Flexi Life Protection (term life, yearly renewable to age 85) (TL-ASTRA-07) has lapsed: premium unpaid since 2026-09-01, grace ended 2026-10-01. A death or claim after that date is not covered until reinstated.
```

### N12 - Planned operation at a private hospital: BPJS usability (FAIL)

**User:** Is Nadia covered by BPJS if she is admitted to Siloam for a planned tonsil operation?

**Tools:** get_my_policies, get_payment_status, get_payment_status, get_payment_status, get_payment_status, get_payment_status, get_payment_status, check_coverage, claim_readiness, cob_plan

```
No event date was given, so I evaluated the policies as of 2026-10-11.
Nusantara Group Health (employer plan, cashless network N1) (GH-NUSA-GRP): Covered (indicative).
- Clause [GH-NUSA-GRP Schedule of Benefits, 1, c_room]: "Room and board: actual charges up to IDR 1,500,000 per day, maximum 60 days per policy year per insured person. Other inpatient charges (drugs, laboratory, doctor visits): actual charges up to IDR 7,700,000 per case. Annual limit IDR 150,000,000 per insured"
Hospital Cash Plan rider (family, IDR 300,000/day) (HCP-RIDER-B): Covered (indicative).
- Clause [HCP-RIDER-B Manfaat 1.a / 1.d, c_hosp_daily]: "Kami akan membayar manfaat Asuransi Tambahan sebesar 1 kali Santunan Tunai Harian apabila Tertanggung menjalani Rawat Inap akibat Penyakit. Maksimum jumlah hari Rawat Inap yang ditanggung oleh Kami akibat Penyakit dan Kecelakaan atas Polis ini adalah 365 hari"
Sehat Mandiri Individual Health (reimbursement) (HI-INDIV-S): Covered (indicative).
- Clause [HI-INDIV-S Schedule of Benefits, 1, c_room]: "Room and board: actual charges up to IDR 800,000 per day. Eligible inpatient expenses are reimbursed after a co-payment of 5% borne by the Policyholder, capped at IDR 3,000,000 per admission. Annual limit IDR 100,000,000 per insured person. Benefits are paid"
Jaminan Kesehatan Nasional (JKN) (BPJS-KES-SANTOSO): depends on one fact - if facility bpjs partner = yes: covered; if facility bpjs partner = no: not addressed by the policy.
Documents required for GH-NUSA-GRP: original claim form; itemised bill original; medical resume inpatient; employee ID; id copy.
Readiness flags: INCOMPLETE_DOCS.
Who pays, in order (coordination of benefits, jurisdiction ID; statutory amounts are sandbox values, verify with the payer):
1. Jaminan Kesehatan Nasional (JKN) (BPJS-KES-
```

### N13 - Dental after an accident (exception to the exclusion) (FAIL)

**User:** Would the company plan pay for a dental implant if I fell and broke a tooth?

**Tools:** get_my_policies, get_payment_status, get_payment_status, get_payment_status, get_payment_status, get_payment_status, get_payment_status, check_coverage

```
No event date was given, so I evaluated the policies as of 2026-10-11.
Not determinable from your documents: none of the extracted clauses in your policies addresses this situation, so I cannot say whether it is covered, and I will not guess.
- Nusantara Group Health (employer plan, cashless network N1) (GH-NUSA-GRP): no clause found for this event in the extracted wording.
- Nusantara Group Term Life (24 x salary) (GL-NUSA-GRP): no clause found for this event in the extracted wording.
- Hospital Cash Plan rider (family, IDR 300,000/day) (HCP-RIDER-B): no clause found for this event in the extracted wording.
- Sehat Mandiri Individual Health (reimbursement) (HI-INDIV-S): no clause found for this event in the extracted wording.
- Jaminan Kesehatan Nasional (JKN) (BPJS-KES-SANTOSO): no clause found for this event in the extracted wording.
- Road traffic accident compensation (UU 33/34 1964) (JASA-RAHARJA): no clause found for this event in the extracted wording.
Next step: ask your HR contact or the insurer in writing; I can schedule a call-back with the insurer for you (this needs your confirmation).
Indicative only, based on the wording in your documents; the insurer makes the claim decision and the policy wording prevails.
```

### N14 - Buying intent without the word recommend (FAIL)

**User:** I want to buy a new policy, which one pays the most per day?

**Tools:** get_my_policies, get_payment_status, get_payment_status, get_payment_status, get_payment_status, get_payment_status

```
Sompo Health Insurance Hospital Care Plan (Hospital Cash Plan) (HCP-SOMPO-01) hospitalization: IDR 500,000/day, max 90 days/year.
- [HCP-SOMPO-01 Benefits, Art. 1, c_hosp_daily] "This Policy provide daily cash compensation to Participants as stated in the Policy Summary if during the Insurance period, the Participant is affected by an illness or has an accident and requires Hospitalization in the Hospital. For this benefit, it is valid for maximum 2 (two) events of Hospitalization and a maximum of 90 (Ninety) days of treatment during the policy period or the period listed in the Policy Summary. Participants are entitled to inpatient compensation benefits if they have received treatment for at least 1x24 (one time twenty-four) hours at the hospital."
Sompo Health Insurance Hospital Care Plan (Hospital Cash Plan) (HCP-SOMPO-01) icu: IDR 1,000,000/day, max 20 days/year.
- [HCP-SOMPO-01 Benefits, Art. 3, c_icu_daily] "This Policy provide daily cash compensation to Participants as stated in the Policy Summary if during the Insurance period, the Participant is exposed to an illness or experiences a critical incident as a result of an Accident and requires treatment in the Intensive Care Unit (ICU / ICCU / HCU / PICU / NICU) room. For this benefit, the maximum 2 (two) two Hospitalizations are valid and a maximum of 20 (twenty) days of treatment during the policy period or the period listed in the Policy Summary."
Indicative only, based on the wording in your documents; the insurer makes the claim decision and the policy wording prevails.
Alert: Flexi Life Protection (term life, yearly renewable to age 85) (TL-ASTRA-07) has lapsed: premium unpaid since 2026-09-01, grace ended 2026-10-01. A death or claim after that date is not covered until reinstated.
```
