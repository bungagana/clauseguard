# Clarification precision report

Generated 2026-10-11. `python bench/clarify_eval.py` reproduces this file (LLM off: rule planner, rule binder, solver, template wording; as-of date 2026-10-11).

Each of 18 base messages is a complete user message over the persona policies (3 personas) made of named fact fragments. A *variant* drops exactly one fragment. Whether the dropped fact is **decision-relevant** is decided by a brute-force oracle that does not use the agent's clarifier: the fragment is replaced by each of its alternative wordings, the complete message is run end to end, and the fact is relevant when the verdict vector (verdict per policy) differs between the alternatives. Irrelevant controls are facts that never move a verdict (names, doctor, phone, bill amount, a stay length that only moves a payable).

## Results

| measure | value | counts |
|---|---|---|
| removals of a decision-relevant fact | 30 | |
| removals of an irrelevant fact | 35 | of which payable-only: 3 |
| **recall** (asks when it should) | **73%** | 22/30 |
| **silence** (stays silent when it should) | **100%** | 35/35 |
| **ask precision** (asked questions that were on a relevant removal) | **100%** | 22/22 |
| **slot accuracy** (asked slot is one the removed fact carries) | **100%** | 22/22 |
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
| B02 | rizky | facility | relevant | - | - | - |
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
| B05 | rizky | facility | relevant | - | - | - |
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
| B10 | dewi | vehicles | relevant | - | - | - |
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
| B20 | rizky | facility | relevant | - | - | - |
| B20 | rizky | hospital_name | irrelevant | - | - | - |

## Misses (relevant fact dropped, no question)

- B01 / dates: `I was admitted with typhoid to a private hospital that is not a BPJS partner. It was a planned admission. The bill was IDR 11,000,000. I was treated by Dr. Hadi. Can I claim?` - oracle verdict vectors: ['{"HCP-SOMPO-01": "COVERED"}', '{"HCP-SOMPO-01": "DENIED"}']
- B02 / facility: `I fell off my motorbike and was hospitalised on 3 October 2026 for 2 days at . No other vehicle was involved. My phone number is 0812-555-0101. Can I claim?` - oracle verdict vectors: ['{"BPJS-KES-RIZKY": "CLARIFY", "HCP-SOMPO-01": "COVERED", "JASA-RAHARJA": "DENIED"}', '{"BPJS-KES-RIZKY": "COVERED", "HCP-SOMPO-01": "COVERED", "JASA-RAHARJA": "DENIED"}']
- B03 / dates: `I was diagnosed with cancer and I am still alive today. My oncologist is Dr. Hadi. Does my critical illness policy pay?` - oracle verdict vectors: ['{"CI-CHUBB-05": "COVERED"}', '{"CI-CHUBB-05": "DENIED"}']
- B04 / dates: `I died of illness . My full name is Rizky Pratama. Will my life policy pay?` - oracle verdict vectors: ['{"TL-ASTRA-07": "COVERED"}', '{"TL-ASTRA-07": "DENIED"}']
- B05 / facility: `I was hospitalised on 3 October 2026 for 4 days for a hernia operation at . The bill was IDR 12,000,000. Can I claim?` - oracle verdict vectors: ['{"BPJS-KES-RIZKY": "CLARIFY", "HCP-SOMPO-01": "DENIED"}', '{"BPJS-KES-RIZKY": "COVERED", "HCP-SOMPO-01": "DENIED"}']
- B07 / dates: `Sari is scheduled for hernia surgery . The hospital is Siloam Surabaya. Will her individual health policy HI-INDIV-S pay?` - oracle verdict vectors: ['{"HI-INDIV-S": "COVERED"}', '{"HI-INDIV-S": "DENIED"}']
- B10 / vehicles: `I had an accident on 5 October 2026 I was on an active delivery order. My licence had expired. I was hospitalised for 6 days. The bill was IDR 22,000,000. Who pays?` - oracle verdict vectors: ['{"BPJS-KES-DEWI": "DENIED", "JASA-RAHARJA": "COVERED", "PA-CHUBB-03": "DENIED", "PLATFORM-ACC": "COVERED"}', '{"BPJS-KES-DEWI": "DENIED", "JASA-RAHARJA": "DENIED", "PA-CHUBB-03": "DENIED", "PLATFORM-ACC": "COVERED"}']
- B20 / facility: `I was hospitalised in the ICU on 3 October 2026 with dengue at . The ward is Melati. Can I claim?` - oracle verdict vectors: ['{"BPJS-KES-RIZKY": "CLARIFY", "HCP-SOMPO-01": "COVERED"}', '{"BPJS-KES-RIZKY": "COVERED", "HCP-SOMPO-01": "COVERED"}']

## False asks (irrelevant fact dropped, question asked)


## Wrong slot (relevant fact dropped, a different slot was asked)
