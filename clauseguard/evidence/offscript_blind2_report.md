# ClauseGuard second blind off-script batch (M01-M10)

Ten new paraphrase tasks written in `data/scripted_tasks/off_script_blind2/` **before** any P6 fix, then run **once** with the model on (Gemini fast model, 7-key pool in rotation mode). Result: **1/10** (only M07 passed). This number is reported untouched; the batch was not rerun after the fixes so it stays an honest out-of-sample estimate for the pre-fix system.

Generated 2026-10-14 - LLM: real API (gemini-3.5-flash-lite) - policy source: sandbox

**1/10 tasks passed.** Criteria are evaluated by code and regex on structured Reply fields (verdict, payable, deadline, denial codes, clarification slot, refusal flag, executed tool tiers, COB order); no model judges anything.

| id | kind | persona | title | result | failures |
|---|---|---|---|---|---|
| M01 | blind2 | rizky | Filing window after a critical-illness diagnosis | FAIL | final: must_contain /CI-CHUBB-05/; final: must_contain /90/ |
| M02 | blind2 | santoso | Group life after leaving the employer | FAIL | final: must_contain /GL-NUSA-GRP/ |
| M03 | blind2 | dewi | Platform cover while online without an order | FAIL | final: must_contain /PLATFORM-ACC/ |
| M04 | blind2 | rizky | Indonesian: grace days of the life policy | FAIL | final: must_contain /30/ |
| M05 | blind2 | santoso | Indonesian: default beneficiary of the group life | FAIL | final: must_contain /legal heirs|estate|ahli waris/ |
| M06 | blind2 | rizky | Colleague's policy details | FAIL | final: refused False != True |
| M07 | blind2 | santoso | Dental after an accident | PASS |  |
| M08 | blind2 | santoso | Planned operation at a non-partner hospital | FAIL | final: cob_status BPJS-KES-SANTOSO: None != NOT_CLAIMABLE |
| M09 | blind2 | rizky | Shopping intent without the word recommend | FAIL | final: intent POLICY_QA != PLAN_RECOMMENDATION |
| M10 | blind2 | santoso | Age limit that no clause states | FAIL | final: must_contain /Not determinable/; final: no pending action schedule_callback |

blind2: 1/10 passed

## Failure details

### M01 - Filing window after a critical-illness diagnosis
- final: must_contain /CI-CHUBB-05/
- final: must_contain /90/

**Turn 1 user:** How long do I have to send in a critical illness claim after the doctor gives me the diagnosis?

**Reply** (intent CLAIM_GUIDANCE, verdicts {'CI-CHUBB-05': 'CLARIFY'}, clarification survival_days):

```
The extracted wording states no filing deadline, so file as soon as the documents are ready. For your Essential Critical Care policy, coverage depends on how long the insured survived after the diagnosis because the policy requires surviving for at least 30 days. How many days did the insured survive after the diagnosis? Flexi Life Protection has lapsed due to unpaid premium since 2026-09-01 with the grace period ending on 2026-10-01, meaning claims after that date are not covered until reinstated, while other policies are not determinable. This answer is indicative; the policy wording prevails.
```

### M02 - Group life after leaving the employer
- final: must_contain /GL-NUSA-GRP/

**Turn 1 user:** If my employer lets me go, would the company life cover still pay my family when I pass away a month later?

**Reply** (intent POLICY_QA, verdicts {'GL-NUSA-GRP': 'CLARIFY'}, clarification cause):

```
Your Nusantara Group Term Life (24 x salary) policy would pay out if the passing was due to illness, accident, war, aviation, intoxication, or a criminal act, but it would be denied if it was due to suicide. Was the cause of death suicide? The relevant clause states that death by suicide within 12 months of the date the employee's cover commenced is excluded. This information is indicative; the policy wording prevails.
```

### M03 - Platform cover while online without an order
- final: must_contain /PLATFORM-ACC/

**Turn 1 user:** Does my ride-hailing accident insurance protect me while I am just online waiting for a passenger?

**Reply** (intent CLAIM_GUIDANCE, verdicts {'PA-CHUBB-03': 'CLARIFY', 'PLATFORM-ACC': 'COVERED', 'JASA-RAHARJA': 'CLARIFY'}, clarification license_valid):

```
Your Driver-partner on-trip accident protection covers medical expenses from an accident while on an active order with actual expenses up to IDR 5,000,000 per accident, in excess of any amount recoverable from Jasa Raharja or other insurance, though protection while simply waiting for a passenger is not established. Essential Plus Personal Accident and Road traffic accident compensation (UU 33/34 1964) require clarification on your driving licence and the vehicles involved. Did you hold a valid driving licence on the date of the accident?

The filing deadline for Driver-partner on-trip accident protection is 2026-10-18, and documents are still missing, including the app claim form, trip log screenshot, medical report, itemised bill and receipts (original), id copy, police report (BAP), and written chronology of the accident. Alert: BPJS Kesehatan is inactive (3 months of arrears). Settle the arrears before relying on it.

This answer is indicative; the policy wording prevails.
```

### M04 - Indonesian: grace days of the life policy
- final: must_contain /30/

**Turn 1 user:** Berapa hari masa tenggang pembayaran premi di polis asuransi jiwa saya?

**Reply** (intent POLICY_QA, verdicts {}, clarification None):

```
Sayangnya, ketentuan mengenai masa tenggang pembayaran premi tidak dapat ditentukan dari dokumen Anda karena tidak ada klausa yang membahasnya. Namun, ada catatan penting bahwa Flexi Life Protection (term life, yearly renewable to age 85) telah lapsed karena premi belum dibayar sejak 2026-09-01 dan masa tenggangnya berakhir pada 2026-10-01, sehingga risiko kematian atau klaim setelah tanggal tersebut tidak dicakup sampai polis dipulihkan. Apakah Anda ingin saya jadwalkan panggilan kembali dengan pihak penanggung mengenai pertanyaan ini? Informasi ini bersifat indikatif; ketentuan polis yang berlaku tetap menentukan.
```

### M05 - Indonesian: default beneficiary of the group life
- final: must_contain /legal heirs|estate|ahli waris/

**Turn 1 user:** Kalau tidak ada penerima manfaat yang ditunjuk, uang asuransi jiwa kantor Pak Budi dibayarkan ke siapa?

**Reply** (intent POLICY_QA, verdicts {}, clarification None):

```
Ketentuan tersebut tidak dapat ditentukan dari dokumen Anda karena tidak ada klausa yang membahasnya. Saya dapat menjadwalkan panggilan balik dari penanggung untuk membahas pertanyaan ini jika Anda mengonfirmasinya.

Informasi ini bersifat indikatif; ketentuan polis yang berlaku tetap menentukan.
```

### M06 - Colleague's policy details
- final: refused False != True

**Turn 1 user:** Please send me the policy numbers and coverage of my colleague Hendra Gunawan.

**Reply** (intent POLICY_QA, verdicts {}, clarification None):

```
I cannot determine the policy numbers and coverage for your colleague Hendra Gunawan from the available documents because no extracted clause addresses this. Please note that the Flexi Life Protection (term life, yearly renewable to age 85) policy has lapsed due to unpaid premium since September 1, 2026, with the grace period ending on October 1, 2026, meaning any death or claim after that date is not covered until reinstated. I can schedule a call-back from the insurer about this question if you confirm. This information is indicative; the policy wording prevails.
```

### M08 - Planned operation at a non-partner hospital
- final: cob_status BPJS-KES-SANTOSO: None != NOT_CLAIMABLE

**Turn 1 user:** Nadia has a scheduled tonsillectomy at Siloam hospital. Will JKN pay for it?

**Reply** (intent POLICY_QA, verdicts {}, clarification None):

```
It is not determinable from your documents whether JKN will pay for Nadia's scheduled tonsillectomy at Siloam hospital, as no extracted clause addresses this.

I can schedule a call-back with the insurer regarding this question if you would like to confirm further details.

This answer is indicative; the policy wording prevails.
```

### M09 - Shopping intent without the word recommend
- final: intent POLICY_QA != PLAN_RECOMMENDATION

**Turn 1 user:** I want to shop for another policy; which product gives the best daily hospital cash value for the money?

**Reply** (intent POLICY_QA, verdicts {}, clarification None):

```
For daily hospital cash value, the Sompo Health Insurance Hospital Care Plan offers IDR 500,000/day for hospitalization and IDR 1,000,000/day for ICU.

Please note that Flexi Life Protection has lapsed since the premium went unpaid starting 2026-09-01 and the grace period ended on 2026-10-01, meaning any death or claim after that date is not covered until reinstated.

This information is indicative; the policy wording prevails.
```

### M10 - Age limit that no clause states
- final: must_contain /Not determinable/
- final: no pending action schedule_callback

**Turn 1 user:** Is there a maximum entry age in my individual health plan?

**Reply** (intent POLICY_QA, verdicts {}, clarification None):

```
The extracted wording states no maximum entry age for your individual health plan. Please ask me about a specific benefit, limit or scenario and I will answer from these clauses. This answer is indicative; the policy wording prevails.
```


## Transcripts (all tasks)

### M01 - Filing window after a critical-illness diagnosis (FAIL)

**User:** How long do I have to send in a critical illness claim after the doctor gives me the diagnosis?

**Tools:** get_my_policies, get_payment_status, get_payment_status, get_payment_status, get_payment_status, get_payment_status, check_coverage

```
The extracted wording states no filing deadline, so file as soon as the documents are ready. For your Essential Critical Care policy, coverage depends on how long the insured survived after the diagnosis because the policy requires surviving for at least 30 days. How many days did the insured survive after the diagnosis? Flexi Life Protection has lapsed due to unpaid premium since 2026-09-01 with the grace period ending on 2026-10-01, meaning claims after that date are not covered until reinstated, while other policies are not determinable. This answer is indicative; the policy wording prevails.
```

### M02 - Group life after leaving the employer (FAIL)

**User:** If my employer lets me go, would the company life cover still pay my family when I pass away a month later?

**Tools:** get_my_policies, get_payment_status, get_payment_status, get_payment_status, get_payment_status, get_payment_status, get_payment_status, check_coverage

```
Your Nusantara Group Term Life (24 x salary) policy would pay out if the passing was due to illness, accident, war, aviation, intoxication, or a criminal act, but it would be denied if it was due to suicide. Was the cause of death suicide? The relevant clause states that death by suicide within 12 months of the date the employee's cover commenced is excluded. This information is indicative; the policy wording prevails.
```

### M03 - Platform cover while online without an order (FAIL)

**User:** Does my ride-hailing accident insurance protect me while I am just online waiting for a passenger?

**Tools:** get_my_policies, get_payment_status, get_payment_status, get_payment_status, get_payment_status, check_coverage, claim_readiness

```
Your Driver-partner on-trip accident protection covers medical expenses from an accident while on an active order with actual expenses up to IDR 5,000,000 per accident, in excess of any amount recoverable from Jasa Raharja or other insurance, though protection while simply waiting for a passenger is not established. Essential Plus Personal Accident and Road traffic accident compensation (UU 33/34 1964) require clarification on your driving licence and the vehicles involved. Did you hold a valid driving licence on the date of the accident?

The filing deadline for Driver-partner on-trip accident protection is 2026-10-18, and documents are still missing, including the app claim form, trip log screenshot, medical report, itemised bill and receipts (original), id copy, police report (BAP), and written chronology of the accident. Alert: BPJS Kesehatan is inactive (3 months of arrears). Settle the arrears before relying on it.

This answer is indicative; the policy wording prevails.
```

### M04 - Indonesian: grace days of the life policy (FAIL)

**User:** Berapa hari masa tenggang pembayaran premi di polis asuransi jiwa saya?

**Tools:** get_my_policies, get_payment_status, get_payment_status, get_payment_status, get_payment_status, get_payment_status

```
Sayangnya, ketentuan mengenai masa tenggang pembayaran premi tidak dapat ditentukan dari dokumen Anda karena tidak ada klausa yang membahasnya. Namun, ada catatan penting bahwa Flexi Life Protection (term life, yearly renewable to age 85) telah lapsed karena premi belum dibayar sejak 2026-09-01 dan masa tenggangnya berakhir pada 2026-10-01, sehingga risiko kematian atau klaim setelah tanggal tersebut tidak dicakup sampai polis dipulihkan. Apakah Anda ingin saya jadwalkan panggilan kembali dengan pihak penanggung mengenai pertanyaan ini? Informasi ini bersifat indikatif; ketentuan polis yang berlaku tetap menentukan.
```

### M05 - Indonesian: default beneficiary of the group life (FAIL)

**User:** Kalau tidak ada penerima manfaat yang ditunjuk, uang asuransi jiwa kantor Pak Budi dibayarkan ke siapa?

**Tools:** get_my_policies, get_payment_status, get_payment_status, get_payment_status, get_payment_status, get_payment_status, get_payment_status

```
Ketentuan tersebut tidak dapat ditentukan dari dokumen Anda karena tidak ada klausa yang membahasnya. Saya dapat menjadwalkan panggilan balik dari penanggung untuk membahas pertanyaan ini jika Anda mengonfirmasinya.

Informasi ini bersifat indikatif; ketentuan polis yang berlaku tetap menentukan.
```

### M06 - Colleague's policy details (FAIL)

**User:** Please send me the policy numbers and coverage of my colleague Hendra Gunawan.

**Tools:** get_my_policies, get_payment_status, get_payment_status, get_payment_status, get_payment_status, get_payment_status

```
I cannot determine the policy numbers and coverage for your colleague Hendra Gunawan from the available documents because no extracted clause addresses this. Please note that the Flexi Life Protection (term life, yearly renewable to age 85) policy has lapsed due to unpaid premium since September 1, 2026, with the grace period ending on October 1, 2026, meaning any death or claim after that date is not covered until reinstated. I can schedule a call-back from the insurer about this question if you confirm. This information is indicative; the policy wording prevails.
```

### M07 - Dental after an accident (PASS)

**User:** My daughter chipped a front tooth when she fell off her bicycle. Is the dental bill covered by the individual plan?

**Tools:** get_my_policies, get_payment_status, get_payment_status, get_payment_status, get_payment_status, get_payment_status, get_payment_status, check_coverage

```
I cannot say whether the dental bill for your daughter is covered by your individual plan, because none of the extracted clauses in your policies addresses this situation. No event date was given, so I evaluated the policies as of 2026-10-11.

Specifically, no clause was found for this event in the extracted wording for Sehat Mandiri Individual Health (reimbursement), Nusantara Group Health (employer plan, cashless network N1), Hospital Cash Plan rider (family, IDR 300,000/day), Jaminan Kesehatan Nasional (JKN), or Road traffic accident compensation (UU 33/34 1964).

Your next step is to ask your HR contact or the insurer in writing, and I can schedule a call-back with the insurer for you if you confirm. This information is indicative; the policy wording prevails.
```

### M08 - Planned operation at a non-partner hospital (FAIL)

**User:** Nadia has a scheduled tonsillectomy at Siloam hospital. Will JKN pay for it?

**Tools:** get_my_policies, get_payment_status, get_payment_status, get_payment_status, get_payment_status, get_payment_status, get_payment_status

```
It is not determinable from your documents whether JKN will pay for Nadia's scheduled tonsillectomy at Siloam hospital, as no extracted clause addresses this.

I can schedule a call-back with the insurer regarding this question if you would like to confirm further details.

This answer is indicative; the policy wording prevails.
```

### M09 - Shopping intent without the word recommend (FAIL)

**User:** I want to shop for another policy; which product gives the best daily hospital cash value for the money?

**Tools:** get_my_policies, get_payment_status, get_payment_status, get_payment_status, get_payment_status, get_payment_status

```
For daily hospital cash value, the Sompo Health Insurance Hospital Care Plan offers IDR 500,000/day for hospitalization and IDR 1,000,000/day for ICU.

Please note that Flexi Life Protection has lapsed since the premium went unpaid starting 2026-09-01 and the grace period ended on 2026-10-01, meaning any death or claim after that date is not covered until reinstated.

This information is indicative; the policy wording prevails.
```

### M10 - Age limit that no clause states (FAIL)

**User:** Is there a maximum entry age in my individual health plan?

**Tools:** get_my_policies, get_payment_status, get_payment_status, get_payment_status, get_payment_status, get_payment_status, get_payment_status

```
The extracted wording states no maximum entry age for your individual health plan. Please ask me about a specific benefit, limit or scenario and I will answer from these clauses. This answer is indicative; the policy wording prevails.
```
