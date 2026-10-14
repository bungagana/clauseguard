# Clarification precision report

Generated 2026-10-11. `python bench/clarify_eval.py` reproduces this file (LLM off: rule planner, rule binder, solver, template wording; as-of date 2026-10-11).

Each of 18 base messages is a complete user message over the persona policies (3 personas) made of named fact fragments. A *variant* drops exactly one fragment. Whether the dropped fact is **decision-relevant** is decided by a brute-force oracle that does not use the agent's clarifier: the fragment is replaced by each of its alternative wordings, the complete message is run end to end, and the fact is relevant when the verdict vector (verdict per policy) differs between the alternatives. Irrelevant controls are facts that never move a verdict (names, doctor, phone, bill amount, a stay length that only moves a payable).

## Results

| measure | value | counts |
|---|---|---|
| removals of a decision-relevant fact | 30 | |
| removals of an irrelevant fact | 35 | of which payable-only: 3 |
| **recall** (asks when it should) | **87%** | 26/30 |
| **silence** (stays silent when it should) | **100%** | 35/35 |
| **ask precision** (asked questions that were on a relevant removal) | **100%** | 26/26 |
| **slot accuracy** (asked slot is one the removed fact carries) | **100%** | 26/26 |
| relevant removals missed where the reply discloses an assumed event date | 3 | |

Base messages excluded because the complete message already triggers a question:

- B13: the complete message already triggers a question or an open verdict (occupation_class)
- B15: the complete message already triggers a question or an open verdict (occupation_class)

## Per scenario

| base | persona | dropped fact | oracle | asked slot | slot ok | assumed today |
|---|---|---|---|---|---|---|
| B01 | rizky | dates | relevant | - | - | yes |
| B01 | rizky | facility | relevant | facility_bpjs_partner | yes | - |
| B01 | rizky | emergency | relevant | is_emergency | yes | - |
| B01 | rizky | bill | irrelevant | - | - | - |
| B01 | rizky | doctor | irrelevant | - | - | - |
| B02 | rizky | dates | irrelevant | - | - | yes |
| B02 | rizky | days | irrelevant (payable only) | - | - | - |
| B02 | rizky | facility | relevant | facility_bpjs_partner | yes | - |
| B02 | rizky | vehicles | relevant | vehicles_involved | yes | - |
| B02 | rizky | phone | irrelevant | - | - | - |
| B03 | rizky | dates | relevant | - | - | - |
| B03 | rizky | alive | relevant | survival_days | yes | - |
| B03 | rizky | doctor | irrelevant | - | - | - |
| B04 | rizky | cause | relevant | cause | yes | - |
| B04 | rizky | dates | relevant | - | - | yes |
| B04 | rizky | name | irrelevant | - | - | - |
| B05 | rizky | dates | irrelevant | - | - | yes |
| B05 | rizky | diagnosis | relevant | cause | yes | - |
| B05 | rizky | facility | relevant | facility_bpjs_partner | yes | - |
| B05 | rizky | bill | irrelevant | - | - | - |
| B06 | santoso | facility | relevant | facility_bpjs_partner | yes | - |
| B06 | santoso | emergency | relevant | is_emergency | yes | - |
| B06 | santoso | bill | irrelevant | - | - | - |
| B07 | santoso | diagnosis | relevant | cause | yes | - |
| B07 | santoso | dates | relevant | - | - | yes |
| B07 | santoso | hospital_name | irrelevant | - | - | - |
| B08 | santoso | cause | relevant | cause | yes | - |
| B08 | santoso | name | irrelevant | - | - | - |
| B09 | santoso | days | irrelevant (payable only) | - | - | - |
| B09 | santoso | facility | relevant | facility_bpjs_partner | yes | - |
| B09 | santoso | nickname | irrelevant | - | - | - |
| B10 | dewi | vehicles | relevant | vehicles_involved | yes | - |
| B10 | dewi | work | relevant | work_related | yes | - |
| B10 | dewi | licence | relevant | license_valid | yes | - |
| B10 | dewi | days | irrelevant | - | - | - |
| B10 | dewi | bill | irrelevant (payable only) | - | - | - |
| B11 | dewi | dates | irrelevant | - | - | yes |
| B11 | dewi | facility | relevant | facility_bpjs_partner | yes | - |
| B11 | dewi | name | irrelevant | - | - | - |
| B12 | dewi | work | irrelevant | - | - | - |
| B12 | dewi | licence | irrelevant | - | - | - |
| B12 | dewi | phone | irrelevant | - | - | - |
| B14 | santoso | dates | irrelevant | - | - | yes |
| B14 | santoso | vehicles | relevant | vehicles_involved | yes | - |
| B14 | santoso | facility | relevant | facility_bpjs_partner | yes | - |
| B14 | santoso | bill | irrelevant | - | - | - |
| B16 | rizky | dates | irrelevant | - | - | - |
| B16 | rizky | cause | irrelevant | - | - | - |
| B16 | rizky | facility | irrelevant | - | - | - |
| B16 | rizky | nickname | irrelevant | - | - | - |
| B17 | santoso | diagnosis | relevant | cause | yes | - |
| B17 | santoso | doctor | irrelevant | - | - | - |
| B17 | santoso | hospital_name | irrelevant | - | - | - |
| B18 | santoso | diagnosis | relevant | cause | yes | - |
| B18 | santoso | facility | relevant | facility_bpjs_partner | yes | - |
| B18 | santoso | age | irrelevant | - | - | - |
| B18 | santoso | doctor | irrelevant | - | - | - |
| B19 | santoso | diagnosis | relevant | cause | yes | - |
| B19 | santoso | facility | relevant | facility_bpjs_partner | yes | - |
| B19 | santoso | emergency | irrelevant | - | - | - |
| B19 | santoso | age | irrelevant | - | - | - |
| B19 | santoso | doctor | irrelevant | - | - | - |
| B20 | rizky | cause | relevant | cause | yes | - |
| B20 | rizky | facility | relevant | facility_bpjs_partner | yes | - |
| B20 | rizky | hospital_name | irrelevant | - | - | - |

## Misses (relevant fact dropped, no question)

- B01 / dates: `I was admitted with typhoid to a private hospital that is not a BPJS partner. It was a planned admission. The bill was IDR 11,000,000. I was treated by Dr. Hadi. Can I claim?` - oracle verdict vectors: ['{"HCP-SOMPO-01": "COVERED"}', '{"HCP-SOMPO-01": "DENIED"}']
- B03 / dates: `I was diagnosed with cancer and I am still alive today. My oncologist is Dr. Hadi. Does my critical illness policy pay?` - oracle verdict vectors: ['{"CI-CHUBB-05": "COVERED"}', '{"CI-CHUBB-05": "DENIED"}']
- B04 / dates: `I died of illness . My full name is Rizky Pratama. Will my life policy pay?` - oracle verdict vectors: ['{"TL-ASTRA-07": "COVERED"}', '{"TL-ASTRA-07": "DENIED"}']
- B07 / dates: `Sari is scheduled for hernia surgery . The hospital is Siloam Surabaya. Will her individual health policy HI-INDIV-S pay?` - oracle verdict vectors: ['{"HI-INDIV-S": "COVERED"}', '{"HI-INDIV-S": "DENIED"}']

## False asks (irrelevant fact dropped, question asked)


## Wrong slot (relevant fact dropped, a different slot was asked)


## Reading the numbers

* **In-sample.** The base messages were written, run, and the agent fixed while looking at this benchmark (first run: recall 69 %, silence 96 % on a 36-removal set; final figures are in the table above), so the final numbers show that the identified causes are fixed, not how well the agent asks on unseen questions.

* **Counts.** 20 base messages were written; 18 are usable (B13 and B15 are excluded: any message in Dewi's household that makes the PA policy relevant asks for `occupation_class`, which the rule binder cannot bind from free text, so the complete message is never question-free). The 18 usable bases give 30 decision-relevant and 35 irrelevant single-fact removals (the target was 30 and 30; the oracle, not the design, decides which class a removal belongs to, and 5 extra irrelevant controls came out of the 35).
* **The oracle shares the solver.** "Relevant" means the verdict vector of the end-to-end agent changes between alternative wordings of the fact. It does not use the agent's clarifier, but it does use the same solver and binder, so it measures whether the agent asks about what the solver is sensitive to, not whether the solver's rules are right.
* **Not every missing fact needs a question.** Facts the system already holds are never asked: employment status, premium and arrears status, diagnosis history of the insured, and an open claim on file that matches the user's date or amount (the claim record can supply the facility). Early drafts of this benchmark used dates that happened to match the seeded claims (3 Oct, 5 Oct); the agent then correctly answered from the record, and those dates were changed so the benchmark measures asking, not record lookup.
* **LLM off.** Rule planner, rule binder, solver, template wording. The clarifier's LLM wording only rephrases the question and never chooses the slot, so slot accuracy is unaffected by it.

## What the benchmark found (fixed)

The first complete run, before any of the fixes below, gave recall 69 % and silence 96 % on a smaller 36-removal set, with false asks and one wrong slot; after the fixes and the growth of the set to 65 removals the figures are those in the table above. Fixes (planner / rule binder / derivation, never the solver):

| finding | effect before the fix | fix |
|---|---|---|
| "I am still alive **today**": the word *today* became the diagnosis date (a later date mention overwrote the real one) | critical-illness claim always DENIED (survival 0 days) | a bare *today* is ignored as an event date when another date is given |
| "still alive" did not bind the survival days | the CI policy asked for survival days even when the user said the insured was alive | alive-so-far = as-of date minus diagnosis date |
| Premium status was judged on the as-of date, not the event date | a death on 20 Sep (inside the grace period) was DENIED as lapsed | status is judged at the event date |
| Accidents were asked "was it diagnosed before the policy started?" and "is the diagnosis on the specified-disease list?" | two illness-only questions on a fall | a discrete accident is bound as not pre-existing and not on the list (only when the date is not before the policy start) |
| "Nadia fell" asked how many vehicles were involved | Jasa Raharja question on a plain fall | a plain fall at home with no road context binds 0 vehicles; road context (order, delivery, riding) still asks |
| "another car hit me" was not read as two vehicles | false question | pattern added |
| `occupation_class` had no question template | "Please tell me the value of 'occupation_class'." | a proper question with the three classes |

## What remains

* **Missing event date (all 4 misses).** When the user gives no date, the agent evaluates as of today, says so ("No event date was given, so I evaluated the policies as of ..."), and asks nothing. The verdict can flip with the real date (waiting periods, grace period, specified-disease period). This is the behaviour that makes "Am I covered if I get hospitalised next week?" answerable with one question about the cause only (task T03), but for a claim in the past it is a recall loss. A fix needs a tense or intent signal (past event vs hypothetical) and was not attempted here.
* **Dewi's PA policy always asks `occupation_class`.** The system holds both the declared and the actual occupation of the persona but binds neither to the slot, so every PA-relevant message from Dewi gets this question first (excluded bases B13 and B15).
