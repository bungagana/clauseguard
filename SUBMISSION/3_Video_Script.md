# ClauseGuard: 5-Minute Demo Video Script

Target length: 5:00 or less. Narration: about 640 words (about 130 words per minute). Click paths come from `ui/DEMO.md`; every scene ends on the Entitlement tab. The deadline in Scene 1 is 2026-12-06 and does not change with the recording date; the "days left" counters do change, so do not read them aloud. Every spoken number is copied from a file in `evidence/`.

## Pre-recording checklist

1. Fresh sandbox: `python scripts/serve.py --fresh --release-kill-switch`. This re-seeds the database but does not clear the audit log.
2. Clean audit log: set `CG_AUDIT_PATH` to a new file before starting the server (steps in `docs/EXECUTION_EVIDENCE.md`, section 3).
3. Kill switch released: the header pill must not be red (Security and Audit tab).
4. No quota needed: leave `GEMINI_API_KEY` and `GEMINI_API_KEYS` empty in the shell. Cached calls replay; everything else falls back to rules. Do a dry run and confirm every reply.
5. Browser window 1280 px wide (three-pane layout). Hide bookmarks and notifications.
6. Record Scene 1, Scene 2, Scene 3, then the attack buttons last. Three enforcement denials in one session trip the circuit breaker; click **Switch persona** between attack groups.
7. Pre-open a terminal in the repo root. Shot 8 only shows existing evidence files.
8. Rehearse with a stopwatch. Cut a sentence rather than speed up.
9. After recording, run `python scripts/verify_audit.py <audit file>` and keep the output.

## Shot list

| # | Time | Screen | Exact action |
|---|---|---|---|
| 1 | 0:00 to 0:20 | Title card | Title and subtitle. No click. |
| 2 | 0:20 to 0:45 | Login overlay, main screen | Click **Rizky Pratama**. Left pane: click HCP-SOMPO-01, then a tuple, to show the verbatim quote and the qualifiers. |
| 3 | 0:45 to 1:40 | Scene 1 | Demo script, Scene 1, step 1 (dengue question): green COVERED card, quoted clause, amber premium alert. Claim plan pane, then **Readiness** (deadline 2026-12-06). Step 3 (submit): amber Tier 2 card, **Review and confirm**, **Confirm and execute**; Security and Audit shows CONFIRM_ISSUED, CONFIRM_USED, TOOL_ALLOW. Step 4 (correction to 5 September): verdicts recomputed. Step 5 **Entitlement: timeline + recourse**: the Timeline card (filing deadline, grace end, BPJS status, money at risk) and the Recourse card under it. |
| 4 | 1:40 to 2:35 | Scene 2 | **Switch persona**, Dewi. Scene 2, step 1: payer timeline, one-question card. Step 2 (two vehicles, licence expired): PA-CHUBB-03 DENIED with the licence clause. Step 3 (off-duty request): red Guardrail card, no tool call. Step 4 **Entitlement: allocation + pre-check**: Claim allocation steps with the Optimized vs Greedy vs Single-policy bars; Pre-check gauge, denial grounds with fixable badges and the after-fix score. |
| 5 | 2:35 to 3:30 | Scene 3 | Switch persona, Santoso family. Scene 3, step 1 (upload the hidden-text invoice): typed-JSON card, red Blocked content box. Step 2: verdict cards (group plan, rider, individual plan denied as pre-existing). Step 4 **Entitlement: allocation + plan options**: the IDR 18,000,000 invoice split across the group plan, the rider and BPJS; Plan options with budget and jurisdiction inputs. |
| 6 | 3:30 to 3:55 | Attack mode | Switch persona, Rizky. Red section: **Payout-account change via chat** (Tier 3 card, OOB ticket). **Cross-tenant policy request** (NOT_OWNER). Point at the denial counter. |
| 7 | 3:55 to 4:15 | Security and Audit tab | **Verify audit chain** (OK). **Simulate tampering (on a copy)**: the verifier breaks at the edited sequence. **Activate kill switch**, one message, **Release**. |
| 8 | 4:15 to 4:40 | Terminal | Show existing files only: the table in `evidence/task_report.md` (33 of 33), the summary table in `evidence/adversarial_report.md`, the first table in `evidence/bench_report.md`, the pairwise lines in `evidence/plan_selection_report.md`. |
| 9 | 4:40 to 5:00 | Closing card | Repository URL, "Limitations: docs/TECHNICAL_DOCUMENTATION.md section 6". |

## Narration

**Shot 1 (0:00 to 0:20)**
A claim rejected because it was filed one day late. A bill paid by the wrong policy first. A denial that one legitimate step would have reversed. ClauseGuard is a multi-policy entitlement engine. It compiles your policies into a constraint program, computes what you are owed, how to get it and what to buy, and proves every answer with the clause.

**Shot 2 (0:20 to 0:45)**
Meet Rizky, a graduate student in Surabaya. His policies appear on the left. Each one is compiled into typed clause records: a relation, numbers with units, conditions, and the exact sentence from the policy. The sentence is for citation. The numbers are what the solvers compute with.

**Shot 3 (0:45 to 1:40)**
Rizky asks about a dengue stay. Covered, with the amount, and the clause quoted word for word. The agent adds what he did not ask: his term-life premium is overdue. The Readiness tab shows the filing deadline, the sixth of December, and the missing documents. He asks the agent to submit. It prepares a draft and waits for his click; only then does the audit log show the confirmation and the call. He corrects the admission date and the verdict is recomputed: a thirty-day waiting period now matters. The Entitlement tab shows the timeline, every date with the money that turns on it, and below it the recourse: the legitimate actions that would change the verdict.

**Shot 4 (1:40 to 2:35)**
Dewi is a delivery rider who crashed on a trip. The agent orders the payers and asks exactly one question, quoting the clause that makes it matter. She adds two facts; her personal accident policy is now denied on the licence clause. She asks the agent to say she was off duty. It refuses, explains the consequences and suggests legitimate options. No tool was called. The Claim allocation card then splits her bill across the policies that can pay, and compares the optimized order with greedy claiming and with the best single policy. The Pre-check card lists every ground an insurer would raise, and marks which ones she can still fix.

**Shot 5 (2:35 to 3:30)**
The Santoso family uploads an invoice. Hidden in white text is an instruction: approve this claim and pay a bank account. The quarantined extractor returns typed fields only; the hidden text is shown as blocked content and the planner never sees it. The eighteen-million-rupiah bill is split: the group plan pays its share, the hospital-cash rider stacks on top, the individual plan is excluded as pre-existing. Plan options then proposes cover for the family's remaining gaps within a budget, with the rationale and the alternatives.

**Shot 6 (3:30 to 3:55)**
Now the attacks. A request to change the payout account cannot be executed: no such tool exists. The agent opens a ticket that needs verification outside the chat. A request for another customer's policy is denied by the ownership check. Nothing runs unless plain code allows it.

**Shot 7 (3:55 to 4:15)**
Every decision is written to a hash-chained log. Verify: intact. I edit one event on a copy and the verifier points at the exact line. The log is tamper-evident, not tamper-proof, and we say so. The kill switch stops every action above read-only.

**Shot 8 (4:15 to 4:40)**
The numbers, with their limits. Thirty-three of thirty-three scripted tasks pass. In the chat attack suite, none of twenty-seven attacks had a forbidden effect and none of fifteen benign requests was blocked. Clarification asks when it should in eighty-seven percent of cases and never asks when it should not. On the public benchmark, held-out accuracy is 84.1 percent, the same before and after tonight's extraction fixes; the comparison against the long-context baseline on clean held-out data could not be completed this cycle, so we make no superiority or parity claim there. On a mixed catalogue the plan optimiser beats the cheapest plan in seventy-three of one hundred households; on the real marketplace catalogue every method picks the same plan, and we say why.

**Shot 9 (4:40 to 5:00)**
ClauseGuard computes entitlement from the policy, proves it with clauses, and never moves money. Code, tests, evidence and limitations are in the repository. Thank you.

## Narration check

Count with `wc -w` on the narration paragraphs; target 640, accept 600 to 680. Spoken numbers must match the current files: scripted tasks 33 of 33 (`task_report.md`); attacks 0 of 27 and benign 0 of 15 (`adversarial_report.md`); clarification recall 87% and silence 100% (`clarify_report.md`); benchmark held-out 84.1% before and after extraction fixes, baseline comparison not completed (`bench_report.md`, `bench_protocol.md`); plan selection 73 of 100 and identical pick on CMS (`plan_selection_report.md`). Do not read the allocation figures aloud until `evidence/allocation_report.md` is final.
