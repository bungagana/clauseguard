# ClauseGuard benchmark report

Benchmark: Mridul, Kapa & Seneviratne (2026), 58 scenarios x 10 synthetic US life-insurance contracts, labels {COVERED, DENIED, NOT_APPLICABLE}. Ground truth is clause-traced. All conditions: Gemini API, temperature 0, schema-constrained JSON, disk-cached. The paper's own LLM baselines were run through web chat; ours are API + schema, so B0 is expected to score higher than the paper's reported numbers.

## Overall (all scenarios the condition was run on)

| system | contracts | n | accuracy | 95% CI (bootstrap over scenarios) | macro-F1 | NA->DENIED | evidence hit (n) | evidence hit, correct only (n) | fallback | clarify-resolved |
|---|---|---|---|---|---|---|---|---|---|---|
| b0 | C1,C2,C7 | 32 | 96.9 | [90.0, 100.0] | 97.3 | 0.0 | 95.5 (22) | 100.0 (21) | 0 | 0 |
| b0cw | C1,C2,C7 | 112 | 87.5 | [78.1, 95.5] | 82.0 | 3.1 | 85.1 (47) | 100.0 (37) | 0 | 0 |
| b4 | C1,C2,C3,C4,C5,C6,C7,C8,C9,C10 | 390 | 84.6 | [77.8, 90.0] | 80.7 | 1.4 | 57.1 (177) | 71.7 (127) | 50 | 21 |
| b4oracle | C1,C2,C3,C4,C5,C6,C7,C8,C9,C10 | 342 | 91.8 | [83.3, 98.0] | 89.3 | 2.9 | 69.6 (168) | 76.0 (146) | 2 | 2 |

- **b0**: whole contract + scenario, schema JSON (extract model, T=0)
- **b0cw**: B0 + explicit closed-world instruction
- **b4**: extracted typed tuples + deterministic solver (LLM binds facts only)
- **b4oracle**: ABox oracle tuples + deterministic solver (LLM binds facts only)

## Paired comparison on the common subset (32 items, 11 scenarios x ['C1', 'C2', 'C7'])

| system | accuracy | macro-F1 | NA->DENIED | evidence hit | in-scope acc (n) | out-of-scope acc (n) |
|---|---|---|---|---|---|---|
| b0 | 96.9 | 97.3 | 0.0 | 95.5 | - | - |
| b0cw | 96.9 | 97.3 | 0.0 | 95.5 | - | - |
| b4 | 84.4 | 87.2 | 0.0 | 63.6 | 84.4 (32) | - |
| b4oracle | 100.0 | 100.0 | 0.0 | 100.0 | 100.0 (32) | - |

### McNemar vs B0CW (paired, exact binomial on discordant pairs)

| system | pairs | system right / B0CW wrong | system wrong / B0CW right | p (exact) |
|---|---|---|---|---|
| b0 | 32 | 0 | 0 | 1.000 |
| b4 | 112 | 11 | 12 | 1.000 |
| b4oracle | 80 | 13 | 0 | 0.000 |

## b4oracle: solver-scope subset vs. B0CW fallback

- In solver scope (coverage / exclusion / period / rider / termination / permitted action): n=340, accuracy 92.1, macro-F1 89.6, NA->DENIED 2.3
- Out of scope (answered by B0CW fallback, flagged): n=2, accuracy 50.0

Per-scenario accuracy (in-scope scenarios below 100% are listed with the failure reason in bench/README.md):

| scenario | category | scope | acc |
|---|---|---|---|
| SCEN-001 | BASIC_DEATH_CLAIM | solver | 100.0 |
| SCEN-002 | SUICIDE_EXCLUSION_WITHIN_PERIOD | solver | 100.0 |
| SCEN-003 | SUICIDE_EXCLUSION_BOUNDARY | solver | 100.0 |
| SCEN-004 | GRADED_DEATH_BENEFIT | solver | 100.0 |
| SCEN-005 | GRADED_BENEFIT_ACCIDENTAL_DEATH_EXCEPTION | solver | 100.0 |
| SCEN-006 | SURVIVORSHIP_BOTH_INSUREDS_DEAD | solver | 100.0 |
| SCEN-007 | FREE_LOOK_CANCELLATION | solver | 100.0 |
| SCEN-008 | POLICY_LAPSE_NON_FORFEITURE | solver | 90.0 |
| SCEN-009 | CONVERSION_PRIVILEGE | solver | 100.0 |
| SCEN-010 | REINSTATEMENT_AFTER_LAPSE | solver | 100.0 |
| SCEN-011 | GRACE_PERIOD_DEATH | solver | 90.0 |
| SCEN-012 | POLICY_LOAN_AVAILABILITY | solver | 90.0 |
| SCEN-013 | PARTIAL_WITHDRAWAL | solver | 100.0 |
| SCEN-014 | FLEXIBLE_PREMIUM_SKIPPING | fallback | 50.0 |
| SCEN-015 | WAIVER_OF_PREMIUM_DISABILITY | solver | 100.0 |
| SCEN-016 | TERMINAL_ILLNESS_ACCELERATED_BENEFIT | solver | 100.0 |
| SCEN-017 | RETURN_OF_PREMIUM_SURVIVAL | solver | 100.0 |
| SCEN-018 | AVIATION_DEATH_PILOT | solver | 90.0 |
| SCEN-019 | WAR_EXCLUSION_MILITARY_DEATH | solver | 90.0 |
| SCEN-021 | SURRENDER_CHARGE_EARLY_EXIT | solver | 90.0 |
| SCEN-025 | CONTESTABILITY_MATERIAL_MISREPRESENTATION | solver | 100.0 |
| SCEN-026 | GROUP_COVERAGE_TERMINATION_EMPLOYMENT_END | solver | 100.0 |
| SCEN-028 | SIMULTANEOUS_DEATH_JOINT_POLICY | solver | 100.0 |
| SCEN-029 | CHILDREN_RIDER_COVERAGE | solver | 100.0 |
| SCEN-030 | CHRONIC_ILLNESS_ADB | solver | 100.0 |
| SCEN-035 | ACCIDENTAL_DEATH_BENEFIT_RIDER_PAYOUT | solver | 100.0 |
| SCEN-037 | PRE_EXISTING_CONDITION_EXCLUSION | solver | 90.0 |
| SCEN-044 | ROP_CONVERSION_TRADE_OFF | solver | 100.0 |
| SCEN-046 | ADB_RIDER_DRUG_ALCOHOL_EXCLUSION | solver | 10.0 |
| SCEN-051 | JOINT_SIMULTANEOUS_DEATH | solver | 100.0 |
| SCEN-052 | JOINT_FIRST_DEATH_DURING_GRACE_PERIOD | solver | 100.0 |
| SCEN-054 | ADB_RIDER_ACCIDENT_IN_GRACE_DEATH_AFTER_LAPSE | solver | 90.0 |
| SCEN-055 | TERMINAL_ILLNESS_ADB_PRE_EXISTING_CONDITION | solver | 100.0 |
| SCEN-056 | CHILD_RIDER_DEATH_AFTER_MAX_AGE | solver | 100.0 |
| SCEN-057 | MATERIAL_MISREPRESENTATION_WITHIN_CONTESTABILITY | solver | 0.0 |

## b4: solver-scope subset vs. B0CW fallback

- In solver scope (coverage / exclusion / period / rider / termination / permitted action): n=340, accuracy 82.9, macro-F1 80.0, NA->DENIED 1.2
- Out of scope (answered by B0CW fallback, flagged): n=50, accuracy 96.0

Per-scenario accuracy (in-scope scenarios below 100% are listed with the failure reason in bench/README.md):

| scenario | category | scope | acc |
|---|---|---|---|
| SCEN-001 | BASIC_DEATH_CLAIM | solver | 90.0 |
| SCEN-002 | SUICIDE_EXCLUSION_WITHIN_PERIOD | solver | 100.0 |
| SCEN-003 | SUICIDE_EXCLUSION_BOUNDARY | solver | 100.0 |
| SCEN-004 | GRADED_DEATH_BENEFIT | solver | 90.0 |
| SCEN-005 | GRADED_BENEFIT_ACCIDENTAL_DEATH_EXCEPTION | solver | 90.0 |
| SCEN-006 | SURVIVORSHIP_BOTH_INSUREDS_DEAD | solver | 90.0 |
| SCEN-007 | FREE_LOOK_CANCELLATION | solver | 100.0 |
| SCEN-008 | POLICY_LAPSE_NON_FORFEITURE | solver | 70.0 |
| SCEN-009 | CONVERSION_PRIVILEGE | solver | 80.0 |
| SCEN-010 | REINSTATEMENT_AFTER_LAPSE | solver | 100.0 |
| SCEN-011 | GRACE_PERIOD_DEATH | solver | 70.0 |
| SCEN-012 | POLICY_LOAN_AVAILABILITY | solver | 90.0 |
| SCEN-013 | PARTIAL_WITHDRAWAL | solver | 100.0 |
| SCEN-014 | FLEXIBLE_PREMIUM_SKIPPING | fallback | 66.7 |
| SCEN-015 | WAIVER_OF_PREMIUM_DISABILITY | solver | 90.0 |
| SCEN-016 | TERMINAL_ILLNESS_ACCELERATED_BENEFIT | solver | 90.0 |
| SCEN-017 | RETURN_OF_PREMIUM_SURVIVAL | solver | 100.0 |
| SCEN-018 | AVIATION_DEATH_PILOT | solver | 70.0 |
| SCEN-019 | WAR_EXCLUSION_MILITARY_DEATH | solver | 70.0 |
| SCEN-020 | MISSTATEMENT_OF_AGE | fallback | 100.0 |
| SCEN-021 | SURRENDER_CHARGE_EARLY_EXIT | solver | 70.0 |
| SCEN-022 | INCREASING_DEATH_BENEFIT_OPTION | fallback | 100.0 |
| SCEN-023 | INDEXED_CREDITING_ZERO_FLOOR | fallback | 100.0 |
| SCEN-024 | GUARANTEED_ISSUE_UNDERWRITING | fallback | 100.0 |
| SCEN-025 | CONTESTABILITY_MATERIAL_MISREPRESENTATION | solver | 80.0 |
| SCEN-026 | GROUP_COVERAGE_TERMINATION_EMPLOYMENT_END | solver | 90.0 |
| SCEN-027 | DIVIDEND_OPTIONS_WHOLE_LIFE | fallback | 100.0 |
| SCEN-028 | SIMULTANEOUS_DEATH_JOINT_POLICY | solver | 90.0 |
| SCEN-029 | CHILDREN_RIDER_COVERAGE | solver | 90.0 |
| SCEN-030 | CHRONIC_ILLNESS_ADB | solver | 90.0 |
| SCEN-031 | ESTATE_PLANNING_ILIT_OWNERSHIP | fallback | 100.0 |
| SCEN-032 | PREMIUM_LOAD_COMPARISON | fallback | 100.0 |
| SCEN-033 | GUARANTEED_INSURABILITY_OPTION | fallback | 100.0 |
| SCEN-034 | SALARY_BASED_BENEFIT_SALARY_INCREASE | fallback | 100.0 |
| SCEN-035 | ACCIDENTAL_DEATH_BENEFIT_RIDER_PAYOUT | solver | 90.0 |
| SCEN-036 | IUL_CAP_RATE_INDEX_GAIN | fallback | 100.0 |
| SCEN-037 | PRE_EXISTING_CONDITION_EXCLUSION | solver | 80.0 |
| SCEN-038 | POLICY_ASSIGNMENT_AS_COLLATERAL | fallback | 66.7 |
| SCEN-039 | JOINT_POLICY_SPLIT_OPTION | fallback | 100.0 |
| SCEN-040 | CLAIM_PAYMENT_SPEED_COMPARISON | fallback | 100.0 |
| SCEN-041 | ACCOUNT_VALUE_DEPLETION_LAPSE_RISK | fallback | 100.0 |
| SCEN-042 | VUL_INVESTMENT_RISK_MARKET_CRASH | fallback | 100.0 |
| SCEN-043 | NO_LAPSE_GUARANTEE_RIDER | fallback | 100.0 |
| SCEN-044 | ROP_CONVERSION_TRADE_OFF | solver | 80.0 |
| SCEN-046 | ADB_RIDER_DRUG_ALCOHOL_EXCLUSION | solver | 20.0 |
| SCEN-051 | JOINT_SIMULTANEOUS_DEATH | solver | 90.0 |
| SCEN-052 | JOINT_FIRST_DEATH_DURING_GRACE_PERIOD | solver | 90.0 |
| SCEN-054 | ADB_RIDER_ACCIDENT_IN_GRACE_DEATH_AFTER_LAPSE | solver | 100.0 |
| SCEN-055 | TERMINAL_ILLNESS_ADB_PRE_EXISTING_CONDITION | solver | 80.0 |
| SCEN-056 | CHILD_RIDER_DEATH_AFTER_MAX_AGE | solver | 90.0 |
| SCEN-057 | MATERIAL_MISREPRESENTATION_WITHIN_CONTESTABILITY | solver | 0.0 |

## B4-oracle residual errors: ground-truth inconsistencies

The oracle condition feeds the benchmark's own ABox into the solver, so its residual errors isolate label noise. Each row quotes the scenario text and the labels the ground truth gives to the *same* contract under the same facts.

| scenario | text (abridged) | contracts wrong | ground truth | conflicting ground truth |
|---|---|---|---|---|
| SCEN-046 | The insured dies in a car accident. Toxicology confirms the insured had a blood alcohol concentration above the legal limit at the time of the accident. The ben | C1, C2, C3, C4, C5, C6, C8, C9, C10 | C1: COVERED | SCEN-035 C1: NOT_APPLICABLE - same wording ('accidental death benefit claim'), same contracts: 046 = COVERED, 035 = NOT_APPLICABLE |
| SCEN-057 | The insured dies 23 months after policy issue. During the claim investigation, the insurer discovers the insured answered 'No' on the application to questions a | C1, C2, C3, C4, C5, C6, C7, C8, C9, C10 | C1: COVERED | SCEN-025 C1: DENIED - material misrepresentation inside the 2-year contestability window: 057 (23 months) = COVERED / NOT_APPLICABLE, 025 (18 months) = DENIED on all 10 |
| SCEN-018 | The insured, who is a licensed private pilot, dies while operating a small private aircraft on a non-commercial flight. No war or military activity is involved. | C8 | C8: COVERED | SCEN-001 C8: DENIED - single death on the second-to-die policy: 018/019/037 = COVERED, 001/004/005 = DENIED, 011 = NOT_APPLICABLE |
| SCEN-011 | The insured dies 20 days after a missed premium due date, during the grace period. No prior loans or withdrawals. | C8 | C8: NOT_APPLICABLE | SCEN-001 C8: DENIED - as above |
| SCEN-008 | After several years, the policy owner stops paying premiums and neither surrenders the policy nor selects a non-forfeiture option within 60 days of lapse. | C10 | C10: NOT_APPLICABLE | SCEN-008 C10: NOT_APPLICABLE - `lapseAutoPaysSurrenderValue` is true for C3 (COVERED) and C10 (NOT_APPLICABLE) in the ABox |

ABox gaps (clause exists in the contract text but not in the ground-truth ABox): SCEN-012 C5; SCEN-021 C9; SCEN-054 C5 (C5 loans, C9 early-surrender schedule, C5 graded accidental carve-out).

## Confusion matrices (rows = ground truth, columns = prediction)

**b0**

| gt \ pred | COVERED | DENIED | NOT_APPLICABLE |
|---|---|---|---|
| COVERED | 15 | 0 | 1 |
| DENIED | 0 | 6 | 0 |
| NOT_APPLICABLE | 0 | 0 | 10 |

**b0cw**

| gt \ pred | COVERED | DENIED | NOT_APPLICABLE |
|---|---|---|---|
| COVERED | 31 | 0 | 7 |
| DENIED | 3 | 6 | 0 |
| NOT_APPLICABLE | 2 | 2 | 61 |

**b4**

| gt \ pred | COVERED | DENIED | NOT_APPLICABLE |
|---|---|---|---|
| COVERED | 94 | 13 | 30 |
| DENIED | 6 | 33 | 1 |
| NOT_APPLICABLE | 7 | 3 | 203 |

**b4oracle**

| gt \ pred | COVERED | DENIED | NOT_APPLICABLE |
|---|---|---|---|
| COVERED | 108 | 10 | 10 |
| DENIED | 0 | 38 | 2 |
| NOT_APPLICABLE | 1 | 5 | 168 |

## Per-category accuracy (common subset)

| category | b0 | b0cw | b4 | b4oracle |
|---|---|---|---|---|
| BASIC_DEATH_CLAIM | 100.0 | 100.0 | 66.7 | 100.0 |
| CONVERSION_PRIVILEGE | 100.0 | 100.0 | 100.0 | 100.0 |
| FREE_LOOK_CANCELLATION | 100.0 | 100.0 | 100.0 | 100.0 |
| GRACE_PERIOD_DEATH | 50.0 | 50.0 | 50.0 | 100.0 |
| GRADED_BENEFIT_ACCIDENTAL_DEATH_EXCEPTION | 100.0 | 100.0 | 66.7 | 100.0 |
| GRADED_DEATH_BENEFIT | 100.0 | 100.0 | 66.7 | 100.0 |
| POLICY_LAPSE_NON_FORFEITURE | 100.0 | 100.0 | 66.7 | 100.0 |
| REINSTATEMENT_AFTER_LAPSE | 100.0 | 100.0 | 100.0 | 100.0 |
| SUICIDE_EXCLUSION_BOUNDARY | 100.0 | 100.0 | 100.0 | 100.0 |
| SUICIDE_EXCLUSION_WITHIN_PERIOD | 100.0 | 100.0 | 100.0 | 100.0 |
| SURVIVORSHIP_BOTH_INSUREDS_DEAD | 100.0 | 100.0 | 100.0 | 100.0 |

## Per-contract accuracy

| contract | b0 | b0cw | b4 | b4oracle |
|---|---|---|---|---|
| C1 | 100.0 | 89.5 | 80.4 | 91.4 |
| C2 | 90.9 | 83.8 | 92.2 | 94.3 |
| C3 | - | - | 85.3 | 94.1 |
| C4 | - | - | 85.3 | 94.1 |
| C5 | - | - | 91.2 | 88.2 |
| C6 | - | - | 85.3 | 94.1 |
| C7 | 100.0 | 89.2 | 82.0 | 97.1 |
| C8 | - | - | 67.6 | 82.4 |
| C9 | - | - | 91.2 | 91.2 |
| C10 | - | - | 85.3 | 91.2 |

Evidence hit = predicted section matches the ground-truth section, or >= 40% token overlap between the predicted excerpt and the ground-truth quote; computed only where the ground truth cites a clause. NOT_SPECIFIED is scored as NOT_APPLICABLE. Bootstrap CI resamples scenarios (each a cluster of contracts), not labels. McNemar uses the exact binomial test on discordant pairs.

## Protocol run 2026-10-14 (see bench_protocol.md, bench_error_taxonomy.md)

The rows above are the previous version and stay as published. Splits: development C1, C7; analysis C2, C3, C4 (tuned against, so post-tuning); held-out C5, C6, C8, C9, C10 (single run, clean for the extraction-side fixes; the solver and fact-binding layers are not clean, see the protocol). Solver scope only, n = 34 scenarios per contract. Wilson 95% intervals.

| set | b4 previous (stored extraction) | b4 after (verification + salvage + recall + documents_present presumption) | oracle ceiling |
|---|---|---|---|
| development (n=68) | 73.5 [62.0, 82.6] | 88.2 [78.5, 93.9] (post-tuning) | 95.6 |
| analysis (n=102) | 87.3 [79.4, 92.4] | 92.2 [85.3, 96.0] (post-tuning) | 94.1 |
| held-out (n=170) | 84.1 [77.9, 88.8] | 84.1 [77.9, 88.8] (143/170; 3 items fixed, 3 broken) | 89.4 |

Measured effect on the analysis set, in order: adapter presumption `documents_present` 0 items (dev +7); evidence verification +3 (SCEN-009 and SCEN-044 on C3, SCEN-018 on C4); recall pass +2 (SCEN-008 on C2, C3); replay of rows the stored records had dropped as out-of-vocabulary +3 on the development set (the current extractor already has an alias table for these; the stored records predate it). The oracle-based `ACCIDENTAL_DEATH` generalisation was tested and reverted (+4 / -8).

Comparison with the long-context baseline: NOT completed. The baseline `gemini-3.6-flash` quota was exhausted for the day; a re-run with `gemini-3.7-flash` produced only 41 items before quota and 503 errors stopped it (19 paired with b4: 19/19 each). On the held-out set there are 0 paired items, so no McNemar test and no claim against the baseline can be made. The only paired evidence is the earlier 3.6 baseline on C1, C2, C7 (78 solver-scope items): after 94.9 vs baseline 83.3, 12 vs 3 discordant, exact p = 0.035; this is post-tuning data and the baseline item set is not the same as the 340-item headline.

Not done: LLM verification pass, self-consistency, stronger model (pro models return RESOURCE_EXHAUSTED on every key). Risk-coverage with the `uncertain` flag: no discrimination (analysis answered 92.8% at coverage 81%, flagged items 89.5%).
