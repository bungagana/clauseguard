# Error taxonomy (analysis set C2, C3, C4; development set C1, C7 shown separately)

Source records: `evidence/bench_b4.jsonl` (stored first-pass extraction, solver scope, n = 102 on the analysis set, 13 wrong) with the oracle run `evidence/bench_b4oracle.jsonl` as reference. Held-out contracts were not inspected.

## Analysis set, 13 errors of the stored extraction

| # | category | items | count | fixed by |
|---|---|---|---|---|
| 1 | extraction: wrong object (tuple type does not match its own evidence: "change death benefit option" extracted as `PERMITS CONVERSION`) | SCEN-009, SCEN-044 on C3 | 2 | evidence cue verification removes the tuple |
| 2 | extraction: qualifier value outside the slot vocabulary (`pilot_role IN [PILOT, CREW]`, domain is PASSENGER / CREW / PRIVATE_PILOT) | SCEN-018 on C4 | 1 | slot-domain repair in verification |
| 3 | extraction: missing tuple (lapse / non-forfeiture rule present in the text, no `COVERS LAPSE`) | SCEN-008 on C2, C3 | 2 | recall pass over uncovered rule sentences |
| 4 | extraction: missing tuple (surrender allowed; only the charge schedule was extracted as `HAS_PERIOD SURRENDER_CHARGE`) | SCEN-021 on C4 | 1 | not fixed |
| 5 | closed-world label scope: gold says COVERED because the contract lists no drug or alcohol exclusion; the contract has no accidental-death cover, the oracle also answers NOT_APPLICABLE | SCEN-046 on C2, C3, C4 | 3 | not fixed (see below) |
| 6 | gold label contradicts its own rationale and a sibling scenario: SCEN-057 (death at 23 months, misrepresentation) is COVERED on C2, C3 while the details text says the insurer may contest, and SCEN-025 (18 months, same facts) is DENIED | SCEN-057 on C2, C3 | 2 | not fixed (label) |
| 7 | gold label not supported by the contract text: C4 has no contestability or incontestability clause at all (`grep contest` finds nothing), gold SCEN-025 is DENIED citing "Section (Incontestability)" | SCEN-025 on C4 | 1 | not fixed (label) |
| 8 | solver scope: scenario raises contestability, contract has no such clause, gold NOT_APPLICABLE, solver COVERED through the death cover | SCEN-057 on C4 | 1 | not fixed |

Schema expressiveness on the analysis set: no item is lost because a rule cannot be represented. The two closest cases (4, and the surrender-charge schedule inside it) are extraction misses, not representation limits: a `PERMITS SURRENDER` tuple exists in the closed vocabulary.

Tried and rejected on the oracle: generalising `ACCIDENTAL_DEATH` to `DEATH` when the contract has no accidental-death cover fixes SCEN-046 (+4 items on C1-C4) but breaks SCEN-035 and SCEN-054 (-8 items) because the gold labels treat "no accidental-death rider" as NOT_APPLICABLE there. The three scenarios are mutually inconsistent as a scope rule, so the change was reverted (`evidence/archive/bench_b4*_solverfix_with_event_generalisation.jsonl`).

## Development set (C1, C7), 18 errors of the stored extraction

| category | count | notes |
|---|---|---|
| scenario-to-slot binding / presumption: the death benefit needs `documents_present`, the benchmark never states it, CLARIFY unresolved becomes NOT_APPLICABLE | 7 (C1: SCEN-001, 004, 005, 011, 018, 019, 037) | benchmark presumption `documents_present = True` (same family as the existing presumptions `premium_status = PAID`) |
| schema expressiveness, closed `EventCode` vocabulary: accelerated death benefits (terminal, chronic) and guaranteed insurability rows were dropped as "not an EventCode" | 3 dropped rows, 3 items (C7 SCEN-016, 030, 055) | the current extractor already carries an alias table written after an earlier blind run; the stored records predate it. Out-of-vocabulary objects are now mapped by shared tokens or kept as `UNMODELED_RULE` |
| schema expressiveness, slot set: coverage of a child rider ends at the child's age 25, the slot set has only the insured's `age` | 1 (C7 SCEN-056) | candidate for a `child_age` slot; not justified on the analysis set, not implemented |
| extraction: wrong slot or relation (`days_hospitalized GE 180` used for 6 months of disability; a military exception extracted as `EXCLUDES WAR cause EQ WAR`; `premium_status EQ PAID` condition contradicting the grace period) | 3 (C7 SCEN-015, 019, 011) | not fixed |
| gold label (as for analysis category 5, 6) | 3 (C1 SCEN-046, 057; C7 SCEN-057) | not fixed |
| clarify majority resolution | 1 (C7 SCEN-015 is also counted above) | |

## Where the oracle also fails (analysis set, 6 of 102)

SCEN-046 on C2, C3, C4 (category 5) and SCEN-057 on C2, C3 (category 6) plus SCEN-057 on C4 (category 8). These are the label-scope and gold-label limits: no extraction can recover them, so the ceiling of the extracted-tuples pipeline on the analysis set is 94.1% (96/102), not 100%.
