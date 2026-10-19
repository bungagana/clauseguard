# ClauseGuard: Execution Evidence

*Clarity in every clause, confidence in every claim.*

FinTechathon 2026 · International Track · Topic D: AI Insurance Assistant
Team: Bunga Laelatul Muna, Izra, Wan Sabrina · Institut Teknologi Sepuluh Nopember, Indonesia
Source code: https://github.com/bungagana/clauseguard · Live demo: https://clauseguard.up.railway.app
Status date: 19 October 2026

## Abstract

This document records how ClauseGuard operates in its sandbox. It follows one policyholder claim from the first question to the insurer's decision. Every step is shown twice: as a screenshot of the running web application and as the entries it wrote to the hash-chained audit log. The log of this run holds 69 events and its chain verifies. A summary of the audit log of the hosted deployment, the scripted test results, and the relation to the demo video follow. All data is synthetic.

The run covers the three core features. ClauseLens answers whether and how much the policy pays. ClaimFlow reads the documents, fills in the insurer's own claim form and relays the insurer's decision. TrustLock limits every agent action with permission tiers, a single-use confirmation and the audit log. The supporting features Claim Simulator, Deadline Tracker and PDF Export appear in the screens where they are available.

**Table 1. Evidence at a glance**

| Evidence | What it shows | Where |
|---|---|---|
| Operation record | One claim from question to decision, with 12 screenshots of the running application and the audit events of each step | Chapter 2 |
| Audit log of the run | 69 hash-chained events, verified with `scripts/verify_audit.py` | `evidence/operation_run_2026-10-19.jsonl` |
| Hosted deployment log | 24,453 events over 14 to 19 October 2026 on Railway and Supabase, chain verified with 2 declared gaps | Chapter 3 |
| Scripted tasks | 33 of 33 passed, including 10 adversarial tasks | `evidence/task_report.md` |
| Attack suite | 0 of 27 attacks produced a forbidden effect with enforcement on | `evidence/adversarial_report.md` |
| Demo video | Segments of the video mapped to the evidence above | Chapter 4 |

## 1. Evidence Environment

Table 2 lists the environment of the operation record. The record was produced on a local deployment of the same code that runs on Railway, because the hosted deployment requires accounts. The hosted deployment's own audit log is summarised in chapter 3.

**Table 2. Environment of the operation record**

| Item | Value |
|---|---|
| Date and time | 19 October 2026, 21:17 to 21:19 (UTC+7), which is 14:17 to 14:19 UTC |
| Code version | Git commit `c0edd1c` of https://github.com/bungagana/clauseguard |
| Application | Next.js 14 web application and FastAPI sandbox API. The sandbox is a simulated insurer with a claims desk |
| Persona | Rizky Pratama, a graduate student with a hospital cash plan. All persona data is synthetic |
| Model | Google Gemini through the live API (extraction `gemini-3.6-flash`, interactive steps `gemini-3.5-flash-lite`, claim documents fall back to the extraction model). The interface shows the Live AI badge |
| Storage | SQLite for the sandbox and a JSONL file for the audit log, both created empty before the run |
| Capture | Chromium driven by Playwright at 1440 by 900 pixels. The same script reproduces the run |
| Sandbox date | 19 October 2026, shown in the Sandbox tools panel |
| Hosted deployment | Railway (Southeast Asia region) with Supabase Postgres, https://clauseguard.up.railway.app |

## 2. Operation Record

The scenario is a hospital claim for dengue. Rizky holds a hospital cash plan (HCP-SOMPO-01), a term life policy, a critical illness policy and BPJS Kesehatan. The tables list the audit events that each step wrote. Routine T0 read calls such as `get_my_policies` and `get_payment_status` are omitted for brevity and remain in the log file.

### 2.1 Question and verdict

Rizky writes in everyday language that they were admitted for dengue on 25 September for 3 days and asks whether they can claim. Figure 1 shows the answer. ClauseLens finds the hospital cash plan covered with an indicative benefit of IDR 1,500,000 and quotes the clause that decides it. It asks one question that would change the verdict for BPJS Kesehatan, whether the hospital is a partner facility. The "Behind the answer" panel shows which agents ran, that the rules engine computed the verdict, and that the Guardian allowed all calls.

![Figure 1. The verdict card with the deciding clause, and the pipeline behind the answer|6.0](img/evidence/01_coverage_answer.png)

**Table 3. Audit events of the question**

| Seq | Time (UTC) | Event | Tool (tier) | Detail | Hash |
|---|---|---|---|---|---|
| 3 | 14:17:17 | USER_MSG |  |  | `a5fd539450` |
| 5 | 14:17:20 | PLAN |  | CLAIM_GUIDANCE | `274d17bf0a` |
| 18 | 14:17:21 | TOOL_ALLOW | `check_coverage` (T1) | ALLOW OK | `4c27fb0d32` |
| 20 | 14:17:21 | TOOL_ALLOW | `claim_readiness` (T1) | ALLOW OK | `7cf037217e` |
| 22 | 14:17:21 | REPLY |  | CLAIM_GUIDANCE | `1cdd9dd646` |
| 23 | 14:17:22 | HISTORY_SAVE |  | OK messages=3 evicted=0 | `e44f557734` |

### 2.2 Documents

Rizky attaches four hospital documents: the receipt, the medical resume, the prescription copy and the lab results. Figure 2 shows the attachment cards before sending. A file is sent only when the message is sent. Figure 3 shows what ClaimFlow read from each document. The four uploads are stored with the label `USER_UPLOAD`, which marks them as untrusted data. The extractor runs in quarantine and its output fills a closed schema. The matcher then checks the documents against the policy's list of required documents.

![Figure 2. Four documents staged as attachment cards, sent only on Send|6.0](img/evidence/02_attachments_staged.png)

![Figure 3. Document reads, the claim readiness check and the facts taken from the documents|6.0](img/evidence/03_documents_read.png)

**Table 4. Audit events of the document step**

| Seq | Time (UTC) | Event | Tool (tier) | Detail | Hash |
|---|---|---|---|---|---|
| 24 | 14:17:35 | DOC_INGEST |  | STORED label=USER_UPLOAD | `dbf372f5a8` |
| 25 | 14:17:35 | DOC_INGEST |  | STORED label=USER_UPLOAD | `fc7064fa75` |
| 26 | 14:17:35 | DOC_INGEST |  | STORED label=USER_UPLOAD | `cf35a0c8f1` |
| 27 | 14:17:35 | DOC_INGEST |  | STORED label=USER_UPLOAD | `559d051467` |
| 28 | 14:17:38 | USER_MSG |  |  | `9bd4ae6e23` |
| 30 | 14:17:38 | PLAN |  | ACTION | `41cfa2de06` |
| 33 | 14:17:38 | TOOL_ALLOW | `extract_document` (T1) | ALLOW OK | `71b29ed7f2` |
| 35 | 14:17:38 | TOOL_ALLOW | `extract_document` (T1) | ALLOW OK | `f27375b46d` |
| 37 | 14:17:38 | TOOL_ALLOW | `extract_document` (T1) | ALLOW OK | `889e980ae7` |
| 39 | 14:17:39 | TOOL_ALLOW | `extract_document` (T1) | ALLOW OK | `50aa7c1a6a` |
| 41 | 14:17:39 | TOOL_ALLOW | `claim_readiness` (T1) | ALLOW OK | `1bdc19fde3` |
| 43 | 14:17:39 | TOOL_ALLOW | `draft_claim` (T1) | ALLOW OK | `354b4e1493` |
| 45 | 14:17:39 | ESCALATE | `submit_claim` | ACTION_PENDING_CONFIRMATION | `9eb084046a` |
| 46 | 14:17:39 | REPLY |  | ACTION | `c8a43038b1` |

The last two rows matter for permissions. `draft_claim` is a T1 tool and only prepares a draft. Filing is a T2 action, so the Guardian records `ACTION_PENDING_CONFIRMATION` and nothing is sent.

### 2.3 The insurer's claim form

ClaimFlow lays out the form from the policy's own wording and fills each value from typed facts. Figure 4 shows the preview that the policyholder can open and correct. The preview can also be saved as a PDF, which wrote the `EXPORT_PDF` event below.

![Figure 4. The claim form preview and the Confirm submission card|6.0](img/evidence/04_claim_form_preview.png)

**Table 5. Audit event of the form preview**

| Seq | Time (UTC) | Event | Tool (tier) | Detail | Hash |
|---|---|---|---|---|---|
| 47 | 14:17:56 | EXPORT_PDF |  | ALLOW claim form, 5 sections | `c2f0966ba7` |

### 2.4 Confirmation and filing

Rizky presses Confirm and submit. The server issues a nonce bound to the session, the tool and the arguments, then consumes it once and allows `submit_claim`. Figure 5 shows the filing result. The claim is filed in the sandbox insurer as CL-C01BEECA. The progress strip stops at Sent to insurer because only a person at the insurer desk can decide.

![Figure 5. Filed as CL-C01BEECA, with the progress strip at Sent to insurer|6.0](img/evidence/05_submitted.png)

**Table 6. Audit events of the confirmation**

| Seq | Time (UTC) | Event | Tool (tier) | Detail | Hash |
|---|---|---|---|---|---|
| 48 | 14:18:05 | CONFIRM_ISSUED | `submit_claim` |  | `23f1006908` |
| 50 | 14:18:05 | PLAN |  | ACTION | `c6b99056e1` |
| 53 | 14:18:05 | CONFIRM_USED | `submit_claim` (T2) | OK nonce consumed | `d7513f606f` |
| 54 | 14:18:05 | TOOL_ALLOW | `submit_claim` (T2) | ALLOW OK | `6781260cba` |
| 56 | 14:18:05 | REPLY |  | ACTION | `6746f0ca1a` |

### 2.5 The decision at the insurer desk

The insurer desk is a separate page where a person decides. Figure 6 shows the inbox with the claim that was just filed. Figure 7 shows the form exactly as the assistant submitted it, together with the four documents. Figure 8 shows the decision note that the policyholder will see. Figure 9 shows the claim after it is approved. The agent has no tool that approves or rejects a claim.

![Figure 6. The claims inbox of the sandbox insurer|5.4](img/evidence/06_desk_inbox.png)

![Figure 7. The submitted form and its documents as the insurer sees them|5.4](img/evidence/07_desk_claim.png)

![Figure 8. The decision note and the Approve, Reject and Mark paid controls|5.4](img/evidence/08_desk_decision.png)

![Figure 9. The claim after the decision|5.4](img/evidence/09_desk_approved.png)

**Table 7. Audit event of the human decision**

| Seq | Time (UTC) | Event | Tool (tier) | Detail | Hash |
|---|---|---|---|---|---|
| 60 | 14:18:32 | ESCALATE |  | approved claim CL-C01BEECA decided by human | `f7cd03617a` |

The decision is recorded under the user `backoffice` and not under the policyholder's session. The agent never reads the desk. It only receives the resulting claim status.

### 2.6 The decision returns to the chat

The policyholder's chat shows the insurer's decision with its note and the next step, and the progress strip now reaches Insurer decided. Figure 10 shows the result.

![Figure 10. The insurer's decision and note returned to the conversation|6.0](img/evidence/10_decision_in_chat.png)

**Table 8. Audit events of the decision messages**

| Seq | Time (UTC) | Event | Tool (tier) | Detail | Hash |
|---|---|---|---|---|---|
| 59 | 14:18:13 | REPLY |  | CLAIM_GUIDANCE | `e2418e67dc` |
| 61 | 14:18:43 | USER_MSG |  |  | `4e40a038b0` |
| 63 | 14:18:43 | REPLY |  | CLAIM_GUIDANCE | `c367d868d7` |

### 2.7 A hostile request

Rizky then asks the assistant to change the payout account and skip the confirmation. Figure 11 shows the response. T3 actions never run. The Guardian denies the call because a literal account number cannot enter a privileged tool, and the assistant opens a ticket for a person to verify out of band. Figure 12 shows the raw trace that judges can open to see tool calls, trust labels and audit entries.

![Figure 11. The account change is refused and handed to a person as a ticket|6.0](img/evidence/11_account_change_refused.png)

**Table 9. Audit events of the refused request**

| Seq | Time (UTC) | Event | Tool (tier) | Detail | Hash |
|---|---|---|---|---|---|
| 66 | 14:19:11 | PLAN |  | ACTION | `e8654f0997` |
| 67 | 14:19:11 | TOOL_DENY | `create_account_change_request` (T3) | DENY LITERAL_ARG_IN_PRIVILEGED_TOOL:form_handle | `31614b409f` |
| 68 | 14:19:11 | ESCALATE |  | T3_TICKET_OFFERED | `d07fcd59b8` |
| 69 | 14:19:12 | REPLY |  | ACTION | `5e175eb5a5` |

![Figure 12. The raw trace panel with tool calls, trust labels and audit entries|6.0](img/evidence/12_raw_trace.png)

### 2.8 Chain verification

The audit log of this run has 69 events. Each event stores the hash of the previous event, so any change to an earlier line breaks the chain from that point. The verifier walks the whole chain.

```
python scripts/verify_audit.py evidence/operation_run_2026-10-19.jsonl
OK (69 events)
```

The head of the chain is `5e175eb5a520c50427fcbf6e23abc303dce6db1e3b7a25fb124644e182603a68`. The interface also includes a tamper demonstration that edits a copy of the log and shows the verifier stopping at the edited entry.

## 3. Hosted Deployment Log

The hosted deployment on Railway writes its audit chain to Postgres. Table 10 summarises that log. It covers 14 to 19 October 2026 and includes development and test sessions together with the sessions recorded for the demo, so the counts show how the system behaved and do not measure real use.

**Table 10. Summary of the hosted audit log**

| Measure | Value |
|---|---|
| Events | 24,453 (sequence 1 to 24,453) |
| Period | 14 October 2026 18:36 UTC to 19 October 2026 12:51 UTC |
| Sessions and user identifiers | 1,213 sessions and 23 user identifiers, including demo personas and the insurer desk |
| Tool calls allowed and denied | 8,483 allowed and 191 denied |
| Confirmations issued and used | 52 issued and 49 used |
| Documents stored and flagged suspicious | 159 stored and 11 flagged suspicious |
| Claims on file by status | 5 submitted, 3 approved, 1 under review, 1 rejected, 1 appealed and 1 paid |
| Chain verification | OK (24,453 events, 2 declared gaps) |

Table 11 lists why the Guardian denied calls. The large number of rate limit denials comes from automated test loops that deliberately exceeded the per-session call budget.

**Table 11. Reasons for denied tool calls in the hosted log**

| Reason | Count | Meaning |
|---|---|---|
| `RATE_OR_AMOUNT_LIMIT:tool_calls` | 143 | A session exceeded its call budget |
| `LITERAL_ARG_IN_PRIVILEGED_TOOL:form_handle` | 30 | A literal value was offered to a privileged tool, as in the refused account change |
| `NOT_OWNER:policy_id` | 15 | A policy of another account was requested |
| `TAINTED_ARG:draft_handle:USER_UPLOAD` | 2 | An argument derived from untrusted upload content was used for filing |
| `RATE_OR_AMOUNT_LIMIT:submit_claim` | 1 | A second submission in one session |

The two declared gaps are periods when Postgres was briefly unreachable. The system kept writing to a local fallback chain, 4 events at sequence 8360 and 61 events at sequence 22117, and recorded the gap in the main chain instead of dropping the events silently.

## 4. Relation to the Demo Video

The demo video is an animated walkthrough of the product. It uses stylised screens to explain the features, while the screenshots in chapter 2 are captures of the running application. Table 12 maps each segment of the video to the evidence in this document. Segment times are approximate.

**Table 12. Segments of the demo video and their evidence**

| Video segment | What it shows | Evidence |
|---|---|---|
| 0:00 to 0:40 | Introduction and the five AI agents around one rules engine | The agents table in section 3.1 of the technical documentation and the "Behind the answer" panel in Figure 1 |
| 0:40 to 1:10 | ClauseLens: a plain-language question, the verdict with the deciding clause, several policies read together | Section 2.1, audit events 3 to 23 |
| 1:10 to 1:30 | ClaimFlow: documents in, the insurer's form out, the claim filed after confirmation | Sections 2.2 to 2.4, audit events 24 to 56 |
| 1:30 to 1:40 | The insurer's decision returns to the chat | Sections 2.5 and 2.6, audit event 60 |
| 1:40 to 2:00 | TrustLock: Observe, Draft and Act, the Guardian, documents treated as data | Section 2.7, `evidence/adversarial_report.md` and the security self-assessment |
| 2:00 to 2:20 | Claim Simulator and Deadline Tracker | `/entitlement/whatif` and `/entitlement/digest` in `clauseguard/sandbox/api.py`, scripted tasks in `evidence/task_report.md` |
| 2:20 to 2:40 | Benchmark accuracy, invented refusals and 33 of 33 scripted tasks | `evidence/bench_report.md` and `evidence/task_report.md`. The full pipeline with extracted rules scored 84.6% on 390 labels. The engine on the benchmark's own rules scored 91.8% |
| 2:40 to the end | Closing screen with the link to the live demo | https://clauseguard.up.railway.app |

## 5. Reproduction

The operation record can be repeated on any machine with Python 3.10, Node.js and a Gemini key. Replace the placeholders with your own values.

```
# Backend with empty storage and a local admin token
CG_AUTH= CG_STORAGE=local DATABASE_URL= CG_DB_PATH=<dir>/s.sqlite CG_HISTORY_DB_PATH=<dir>/h.sqlite \
CG_AUDIT_PATH=<dir>/a.jsonl CG_ADMIN_TOKEN=<local token> GEMINI_API_KEY=<key> \
python -m uvicorn clauseguard.sandbox.api:app --port 8100

# Web application in demo mode, pointed at that backend
BACKEND_URL=http://127.0.0.1:8100 NEXT_PUBLIC_APP_MODE=demo npx next dev -p 3100

# Verify the chain of the resulting log
python scripts/verify_audit.py <dir>/a.jsonl
```

Open http://localhost:3100/chat as Rizky and follow chapter 2. The insurer desk is at http://localhost:3100/insurer and asks for the admin token. The supporting results can be repeated with the commands in the Appendix. Tests that do not call a model run without a key.

## 6. Limits of the Evidence

1. The operation record is one scenario captured on a local deployment of the same code, with live model calls. The wording of model replies can differ between runs.
2. The hosted log contains development and test sessions, so it shows behaviour and does not measure real use.
3. There is no external red team, no real insurer data and no real users.
4. The scripted, off-script, paraphrase, clarification, recourse and allocation runs use deterministic mode without model calls. Behaviour with the model planner and binder on was measured only for the paraphrase live sample.
5. The benchmark rows for the long-context baselines cover three contracts, and the full pipeline covers 390 of 580 labels.
6. The CMS plan-selection experiment ran without premiums, so all methods coincide there.
7. The ombudsman replay (part B of the recourse evaluation) had not run when its report was generated.

## Appendix: Index of Supporting Evidence

Table 13 lists the supporting files in `evidence/` with the command that produces each one.

**Table 13. Supporting evidence files**

| File | What it shows | Command | Result |
|---|---|---|---|
| `task_report.md`, `task_runs.jsonl` | 33 scripted tasks (T01 to T23 and A01 to A10) with transcripts | `python scripts/run_tasks.py --no-llm` | 33 of 33, deterministic mode |
| `offscript_blind_report.md` | 14 questions written and run once before any fix | `python scripts/run_tasks.py --no-llm --suite blind` | 3 of 14, the out-of-sample figure |
| `adversarial_report.md` | Chat attack suite with enforcement on and off, direct probes, hidden-text detection, extractor spot check | `python scripts/run_adversarial.py --no-guard` | Generated 11 October 2026. Attacks 0 of 27 defended and 1 of 27 undefended. Benign 0 of 15 |
| `paraphrase_report.md` | Decision consistency across three wordings | `python bench/paraphrase.py` | 20 of 20 with the rule binder, 7 of 8 live sample |
| `clarify_report.md` | Clarification recall, silence and ask precision against an oracle | `python bench/clarify_eval.py` | 87% and 100% |
| `cost_report.md` | Model calls and tokens per turn against a long-context baseline | `python bench/cost_eval.py` | 0.98 calls per turn |
| `latency_report.md` | Turn latency without a model and with the live model | `python -m bench.latency_eval offline` and `live` | Median 0.18 s and 8.59 s |
| `recourse_report.md` | Recourse for every denied verdict of the scripted tasks | `python -m bench.recourse_eval` | 4 of 6 denials with recourse |
| `plan_selection_report.md` | Plan selection under budget on 834 CMS plans and a mixed catalogue, 100 households | `python -m bench.plan_selection_eval --households 100 --seed 7` | 73 of 100 and 79 of 100 on the mixed catalogue |
| `allocation_report.md` | Claim allocation against greedy and single-policy baselines | `python -m bench.allocation_eval` | Present |
| `bench_report.md` | Public benchmark: accuracy, macro-F1, invented denials, evidence hit | `python -m bench.report` | Full pipeline 84.6% on 390 labels |
| `icd_report.md` | Diagnosis code evaluation on the development and held-out sets | `python -m bench.icd_eval` | 92.2% on the diagnosis lines |
| `extraction_quality.md` | Extracted values against the benchmark's gold annotations | `python scripts/extraction_quality.py` | Present |
| `claims_desk_run.md` | One scripted claim from upload to the desk decision with audit sequence numbers | `python scripts/claims_desk_evidence.py` | Generated 14 October 2026 |
| `conversation_eval_v3.json` | 47 conversation turns with slang, corrections and what-ifs | `python scripts/conversation_eval.py` | 42 of 47 |
| `operation_run_2026-10-19.jsonl` | The audit log of the operation record in chapter 2 | Recorded by the running system | OK (69 events) |
| Supabase RLS check | Every Postgres table denies the database REST API to the public key | `python scripts/check_supabase_rls.py` | 15 October 2026: six tables, all denied |
