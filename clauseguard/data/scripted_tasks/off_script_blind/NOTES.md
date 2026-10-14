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
