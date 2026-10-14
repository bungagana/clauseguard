# bench/ — public benchmark harness

Benchmark: Mridul, Kapa & Seneviratne, *A Benchmark for Gap and Overlap Analysis as a Test of KG Task
Readiness* (QKG @ ESWC 2026), CC-BY-4.0. 10 synthetic US life-insurance contracts (C1..C10), 58
scenarios, 580 clause-traced labels in {COVERED, DENIED, NOT_APPLICABLE}. Data copied to
`data/benchmark/` (contracts, TBox/ABox, scenario batches with ground truth, `all_scenarios.json`).

## Files

| file | role |
|---|---|
| `abox_to_tuples.py` | rdflib over `life_insurance_abox.ttl` → one oracle `PolicyRecord` per contract (`data/benchmark/oracle/C*.json`, tier `POLICY_DOC_VERIFIED`, `unmapped.json`) |
| `scenario_facts.py` | scenario text → `ScenarioFacts` via `clauseguard.agent.facts.bind_facts` (fast model, cached) + `scenario_overrides.json` + benchmark presumptions; `in_solver_scope` label |
| `scenario_overrides.json` | per-scenario `in_solver_scope` flag, 3 hand slot corrections (each with a `note`), out-of-scope reasons |
| `solve.py` | event-scoped view of a `PolicyRecord` for the frozen solver + CLARIFY resolution (majority over the slot domain, flagged) |
| `run_bench.py` | `--system {b0,b0cw,b4,b4oracle} [--contracts C1,C2] [--scenarios N] [--scenario-ids ..] [--model ..] [--skip-fallback]` → `evidence/bench_<system>.jsonl` (resumable, cached) |
| `metrics.py` | accuracy, macro-F1, NA→DENIED rate, evidence hit, in/out-of-scope split, per-category, bootstrap 95% CI over scenarios, McNemar vs B0CW |
| `report.py` | `python -m bench.report` → `evidence/bench_report.md` |
| `allocation_eval.py` | `python -m bench.allocation_eval` → `evidence/allocation_report.md`: claim allocation optimizer vs greedy vs single policy on the persona policies and on CMS PUF plans (bill amounts sampled, plan terms real) |
| `data.py` | loaders (contract text, scenarios + ground truth, oracle / extracted records), section-key and quote normalisation |

Run order: `python -m bench.abox_to_tuples` → `python -m bench.run_bench --system b4oracle` → `--system b0cw --contracts C1,C2,C7` → `--system b0 --contracts C1,C2,C7` → (`--system b4` once `data/extracted/C*.json` exists) → `python -m bench.report`.

## Conditions

- **B0** whole contract text + scenario + label definitions → `{label, evidence_section, evidence_text}` (schema-constrained JSON, temperature 0, minimal thinking).
- **B0CW** B0 + closed-world instruction: "if no clause governs the scenario, answer NOT_APPLICABLE; do not infer denial".
- **B4ORACLE** ABox oracle tuples + `solver.decide`; the LLM only binds the scenario's facts. Separates extraction error from reasoning error.
- **B4** same with `data/extracted/C*.json` (policy extractor output) when present.

For B4 conditions: `CLARIFY` is resolved from the scenario's stated facts; if a slot is still unbound and verdict-changing, the record takes the majority verdict over `SLOT_DOMAINS[slot]` with `flags.clarify_majority` (ties: first domain value, `clarify_tie`). Scenarios outside the solver's scope are answered by B0CW and flagged `fallback=true`; the report shows the solver-scope subset and the overall number separately.

## Scenario scope (34 in, 24 out)

In scope = the question is a coverage / exclusion / period / rider / termination / permitted-action question with an event in the solver vocabulary: SCEN-001..013, 015..019, 021, 025, 026, 028, 029, 030, 035, 037, 044, 046, 051, 052, 054..057.
Out of scope (B0CW fallback): premium skipping (014), misstatement of age (020), death-benefit option (022), index floor/cap (023, 036), underwriting (024), dividends (027), estate planning (031), premium load (032), guaranteed insurability (033), salary-based benefit (034), collateral assignment (038), split option (039), claim payment speed (040), account-value depletion (041), VUL market risk (042), no-lapse rider availability (043), premium guarantee (045), non-forfeiture elections (047, 050), late entrant (048), settlement options (049), loan at first death (053), cash-value projection (058).

## Fact binding for the benchmark

`bind_facts` (fast model, closed `FactSheet`) bound every in-scope scenario correctly except three, corrected in `scenario_overrides.json`:
SCEN-005 (base death benefit, not the ADB rider: category *graded benefit, accidental-death exception*), SCEN-018 (cause AVIATION was left null although `pilot_role` was bound), SCEN-054 (the model bound the accident day 20 as days overdue; the text says the death was 31 days after the 31-day grace period expired = 62 days overdue, policy lapsed).
Composed events from `(event, subject)`: `CHILD_DEATH`, `JOINT_DEATH`, `JOINT_FIRST_DEATH` (bench-visible strings outside the closed `EventCode`; recommend adding them). `survival_days` doubles as *expected* survival for terminal-illness life-expectancy thresholds (10 months → 304).

Benchmark presumptions (`BENCH_PRESUMPTIONS`, applied only to still-unbound slots of in-scope scenarios, recorded per record under `presumed`): in_force=True, premium_status=PAID, misrepresentation=False, intoxicated=False, employment_active=True, military_service=False; for death events: cause=UNKNOWN, parties_both_dead=False. The benchmark's ground truth assumes the same closed world ("all premiums paid", "no misrepresentation") so the solver is not asked to clarify what the benchmark never states. In the product these slots are clarified, not presumed.

## ABox → tuple mapping

| ABox class | tuple(s) |
|---|---|
| `SuicideExclusion` | `HAS_PERIOD SUICIDE` window = `suicideExclusionPeriodMonths` MONTHS from ISSUE; `benefit_type` ReturnPremiumsPaid/…MinusWithdrawals(AndCharges) → RETURN_PREMIUMS, ReturnAccountValue → REDUCED, NoBenefit → NONE |
| `PremiumNonpaymentGracePeriod`, `AccountValueDepletionGracePeriod` | `HAS_PERIOD GRACE` window = `gracePeriodDays` DAYS from PREMIUM_DUE; `PolicyRecord.grace_days`. C6's grace entity has no day count → `DEFINES` only |
| `IncontestabilityProvision` | `HAS_PERIOD CONTESTABILITY` window = `contestabilityPeriodYears` YEARS from ISSUE |
| `FreeLookProvision` | `PERMITS FREE_LOOK` applies_if `days_since_effective <= freeLookDays` |
| `WarExclusion` | `EXCLUDES WAR` (+ window months when `exclusionIsTimeBounded`) |
| `AviationExclusion` | `EXCLUDES AVIATION` + `EXCEPTS` applies_if `pilot_role == PASSENGER` (clause covers pilot/crew only) |
| `LevelDeathBenefit`, `IncreasingDeathBenefit`, `GradedDeathBenefit` (benefit_type GRADED, schedule in `formula`), `BasicGroupCoverage` (salary multiple in `formula`), `VoluntarySupplementalCoverage` (plan VOLUNTARY) | `COVERS DEATH` amount = faceAmount USD |
| `SurvivorshipDeathBenefit` | `COVERS JOINT_DEATH`; `COVERS JOINT_FIRST_DEATH` (benefit NONE, policy continues); `EXCLUDES DEATH` applies_if `parties_both_dead == False` |
| `WaiverOfPremiumRider` / `WaiverOfPremiumProvision` | `COVERS PREMIUM_WAIVER` applies_if `age <= waiverMaxAgeAtDisability`, `days_since_event >= waiting months` |
| `TerminalIllnessADBRider` / `TerminalIllnessADB` | `COVERS TERMINAL_ILLNESS` (pct, max) + `CONDITIONED_ON TERMINAL_ILLNESS` applies_if `survival_days <= lifeExpectancyMonths*30.4` |
| `ChronicIllnessADBRider` | `COVERS CHRONIC_ILLNESS` (ADL rule in `formula`) |
| `ChildrenTermRider` | `COVERS CHILD_DEATH` amount, `age_max`; `TERMINATES_IF CHILD_DEATH` applies_if `age >= childrenRiderMaxAge` (rider-scoped) |
| `AccidentalDeathBenefitRider` | `COVERS ACCIDENTAL_DEATH` amount, applies_if `days_since_event <= adbRiderAccidentDeathWindowDays`, `age_max` |
| `GuaranteedInsurabilityRider` | `PERMITS GUARANTEED_INSURABILITY` (not an `EventCode`; out of scope) |
| `NoLapseGuaranteeRider` (not_selected), `AviationExclusionWaiver` | `RiderRecord` (+ `DEFINES`) |
| `PolicyLoan` | `PERMITS POLICY_LOAN` (+ `CONDITIONED_ON POLICY_LOAN` applies_if `months_since_issue >= loanMinimumYearsInForce*12`) |
| `PartialWithdrawal` | `PERMITS PARTIAL_WITHDRAWAL` |
| `CashSurrenderOption` / `SurrenderCharge` / (cash value present) | one `PERMITS SURRENDER` |
| `ConversionPrivilege` | `PERMITS CONVERSION` (`age_max`, deadline, min/max in `formula`) |
| `ReinstatementProvision` | `PERMITS REINSTATEMENT` applies_if `days_since_event <= reinstatementPeriodYears*365` |
| `ExtendedTermOption` (automatic), `ReducedPaidUpOption` whose text says "automatically", `lapseAutoPaysSurrenderValue` | `COVERS LAPSE` (automatic non-forfeiture) |
| `ReturnOfPremiumBenefit` | `COVERS RETURN_OF_PREMIUM` |
| `CoverageTerminationTrigger` | `TERMINATES_IF GROUP_TERMINATION` applies_if `employment_active == False`; `COVERS GROUP_TERMINATION` (conversion/portability rights) |
| other provisions (`MisstatementOfAge`, `Assignment`, `BeneficiaryChange`, `SettlementOption`, `Portability`, `SplitOption`, `SimultaneousDeathEvent`, `GuaranteedRenewability`, `DeathBenefitChangeOption`, `LateEntrant`, estate-planning provisions, non-automatic non-forfeiture options) | `DEFINES` (display/citation only) |

**Unmapped classes** (no solver semantics; listed per contract in `data/benchmark/oracle/unmapped.json`): parties (`Insured`, `FirstInsured`, `SecondInsured`, `PolicyOwner`, `*Beneficiary`, `Insurer`, `Employee`, `Employer`, `IrrevocableTrust`, `MasterGroupPolicy`), premiums (`LevelPremium`, `FlexiblePremium`, `EmployerPaidPremium`, `EmployeePaidPremium`, `PremiumLoad`), cash value (`GuaranteedCashValue`, `AccountValue`), charges (`CostOfInsurance`, `AdministrativeCharge`, `MortalityAndExpenseCharge`), crediting (`FixedInterestCrediting`, `VariableSubAccountCrediting`, `IndexedCrediting`, `DividendCrediting`, `SubAccount`, `IndexAccount`, `CapRate`, `FloorRate`, `ParticipationRate`, `PaidUpAdditionsDividendOption`). The ABox has no `DrugAlcoholExclusion`, `PreExistingConditionExclusion` or `MaterialMisrepresentation` instances (the C7 ADB rider's drug/alcohol exclusion exists only in the contract text), no loan entity for C5 and no early-surrender schedule for C9.

## Solver adapter (`solve.py`) and recommended solver changes

The frozen solver is called on an event-scoped *view* of the policy. The view closes four gaps that should eventually move into `clauseguard/solver.py`:

1. `PERMITS` is never consulted by `solver.run` (only `COVERS`). The view presents `PERMITS` tuples as `COVERS` for action events (POLICY_LOAN, SURRENDER, PARTIAL_WITHDRAWAL, CONVERSION, REINSTATEMENT, FREE_LOOK, LAPSE, GROUP_TERMINATION). *Recommendation: treat PERMITS like COVERS in the candidate step.*
2. `CONDITIONED_ON` tuples are applied to every event, so a loan condition would deny a death claim. The view keeps only those whose `object` is the event (or a cover tuple id for that event). *Recommendation: scope CONDITIONED_ON by object.*
3. Rider-scoped `EXCLUDES` / `HAS_PERIOD` / `TERMINATES_IF` apply to every event while the rider is attached (the ADB rider's intoxication exclusion would deny the base death benefit). The view keeps them only for events the rider covers; policy-level `TERMINATES_IF` only for benefit events. *Recommendation: rider tuples govern only the rider's own events.*
4. The closed-world shortcut is skipped whenever a `HAS_PERIOD SUICIDE` tuple exists, for any event, so unrelated periods (grace) can deny an action event with no candidate (e.g. "can I reinstate" with an overdue premium). The view keeps SUICIDE for DEATH/SUICIDE and GRACE/CONTESTABILITY for benefit events only. *Recommendation: run the period step only when there is a candidate cover (or a governing exclusion) for the event; make the suicide escape conditional on a death event.*
5. (Mapping, not solver) a coverage whose `applies_if` fails yields NOT_APPLICABLE, never DENIED. Eligibility limits that should *deny* (child rider max age, loan minimum years) are therefore encoded as `TERMINATES_IF` / `CONDITIONED_ON`, not as `applies_if` on the cover.

## Known B4-oracle residual errors (in-scope, after the fixes above)

| scenario | contracts | cause |
|---|---|---|
| SCEN-046 | 9 (all but C7) | scenario says "files an accidental death benefit claim" → event ACCIDENTAL_DEATH → no rider → NOT_APPLICABLE; ground truth labels COVERED (base death benefit). The same wording in SCEN-035 is labelled NOT_APPLICABLE for the same contracts: the ground truth is inconsistent between 035 and 046. |
| SCEN-057 | 10 | material misrepresentation at 23 months → solver DENIED (contestability); ground truth COVERED for 7 contracts ("insurer may contest") and NOT_APPLICABLE for C4/C5/C6 although the ABox gives all three a 2-year contestability provision. SCEN-025 is the same situation at 18 months and is labelled DENIED everywhere. |
| SCEN-018, 019, 037 | C8 | single death on the survivorship policy: ground truth DENIED in SCEN-001/004/005 (no benefit at first death) but COVERED in exclusion-check scenarios; the oracle encodes the first rule. |
| SCEN-011 | C8 | same first-death rule; ground truth NOT_APPLICABLE here. |
| SCEN-008 | C10 | `lapseAutoPaysSurrenderValue` is true for C3 (ground truth COVERED) and C10 (ground truth NOT_APPLICABLE). |
| SCEN-012 | C5 | contract allows loans (Section 4.3) but the ABox has no `PolicyLoan` for C5. |
| SCEN-021 | C9 | early-surrender ROP schedule (0% in years 1-5) is not in the ABox. |
| SCEN-054 | C5 | graded-benefit accidental-death carve-out is not an ADB rider; ground truth DENIED (lapsed), oracle NOT_APPLICABLE. |

## Deviations from the plan

- The extract model (`gemini-3.6-flash`) hit its free-tier **daily** quota during this run (server asked to retry in ~15 h), so B0 / B0CW / fallbacks were run with `--model gemini-3.5-flash-lite` (the fast model). Each record carries `model`; rerun with the default model once the quota resets (cache keys include the model, so nothing is overwritten).
- `clauseguard/llm.py`: Gemini 3.x rejects `thinking_budget=0` with `400 INVALID_ARGUMENT`; the wrapper now retries once with `thinking_level="minimal"` (a swap does not consume a retry), caps quota backoff at 65 s and fails fast on multi-hour retry hints so runs stay resumable.
- `in_solver_scope` is a hand label (24 of 58 out of scope) stored next to the overrides with the reason; metrics are reported for the solver-scope subset and overall.

## Run status (2026-10-11)

- `b4oracle`: all 34 in-scope scenarios x 10 contracts done (340 records, no LLM cost beyond 58 fact-binding calls); 2 of 240 fallback records done.
- `b0cw`: 93 of 174 records (SCEN-001..031 x C1,C2,C7); `b0`: 0 of 174.
- Both Gemini free-tier daily quotas were exhausted (shared key); resume with:
  `python -m bench.run_bench --system b0cw --contracts C1,C2,C7 --sleep 5` (default model = extract model),
  `python -m bench.run_bench --system b0 --contracts C1,C2,C7 --sleep 5`,
  `python -m bench.run_bench --system b4oracle --sleep 5`, then `python -m bench.report`.
  Records already written with `--model gemini-3.5-flash-lite` carry that model name; delete them (or keep a separate `--out`) if the whole baseline should be on one model.

## Run status update (key pool)
- b4oracle: 340/340 in-scope (92.1%); 2/240 fallback. b4: 340/340 in-scope (82.9%, CI 75.9-89.1) + 50 fallback records (C1,C2,C7 up to SCEN-043). b0cw: 112/174. b0: 32/174. Pool 429s again ("API requests" per-minute/day); resume with the commands above. Baselines on gemini-3.5-flash-lite.
