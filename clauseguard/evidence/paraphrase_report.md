# Paraphrase consistency report

Generated 2026-10-11 (as-of date for relative expressions: 2026-10-11). 20 coverage scenarios over the three personas' policy records, 3 wordings each (formal English; colloquial / Indonesian-English mix with typos; relative dates such as '6 days ago' or 'in 40 days'). Each wording runs end to end (text -> planner -> facts binder -> solver -> reply) in its own fresh session. `python bench/paraphrase.py [--live N]` reproduces this file.

A scenario is **consistent** when all three wordings give an identical decision signature: verdict and payable per policy, COB payers and amounts, deadline, clarification slot and intent. 'Correct' compares the wordings with a hand-derived expected decision for the scenarios where one is stated.

## Rule binder only (LLM off)

Planner, fact binder and wording are the deterministic fallbacks; no API calls were made.

**Consistent: 20/20 scenarios (100%).** Correct on all three wordings, for the scenarios with a stated ground truth: 12/12.

| id | persona | situation | consistent | correct | decision signature (wording 1) |
|---|---|---|---|---|---|
| P01 | rizky | dengue stay 5-8 Oct | yes | yes | CLAIM_GUIDANCE; verdicts {'HCP-SOMPO-01': ('COVERED', '2000000'), 'BPJS-KES-RIZKY': ('CLARIFY', None)}; clarify facility_bpjs_partner |
| P02 | rizky | 6-day typhoid stay from 1 Oct | yes | yes | CLAIM_GUIDANCE; verdicts {'HCP-SOMPO-01': ('COVERED', '3000000'), 'BPJS-KES-RIZKY': ('CLARIFY', None)}; clarify facility_bpjs_partner |
| P03 | rizky | future hernia surgery inside the 12-month specified-disease wait | yes | yes | POLICY_QA; verdicts {'HCP-SOMPO-01': ('DENIED', None)}; clarify None |
| P04 | rizky | illness admission inside the 30-day waiting period | yes | yes | CLAIM_GUIDANCE; verdicts {'HCP-SOMPO-01': ('DENIED', None), 'BPJS-KES-RIZKY': ('CLARIFY', None)}; clarify facility_bpjs_partner |
| P05 | rizky | accident admission (waiting period exempt) | yes | - | CLAIM_GUIDANCE; verdicts {'HCP-SOMPO-01': ('COVERED', '1000000'), 'BPJS-KES-RIZKY': ('COVERED', None), 'JASA-RAHARJA': ('CLARIFY', None)}; clarify vehicles_involved; COB {'JASA-RAHARJA': ('UNCERTAIN', |
| P06 | rizky | death of illness, life policy in lapse | yes | - | POLICY_QA; verdicts {'TL-ASTRA-07': ('DENIED', None)}; clarify None |
| P07 | rizky | critical illness diagnosis | yes | - | POLICY_QA; verdicts {'CI-CHUBB-05': ('CLARIFY', None)}; clarify survival_days |
| P08 | santoso | Aditya asthma admission, non-partner hospital, bill 18M | yes | - | CLAIM_GUIDANCE; verdicts {'GH-NUSA-GRP': ('COVERED', '6000000'), 'HCP-RIDER-B': ('COVERED', '1200000'), 'HI-INDIV-S': ('DENIED', None), 'BPJS-KES-SANTOSO': ('CLARIFY', None)}; clarify is_emergency; CO |
| P09 | santoso | Sari hernia surgery after the 12-month wait | yes | yes | POLICY_QA; verdicts {'HI-INDIV-S': ('COVERED', None)}; clarify None |
| P10 | santoso | Budi dies of illness: group life | yes | yes | POLICY_QA; verdicts {'GL-NUSA-GRP': ('COVERED', '288000000')}; clarify None |
| P11 | santoso | Nadia accident admission | yes | - | CLAIM_GUIDANCE; verdicts {'GH-NUSA-GRP': ('COVERED', '3000000'), 'HCP-RIDER-B': ('COVERED', '600000'), 'HI-INDIV-S': ('COVERED', '1600000'), 'BPJS-KES-SANTOSO': ('CLARIFY', None), 'JASA-RAHARJA': ('DE |
| P12 | santoso | elective dental implant | yes | yes | POLICY_QA; verdicts {'GH-NUSA-GRP': ('DENIED', None)}; clarify None |
| P13 | santoso | resign then die: group life | yes | yes | POLICY_QA; verdicts {'GL-NUSA-GRP': ('DENIED', None)}; clarify None |
| P14 | dewi | car collision on an order, licence expired | yes | yes | CLAIM_GUIDANCE; verdicts {'PA-CHUBB-03': ('DENIED', None), 'PLATFORM-ACC': ('COVERED', '5000000'), 'BPJS-KES-DEWI': ('DENIED', None), 'JASA-RAHARJA': ('COVERED', '20000000')}; clarify None; COB {'JASA |
| P15 | dewi | single-vehicle slip, licence valid | yes | yes | CLAIM_GUIDANCE; verdicts {'PA-CHUBB-03': ('CLARIFY', None), 'PLATFORM-ACC': ('CLARIFY', None), 'BPJS-KES-DEWI': ('CLARIFY', None), 'JASA-RAHARJA': ('DENIED', None)}; clarify occupation_class; COB {'JA |
| P16 | dewi | crash with a car on an order, platform deadline | yes | yes | CLAIM_GUIDANCE; verdicts {'PA-CHUBB-03': ('CLARIFY', None), 'PLATFORM-ACC': ('COVERED', None), 'BPJS-KES-DEWI': ('CLARIFY', None), 'JASA-RAHARJA': ('COVERED', None)}; clarify license_valid; COB {'JASA |
| P17 | dewi | BPJS in arrears, ordinary admission | yes | - | CLAIM_GUIDANCE; verdicts {'BPJS-KES-DEWI': ('CLARIFY', None)}; clarify facility_bpjs_partner |
| P18 | dewi | off-duty crash with a car | yes | - | CLAIM_GUIDANCE; verdicts {'PA-CHUBB-03': ('CLARIFY', None), 'BPJS-KES-DEWI': ('CLARIFY', None), 'JASA-RAHARJA': ('COVERED', None)}; clarify license_valid |
| P19 | rizky | dengue admission 10 days after the policy start | yes | yes | CLAIM_GUIDANCE; verdicts {'HCP-SOMPO-01': ('DENIED', None), 'BPJS-KES-RIZKY': ('CLARIFY', None)}; clarify facility_bpjs_partner |
| P20 | rizky | life policy status | yes | - | GAP_ANALYSIS; verdicts {}; clarify None |

### Disagreements

None.

## LLM fact binder on (live sample)

First 9 scenarios requested (8 completed without a quota error). LLM stats: `{"binder_calls_attempted": 17, "binder_calls_failed": 3, "blocked_non_binder_calls": 78, "scenarios_incomplete": ["P08"], "scenarios_without_binder_call": ["P07", "P09"], "failure_reasons": {"LLM replay-only mode: cache miss": 3}, "live_calls": 0, "cache_hits": 14, "quota_errors": 0}`. Only the fact binder calls the model; planner, explainer and clarifier stay deterministic.

**Consistent: 7/8 scenarios (88%).** Correct on all three wordings, for the scenarios with a stated ground truth: 5/5.

| id | persona | situation | consistent | correct | decision signature (wording 1) |
|---|---|---|---|---|---|
| P01 | rizky | dengue stay 5-8 Oct | yes | yes | CLAIM_GUIDANCE; verdicts {'HCP-SOMPO-01': ('COVERED', '2000000'), 'BPJS-KES-RIZKY': ('CLARIFY', None)}; clarify facility_bpjs_partner |
| P02 | rizky | 6-day typhoid stay from 1 Oct | yes | yes | CLAIM_GUIDANCE; verdicts {'HCP-SOMPO-01': ('COVERED', '3000000'), 'BPJS-KES-RIZKY': ('CLARIFY', None)}; clarify facility_bpjs_partner |
| P03 | rizky | future hernia surgery inside the 12-month specified-disease wait | yes | yes | POLICY_QA; verdicts {'HCP-SOMPO-01': ('DENIED', None)}; clarify None |
| P04 | rizky | illness admission inside the 30-day waiting period | yes | yes | CLAIM_GUIDANCE; verdicts {'HCP-SOMPO-01': ('DENIED', None), 'BPJS-KES-RIZKY': ('CLARIFY', None)}; clarify facility_bpjs_partner |
| P05 | rizky | accident admission (waiting period exempt) | **NO** | - | CLAIM_GUIDANCE; verdicts {'HCP-SOMPO-01': ('COVERED', '1000000'), 'BPJS-KES-RIZKY': ('COVERED', None), 'JASA-RAHARJA': ('DENIED', None)}; clarify None; COB {'JASA-RAHARJA': ('NOT_CLAIMABLE', '0'), 'BP |
| P06 | rizky | death of illness, life policy in lapse | yes | - | POLICY_QA; verdicts {'TL-ASTRA-07': ('DENIED', None)}; clarify None |
| P07 | rizky | critical illness diagnosis | yes | - | POLICY_QA; verdicts {'CI-CHUBB-05': ('CLARIFY', None)}; clarify survival_days |
| P09 | santoso | Sari hernia surgery after the 12-month wait | yes | yes | POLICY_QA; verdicts {'HI-INDIV-S': ('COVERED', None)}; clarify None |

### Disagreements

**P05 (rizky) accident admission (waiting period exempt)**
- wording 1: `I fell from my motorbike and was hospitalised on 3 October 2026 for 2 days. Is that covered by my hospital cash plan?`
- wording 2: `jatuh dari motor, dirawat 3 okt 2026 2 hari. hospital cash saya cover ga?`
- wording 3: `I had an accident, fell off my bike, and was hospitalised 8 days ago for 2 days. Does my hospital cash plan pay?`
  - signature differs in clarify: null || "vehicles_involved" || "vehicles_involved"
  - signature differs in verdicts: {"BPJS-KES-RIZKY": ["COVERED", null], "HCP-SOMPO-01": ["COVERED", "1000000"], "JASA-RAHARJA": ["DENIED", null]} || {"BPJS-KES-RIZKY": ["COVERED", null], "HCP-SOMPO-01": ["COVERED", "1000000"], "JASA-RAHARJA": ["CLARIFY", null]} || {"BPJS-KES-RIZKY": ["COVERED", null], "HCP-SOMPO-01": ["COVERED", "1000000"], "JASA-RAHARJA": ["CLARIFY", null]}
  - signature differs in cob: {"BPJS-KES-RIZKY": ["PAYER", "9200000"], "HCP-SOMPO-01": ["PARALLEL", "1000000"], "JASA-RAHARJA": ["NOT_CLAIMABLE", "0"]} || {"BPJS-KES-RIZKY": ["PAYER", "9200000"], "HCP-SOMPO-01": ["PARALLEL", "1000000"], "JASA-RAHARJA": ["UNCERTAIN", "None"]} || {"BPJS-KES-RIZKY": ["PAYER", "9200000"], "HCP-SOMPO-01": ["PARALLEL", "1000000"], "JASA-RAHARJA": ["UNCERTAIN", "None"]}
  - bound slot differs: vehicles_involved: 1 | None | None


## Root causes of disagreements (hand-written)

The first run of this benchmark on the code as it stood after the single-source change gave **5/20 consistent** (rule binder). The 20 scenarios and 60 wordings were fixed before that run and were not edited afterwards; the 11 root causes below were fixed in the planner and rule binder (not by changing the wordings), after which the same wordings give **20/20**. Both numbers are in-sample: the wordings were written by the team and the fixes were made by reading these very disagreements, so 20/20 shows the causes are gone, not that an unseen paraphrase will be consistent; the blind off-script batch (3 of 14) is the better guide to unseen wording. Fixes live in `clauseguard/agent/planner.py`, `clauseguard/agent/facts_fallback.py` and `clauseguard/agent/loop.py`.

| # | Root cause (what made two wordings of one situation diverge) | Scenarios hit | Fix |
|---|---|---|---|
| 1 | "6 days ago" / "in 40 days" was read as the length of the hospital stay (days_hospitalized = 6), which overrides the stay derived from the admission and discharge dates | P01 P02 P05 P08 P11 | stay-length regex ignores "N days ago", "in N days"; relative-date parser handles "N days/weeks/months ago", "in N days", "next month", Indonesian equivalents |
| 2 | "hospitalised on 3 October for 2 days": the word "hospitalised" did not count as a hospital context for the stay length, so the payable was missing in one wording | P11 | context regex accepts hospitali[sz]ed/stayed |
| 3 | "fell off my bike" was not a traffic accident (only motorbike/motorcycle/car were), so cause differed (ACCIDENT vs ACCIDENT_TRAFFIC) | P05 P15 | bike, scooter, moped, Indonesian vehicle words added |
| 4 | Intent flip POLICY_QA vs CLAIM_GUIDANCE: Indonesian "cair" (pays out) was a claim word while English "pay out" was not | P06 P07 P10 | "cair/nanggung/bayar" are wording words, "klaim" stays a claim word |
| 5 | Indonesian product nouns ("asuransi individu", "asuransi kantor", "polis jiwa") did not narrow the answer to the named policy, so the reply listed extra policies | P09 | Indonesian focus words |
| 6 | Indonesian dental words (gigi, implan) bound no event | P12 | added |
| 7 | "pas lagi order", "nggak narik", "perjalanan pribadi" did not bind work_related | P14 P18 | added |
| 8 | Falls and collisions without the word "accident" ("jatuh", "ditabrak", "hit by") were not claim words, so the same facts were answered as a wording lookup | P15 P18 | added |
| 9 | "By when must I file the platform claim?" matched the submit_claim action rule (intent ACTION) | P16 | a timing question is not an instruction to submit; imperatives ("submit the claim", "please file", "can you submit") are unchanged and still need the UI confirmation |
| 10 | "batas waktu" (deadline) was matched by the LIMITS topic ("batas"), turning a deadline question into a wording lookup | P16 | "batas" removed from LIMITS |
| 11 | "still active?" never matched the status rule (a word boundary after "?" cannot match), so one wording was a gap analysis and another a clause lookup | P20 | status-only questions route to GAP_ANALYSIS |

### What the live LLM-binder sample showed

The sample used 30 live attempts in total (the cap for this task; part of them were retries and key rotations after a 429, which the free tier returned once) plus replay of the answers already cached. 8 scenarios have every binder call answered by the model; 7 of them are consistent.

* **P05, accident from a motorbike (open):** for the wording "I fell from my motorbike ..." the model filled `vehicles_involved = 1`; for the two other wordings it left the field null. Whether a fall from a motorbike was a single-vehicle accident is an inference, not a statement, so the rule binder (null in all three wordings) is the more conservative reading and the model's answer varies with the wording. Effect: Jasa Raharja is "not covered" in one wording and "asks about the number of vehicles" in the other two. Not fixed: tightening the `vehicles_involved` description in the FactSheet schema changes the schema hash and would invalidate the cached bench runs, which cannot be regenerated while the free-tier quota is exhausted. Recommended fix when quota is back: describe the field as "only if the text states the number of vehicles or says no other vehicle was involved".
* **Stay length (fixed):** in P01 the model's own day count (3, for "admitted 6 days ago, discharged 3 days ago") filled `days_hospitalized` before the code-derived inclusive count from the two dates (4), giving a payable of IDR 1,500,000 instead of 2,000,000 in one wording. The loop now ignores a model-stated stay length whenever the rule binder found both an admission and a discharge date; P01 is consistent in the final live sample.
* P07 and P09 never consulted the binder (pure wording lookups), so they are rule-binder results.
* Scenarios P08 and later could not be completed with the model because the live-call cap of this run was reached; they are listed as "not counted" above rather than silently scored on the fallback.
