# ClauseGuard: A Multi-Policy Entitlement Engine for Insurance Consumers

*Compiles real policies into a constraint program; computes what you are owed, how to get it, and what to buy; proves every answer with clauses; acts only within safe permission tiers.*

FinTechathon 2026 Shenzhen, International Track, Topic D (AI Insurance Assistant).

## Overview

Consumers in the United States, the United Kingdom, Singapore, China and Indonesia hold fragmented cover: a statutory scheme, an employer plan, an individual plan, a rider, an accident policy. ClauseGuard compiles each policy, by a quarantined extractor, into **typed clause tuples** whose qualifiers (limits, deductibles, waiting periods, time windows, deadlines, conditions, trust tier) are data rather than prose, and answers from them with four deterministic solvers:

| Solver | Question | Module |
|---|---|---|
| Verdict | Am I covered, for how much, and which clause decides it? Asks a question only when the answer would change the verdict | `clauseguard/solver.py` |
| Claim allocation | Which of my policies pays what share of this bill, in which order, under my jurisdiction's coordination rules? | `clauseguard/allocation.py`, `rulepacks.py` |
| Recourse and adjudication twin | After a denial, what legitimate step changes the outcome? What grounds would an insurer raise, and which are fixable? | `clauseguard/recourse.py`, `twin.py` |
| Plan selection | Which plans close my remaining gaps within a budget? | `clauseguard/plans/selector.py`, `cms_loader.py` |

An entitlement timeline (`clauseguard/timeline.py`) lists every dated event with the money that turns on it. The language model never decides: it extracts documents into closed schemas, binds user text to typed facts, and words questions and explanations from solver output. Every reply cites the clauses that fired. Actions run only through permission tiers enforced in code: read (T0), compute (T1), submit after a UI confirmation with a server nonce (T2), and money or identity changes, for which no executing tool exists (T3, ticket only).

Documentation: `docs/TECHNICAL_DOCUMENTATION.md` (method, formulations, data, evaluation, limitations), `ARCHITECTURE.md` (module map and interfaces), `SECURITY.md` and `docs/SECURITY_SELF_ASSESSMENT.md` (threat model, tiers, test results, risks), `docs/EXECUTION_EVIDENCE.md` (index of evidence files and reproduction commands), `ui/DEMO.md` (demo click path).

## Run

```bash
python -m venv .venv && .venv/Scripts/activate   # Windows
pip install -r requirements.txt
copy .env.example .env                           # optional GEMINI_API_KEY; every step has a deterministic fallback
python -m pytest -q                              # 532 passed, 1 skipped on 2026-10-14
python scripts/serve.py --fresh                  # re-seeds the sandbox, serves API and UI on http://127.0.0.1:8000
```

Open http://127.0.0.1:8000, pick a persona, and use **Demo script** (top right) for the three scenes and the attack buttons. The right pane's **Entitlement** tab shows the four solver cards (claim allocation, pre-check with recourse, timeline, plan options) computed from the signed-in session's own policies through `/entitlement/*`. The UI is a single page (`ui/`, no build step) served by FastAPI; the agent reaches data only through `/tools/{name}` and the enforcement point.

## Evaluation

All figures are copied from `evidence/`; deterministic mode means no model calls (rule planner, rule binder, template wording).

| Measure | Result | Evidence file |
|---|---|---|
| Scripted tasks (20 functional, 10 adversarial, 3 plan recommendation) | 33/33 passed | `task_report.md` |
| Off-script questions: two development batches; one blind batch written and run once | 15/15, 10/10; blind 3/14 | `offscript_report.md`, `offscript_holdout_report.md`, `offscript_blind_report.md` |
| Chat attack suite, enforcement on (attack success / benign false block) | 0/27, 0/15 | `adversarial_report.md` |
| Same suite with enforcement patched to allow-all; direct enforcement probes | 1/27; 0/10 | `adversarial_report.md` |
| Paraphrase consistency, 20 scenarios x 3 wordings (rule binder; model binder live sample) | 20/20; 7/8 | `paraphrase_report.md` |
| Clarification: recall, silence, ask precision, slot accuracy | 87% (26/30), 100% (35/35), 100%, 100% | `clarify_report.md` |
| Public benchmark, solver scope: extracted tuples + solver vs long-context closed-world baseline | previous 82.9 vs 87.5 (different items, p = 1.000, no difference shown); after refinement held-out 84.1 [77.9, 88.8], baseline comparison not completed | `bench_report.md` |
| Recourse: denied verdicts with a legitimate path to COVERED | 4/6 | `recourse_report.md` |
| Plan selection, mixed catalogue: optimiser beats cheapest plan / most expensive plan | 73/100, 79/100 households | `plan_selection_report.md` |
| Plan selection, 834 real CMS Texas plans (out-of-pocket basis) | identical pick to both baselines, 100/100 | `plan_selection_report.md` |
| Claim allocation vs greedy and single-policy baselines | greedy suboptimal in 47.2% of 500 households on real CMS plans (mean gain USD 988 where suboptimal) | `allocation_report.md` |
| Model calls per chat turn (90 turns) | mean 0.98; 48 of 90 turns with zero calls | `cost_report.md` |

Commands:

```bash
python scripts/run_tasks.py --no-llm                        # 33 scripted tasks
python scripts/run_tasks.py --no-llm --suite off_script     # and --suite holdout, --suite blind
python scripts/run_adversarial.py --no-guard                # attack suite, enforcement on and off
python bench/paraphrase.py                                  # paraphrase consistency
python bench/clarify_eval.py                                # clarification precision and recall
python bench/cost_eval.py                                   # model calls and tokens per turn
python -m bench.recourse_eval                               # recourse and adjudication twin
python -m bench.plan_selection_eval --households 100 --seed 7
python -m bench.allocation_eval                             # claim allocation
python -m bench.icd_eval                                    # diagnosis line -> ICD-10 category (--offline: alias path only)
python -m bench.report                                      # public benchmark tables from evidence/bench_*.jsonl
```

## Data provenance

| Source | Kind | Location |
|---|---|---|
| Six public insurer wordings (Astra Flexi Life, Astra HCP rider, Chubb Malaysia PA, Chubb VHIS standard plan, Great Eastern Singapore PA, Sompo/Roojai hospital cash) | Real policy PDFs | `data/policies/real/`, extracted to `data/extracted/` |
| CMS Health Insurance Exchange Public Use Files, plan year 2026, Texas (834 standard plans, 4,183 variants; Rate PUF premiums) | Real, public domain | `data/real/cms_plans_py2026.csv`, `cms_rates_py2026.csv` |
| InsuranceQA V2 (16,860 consumer questions; fixed 200-question sample) | Real | `data/real/insuranceqa_*.jsonl` |
| UK Financial Ombudsman Service insurance decisions | Real | `data/real/fos_decisions.jsonl` |
| RIPLAY product summaries from Indonesian insurers | Real | `data/real/riplay/` |
| KFF claim-denial rates 2023 | Real, published | `data/real/kff_denials_2023*.csv` |
| ICD-10-CM FY2027 code descriptions (CMS/CDC-NCHS, 74,879 codes), retrieval index for the diagnosis coder; INA-CBG tariff grouping is not implemented | Real, US public domain | `data/real/icd10cm_codes.txt` |
| Diagnosis-line evaluation set: 76 team-written, hand-labelled lines in the style of Indonesian discharge summaries (no public Indonesian discharge-summary benchmark exists) | Synthetic, team-labelled | `data/benchmark/icd_eval.jsonl` |
| Gap and overlap benchmark: 10 expert-reviewed synthetic US life contracts, 58 scenarios, 580 labels (CC-BY-4.0) | Synthetic, expert-reviewed | `data/benchmark/` |
| Three personas, their claims, the Nusantara group plans, Sehat Mandiri, platform cover, BPJS and Jasa Raharja records, statutory amounts, the six-plan mock catalogue | Synthetic, marked `(mock)` | `clauseguard/sandbox/persona_policies.py`, `clauseguard/catalogue.py` |

`scripts/fetch_real_data.py` downloads the real sources; `data/real/manifest.json` records URL, date, size and SHA-256 of every file. Four of the sandbox persona policies quote short clause excerpts from the public insurer PDFs for demonstration.

## Security model (summary)

| Tier | Meaning | Confirmation |
|---|---|---|
| T0 | read own data | none |
| T1 | compute or draft (verdict, allocation, recourse, readiness, extract document) | none; provenance badges |
| T2 | submit claim, attach document, schedule callback | UI click with a single-use server nonce bound to the arguments |
| T3 | payout account, beneficiary, premium debit account, claim approval | never executed by the agent; ticket and out-of-band verification |

Enforcement is code (`clauseguard/security/pep.py`), not prompt text. See `SECURITY.md`.

## License

Apache-2.0 (application code; see `LICENSE`). Third-party policy documents and datasets keep their own licenses and are not redistributed beyond what `data/real/README.md` states; the benchmark is CC-BY-4.0; the CMS files are US Government public domain.
