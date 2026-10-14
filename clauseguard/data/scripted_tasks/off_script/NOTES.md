## How to read this report

The 15 questions were written to be realistic and deliberately different from T01-T23 / A01-A10: varied phrasing, typos, slang, Indonesian and Indonesian-English mixes, relative dates ("kemarin", "next month", "6 days ago"), a hypothetical resignation, a negated vehicle ("no other vehicle"), and an instruction the assistant has no tool for ("pls cancel my policy"). Pass criteria are objective fields of the structured reply (intent, verdict per policy, payable, denial code, deadline, COB order and status, refusal flag, alerts, executed tool tiers, quoted clause ids); no model judges anything, and no criterion was loosened to make a question pass.

**First probe, before any fix: 6 of 15 passed** (counted by reading the replies against the same criteria, not from a YAML run) (O02, O03, O04, O07, O12, O14). The 9 failures were real defects, all fixed in the planner / rule binder / loop (not in the solver or the PEP):

| question | defect found | fix |
|---|---|---|
| O01, O09, O13 (Indonesian) | Indonesian questions were classified OUT_OF_SCOPE ("klaim", "cair", "opname", "santunan", "rawat inap" unknown) | Indonesian claim / benefit / status vocabulary in the planner; Indonesian months (okt, agu, des, mei) in the date parser |
| O05, O08 | "next month" was not a date, so the reply said "no event date given" and assumed today; "then die" bound no event and the agent asked what happened | relative dates (next month, in N days/weeks, N days ago, kemarin, besok ...); "die" as a death event |
| O06 | the open dengue/asthma claim on file was merged into a different admission the user described (claim's discharge date + user's admission date gave a 13-day stay and a payable of IDR 3,900,000) | a claim on file is used only when it does not contradict a date the user stated |
| O10 | "no other vehicle" matched the positive pattern "other vehicle", so a single-vehicle fall was treated as a two-vehicle collision | negations / single-vehicle patterns are checked first; "fell", "skidded" are claim words |
| O11 | "during an order" was not recognised as work-related, so the user got a licence question instead of the platform deadline | work-related patterns extended (English and Indonesian) |
| O15 | "pls cancel my policy" fell through to a benefit lookup, which dumped clause text and answered nothing | imperative policy-lifecycle requests are declined with a human route, nothing executed |

A second batch of 10 questions (`off_script_holdout`) behaved the same way: 5 of 10 at the first probe, 10 of 10 after fixes - it is also a development set. The only out-of-sample number is the blind batch (`off_script_blind`, 14 questions written and run once): 3 of 14.

Limits that remain: the planner and binder are lexical (rules), so a wording with none of the known words is declined ("outside what I can answer") rather than guessed; dental treatment after an accident ends as "not determinable" because the wording excludes dental treatment except after an accident and no clause grants a dental benefit; with the LLM planner and binder on, behaviour on these questions was not re-measured (free-tier quota).
