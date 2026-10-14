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
- Agents that read: Document Reader (policy PDF to typed rules), Conversation Agent (new situation, follow-up, correction, what-if), Fact Agent, Explainer, Watchdog
- Code that decides: four solvers, the permission enforcer (T0 to T3), the hash-chained audit log
- Claims: the insurer's own form laid out from its clauses, filled from typed facts, shown before Confirm; uploads matched to the policy's document list
- Insurer side: a claims desk receives form and attachments, decides with a note, can halt the agent; the decision returns to the customer
- Rule packs as data: Indonesia (statutory first, group before individual) and a generic pack
Notes: One slide, two halves. The agents read: a Document Reader turns a policy into typed rules, a Conversation Agent reads each message in context, a Fact Agent binds the facts, an Explainer words the answer in the customer's language, a Watchdog watches deadlines. Code decides: the solvers, the permission enforcer and the audit log. For a claim, the agent lays out the insurer's own form from that insurer's wording, fills it from typed facts, shows it before the Confirm tap and files the uploaded documents with it. On the other side a claims desk, behind its own token, reviews, decides with a note and can halt the agent; the decision flows back to the customer's chat.

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

## Slide 9: Demo, from question to decision
- Rizky, dengue, three days: covered Rp 1.5 million, filing deadline, the clause; one question (partner hospital?) and the BPJS answer follows
- Four hospital documents uploaded at once: read, matched to Sompo's list, bill Rp 2.6 million taken from the invoice; the Sompo claim form appears, downloadable as PDF
- Confirm: the claim and its attachments reach the insurer's desk; approved there with a note; the customer's digest shows the decision
- Dewi, motorbike crash with four policies: who pays first, the expired licence, what-if with a valid one
- Attack: payout-account change goes to a ticket, nothing changes; the audit chain verifies and a tampered copy breaks
Notes: One story end to end. A student with dengue asks what he gets; the answer is the amount, the deadline and the sentence of the policy that decides it, with one question about the hospital. He attaches four hospital documents in one go; the assistant reads them, ticks the insurer's own document list, takes the bill from the invoice and shows Sompo's claim form, which he can download. He taps Confirm, the claim lands on the insurer's desk with the attachments, a person approves it with a note, and the decision appears in his chat. Then a delivery rider with four policies, the what-if panel, and an attack that ends in a ticket.

## Slide 10: What is real and what is next
- Real inputs today: six public insurer wordings, CMS PUF plan year 2026 (834 Texas plans), InsuranceQA questions, UK ombudsman decisions, RIPLAY summaries
- Synthetic, stated as such: benchmark contracts (expert-reviewed), personas, mock group plans, statutory amounts
- Next: ombudsman replay for the twin, premiums in the CMS experiment, on-premise extraction, external red team, Indonesian labelled set
- Not built: anchoring the audit chain outside the host; integration with a real insurer's API (the desk is a sandbox)
- Running: web client on Vercel, Postgres audit chain on Supabase, backend as a Docker image; code, tests, evidence and limitations in the repository
Notes: What is real: the six insurer wordings, the CMS marketplace plans, the consumer questions, the ombudsman decisions and the Indonesian product summaries are public data downloaded with a reproducible script and a manifest of hashes. What is synthetic is stated as synthetic: the benchmark contracts, the personas and the statutory amounts. Next steps are the ombudsman replay for the adjudication twin, premiums in the plan experiment, an on-premise extraction model, an external red team and a labelled Indonesian set. Everything, including the limitations, is in the repository. Thank you.
