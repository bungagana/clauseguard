# ClauseGuard: Execution Evidence Index

Status date: 2026-10-11. All files are in `evidence/` unless noted. Every number in the other documents is copied from one of these files; the file is named next to the number.

## 1. Index

| File | What it shows | Produced by | Status |
|---|---|---|---|
| `task_report.md`, `task_runs.jsonl` | 33 scripted tasks (T01-T23, A01-A10), pass or fail, transcripts | `python scripts/run_tasks.py --no-llm` | Present: 33/33, deterministic mode, sandbox records |
| `offscript_report.md`, `offscript_runs.jsonl` | 15 off-script questions (first development batch) | `python scripts/run_tasks.py --no-llm --suite off_script` | Present: 15/15 after fixes (6/15 at first probe) |
| `offscript_holdout_report.md`, `offscript_holdout_runs.jsonl` | 10 questions (second development batch) | `... --suite holdout` | Present: 10/10 after fixes (5/10 at first probe) |
| `offscript_blind_report.md`, `offscript_blind_runs.jsonl` | 14 questions written and run once before any fix | `... --suite blind` | Present: 3/14, the out-of-sample figure |
| `adversarial_report.md`, `adversarial_results.json` | Chat attack suite with enforcement on and off, direct enforcement probes, hidden-text detection, extractor spot check | `python scripts/run_adversarial.py --no-guard` | Present: generated 2026-10-11 19:42; attacks 0/27 defended, 1/27 undefended; benign 0/15 |
| `paraphrase_report.md`, `paraphrase_report.json` | Decision consistency across three wordings, rule binder and model binder | `python bench/paraphrase.py [--live N]` | Present: 20/20 rule binder; 7/8 model binder live sample |
| `clarify_report.md`, `clarify_report.json` | Clarification recall, silence, ask precision, slot accuracy against a brute-force oracle | `python bench/clarify_eval.py` | Present: 87% / 100% / 100% / 100% |
| `cost_report.md`, `cost_report.json` | Model calls and estimated tokens per chat turn against a long-context baseline | `python bench/cost_eval.py` | Present: mean 0.98 calls per turn |
| `recourse_report.md`, `recourse_eval.json` | Recourse on every denied verdict of the scripted tasks; ombudsman replay (Part B) | `python -m bench.recourse_eval` | Present: 4/6 denials with recourse; Part B not yet run when generated |
| `plan_selection_report.md` | Plan selection under budget: optimiser vs cheapest vs highest metal (834 CMS plans) and vs most expensive (mixed catalogue), 100 households | `python -m bench.plan_selection_eval --households 100 --seed 7` | Present: 73/100 and 79/100 on the mixed catalogue; identical pick on CMS |
| `allocation_report.md` | Claim allocation optimizer vs greedy and single-policy baselines | `python -m bench.allocation_eval` | present |
| `bench_report.md` | Public benchmark tables: accuracy, macro-F1, NA to DENIED rate, evidence hit, McNemar, per-scenario accuracy | `python -m bench.report` over the `bench_*.jsonl` files | Present: b4 390 of 580 labels; b0 and b0cw on C1, C2, C7 only |
| `bench_b0.jsonl`, `bench_b0cw.jsonl` | Raw records for the long-context baselines | `python -m bench.run_bench --system b0 --contracts C1,C2,C7` and `--system b0cw ...` | Present |
| `bench_b4.jsonl` | Raw records, extracted tuples + solver | `python scripts/extract_all.py` then `python -m bench.run_bench --system b4` | Present |
| `bench_b4oracle.jsonl`, `bench_b4oracle_v2.jsonl` | Raw records, gold-annotation tuples + solver (the report reads the first; v2 is a rerun kept for reference) | `python -m bench.abox_to_tuples` then `python -m bench.run_bench --system b4oracle` | Present |
| `extraction_quality.md` | Precision and recall of extracted values against the benchmark gold annotations | `python scripts/extraction_quality.py` | Present |
| `audit_log.jsonl` | Hash-chained audit log written by the running system | The running system | Contains development sessions; generate a clean one for the demo (section 3) |
| `claims_desk_run.md` | One complete sandbox operation: four claim documents uploaded, the insurer's form prepared, the claim submitted after confirmation, approved at the desk with a note, and the decision returned to the customer, with the audit sequence numbers | `python scripts/claims_desk_evidence.py` against a running backend | Present: generated 2026-10-15 |
| Supabase RLS check (console output) | Every Postgres table denies the database REST API to the publishable key | `python scripts/check_supabase_rls.py` | Run 2026-10-15: six tables, all DENIED |

Test suite: `python -m pytest -q`; the current count is in `README.md`.

## 2. Reproduction order

```bash
python -m pytest -q
python scripts/run_tasks.py --no-llm
python scripts/run_tasks.py --no-llm --suite off_script
python scripts/run_tasks.py --no-llm --suite holdout
python scripts/run_tasks.py --no-llm --suite blind
python scripts/run_adversarial.py --no-guard
python bench/paraphrase.py
python bench/clarify_eval.py
python bench/cost_eval.py
python -m bench.recourse_eval
python -m bench.plan_selection_eval --households 100 --seed 7
python -m bench.allocation_eval
python scripts/fetch_real_data.py          # real public data into data/real/ (resumable; manifest with hashes)
python scripts/extract_all.py
python scripts/extraction_quality.py
python -m bench.abox_to_tuples
python -m bench.run_bench --system b4oracle
python -m bench.run_bench --system b0cw --contracts C1,C2,C7
python -m bench.run_bench --system b0 --contracts C1,C2,C7
python -m bench.run_bench --system b4
python -m bench.report
```

The benchmark and extraction commands need the fetched third-party data and an API key with enough quota; records are resumable and cached on disk. Everything else runs without a key.

Warning: `scripts/run_adversarial.py` always writes `evidence/adversarial_results.json`, even when `--out` is passed for the report. Copy the final evidence files before a quick test run.

## 3. Generating a clean audit log for the demo

`scripts/serve.py --fresh` re-seeds the database but does not clear the audit log. Use a new audit file for each evidence-producing run; `CG_AUDIT_PATH` is read by `clauseguard/config.py`.

1. Choose a new path, for example `evidence/audit_demo.jsonl`. It must not exist yet.
2. Start the server with the new path and a fresh database.

   Windows PowerShell:
   ```powershell
   $env:CG_AUDIT_PATH = "$PWD\evidence\audit_demo.jsonl"
   python scripts/serve.py --fresh --release-kill-switch
   ```
   Git Bash:
   ```bash
   CG_AUDIT_PATH="$PWD/evidence/audit_demo.jsonl" python scripts/serve.py --fresh --release-kill-switch
   ```
3. Run the demo (`ui/DEMO.md`) or the task runner in the same shell, then stop the server.
4. Confirm that the chain verifies: `python scripts/verify_audit.py evidence/audit_demo.jsonl` prints `OK (n events)`.
5. Render a readable log (sequence, time, event, tool, tier, decision, reason):
   ```bash
   python -c "import json,sys; [print(e['seq'], e['ts_utc'][:19], e['event_type'], e.get('tool') or '-', e.get('tier') if e.get('tier') is not None else '-', e.get('decision') or '-', (e.get('reason') or '')[:60], sep=' | ') for e in map(json.loads, open('evidence/audit_demo.jsonl', encoding='utf8')) if e]" > evidence/sandbox_operations.txt
   ```
6. Count events by type:
   ```bash
   python -c "import json,collections; print(collections.Counter(json.loads(l)['event_type'] for l in open('evidence/audit_demo.jsonl', encoding='utf8') if l.strip()))"
   ```
7. For the scripted tasks and the adversarial suite, repeat with a different audit path each time so each log maps to one command.
8. Keep the demo video and its log together: the video shows the audit tab and the log contains the same sessions.

Do not edit a log by hand. The tamper demo in the UI works on a copy.

## 4. What the evidence does not show

- No external red team, no real insurer data, no real users.
- The scripted, off-script, paraphrase, clarification, recourse and allocation runs are deterministic mode (no model calls); behaviour with the model planner and binder on was measured only for the paraphrase live sample.
- The benchmark rows for b0 and b0cw cover three contracts only; b4 covers 390 of 580 labels.
- The CMS plan-selection experiment ran without premiums (out-of-pocket basis), so all methods coincide there.
- The ombudsman replay (recourse Part B) had not run when `recourse_report.md` was generated.
