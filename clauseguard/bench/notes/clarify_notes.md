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
