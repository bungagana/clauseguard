# Benchmark protocol (written before any new run, 2026-10-14)

Benchmark: Mridul, Kapa & Seneviratne (2026), arXiv:2604.10853; 10 contracts x 58 scenarios, labels COVERED / DENIED / NOT_APPLICABLE.
Systems: **b4** = LLM-extracted typed tuples + deterministic solver; **b0cw** = long-context closed-world LLM baseline (whole contract in prompt, same extract model); **b4oracle** = ABox tuples + solver (upper bound).

## Splits

| set | contracts | role |
|---|---|---|
| development | C1, C7 | extractor prompts were tuned on these before this protocol started |
| analysis | C2, C3, C4 | errors may be inspected and fixes tuned against them; every number on this set is post-tuning |
| held-out | C5, C6, C8, C9, C10 | per-item scenarios, labels, extracted tuples and errors are not opened until the single final run; only aggregates may be computed before it |

Unit of evaluation: (scenario, contract) pair. Primary population: the 34 solver-scope scenarios (the published headline). Secondary: all scenarios the condition was run on (solver scope plus B0CW fallback for the 24 out-of-scope scenarios). Held-out primary n = 34 x 5 = 170, analysis primary n = 34 x 3 = 102.

## Statistics

Accuracy with Wilson 95% interval. Paired comparison against b0cw on the same (scenario, contract) items: discordant counts and exact two-sided McNemar (binomial) test. Risk-coverage reports coverage and accuracy together and the baseline's accuracy on the same answered items.

## Procedure

1. Reproduce the "before" table from existing `evidence/bench_*.jsonl`, no model calls. Held-out contracts contribute aggregates only.
2. The b0cw baseline exists only for C1, C2, C7 (n=112). It is run once for C3, C4 and for the held-out contracts with the unchanged baseline code and per-item output suppressed for held-out. It is a fixed comparator and is not tuned.
3. Error taxonomy and all tuning use the analysis set (and the development set as a regression check) only.
4. A fix is adopted only if it is generic (no contract, scenario or wording specific rule), improves or leaves unchanged analysis accuracy, and does not regress development accuracy.
5. After the fix set is frozen, held-out extraction and solving run exactly once. No parameter changes after that. If the held-out result does not beat the baseline, it is reported as such.

## Known contamination, disclosed up front

- Earlier reports pooled results over all ten contracts, and `bench/README.md`, `scenario_overrides.json` and the benchmark presumptions in `bench/scenario_facts.py` were written while looking at pooled per-scenario results. The solver and fact-binding layers are therefore not clean with respect to the held-out contracts; only the new extraction-side fixes are.
- b4oracle was run on all ten contracts; its numbers are an upper bound, not a held-out result.
- With about 170 paired held-out items and baseline accuracy near 0.87, a difference of a few points cannot reach significance; the report states the interval and p-value rather than only the point estimate.

## Amendments before any tuning run (same day)

- Success criterion: the point-estimate accuracy of b4 on the clean held-out set is above the baseline's on the same items. Wilson intervals and the exact paired McNemar p-value are reported as computed. A non-significant difference is reported as "not distinguishable", never as superiority.
- Reported per set next to b4: oracle (b4oracle) accuracy as the ceiling for extraction.
- Paired 2x2 table (both right / only b4 right / only baseline right / both wrong) on the analysis set, with a cause bucket for every discordant item.
- Error taxonomy includes the category "schema expressiveness" (rule present in the text but not representable by the closed relation types and qualifier fields).

## Amendment: model availability (2026-10-14, before any refinement or baseline run on the new model)

- The extraction model `gemini-3.6-flash` returned 503 for roughly one hour and then reported its daily quota as exhausted on every key of the shared pool (retry hint about 24 h). `gemini-3.5-flash` is exhausted the same way; the pro models (`gemini-3.1-pro-preview`, `gemini-2.5-pro`) return RESOURCE_EXHAUSTED on all seven keys (not available on the free tier), so no stronger model could be tested.
- Responding models at that time: `gemini-3.7-flash`, `gemini-3-flash-preview`, `gemini-flash-latest`, `gemini-2.5-flash`. All new model calls use `gemini-3.7-flash`: (a) the long-context baseline is re-run on all 340 solver-scope items with this model, so that b4 and the baseline are paired on identical items for the first time (the earlier 87.5 was measured with `gemini-3.6-flash` on C1, C2, C7 only, 112 items including out-of-scope scenarios, while the 82.9 covered 340 different items); (b) the recall pass of the refinement stage uses the same model.
- The first-pass tuples of every contract are the stored records in `data/extracted/` (produced by the earlier extractor run; the disk cache no longer reproduces them because the tuple prompt changed after they were generated). Refinement is applied on top of those records, so "before" and "after" differ only by the refinement stages.
- The baseline is run once on all ten contracts in one job. Its per-item output for C5, C6, C8, C9, C10 is written to a log that is not read; only aggregates are computed.
- Contamination note found while reading the extractor: its docstring says a rescue rule (`window_from_text`) was added after a run that showed problems on C8 and C9. The first-pass extraction layer is therefore not fully clean for those two held-out contracts either.
