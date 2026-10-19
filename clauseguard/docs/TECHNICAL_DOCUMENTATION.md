# ClauseGuard: Technical Documentation

*Clarity in every clause, confidence in every claim.*

FinTechathon 2026 · International Track · Topic D: AI Insurance Assistant
Team: Bunga Laelatul Muna, Izra, Wan Sabrina · Institut Teknologi Sepuluh Nopember, Indonesia
Live demo: https://clauseguard.up.railway.app · Source code: https://github.com/bungagana/clauseguard

## 1. Problem & scope

### 1.1 Topic and problem

ClauseGuard addresses Topic D, the AI insurance assistant. Many households hold several policies at once, for example national health insurance (BPJS Kesehatan), an employer plan, a personal policy and an accident cover. The rules that decide a claim sit in long policy documents that people rarely read. These rules include filing deadlines, waiting periods, required documents and the order in which payers pay. Indonesia's financial services authority (OJK) reports that more than half of insurance complaints concern difficulty with claims. In the United States, about one in five in-network claims was denied in 2023 and fewer than 1% were appealed (KFF, 2025).

Five costly mistakes recur. A claim is filed after the deadline. A claim is filed inside a waiting period. The wrong payer is claimed first. The customer pays twice for overlapping cover or misses benefits that stack. A policy lapses during its grace period. All five can be computed from the customer's own documents.

### 1.2 User personas

| Persona | Profile | Policies held |
|---|---|---|
| Rizky, 24 | Graduate student with a dengue hospital claim in progress | Hospital cash plan (Sompo), term life with an overdue premium, critical illness, BPJS Kesehatan class 2 |
| The Santoso family | Family of four, the head of the family is an employee | Employer group health and life, a family hospital-cash rider, the wife's individual health plan, BPJS Kesehatan class 1 |
| Dewi, 29 | Ride-hailing courier | Personal accident, the platform's on-trip accident cover, BPJS Kesehatan class 3 with three months of arrears, Jasa Raharja |

The three personas and their policies are synthetic. Their policy wording is modelled on public insurer documents. Real customers can also sign up, upload their own policy PDF and ask about it right away.

### 1.3 Financial tasks the agent completes

1. **Check coverage.** For each policy the agent decides whether the event is covered, the indicative benefit and the filing deadline, with the deciding clause quoted.
2. **Order the payers.** For one hospital bill the agent computes which policy pays first and how much each one pays.
3. **Prepare and file the claim.** The agent reads the hospital documents, matches them to the insurer's list of required documents, fills in that insurer's claim form and files it after the customer taps Confirm.
4. **Follow up on the decision.** The agent relays the insurer's decision, explains what can be fixed and checks whether a rejection has grounds for appeal.
5. **Watch deadlines and policy status.** The agent warns before a filing deadline or a premium grace period runs out.
6. **Close coverage gaps.** The agent recommends the plans that close the largest gap within a monthly budget.

### 1.4 Success metrics

| Metric | Definition | Result |
|---|---|---|
| Scripted task completion | Share of claim tasks that pass automatic checks on verdict, amount, deadline, denial code and actions | 33 of 33 (100%) |
| Coverage accuracy | Correct verdicts on a public insurance benchmark | 84.6% (n = 390) |
| Invented denials | Denials returned where no clause applies | 1.4% |
| Clarification precision | Asks when the answer would change and stays silent otherwise | 87% and 100% |
| End-to-end claim | Documents, form, confirmation, desk decision and the decision back in the chat | Completed and recorded with audit sequence numbers |
| Conversation quality | Turns passed out of 47 turns of slang, typos, corrections and what-ifs | 42 of 47 (89%) |
| Action safety | Attacks that produced any effect | 0 of 27 |

## 2. System architecture

### 2.1 Component diagram

![Figure 1. ClauseGuard architecture. AI agents understand and explain, the rules engine decides, the guardian enforces permissions and every step is recorded.](img/architecture.png)

| Component | Role |
|---|---|
| UI and dialog | A web app for customers (chat, verdict cards, claim form, document upload) and a claims desk for the insurer's staff |
| Orchestrator | The agent loop that runs planning, the permission check, tool calls, fact binding, the rules engine and reply writing for every turn |
| LLM | Google Gemini, used to understand messages, read documents and word replies |
| AI agents | Conversation Agent, Fact Agent, Document Reader Agent, Explainer Agent and Watchdog Agent |
| Tools and API | 19 permission-tiered tools (read policies, check coverage, draft a claim, file a claim, attach a document, file an appeal and others) that call the sandbox insurer API |
| Rules engine | Deterministic code that decides coverage, amounts, deadlines, payer order and claim readiness |
| Guardian | The permission enforcement point in code that checks every tool call |
| Data store | Postgres on Supabase for the audit chain, chat history, claims and tickets. A sandbox database for policies and customers |
| Sandbox insurer | A simulated insurer with its own claims desk, where a person decides the claims the agent files |

### 2.2 Data flow

1. The customer sends a message or a file through the web app.
2. Files pass a hidden-text scanner. Personal data such as national ID numbers, bank accounts and phone numbers is removed locally.
3. The Document Reader Agent turns the file into a typed record, for example document type, dates, bill total and diagnosis.
4. The customer's policies are available as typed rules, and each rule links to its sentence in the policy.
5. Engine results and replies are kept in the customer's session. Chat history, claims and the audit log are stored in Postgres per account.

### 2.3 Decision flow

1. The Conversation Agent decides how the message relates to the conversation: a new situation, a correction, an answer to a question, a what-if or a general question.
2. The planner decides the intent and the tools needed. Safety classifications are decided first by code.
3. The Guardian checks every tool against its permission tier and the autonomy mode the customer chose.
4. The Fact Agent turns sentences into typed facts. The rules engine computes the verdict for every policy.
5. If one unknown fact would change the verdict, the agent asks for that fact only.
6. The Explainer Agent writes the reply. Every amount, date and identifier is checked against the engine's results before it is shown.
7. Any action that sends something to the insurer waits for the customer's confirmation. A person at the insurer decides the claim, and the decision comes back to the chat.

### 2.4 Technology stack, deployment and rationale

| Layer | Technology | Reason |
|---|---|---|
| Rules engine and agent | Python, FastAPI, Pydantic | Strict typed schemas for policy rules, facts and model output. Pydantic rejects model output that does not fit the schema |
| LLM | Google Gemini Flash Lite | Schema-constrained JSON output, low latency, low cost and good understanding of everyday Indonesian |
| Optimisation | SciPy (MILP, HiGHS) | Plan selection as an integer programme with optimal, checkable results |
| Web app | Next.js, TypeScript, Tailwind CSS | A chat interface with interactive cards, one code base for customers and the insurer's desk |
| Accounts and storage | Supabase Auth and Postgres | Email sign-in with confirmation, row-level security, and an audit chain that survives server restarts |
| Hosting | Railway, Southeast Asia region | Web and API as two services close to the database, deployed automatically from the repository |

## 3. Core algorithm description

### 3.1 Planning

The planner has two layers. The first layer is code rules for safety-relevant classifications, such as misrepresentation requests, access to another customer's data, account changes and requests to reveal system internals. The model cannot change these classifications. The second layer is a model that reads the message in the context of the conversation. It decides the intent, the read-only tools needed and the topic of the question, for example documents, deadline, amount or claim progress. A request to act is accepted only when the model reads a clear request or an accepted offer from the agent.

### 3.2 Tool calling

Every tool is registered with a permission tier, argument types and a result type. Tool results are stored as typed handles with a trust label. Tier 2 tools accept handles only, so free text from documents or models cannot become an argument of a submission. When several policies could take a claim, the agent asks which one to file first, with one button per policy.

### 3.3 Memory

The agent uses three kinds of memory. Session working memory holds typed facts, dates, documents read and any form waiting for confirmation. Conversation memory holds the last four exchanges as data for references such as "that one" or "the other policy". Chat history is stored per account in Postgres, so it can be opened from another device.

### 3.4 Retrieval

Policy information is retrieved from a typed clause store. Each policy has been compiled into rules such as covers, excludes, waiting period, filing deadline, pays and requires document. The rules engine retrieves the relevant rules by event, cause and insured person. This design was chosen because an insurance verdict needs the exact rule with its numbers and time windows. Every rule used can be shown with its original sentence. For diagnoses, the agent uses BM25 retrieval over 74,879 ICD-10 code descriptions, then the model picks one code from the candidate list and code verifies the pick.

### 3.5 Claim allocation model

For one bill *B* and several policies, payers are layered by the Indonesian coordination rules. Jasa Raharja pays first for road accidents involving two or more vehicles. BPJS Kesehatan pays when the hospital is a partner facility and membership is active. Employer group cover pays before individual cover. Daily cash benefits are paid in parallel because they stack.

Policy *i* pays *min(A_i, s_i − m_i)*. Here *s_i* is the amount presented, *m_i* is the member's cost sharing (deductible and co-payment) and *A_i* is the policy's payment cap. Each payer is presented only what is still unpaid, so the total never exceeds the bill. Within a layer, every claiming order is evaluated and the order that recovers the most is chosen.

### 3.6 Claim risk assessment

The adjudication twin checks each clause that could deny a claim separately and lists every ground an assessor could raise. Documents are cross-checked, for example dates against days in hospital, diagnosis codes against the cause, and receipt totals against their line items. The result is a claim readiness score with the grounds that can be fixed. When a claim is denied, the engine searches for the smallest legitimate change that makes it covered, such as waiting until a date, providing a document or using another policy. Facts that describe what happened, such as cause, dates and diagnosis, are locked in code and are never changed.

### 3.7 Prompt design

Every model call uses a closed output schema at temperature zero. The model fills choices from fixed lists, for example the intent, the relation of the message or one policy from a candidate list. Code validates every output before it is used. Customer messages and document content are marked as data in the prompt, and the model is instructed to ignore any instruction inside them. The planner and conversation prompts contain worked examples in Indonesian and English. The reply writer receives the engine's results and six example replies. The model writes short private reasoning notes, drafts two candidate replies and picks the better one.

### 3.8 Guardrails and explainability

A reply verifier checks that every amount, date, percentage and policy number in a reply comes from the engine's results. If the first candidate fails, the second is checked, then a fixed text is used. Clause quotes must match the policy text exactly. Every answer has a "How was this decided" panel that shows how the message was understood, the facts used, the clauses that applied, the engine's verdict, the wording check and the audit record numbers. If the model is unavailable, the customer is told plainly and can use their own API key.

### 3.9 Evaluation

| Evaluation | Dataset or scenario | Baseline | Result |
|---|---|---|---|
| Claim tasks | 33 scripted tasks (20 functional, 10 adversarial, 3 recommendations) | None | 33 of 33 passed |
| Coverage accuracy | Public life insurance benchmark, 10 contracts, 580 labels (CC-BY-4.0) | A model reading the whole contract (b0, b0cw) | 84.6% with 1.4% invented denials. Baseline b0cw 87.5% with 3.1% invented denials on a 112-item subset |
| Clarification | 18 messages with one fact removed per test, judged by an oracle | Asking for every missing fact | Asks when needed 87%, silent when not needed 100% |
| Paraphrase consistency | 20 scenarios in three wordings | None | 20 of 20 identical verdicts |
| Payer order | 500 households with 200 real US marketplace plans | Claiming in the order held, single policy only | The held order is suboptimal in 47.2% of households, by USD 988 on average |
| Plan selection | 100 households, mixed catalogue | Cheapest plan, most expensive plan | Closes more gap in 73 and 79 of 100 |
| Diagnosis coding | 76 labelled diagnosis lines | Alias dictionary | 92.2% correct category. Alias dictionary 17.2% |
| Conversation | 47 narrative, slang, typo, correction and what-if turns | Previous prompt version | 42 of 47, up from 40 of 47 |
| Cost | 90 turns of the scripted tasks | A model reading whole documents | 0.98 model calls per turn, 17% of the baseline's tokens |

**Ablation.**

| Component removed | Effect |
|---|---|
| Permission enforcement in code | Successful attacks rise from 0 to 1 of 27 |
| Extracted rules replaced by the benchmark's gold rules | Accuracy rises from 84.6% to 91.8%, so the remaining gap comes from document reading |
| Rules engine replaced by model-only answers | Invented denials rise from 1.4% to 3.1% and the deciding clause cannot be shown |
| Verdict-sensitivity clarification | Without it the agent asks for every missing fact. With it, 35 of 35 irrelevant gaps were not asked about |

## 4. Security design

### 4.1 Permission tiers

| Tier | Type | Example actions | Rule |
|---|---|---|---|
| T0 | Automatic | Read the customer's own policies, claim status, premium status and deadline reminders | Always restricted to the signed-in account |
| T1 | Automatic | Check coverage, compute payer order, draft a claim, prepare a form, draft an appeal | No effect outside the session |
| T2 | Needs confirmation | File a claim, attach a document to a claim, file an appeal, book a call-back | Runs after the customer taps Confirm. The server issues a single-use token bound to the session, the tool and the exact arguments |
| T3 | Forbidden for the agent | Change the payout account, change a beneficiary, move money | No tool executes it. The agent opens a ticket for a person at the insurer, who verifies identity through a separate channel |

The customer also chooses an autonomy mode. Observe only answers. Draft prepares without sending. Act sends after confirmation.

### 4.2 Threat model

| Threat | Example | Control | Test result |
|---|---|---|---|
| Prompt injection | Hidden instructions in a hospital receipt, such as white text asking to approve the claim | Hidden-text scanner, a quarantined extractor with no tools, untrusted labels on document text, handle-only T2 arguments | 0 of 27 attacks succeeded. White, tiny, off-page and annotation text detected 20 of 20 |
| Data leakage | Asking for another customer's policies or claims, or for system internals | Account isolation on every route, row-level security in the database, output filtering for account and identity numbers, removal of personal data before a document reaches the model | A second account gets a refusal or an empty list for the first account's uploads, chats and claims. Every attempt is recorded in the audit log |
| Unauthorized transaction | Filing a claim without confirmation, changing a bank account with an urgent excuse | Single-use confirmation tokens, no T3 tools, per-session action limits, a circuit breaker, a halt switch at the insurer's desk | Attacks without confirmation and account-change requests produced no effect |
| Hallucinated advice | Stating an amount, date or denial that is not in the policy | Verdicts from the rules engine, a number and date check on replies, exact clause quotes, an indicative label | 1.4% invented denials on the benchmark. Replies that state values outside the engine's results are rejected before they are shown |

### 4.3 Risk controls

**Transaction limits.** A claim amount cap of IDR 100,000,000 per submission. At most three T2 actions and 60 tool calls per session. One T3 ticket per 24 hours. A session stops automatically after three permission denials.

**Audit log.** Every message, plan, tool call, permission decision and reply is recorded in a hash chain. Each record carries the hash of the previous record, so a change to any record is detected on verification.

**Human in the loop.** The customer confirms every submission. A person at the insurer decides every claim at the claims desk. The insurer holds a halt switch that stops every agent action for every customer.

**Data privacy.** National ID numbers, bank account numbers, card numbers, phone numbers, dates of birth and personal names are removed locally before a document is sent to the model. If any personal data remains, the model call is blocked. Customers sign in with a confirmed email, and each account's data is isolated.

**Regulatory compliance.** Every answer is marked indicative and states that the policy wording prevails. After a rejection, the agent gives the official complaint route (the insurer's complaint unit, OJK contact 157 and the financial services dispute resolution body LAPS SJK). Identity verification (KYC) for sensitive changes is done by the insurer through a separate channel. The agent does not move funds, so AML screening stays with the insurer.

This topic does not use a blockchain, so key management, signing policy and transaction simulation for Topic F do not apply.

## 5. Innovation & interaction

### 5.1 Difference from existing solutions

| Capability | Insurer chatbot | General AI chatbot | Policy comparison site | ClauseGuard |
|---|---|---|---|---|
| Reads all of a customer's policies from different insurers together | Own products only | When uploaded, with no fixed rules | No | Yes |
| Coverage verdict with the deciding clause quoted | General answers | From model memory | No | Yes, computed by the rules engine |
| Payer order across policies, including BPJS and Jasa Raharja | No | Inconsistent | No | Yes |
| Fills in the insurer's own claim form from documents | Own form | No | No | Yes |
| Files a claim with confirmation and receives the decision in the chat | Partly | No | No | Yes |
| Checks whether a rejection has grounds for appeal | No | Not verified | No | Yes, with the clause |
| Action limits enforced in code | Not relevant | None | Not relevant | Four permission tiers |

The core innovation is to treat an insurance policy as a program of rules. The language model understands the conversation and the documents. The rules engine computes what the customer is owed. Every answer can be proven with a clause.

### 5.2 Interaction design

1. **Everyday language.** Customers write in Indonesian, English or a mix, including abbreviations and typos. The agent replies in the same language.
2. **One question only.** The agent asks only when the answer would change, with quick-reply buttons.
3. **Evidence cards.** Verdicts per policy, clause quotes, payer order, claim readiness and the content of each document appear as cards. For follow-up questions the cards fold so the conversation stays short.
4. **Correctable form.** The claim form is shown before it is sent. The customer can change fields such as the hospital name or a date, and the form is rebuilt.
5. **Confirmation card.** Filing needs one Confirm tap, and the card shows the documents attached and those still missing.
6. **Proactive news.** The insurer's decision appears in the chat without being asked for, with an explanation and the next step.
7. **Autonomy mode.** The Observe, Draft and Act switch is always visible at the top of the screen.

## 6. Limitations & known risks

This list is consistent with the risk register in the Security Self-Assessment. The K numbers refer to that document.

| No. | Limitation or risk | Residual level | Current handling |
|---|---|---|---|
| K1 | The extractor is a model and can misread a value inside the schema. On the benchmark, extracted rules score 7 points below gold rules | High | Cross-checks of totals and line items, an unverified label, and the customer reviews values from documents before sending |
| K2 | Advice text can be wrong. The permission layer limits actions and does not check the correctness of advice | Medium | Verdicts from the rules engine, a number check on replies, an indicative label |
| K3 | Text drawn inside an image is not detected as hidden text (0 of 20) | Medium | Typed extractor output, untrusted labels that block T2 |
| K4 | The audit log can be rebuilt by anyone with write access to its storage | Medium | Chain verification shows changes to existing records |
| K8 | A policy uploaded by the customer can mislead verdicts if its content was manipulated | Medium | An unverified label, and it cannot trigger T2 |
| K9 | Confirmation relies on the customer reading the card | Medium | A summary with trust labels and a token per call |
| K12 | Dependence on a hosted model service and its quota | Low | Key rotation, a plain notice to the customer, and the option to use the customer's own key |
| K15 | Test sets are small and written by the team. The blind question batch for the model-free mode passed 3 of 14 | High | Every result is reported with its sample size |
| K18 | Session working memory ends when the server restarts | Low | Chat history is stored, and the customer is told and asked to restate the situation |

Other scope limitations:

- The public benchmark covers life insurance only. Indonesian products are tested on hand-verified sandbox policies.
- The rules engine covers coverage, exclusion, period, rider and termination questions. 24 of 58 benchmark scenarios (dividends, investment-linked caps, estate planning) are outside its scope.
- Amounts and payer rules for BPJS Kesehatan and Jasa Raharja are modelled from public regulation and marked to be verified with the payer. INA-CBG tariff grouping is not implemented.
- A claim that has been filed cannot be amended directly. A fixable rejection is followed by a new submission after the customer confirms.

## References

- Mridul, Kapa and Seneviratne (2026). A benchmark for gap and overlap analysis of insurance contracts. arXiv:2604.10853.
- Debenedetti et al. (2025). CaMeL: defeating prompt injections by design. arXiv:2503.18813.
- Wachter, Mittelstadt and Russell (2017). Ustun, Spangher and Liu (2019). Counterfactual explanations and algorithmic recourse.
- OWASP Top 10 for Agentic Applications (2026).
- KFF (2025). HealthCare.gov insurers denied nearly 1 in 5 in-network claims in 2023.
- OJK (2023). Claim difficulty is the most reported insurance complaint.
