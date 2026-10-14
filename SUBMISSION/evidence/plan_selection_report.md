# Plan selection under budget: optimiser vs baselines

Generated 2026-10-11T20:49:02 by `python -m bench.plan_selection_eval --households 100 --seed 7`.

## Experiment A: CMS Exchange plans

### Data provenance

- plan file: `cms_plans_py2026.csv` (real CMS Exchange PUF PY2026 extract, built by scripts/fetch_real_data.py from plan-attributes-puf.zip and benefits-and-cost-sharing-puf.zip), 4183 rows
- state(s): TX (4183 rows)
- plans loaded: 834 standard components from 15 issuers; metal levels: Bronze 43, Catastrophic 29, Expanded Bronze 182, Gold 277, Silver 303
- benefit perils per plan: ACCIDENT_MEDICAL, HOSPITALIZATION, ICU, OUTPATIENT, PREGNANCY (834 plans)
- rate file: `cms_rates_py2026.csv` (age 30, non-tobacco, lowest rating area); plans with a premium: 834/834
- cost basis used by every method: **premium** (monthly premium from the Rate PUF); median plan cost 599.15/month
- households: 100, seed 7, persona patterns {'santoso': 31, 'dewi': 34, 'rizky': 35}; budgets: 18 without, the rest 1-3x the median plan cost
- optimiser solver: {'scipy.optimize.milp': 100}

### Results (mean over households)

| method | gap cells closed per 100/month | median | cells closed | weight closed | cost/month | residual cells | plans | households with nothing | over budget |
|---|---|---|---|---|---|---|---|---|---|
| optimiser | 2.129 | 1.751 | 6.08 | 13.95 | 285.54 | 0.00 | 1.00 | 0 | 0 |
| cheapest plan | 2.129 | 1.751 | 6.08 | 13.95 | 285.54 | 0.00 | 1.00 | 0 | 0 |
| highest metal | 1.466 | 1.206 | 6.08 | 13.95 | 414.72 | 0.00 | 1.00 | 0 | 0 |

### Pairwise

- optimiser closes more weighted gap than the cheapest plan in 0/100 households (ties 100; identical pick in 100); never less, as it is the optimum of that objective under the same budget.
- optimiser closes more weighted gap than the highest metal plan in 0/100 households (ties 100); in 100 it closes at least as much for less money.
- budget violations: optimiser 0, cheapest 0, highest metal plan 0 (baselines fall back to the cheapest fitting plan when their pick does not fit).

### Why the methods coincide here

Every one of the 834 plans covers the same perils (accident medical, hospitalization, icu, outpatient, pregnancy): the ACA essential-health-benefit schedule fixes what a marketplace plan covers, so any single plan closes every medical gap cell and the choice reduces to price. The optimiser's answer equals the cheapest eligible plan under the premium objective, which is the correct optimum for a single-peril-set catalogue.
Death, disability and critical-illness gaps cannot be closed by any ACA plan and are not counted as open gaps in this experiment (the selector only scores perils a candidate closes).

## Experiment B: mixed-peril catalogue (mock, for contrast)

- plans: the 6 illustrative MOCK plans of `clauseguard.catalogue.CATALOGUE` (IDR, invented prices; not an offer from any insurer); perils per plan differ (hospital cash, personal accident, term life, critical illness, group top-up, individual hospitalisation)
- cost basis: **premium**; median plan cost IDR 200,000/month; same 100 households and seed; budgets 1-3x the median
- optimiser solver: {'scipy.optimize.milp': 100}

### Results (mean over households)

| method | gap cells closed per 100/month | median | cells closed | weight closed | cost/month | residual cells | plans | households with nothing | over budget |
|---|---|---|---|---|---|---|---|---|---|
| optimiser | 0.003 | 0.002 | 7.11 | 21.73 | 383,600.00 | 2.49 | 2.11 | 0 | 0 |
| cheapest plan | 0.005 | 0.004 | 4.60 | 12.06 | 90,000.00 | 5.00 | 1.00 | 0 | 0 |
| most expensive plan | 0.002 | 0.001 | 3.52 | 9.92 | 264,600.00 | 6.08 | 1.00 | 0 | 0 |

### Pairwise

- optimiser closes more weighted gap than the cheapest plan in 73/100 households (ties 27; identical pick in 27); never less, as it is the optimum of that objective under the same budget.
- optimiser closes more weighted gap than the most expensive plan in 79/100 households (ties 21); in 19 it closes at least as much for less money.
- budget violations: optimiser 0, cheapest 0, most expensive plan 0 (baselines fall back to the cheapest fitting plan when their pick does not fit).

## Reading the numbers

- A gap cell is one (peril, person) pair with no active cover; cells are weighted by `PERIL_WEIGHT` (hospitalisation and death 5, critical illness 4, ...).
- Every method sees the same candidates, the same open gaps and the same rule that an indemnity plan is never added on top of active indemnity cover for the same perils.
- A candidate plan is assumed to enrol every household member (family enrolment) at the stated cost; per-member pricing needs the Rate PUF.
- Indicative; consult a licensed agent. The households are synthetic; the CMS plan figures are the issuers' PUF filings, not quotes; the mock prices are illustrative.
