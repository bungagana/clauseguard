# ClauseGuard: Technical Documentation

*Clarity in every clause, confidence in every claim.*

FinTechathon 2026 · International Track · Topic D: AI Insurance Assistant
Team: Bunga Laelatul Muna, Izra, Wan Sabrina · Institut Teknologi Sepuluh Nopember, Indonesia
Live demo: https://clauseguard.up.railway.app · Source code: https://github.com/bungagana/clauseguard

## 1. Summary

ClauseGuard is an AI insurance assistant for policyholders. A customer describes what happened in their own words, in English or Indonesian, and ClauseGuard answers three questions from the customer's own policies: is this covered, how much is paid, and by when must the claim be filed. Every answer quotes the clause that decides it. ClauseGuard then reads the customer's hospital documents, prepares the insurer's own claim form, files the claim once the customer confirms, and brings the insurer's decision back to the chat with the next step.

The design rests on one principle: **language models understand and explain, code decides and acts.** Coverage verdicts, amounts and deadlines come from a deterministic rules engine that runs over the policy wording compiled into typed rules. Actions run inside four permission tiers enforced in code. Money and identity changes are never executed by the assistant.

| Measure | Result |
|---|---|
| Attacks that changed anything, of 27 (permission enforcement on) | 0 |
| Accuracy on a public insurance benchmark (390 labels) | 84.6% |
| Denials invented where no clause applies | 1.4% |
| Scripted claim tasks passed | 33 of 33 |
| Automated tests passed | 554 |

## 2. The problem

Most households hold several policies at once: national health insurance, an employer plan, an individual plan, a rider, an accident cover. The rules that decide a claim (filing deadlines, waiting periods, required documents, which payer goes first) sit in documents that customers rarely read. In Indonesia, the financial services authority (OJK) reports that more than half of insurance complaints concern difficulty with claims. In the United States, marketplace insurers denied about one in five in-network claims in 2023, and fewer than 1% were appealed (KFF, 2025). In China and Hong Kong, published disputes concentrate on strict critical-illness definitions and non-disclosure.

A general chatbot answers these questions from memory and can state a wrong rule with confidence. Five costly mistakes recur, and each one is arithmetic on the customer's own documents: filing after the deadline, claiming inside a waiting period, claiming from the wrong payer first, paying twice for overlapping cover or missing benefits that stack, and letting a policy lapse during its grace period.

## 3. What ClauseGuard does

### 3.1 Core features

**ClauseLens: understands your cover.** The customer asks in plain words ("three days in hospital with dengue, can I claim?"). ClauseLens reads all of the customer's policies together and returns, per policy, covered or not, the indicative amount and the last day to file, with the deciding clause quoted word for word. When one missing fact would change the answer, it asks for that fact only. When several policies apply, it computes which payer goes first and how much each one pays.

**ClaimFlow: handles your claim.** The customer sends hospital documents (invoice, medical resume, prescription, lab results). ClaimFlow shows what it read from each file, checks the files against the insurer's own list of required documents, and fills in that insurer's claim form. The customer can correct any field before sending. The claim is filed only after the customer taps Confirm. When the insurer decides, the decision and the assessor's note arrive in the chat, together with what can be fixed or whether an appeal has grounds.

**TrustLock: keeps you in control.** The customer chooses how far the assistant may go (Observe, Draft or Act). Submitting anything requires a one-time confirmation that the model cannot produce. Changing a payout account or a beneficiary is reserved for a person at the insurer. Hidden instructions inside uploaded files are detected and ignored. Every step is written to a tamper-evident log.

### 3.2 Supporting features

| Feature | What it gives the customer |
|---|---|
| Deadline Tracker | Warnings before a claim deadline or premium grace period runs out |
| Claim Simulator | What-if answers ("if I had stayed five days") without affecting a real claim |
| Own policy upload | Any policy PDF is read live and can be asked about immediately; marked unverified until reviewed |
| Document reader | A per-file summary of amounts, dates, diagnosis and which requirement the file satisfies |
| Appeal helper | Checks whether a rejection contradicts the policy and drafts an appeal letter that quotes the clause |
| PDF export | The answer, the evidence and the claim form as a document |
| Bilingual | Replies in the language the customer writes, English or Indonesian |
| Accounts and history | Email sign-in; each customer's policies, claims and chats stay on their account |

### 3.3 A complete claim, end to end

1. Rizky, a graduate student, writes: "I was admitted for dengue on 25 September for three days."
2. ClauseLens answers: the hospital cash plan covers it, IDR 1,500,000, file by 27 November, quoting Benefits Article 1. For national health insurance, it asks one question: was the hospital a partner facility?
3. Rizky sends four hospital files. ClaimFlow lists what each file contains and confirms that every required document is present.
4. Rizky asks the assistant to submit. ClaimFlow shows the insurer's claim form filled in; Rizky taps Confirm.
5. An assessor at the insurer's desk approves the claim with a note. The decision appears in Rizky's chat without being asked for.

This flow was recorded against the sandbox insurer with its audit sequence numbers (execution evidence, item "claims desk run").

## 4. Architecture

![Figure 1. ClauseGuard architecture: AI agents understand and explain; the rules engine decides; the guardian enforces permissions; every step is recorded.](img/architecture.png)

| Component | Kind | Responsibility |
|---|---|---|
| Conversation Agent | AI | Reads how a message relates to the conversation: a new situation, a correction, an answer to the assistant's question, a what-if, or a general question |
| Fact Agent | AI | Turns free text into typed facts (dates, days in hospital, bill, cause) |
| Document Reader Agent | AI, quarantined | Removes personal data locally, then turns policy wording and claim documents into typed records; it has no tools and no conversation history |
| Rules engine | Code | Decides coverage, amounts, deadlines, payer order and readiness from the typed rules |
| Guardian | Code | Enforces the four permission tiers on every tool call |
| Explainer Agent | AI | Words the answer; every amount, date and identifier is checked against the engine before it is shown |
| Watchdog Agent | AI and code | Follows deadlines and claim decisions, and tells the customer before money is lost |
| Audit log | Code | Hash-chained record of every step, written by code only |

Each language-model call is schema-constrained: the model fills a closed structure (an intent from a fixed list, a choice among given candidates, a fact from a fixed vocabulary), and code validates the result before it is used. No model output ever becomes a tool argument for a submission, and no model is inside the rules engine.

## 5. Core method

### 5.1 Policies as typed rules

Each policy is compiled into a record of clause rules: *covers*, *excludes*, *except*, *conditioned on*, *period* (waiting, grace, filing deadline, survival), *pays*, *requires document*, *terminates if*. Each rule carries typed qualifiers (amounts, per-day limits, deductibles, co-payments, time windows, conditions) and the verbatim clause text with its section. The clause text is shown to the customer but never used to decide. Extraction runs in two passes (outline, then rules per section) with temperature zero and a closed schema.

### 5.2 The verdict

For a policy and the customer's facts, the engine evaluates the rules in a fixed order: find the covering rules for the event; if none and nothing governs the event, the answer is *not addressed by this policy* (it never invents a denial); then exclusions, unmet conditions and periods, and termination; otherwise *covered*, with the payable amount computed from the benefit rules and limits. Every step records the rule that fired, which is why each answer can quote its clause.

**Ask only what changes the answer.** If a fact is missing, the engine re-runs the verdict for every possible value of that fact. If the verdict does not change, the assistant does not ask. If it does, the assistant asks for that one fact and explains which clause makes it matter.

### 5.3 Who pays first

For one bill and several eligible policies, payers are layered by the coordination rules of the jurisdiction (for Indonesia: the statutory road-accident scheme, then national health insurance at a partner facility, then employer group before individual cover; fixed daily benefits are paid in parallel). Policy *i* pays *min(cap, presented amount minus the member's cost sharing)*, and each payer is presented only what is still unpaid, so the total never exceeds the bill. Within a layer, every claiming order is evaluated exactly and the one that recovers the most is chosen.

### 5.4 Fixing a rejection

When a verdict is a denial, the engine searches for the smallest set of *legitimate* changes that would make it covered (wait until a date, provide a document, use another policy in the portfolio, choose a partner hospital for a future stay) and returns the options that are best in time, money and effort. Facts that describe what happened (cause, dates, diagnosis, licence, intoxication) can never be changed, so the search cannot coach misrepresentation. An adjudication twin lists every ground an assessor could raise, not only the first, and gives a readiness score before filing.

### 5.5 Closing gaps within a budget

For coverage gaps, a mixed-integer programme selects the plans that close the most weighted gap within the customer's monthly budget, without buying overlapping indemnity cover.

### 5.6 Understanding the conversation

Before any fact is used, the Conversation Agent classifies the message against the situation already established, using the last few exchanges for references such as "that one" or "and the other policy?". A correction updates only the corrected fact; a what-if is answered as a what-if; a new situation clears the previous one. The planner also reads what the customer wants to know (documents, deadline, amount, progress of a filed claim), and the deterministic answer to that question is placed first. When more than one policy could take a claim, the assistant asks which one to file instead of choosing. A request to act is accepted only when the model reads an explicit request or an accepted offer; a greeting can never prepare a submission.

### 5.7 Writing the answer

The Explainer Agent receives only the engine's results and worked examples. It writes two candidate replies; a verifier checks that every number, date and identifier in the chosen candidate appears in the engine's results, and falls back to the other candidate, then to a fixed text, if not. Quoted clause text must match the policy word for word. If the language model is unavailable, the customer is told so plainly and may use their own key; no rule-based text is presented as the assistant's answer.

## 6. Security

Four permission tiers are enforced by code on every tool call:

| Tier | What it allows | How it is controlled |
|---|---|---|
| T0 | Read the customer's own data | Account isolation on every request |
| T1 | Compute, draft, prepare a form | Runs automatically, no side effects outside the session |
| T2 | Submit a claim, attach a document, file an appeal, book a call-back | Only after the customer taps Confirm; a single-use server token bound to the exact arguments |
| T3 | Money and identity (payout account, beneficiary) | No executing tool exists; the assistant opens a ticket for a person at the insurer |

Further controls: text from documents, tools and models is labelled untrusted and can never become a T2 or T3 argument; uploaded files are scanned for hidden instructions (white text, tiny fonts, off-page text, annotations); personal data is removed locally before any document reaches a hosted model; a circuit breaker stops a session after repeated denials; the insurer holds a halt switch that stops every assistant action for every customer; customers sign in with confirmed email accounts, and one account can never read another's policies, claims, files or chats. The threat model, OWASP mapping, test results and risk register are in the Security Self-Assessment.

## 7. Data

| Source | Use |
|---|---|
| Six public insurer policy wordings (Sompo, Astra, Chubb, Great Eastern) and 30 Indonesian product summaries (RIPLAY) | Extraction; the sandbox policies quote these clauses verbatim |
| Public insurance benchmark: 10 contracts, 58 scenarios, 580 clause-traced labels (Mridul, Kapa and Seneviratne, 2026, CC-BY-4.0) | Accuracy evaluation |
| US marketplace plans (CMS Public Use Files, 2026, 834 plans) | Plan selection and payer-order experiments |
| ICD-10-CM code list (public domain, 74,879 codes) | Mapping diagnoses to critical-illness rules |
| InsuranceQA and UK Financial Ombudsman decisions | Robustness and dispute replay material |

The three demo customers, their claims and the sandbox insurer are synthetic. Statutory schemes (BPJS Kesehatan, Jasa Raharja) are modelled from public regulation. Benefit amounts on the sandbox policies are set to match the worked examples. No real customer data is used.

## 8. Evaluation

All results are reproducible from the scripts listed in the Execution Evidence Index; every figure below names its report.

| Evaluation | Result | Report |
|---|---|---|
| Scripted claim tasks (functional, adversarial, plan recommendation) | 33 of 33 passed | task report |
| Attacks through the full chat (prompt injection, privilege escalation, data exfiltration, misrepresentation) | 0 of 27 succeeded; 0 of 15 benign requests blocked | adversarial report |
| Same attacks with the permission enforcement removed | 1 of 27 succeeded | adversarial report |
| Public benchmark, extracted rules plus engine (n = 390) | 84.6% accuracy [77.8, 90.0]; 1.4% invented denials | benchmark report |
| Same, with the benchmark's own gold rules (n = 342) | 91.8%; the remaining gap comes from document reading | benchmark report |
| Clarification (ask only when the answer would change) | asks when needed 87%; stays silent when not needed 100% | clarification report |
| Paraphrase consistency (three wordings per question) | 20 of 20 identical decisions | paraphrase report |
| Payer order versus claiming in the order held (500 households, real US plans) | the held order is suboptimal in 47.2% of households, by USD 988 on average | allocation report |
| Plan selection versus cheapest plan (100 households) | closes more gap in 73 of 100 | plan selection report |
| Hidden-text detection (20 files per technique) | 20 of 20 for white, tiny, off-page and annotation text; 0 of 20 for text drawn inside an image | adversarial report |
| Diagnosis coding (76 labelled lines) | 92.2% correct category; 3 of 76 wrong codes, none inside a critical-illness range | diagnosis report |
| Conversation quality (47 turns: slang, typos, corrections, what-ifs, small talk, attacks) | 42 of 47 passed | conversation report |
| Cost | 0.98 model calls per chat turn on average | cost report |
| Automated tests | 554 passed | test suite |

**Why each component exists.** On the benchmark, model-only answers invent denials where no clause governs more often (3.1%) than the engine (1.4%), and cannot show which clause decided. Without the permission layer, one attack succeeds; with it, none does. Asking only verdict-changing questions kept the assistant silent on all 35 irrelevant gaps. The payer-order optimiser recovers more than claiming in the order policies are held whenever deductibles, co-payments or caps are involved.

## 9. Implementation and deployment

| Layer | Technology |
|---|---|
| Rules engine, agents, sandbox insurer API | Python, FastAPI, Pydantic |
| Language models | Google Gemini (schema-constrained JSON output, temperature zero) |
| Web application and insurer desk | Next.js, TypeScript, Tailwind CSS |
| Accounts and storage | Supabase Auth and Postgres (audit chain, chat history, claims), with row-level security |
| Hosting | Railway: web service and API service, Southeast Asia region |

The sandbox insurer is a separate service with its own claims desk. Claims filed by the assistant arrive there with the filled form and the attached files; a person moves them through received, under review, approved, rejected or paid, with a note that is returned to the customer.

## 10. Limitations

- The extractor is a language model and can read a value wrongly inside the schema; on the benchmark, extraction coverage per contract ranges from 0.62 to 1.00, and the gap between extracted and gold rules is 7 points.
- The engine covers coverage, exclusion, period, rider and termination questions; 24 of 58 benchmark scenarios (dividends, investment-linked caps, estate planning) are outside its scope.
- The public benchmark covers life insurance only; Indonesian products are tested on hand-verified sandbox policies and team-written tasks. The blind off-script batch for the rule-only mode passed 3 of 14.
- Statutory amounts and payer rules are modelled and marked "verify with the payer"; INA-CBG tariff grouping is not implemented.
- Text drawn inside an image is not detected as hidden text.
- The permission layer limits what the assistant can do; it does not guarantee that advice text is correct, which is why every answer is marked indicative.
- The assistant's working memory of a conversation ends when the server restarts; the customer is told and asked to restate the situation. Saved chats and filed claims are kept.

## 11. Running it

```bash
git clone https://github.com/bungagana/clauseguard.git && cd clauseguard
cd clauseguard && pip install -r requirements.txt && python scripts/serve.py --fresh
cd ../clauseguard-web && npm install && npm run dev
cd ../clauseguard && python -m pytest -q
```

Without a model key, every step falls back to its deterministic path. The full list of evaluation commands is in the Execution Evidence Index.

## 12. References

- Mridul, Kapa and Seneviratne (2026). A benchmark for gap and overlap analysis of insurance contracts. arXiv:2604.10853.
- Debenedetti et al. (2025). CaMeL: defeating prompt injections by design. arXiv:2503.18813.
- Wachter, Mittelstadt and Russell (2017); Ustun, Spangher and Liu (2019). Counterfactual explanations and algorithmic recourse.
- OWASP Top 10 for Agentic Applications (2026).
- KFF (2025). HealthCare.gov insurers denied nearly 1 in 5 in-network claims in 2023.
- OJK (2023). Claim difficulty is the most reported insurance complaint.
