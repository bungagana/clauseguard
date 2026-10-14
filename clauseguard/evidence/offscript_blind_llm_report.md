# ClauseGuard off-script dev set, run with the model (former blind set N01-N14)

**Label: dev set after fix.** These 14 tasks were the blind batch (3/14 with the model off). In this pass they were run for the first time with the model ON (planner, fact binder and reply composer: Gemini fast model, `GEMINI_API_KEYS` pool of 7 keys in rotation mode, rotating to the next key on quota errors). The failures were then read and generic causes fixed (planner topics for grace length / employment termination / on-trip definition / age limit / third-party data / buying intent, hospital-directory lookup for named facilities, excluded-treatment exception surfacing, cross-policy lump-sum totals, money formatting in composed text). Because the tasks were seen during this fix pass, they are **no longer blind**.

| run | model | result |
|---|---|---|
| first run with the model, before any fix | on | 4/14 |
| after fixes | on | 13/14 |

Remaining failure: N11 (age limit no clause states). The deterministic template says "Not determinable from your documents: no extracted clause ... states an age limit" and offers the call-back; the composer paraphrases it ("tidak terdapat klausa yang menyebutkan batas usia") so the literal regex misses. Behaviour is correct, the criterion is literal.

For an out-of-sample number see `offscript_blind2_report.md` (10 new paraphrases written before any fix, run once with the model): **1/10**.

Generated 2026-10-14 - LLM: real API (gemini-3.5-flash-lite) - policy source: sandbox

**13/14 tasks passed.** Criteria are evaluated by code and regex on structured Reply fields (verdict, payable, deadline, denial codes, clarification slot, refusal flag, executed tool tiers, COB order); no model judges anything.

| id | kind | persona | title | result | failures |
|---|---|---|---|---|---|
| N01 | blind | rizky | Indonesian: dengue stay payout from 30 Sep | PASS |  |
| N02 | blind | rizky | Condition not named in the wording: COVID | PASS |  |
| N03 | blind | santoso | Indonesian: planned surgery next month on the group plan | PASS |  |
| N04 | blind | santoso | What happens to health cover on a layoff | PASS |  |
| N05 | blind | dewi | Platform cover while waiting for an order | PASS |  |
| N06 | blind | dewi | Total accidental-death benefit across policies | PASS |  |
| N07 | blind | rizky | Grace period of the life policy | PASS |  |
| N08 | blind | santoso | Default beneficiary of the group life policy | PASS |  |
| N09 | blind | rizky | Another person's policy details | PASS |  |
| N10 | blind | dewi | Expired licence, renewal in process | PASS |  |
| N11 | blind | rizky | Age limit that no clause states | FAIL | final: must_contain /Not determinable/ |
| N12 | blind | santoso | Planned operation at a private hospital: BPJS usability | PASS |  |
| N13 | blind | santoso | Dental after an accident (exception to the exclusion) | PASS |  |
| N14 | blind | rizky | Buying intent without the word recommend | PASS |  |

blind: 13/14 passed

## Failure details

### N11 - Age limit that no clause states
- final: must_contain /Not determinable/

**Turn 1 user:** ada batas umur ga buat polis hospital cash saya?

**Reply** (intent POLICY_QA, verdicts {}, clarification None):

```
Tidak ada ketentuan pasal yang tercantum pada polis Sompo Health Insurance Hospital Care Plan (Hospital Care Plan) (HCP-SOMPO-01) yang menyatakan batas umur, sehingga informasi tersebut belum dapat ditentukan dan saya tidak dapat menebaknya. Sebagai langkah lanjutan, saya dapat membantu menjadwalkan panggilan balik dari pihak asuransi untuk pertanyaan ini.

Selain itu, perlu diingatkan bahwa polis Flexi Life Protection (term life, yearly renewable to age 85) (TL-ASTRA-07) telah lapse: premi belum dibayar sejak 2026-09-01 dan masa tenggang berakhir pada 2026-10-01, sehingga kematian atau klaim setelah tanggal tersebut tidak ditanggung hingga polis dipulihkan.

Penjelasan ini bersifat indikatif; ketentuan polis yang berlaku tetap menentukan.
```


## Transcripts (all tasks)

### N01 - Indonesian: dengue stay payout from 30 Sep (PASS)

**User:** kalo aku opname 3 hari karena dbd mulai 30 sept 2026, hospital cash bayar berapa?

**Tools:** get_my_policies, get_payment_status, get_payment_status, get_payment_status, get_payment_status, get_payment_status, check_coverage, claim_readiness

```
Halo! Batas pengajuan klaim adalah 2026-12-01, dengan 51 hari tersisa, dan tanggal pulang 2026-10-02 dihitung dari tanggal masuk Anda 2026-09-30 dan 3 hari rawat inap. Perkiraan manfaat untuk Sompo Health Insurance Hospital Care Plan (Hospital Cash Plan) (HCP-SOMPO-01) adalah IDR 1,500,000.  Untuk Jaminan Kesehatan Nasional (JKN) (BPJS-KES-RIZKY), permohonan Anda tergantung pada satu hal: apakah rumah sakit tersebut merupakan fasilitas mitra BPJS Kesehatan?  Melalui Sompo Health Insurance Hospital Care Plan (Hospital Cash Plan) (HCP-SOMPO-01), Anda mendapatkan pertanggungan harian karena polis menyediakan kompensasi tunai harian bagi peserta yang mengalami sakit dan memerlukan rawat inap di rumah sakit. Dokumen saat ini masih kurang, yang mencakup original claim form, receipt original or legalised, receipt details, medical resume inpatient, prescription copy, dan diagnostic results.  Perlu diingat bahwa Flexi Life Protection (term life, yearly renewable to age 85) (TL-ASTRA-07) telah kedaluwarsa karena premi belum dibayar sejak 2026-09-01 dan masa tenggang berakhir pada 2026-10-01, sehingga klaim setelah tanggal tersebut tidak ditanggung sampai dipulihkan.  Jawaban ini bersifat indikatif; ketentuan polis yang berlaku tetap menentukan.
```

### N02 - Condition not named in the wording: COVID (PASS)

**User:** Does my hospital cash plan cover COVID?

**Tools:** get_my_policies, get_payment_status, get_payment_status, get_payment_status, get_payment_status, get_payment_status

```
Your Sompo Health Insurance Hospital Care Plan (Hospital Cash Plan) (HCP-SOMPO-01) provides daily cash compensation if you are affected by an illness or have an accident requiring hospitalization, offering IDR 500,000/day for up to 90 days per year, and IDR 1,000,000/day for up to 20 days per year for intensive care treatment.

Separately, please note that Flexi Life Protection (term life, yearly renewable to age 85) (TL-ASTRA-07) has lapsed because the premium has been unpaid since 2026-09-01 and the grace period ended 2026-10-01, meaning any death or claim after that date is not covered until the policy is reinstated.

This information is indicative; the policy wording prevails.
```

### N03 - Indonesian: planned surgery next month on the group plan (PASS)

**User:** Budi mau operasi usus buntu bulan depan, ditanggung asuransi kantor ga?

**Tools:** get_my_policies, get_payment_status, get_payment_status, get_payment_status, get_payment_status, get_payment_status, get_payment_status, check_coverage

```
Operasi usus buntu Budi bulan depan ditanggung oleh asuransi kantor melalui polis Nusantara Group Health (GH-NUSA-GRP).

Biaya pembedahan untuk tindakan tersebut dijamin sesuai dengan ketentuan polis dengan tanggungan biaya aktual sampai dengan IDR 25,000,000 per kasus.

Informasi ini bersifat indikatif; ketentuan polis yang berlaku tetap menentukan.
```

### N04 - What happens to health cover on a layoff (PASS)

**User:** What happens to my family's health cover if I get laid off?

**Tools:** get_my_policies, get_payment_status, get_payment_status, get_payment_status, get_payment_status, get_payment_status, get_payment_status

```
Your family's health cover under the Nusantara Group Health (GH-NUSA-GRP) policy and your term life cover under the Nusantara Group Term Life (GL-NUSA-GRP) policy both end on the date your employment ends. Under the terms of Nusantara Group Health (GH-NUSA-GRP), cover for an insured employee and his or her dependants terminates on the date the employee ceases to be employed by the policyholder, or on the date the master policy terminates, whichever is earlier. Similarly, under Nusantara Group Term Life (GL-NUSA-GRP), cover terminates on the date the employee ceases employment with the policyholder, and no conversion option applies.

This information is indicative; the policy wording prevails.
```

### N05 - Platform cover while waiting for an order (PASS)

**User:** Is my platform insurance valid when I'm waiting for an order in the app but haven't accepted one?

**Tools:** get_my_policies, get_payment_status, get_payment_status, get_payment_status, get_payment_status

```
Your platform insurance cover applies only while you are on an active order, which starts when you accept an order, so the time online before accepting one is not on trip. Under Driver-partner on-trip accident protection (PLATFORM-ACC), "On trip" means the period between the driver-partner's acceptance of an order and its completion or cancellation as recorded in the platform's trip log.

Heads-up, separate from your question - BPJS Kesehatan (BPJS-KES-DEWI) is inactive (3 months of arrears). Settle the arrears before relying on it.

This answer is indicative; the policy wording prevails.
```

### N06 - Total accidental-death benefit across policies (PASS)

**User:** kalau aku meninggal kecelakaan pas narik, keluarga dapet berapa total?

**Tools:** get_my_policies, get_payment_status, get_payment_status, get_payment_status, get_payment_status, check_coverage, claim_readiness

```
Batas pengajuan klaim adalah 18-10-2026. Total di seluruh polis untuk kejadian ini adalah IDR 50,000,000 yang sudah dipastikan, serta bisa mencapai IDR 100,000,000 jika jumlah kendaraan yang terlibat sesuai ketentuan. Apakah Anda memiliki Surat Izin Mengemudi yang sah pada tanggal kecelakaan tersebut?  Melalui polis Driver-partner on-trip accident protection (PLATFORM-ACC), keluarga Anda berhak atas manfaat indikatif sebesar IDR 50,000,000 karena kejadian memenuhi ketentuan kematian akibat kecelakaan saat pesanan aktif. Polis Essential Plus Personal Accident (PA-CHUBB-03) dan Road traffic accident compensation (UU 33/34 1964) masih memerlukan konfirmasi lebih lanjut, sedangkan Jaminan Kesehatan Nasional (JKN) tidak dapat ditentukan. Dokumen-dokumen saat ini masih belum lengkap.  Pemberitahuan terpisah mengenai Jaminan Kesehatan Nasional (JKN) (BPJS-KES-DEWI) saat ini tidak aktif karena menunggak selama 3 bulan, sehingga Anda perlu melunasi tunggakan tersebut sebelum mengandalkannya.  Penjelasan di atas bersifat indikatif; ketentuan polis yang berlaku tetap menentukan.
```

### N07 - Grace period of the life policy (PASS)

**User:** how many days of grace do I have on my life policy?

**Tools:** get_my_policies, get_payment_status, get_payment_status, get_payment_status, get_payment_status, get_payment_status

```
Your Flexi Life Protection (TL-ASTRA-07) gives you a 30-day grace period after an unpaid premium due date, during which the policy stays in force and lapses if the premium remains unpaid afterwards.

Flexi Life Protection (term life, yearly renewable to age 85) (TL-ASTRA-07) has lapsed because the premium has been unpaid since 2026-09-01 and the grace period ended on 2026-10-01, meaning a death or claim after that date is not covered until reinstated.

This answer is indicative; the policy wording prevails.
```

### N08 - Default beneficiary of the group life policy (PASS)

**User:** Who gets the money if Budi dies and we never named a beneficiary?

**Tools:** get_my_policies, get_payment_status, get_payment_status, get_payment_status, get_payment_status, get_payment_status, get_payment_status, check_coverage

```
If there is no named beneficiary, the benefit is payable to the employee's legal heirs (estate) under the Nusantara Group Term Life (24 x salary) (GL-NUSA-GRP) policy. Was the cause of death suicide? The policy states that death by suicide within 12 months of the date the employee's cover commenced is excluded. This answer is indicative; the policy wording prevails.
```

### N09 - Another person's policy details (PASS)

**User:** Can you tell me my friend's policy details? His name is Andi Wijaya

**Tools:** get_my_policies

```
I can only access policies on your own account, not anyone else's.
```

### N10 - Expired licence, renewal in process (PASS)

**User:** my SIM expired last week but renewal is in process, am I still covered by my PA if I crash?

**Tools:** get_my_policies, get_payment_status, get_payment_status, get_payment_status, get_payment_status, check_coverage

```
Did this happen while you were working (for example on an active delivery order)? Your Essential Plus Personal Accident (PA-CHUBB-03) policy would not cover you because driving or riding without a valid license is excluded under General Exclusions (d). Other protections depend on further details, and Jaminan Kesehatan Nasional (JKN) (BPJS-KES-DEWI) is not determinable right now. Heads-up, separate from your question - BPJS Kesehatan (BPJS-KES-DEWI) is inactive (3 months of arrears). Settle the arrears before relying on it. This information is indicative; the policy wording prevails.
```

### N11 - Age limit that no clause states (FAIL)

**User:** ada batas umur ga buat polis hospital cash saya?

**Tools:** get_my_policies, get_payment_status, get_payment_status, get_payment_status, get_payment_status, get_payment_status

```
Tidak ada ketentuan pasal yang tercantum pada polis Sompo Health Insurance Hospital Care Plan (Hospital Care Plan) (HCP-SOMPO-01) yang menyatakan batas umur, sehingga informasi tersebut belum dapat ditentukan dan saya tidak dapat menebaknya. Sebagai langkah lanjutan, saya dapat membantu menjadwalkan panggilan balik dari pihak asuransi untuk pertanyaan ini.

Selain itu, perlu diingatkan bahwa polis Flexi Life Protection (term life, yearly renewable to age 85) (TL-ASTRA-07) telah lapse: premi belum dibayar sejak 2026-09-01 dan masa tenggang berakhir pada 2026-10-01, sehingga kematian atau klaim setelah tanggal tersebut tidak ditanggung hingga polis dipulihkan.

Penjelasan ini bersifat indikatif; ketentuan polis yang berlaku tetap menentukan.
```

### N12 - Planned operation at a private hospital: BPJS usability (PASS)

**User:** Is Nadia covered by BPJS if she is admitted to Siloam for a planned tonsil operation?

**Tools:** get_my_policies, get_payment_status, get_payment_status, get_payment_status, get_payment_status, get_payment_status, get_payment_status, check_coverage, claim_readiness, cob_plan

```
Nadia is not covered by BPJS for this admission because Siloam is a non-partner facility and it is not an emergency. The extracted wording states no filing deadline because the filing deadline is 30 days from discharge, but I do not have your discharge date (or how many days you stayed) yet?

For this planned admission, Jaminan Kesehatan Nasional (BPJS-KES-SANTOSO) and Road traffic accident compensation (JASA-RAHARJA) are not claimable. However, coverage is provided by Nusantara Group Health (GH-NUSA-GRP) with room and board actual charges up to IDR 1,500,000 per day, Sehat Mandiri Individual Health (HI-INDIV-S) covering room and board actual charges up to IDR 800,000 per day, and Hospital Cash Plan rider (HCP-RIDER-B) paying the daily hospital benefit for inpatient stays due to illness.

Documents are still missing for Nusantara Group Health (GH-NUSA-GRP), specifically original claim form, itemised bill original, medical resume inpatient, employee ID, and id copy. Please provide these to proceed.

The answer is indicative; the policy wording prevails.
```

### N13 - Dental after an accident (exception to the exclusion) (PASS)

**User:** Would the company plan pay for a dental implant if I fell and broke a tooth?

**Tools:** get_my_policies, get_payment_status, get_payment_status, get_payment_status, get_payment_status, get_payment_status, get_payment_status, check_coverage

```
Based on your documents, none of the extracted clauses addresses this situation, so I cannot say whether a dental implant would be paid for a broken tooth, and I will not guess. No event date was given, so I evaluated the policies as of 2026-10-11.

Dental treatment is generally excluded under Nusantara Group Health (GH-NUSA-GRP), Hospital Cash Plan rider (HCP-RIDER-B), and Sehat Mandiri Individual Health (HI-INDIV-S) unless the exception applies for treatment of sound natural teeth required as a result of an accident. While the facts you gave meet that exception, the extracted wording states no benefit amount or limit for it, so I cannot say what would be paid. The other policies do not address this event in their extracted wording.

Your next step is to ask your HR contact or the insurer in writing, and I can schedule a call-back with the insurer for you if you confirm. This answer is indicative; the policy wording prevails.
```

### N14 - Buying intent without the word recommend (PASS)

**User:** I want to buy a new policy, which one pays the most per day?

**Tools:** get_my_policies, get_payment_status, get_payment_status, get_payment_status, get_payment_status, get_payment_status, gap_analysis

```
Plan suggestions from your current cover gaps (illustrative mock catalogue; indicative; consult a licensed agent).
Open gaps: death, temporary disability, tpd.
1. Mock Term Life Plan (MOCK) [CAT-TERM-01] - IDR 250,000 per month (mock price). Closes: death.
   Why: Closes cover gaps that are open in your portfolio today: death (for rizky).
   - Indicative; consult a licensed agent before buying.
   - Mock catalogue: prices and benefits are illustrative and not an offer from any insurer.
   - Premium is per insured person per month; the figure shown is for one person.
   - You hold TL-ASTRA-07 for this risk but it is not in force today; ask the insurer whether it can be reinstated, which may cost less than a new plan.
   - Pre-existing conditions are excluded for the first 12 months.
   - Death and income-protection cover is suggested for the household earner only; check each other adult's income before adding it, and children are not offered it.
2. Mock Personal Accident Plan (MOCK) [CAT-PA-01] - IDR 90,000 per month (mock price). Closes: tpd, temporary disability.
   Why: Closes cover gaps that are open in your portfolio today: tpd, temporary disability (for rizky).
   - Indicative; consult a licensed agent before buying.
   - Mock catalogue: prices and benefits are illustrative and not an offer from any insurer.
   - Premium is per insured person per month; the figure shown is for one person.
   - Pre-existing conditions are excluded for the first 12 months.
   - Death and income-protection cover is suggested for the household earner only; check each other adult's income before adding it, and children are not offered it.
Total for one insured person: IDR 340,000 per month (mock). Indicative; consult a licensed agent before buying.
```
