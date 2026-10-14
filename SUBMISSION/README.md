# ClauseGuard — submission package

FinTechathon 2026 Shenzhen, International Track, Topic D (AI Insurance Assistant).
Entry: **ClauseGuard: A Multi-Policy Entitlement Engine for Insurance Consumers** — Institut Teknologi Sepuluh Nopember, Indonesia.

## Checklist items

| # | Item | File(s) |
|---|---|---|
| 1 | Technical documentation (architecture, core algorithm, security design) | `1_Technical_Documentation.docx` — source: `../clauseguard/docs/TECHNICAL_DOCUMENTATION.md`, `../clauseguard/ARCHITECTURE.md` |
| 2 | Presentation deck (≤ 10 minutes) | `2_Presentation_Deck.pptx` — source: `../clauseguard/docs/DECK.md`, built by `../clauseguard/docs/deck/build_deck.py` |
| 3 | Demo video (≤ 5 minutes) | script: `3_Video_Script.md` (backend UI) and `../clauseguard-web/DEMO_SCRIPT.md` (web client) |
| 4 | Source code with README, repository link, deployment instructions, test cases | the repository root; archive: `python ../clauseguard/scripts/make_submission_zip.py` writes `4_Source_Code_ClauseGuard.zip` here |
| 5 | Security self-assessment (permission tiers, known risks) | `5_Security_Self_Assessment.docx` — source: `../clauseguard/docs/SECURITY_SELF_ASSESSMENT.md`, `../clauseguard/SECURITY.md` |
| 6 | Execution evidence (sandbox operation logs, demo video) | `6_Execution_Evidence_Index.docx`, `evidence/` (reports and raw runs), `../clauseguard/docs/EXECUTION_EVIDENCE.md` |

## Evidence set

| File | Shows | Reproduce |
|---|---|---|
| `evidence/task_report.md`, `task_runs.jsonl` | 33 scripted tasks in the sandbox insurer, transcripts and pass criteria | `python scripts/run_tasks.py --no-llm` |
| `evidence/offscript_report.md`, `offscript_blind_report.md`, `offscript_runs.jsonl` | off-script questions, development and blind batches | `python scripts/run_tasks.py --no-llm --suite off_script` / `--suite blind` |
| `evidence/adversarial_report.md` | chat attack suite with enforcement on and off, hidden-text detection | `python scripts/run_adversarial.py --no-guard` |
| `evidence/bench_report.md` | public benchmark: accuracy, confidence intervals, fabricated-denial rate, paired comparison | `python -m bench.run_bench`, `python -m bench.report` |
| `evidence/paraphrase_report.md`, `clarify_report.md` | decision consistency across wordings; clarification recall and precision | `python bench/paraphrase.py`, `python bench/clarify_eval.py` |
| `evidence/allocation_report.md`, `plan_selection_report.md`, `recourse_report.md` | claim allocation vs greedy, plan selection vs baselines, recourse on denials | `python -m bench.allocation_eval`, `python -m bench.plan_selection_eval`, `python -m bench.recourse_eval` |
| `evidence/extraction_quality.md`, `riplay_provenance.md` | extraction precision/recall against gold annotations; provenance of every sandbox policy wording | `python scripts/extraction_quality.py` |
| `evidence/audit_log_scripted_tasks_clean.jsonl` | hash-chained audit log of a clean scripted run | `python scripts/verify_audit.py <file>` |

All commands run from `../clauseguard/` and need no API key (deterministic mode); live-model runs are marked as such inside each report.

## Scope of claims

- Accuracy figures lead with the extracted-rules condition (84.6 %, n = 390); the 91.8 % figure is the ceiling with the benchmark's own rules and is labelled as such.
- The API-matched long-context baseline shows no significant difference on the common items; no superiority over frontier models is claimed.
- Redacted document text, never whole PDFs, is sent to a hosted model; redaction is not claimed perfect.
- Allocation gains are simulations over real plan terms, not money saved in real life.
- The three personas are synthetic; public-scheme policies (BPJS Kesehatan, Jasa Raharja) are modelled from regulation.

## Data and licences

CMS Exchange PUFs PY2026: US Government public domain. UK Financial Ombudsman decisions: Crown copyright, OGL v3. InsuranceQA: research use (Feng et al., 2015). The benchmark (CC-BY-4.0), insurer PDFs and RIPLAY documents are fetched by `scripts/fetch_real_data.py` with URL, date and hash recorded in `data/real/manifest.json`; none is redistributed in this package.
