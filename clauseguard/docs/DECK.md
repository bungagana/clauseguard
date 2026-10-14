# ClauseGuard: Presentation Deck (10 slides, 10 minutes)

Format: 16:9, one accent colour. `docs/deck/build_deck.py` reads this file and builds `docs/deck/ClauseGuard_deck.pptx`. Keep the structure: `## Slide N: title`, bullet lines starting with `- `, then `Notes:` and the speaker text. Speaker notes are at most 100 words each. Every number is copied from a file in `evidence/`.

## Slide 1: ClauseGuard
- A Multi-Policy Entitlement Engine for Insurance Consumers
- Compiles real policies into a constraint program; computes what you are owed, how to get it, and what to buy
- Proves every answer with clauses; acts only within safe permission tiers
- FinTechathon 2026 | International Track | Topic D | Team ClauseGuard
Notes: Good day. ClauseGuard is an entitlement engine for people who hold several insurance policies. It compiles each policy into typed clauses and runs four deterministic solvers over them: what you are owed, how the bill is split between your policies, what you can still do after a denial, and what to buy to close your gaps. Every answer cites the clause it used. The language model never decides; it only extracts, binds facts and words the reply. Over ten minutes we show the problem, the method, the security boundary and the results, including the ones that are not flattering.

## Slide 2: Coverage is fragmented everywhere
- US: 19% of in-network marketplace claims denied in 2023; under 1% appealed (KFF, 2025)
- Indonesia: more than half of insurance complaints concern claim difficulty (OJK, 2023); 53% of consumer claims rejected (YLKI, 2025)
- Hong Kong: about 30% of settled complaints are non-disclosure; China: payout-rate lawsuits over strict definitions
- A household holds a statutory scheme, a group plan, an individual plan, a rider: who pays first, and how much?
- Five rule failures: late filing, waiting period, wrong payer order, double cover, lapse
Notes: Insurance consumers in the United States, the United Kingdom, Singapore, China and Indonesia share one condition: coverage is split across several policies whose rules nobody reads. In the US, one in five in-network claims was denied in 2023 and under one percent appealed. In Indonesia, the regulator reports that more than half of complaints concern claim difficulty. The failures are arithmetic on the user's own documents: a deadline, a waiting period, the order of payers, cover paid twice. A chat model answers from memory. We want the answer computed from the policy and proved.

## Slide 3: Insurance as a constraint program
- Quarantined extractor compiles each policy into typed clause tuples: relation, qualifiers, verbatim evidence, trust tier
- Qualifiers are data, not prose: limits, deductibles, windows, deadlines, applies-if conditions, basis
- A situation is a closed set of fact slots; an unbound slot is absent, never false
- Four solvers read the store; no model runs inside any of them
- Real inputs: six insurer wordings, 834 CMS marketplace plans, RIPLAY summaries
Notes: Each policy is compiled once by a quarantined extractor into typed clause tuples. The relation is one of twelve values. The qualifiers are numbers with units, time windows, deadlines and conditions over a closed slot vocabulary. The verbatim clause travels with the tuple for citation only. Trust is a qualifier too, so the same filter that rejects an expired exclusion rejects an instruction smuggled through an upload. The user's situation is a set of typed facts. Four deterministic solvers read these objects. The model extracts, binds facts and phrases text. It never decides.

## Slide 4: Architecture
- Policy PDF or CMS row, quarantined extractor, typed clause store, four solvers, cited reply
- Planner proposes intent and tool names; a code-only enforcement point decides what runs
- Uploaded documents pass a hidden-text scan and a quarantined extractor; typed fields only
- Hash-chained audit log, output guard, kill switch
- Rule packs as data: Indonesia (statutory first, group before individual) and a generic pack
Notes: This is the system on one slide. Documents enter through a quarantined extractor and land in the typed clause store. The solvers, written in plain Python, read the store. The planner sees the user's text and tool names only, never document text, and proposes tool calls that an enforcement point in ordinary code accepts or denies. Coordination rules are a data file per jurisdiction: an Indonesian pack with statutory schemes first, and a generic pack for a US or UK household. Every decision is written to a hash-chained audit log.

## Slide 5: Solver 1, verdict, with one example
- Order: candidates, closed world, exclusions unless excepted, periods and conditions, termination, else covered with payable
- Tuple: HAS_PERIOD WAITING, 30 days, exempt if accident or emergency
- Facts: hospitalised for illness, 20 days after the effective date: DENIED, code WAITING_PERIOD, clause quoted
- Day 44 and 5 hospital days at IDR 500,000: COVERED, IDR 2,500,000
- Clarify by verdict sensitivity: try every value of a missing fact; ask only if the verdict changes
Notes: The verdict solver runs a fixed order: find the covering clauses, apply the closed world so that no clause means not applicable rather than denied, then exclusions unless an exception holds, then waiting, grace, survival and contestability periods, then termination, otherwise covered with the payable. Here a thirty-day waiting period denies an admission on day twenty and the reply quotes the clause; on day forty-four the same policy pays two and a half million rupiah. When a fact is missing, the solver tries every value; it asks only if the verdict changes.

## Slide 6: Solvers 2 to 4, entitlement beyond the verdict
- Claim allocation: sequential payers, p_i = min(A_i, s_i minus cost sharing); exact order search within a layer; greedy and single-policy baselines
- Recourse: smallest legitimate fact changes that flip DENIED to COVERED, Pareto-minimal in (days, money, effort); the event itself never changes
- Adjudication twin: every denial ground isolated one clause at a time; readiness score 1 minus the ground weights
- Plan selection: weighted set cover under budget as one mixed-integer programme; indemnity plans never overlap
- Timeline: every dated event with the money that turns on it
Notes: Three more solvers turn a verdict into an entitlement. The allocation optimizer splits one bill across the eligible policies under the jurisdiction's rule pack, presenting each payer what is still unpaid, and searches the claiming order exactly where deductibles or caps make order matter. Recourse searches for the smallest legitimate actions that turn a denial into cover: wait, provide a document, settle arrears, claim elsewhere. Facts about the event itself are immutable. The twin lists every denial ground a claims desk would raise. Plan selection is weighted set cover under a budget, solved as one mixed-integer programme.

## Slide 7: Security by construction
- T0 read own data | T1 compute and draft | T2 submit after a UI click and a server nonce | T3 money and identity: no tool exists, ticket only
- Enforced in code: clauseguard/security/pep.py, rules R1 to R9; untrusted text never becomes a T2 or T3 argument
- Chat attack suite: 0 of 27 attacks had a forbidden effect; 0 of 15 benign requests blocked
- Enforcement patched to allow-all: 1 of 27 succeeds; direct probes 0 of 10 with the guard on
- Hidden text: white text, tiny font, off-page, annotation 20/20; metadata and image alt 12/20; rendered image 0/20
Notes: Security is enforced in code, not in the prompt. Reading and computing are free. Submitting needs a click in the interface and a one-time server nonce the model cannot produce. For money and identity the tool does not exist; the agent can only open a ticket for out-of-band verification. In our chat attack suite no attack had a forbidden effect and no benign request was blocked. With the enforcement function patched to allow everything, the kill-switch attack succeeds, which is why it is there. Hidden-text detection is heuristic and misses text rendered as an image.

## Slide 8: Results, with their limits
- Scripted tasks 33 of 33; off-script 15 of 15 and 10 of 10 (development sets); blind batch 3 of 14 (out of sample)
- Paraphrase consistency 20 of 20 with the rule binder, 7 of 8 with the model binder
- Clarification: asks when it should 87% (26/30), silent when it should 100% (35/35), slot correct 100%
- Public benchmark: previous in-scope comparison (82.9 vs 87.5) used mismatched item counts and is corrected; held-out accuracy after the extraction fixes is 84.1%, unchanged from before the fixes; baseline comparison on held-out data not completed (API quota)
- Recourse: 4 of 6 denied verdicts have a legitimate path to cover. Plan selection: optimiser beats the cheapest plan in 73 of 100 households on the mixed catalogue; identical pick on the single-peril CMS catalogue
Notes: Our numbers, with their limits. Scripted tasks pass thirty-three of thirty-three. Two off-script batches pass fully but are development sets; the blind batch, written and run once, passes three of fourteen, the honest generalisation figure for the rule layer. Clarification asks when it should in eighty-seven percent of cases and never asks when it should not. On the public benchmark, the old 82.9-vs-87.5 "parity" claim compared different item counts and has been corrected; held-out accuracy is 84.1% both before and after the extraction fixes, and the baseline comparison on clean held-out data could not be completed this cycle. The CMS plan experiment is honest too: every marketplace plan covers the same perils, so the optimiser and the baselines pick the same plan.

## Slide 9: Demo, the Entitlement tab
- Scene 1, Rizky: dengue stay, COVERED with the clause, deadline 2026-12-06, unprompted premium alert; Timeline and Recourse cards
- Scene 2, Dewi: motorbike crash, payer order, one question; Claim allocation and Pre-check cards with denial grounds and fixable badges
- Scene 3, Santoso family: invoice with hidden white text blocked; Allocation splits the bill; Plan options close the family's gaps under a budget
- Attack buttons: payout-account change refused with a ticket; cross-tenant request denied; audit chain verified, tamper detected
Notes: Three scenes. A student asks about a dengue stay and gets the covered amount, the clause, the filing deadline and an unprompted warning about an unpaid premium; the Timeline card lists every date with money at risk. A delivery rider crashed: the Claim allocation card shows who pays what, and the Pre-check card lists the grounds an insurer would raise and which are fixable. A family uploads an invoice with hidden white text; it is blocked, the bill is split across the group plan and the stacking rider, and Plan options closes the remaining gaps within a budget.

## Slide 10: What is real and what is next
- Real inputs today: six public insurer wordings, CMS PUF plan year 2026 (834 Texas plans), InsuranceQA questions, UK ombudsman decisions, RIPLAY summaries
- Synthetic, stated as such: benchmark contracts (expert-reviewed), personas, mock group plans, statutory amounts
- Next: ombudsman replay for the twin, premiums in the CMS experiment, on-premise extraction, external red team, Indonesian labelled set
- Not built: anchoring the audit chain outside the host; insurer API integration
- Code, tests, evidence and limitations are in the repository
Notes: What is real: the six insurer wordings, the CMS marketplace plans, the consumer questions, the ombudsman decisions and the Indonesian product summaries are public data downloaded with a reproducible script and a manifest of hashes. What is synthetic is stated as synthetic: the benchmark contracts, the personas and the statutory amounts. Next steps are the ombudsman replay for the adjudication twin, premiums in the plan experiment, an on-premise extraction model, an external red team and a labelled Indonesian set. Everything, including the limitations, is in the repository. Thank you.
