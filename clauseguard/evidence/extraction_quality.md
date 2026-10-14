# Extraction quality vs benchmark ABox (C1..C10)

Gold: `data/benchmark/ontologies/life_insurance_abox.ttl`. Extracted: `data/extracted/C*.json` produced by `scripts/extract_all.py` (two-pass extractor, model `gemini-3.6-flash`, temperature 0).

Held-out discipline: prompts and normalisation rules were tuned on **C1 and C7 only**; C2-C6 and C8-C10 are held out.

## Per-field precision / recall (exact value match)

| field | TP | FP | FN | TN | precision | recall |
|---|---|---|---|---|---|---|
| suicide_months | 10 | 0 | 0 | 0 | 1.00 | 1.00 |
| grace_days | 9 | 0 | 0 | 1 | 1.00 | 1.00 |
| contest_years | 8 | 0 | 2 | 0 | 1.00 | 0.80 |
| free_look_days | 3 | 0 | 0 | 7 | 1.00 | 1.00 |
| loan_available | 5 | 1 | 0 | 4 | 0.83 | 1.00 |

Suicide benefit type (ReturnPremiums/NoBenefit/AccountValue -> RETURN_PREMIUMS/NONE/REDUCED) correct: 8/10.

## Per-contract values (gold -> extracted)

| contract | tuples | coverage | suicide_months | grace_days | contest_years | free_look_days | loan_available |
|---|---|---|---|---|---|---|---|
| C1 | 15 | 1.00 | 24 -> 24 | 31 -> 31 | 2 -> 2 | None -> None | False -> False |
| C2 | 15 | 0.73 | 24 -> 24 | 31 -> 31 | 2 -> 2 | 30 -> 30 | True -> True |
| C3 | 21 | 0.82 | 24 -> 24 | 61 -> 61 | 2 -> 2 | None -> None | True -> True |
| C4 | 16 | 0.75 | 24 -> 24 | 61 -> 61 | 2 -> None **x** | None -> None | True -> True |
| C5 | 19 | 0.89 | 24 -> 24 | 30 -> 30 | 2 -> 2 | 30 -> 30 | False -> True **x** |
| C6 | 16 | 0.73 | 12 -> 12 | None -> None | 2 -> None **x** | None -> None | False -> False |
| C7 | 29 | 0.71 | 24 -> 24 | 31 -> 31 | 2 -> 2 | None -> None | False -> False |
| C8 | 14 | 0.67 | 24 -> 24 | 60 -> 60 | 2 -> 2 | 30 -> 30 | True -> True |
| C9 | 18 | 0.73 | 24 -> 24 | 31 -> 31 | 2 -> 2 | None -> None | False -> False |
| C10 | 20 | 0.62 | 24 -> 24 | 61 -> 61 | 2 -> 2 | None -> None | True -> True |

Notes:
- `grace_days` for C6 has no `gracePeriodDays` literal in the ABox (the group certificate defines the grace period in prose), so an extracted value there counts as FP under exact matching; see the per-contract row.
- The two `contest_years` FNs (C4, C6) are gold values that do not appear in the contract text: contract_4 has no contestability clause at all and the ABox labels C6's as `Section 1.3 (implied from master policy)`. The extractor correctly did not invent them.
- The `loan_available` FP (C5) is a gold gap: contract_5 §4.3 states `You can borrow against the cash value`, but the ABox has no `PolicyLoan` node for C5.
- Models: C1-C3 `gemini-3.6-flash` (primary); C4-C6, C8-C9 `gemini-3.8-flash`; C10 `gemini-3.7-flash`; C7 `gemini-3-flash-preview` - the free-tier daily quota (20 requests/model, shared with other module runs on the same key) forced the fallback chain in `policy_extractor.MODEL_CHAIN`. Each tuple records its model in `extractor_version`.
- Post-blind-run code changes (disclosed): (a) `window_from_text` rescue parses 'N days/months/years' from the evidence when a fallback model leaves `window_len` empty on a HAS_PERIOD row (rescued tuples carry confidence <= 0.7); (b) object aliases for codes the fallback models invented (ACCELERATED_DEATH_* -> TERMINAL/CHRONIC_ILLNESS, HIV_AIDS -> SPECIFIED_DISEASE). No prompt text was changed after the blind run.
- Windows are converted in code (years -> months x12, days kept); a value counts only if the number matches exactly.
- `loan_available` is the presence of a PERMITS POLICY_LOAN tuple vs `li:hasPolicyLoan` in the ABox.
