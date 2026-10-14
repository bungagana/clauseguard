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
