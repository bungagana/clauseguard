# Token and call cost report

Generated 2026-10-11. `python bench/cost_eval.py` reproduces this file with no API calls (`CG_LLM_REPLAY_ONLY=1`). Scope: 90 chat turns of the 33 scripted tasks (T01-T23 functional incl. plan recommendation, A01-A10 adversarial), run with the LLM paths enabled. The loop's call-hook records every LLM call the loop *attempts*; with no cached answer it falls back to its deterministic path, so these are the calls per turn the design issues, independent of API quota.

## LLM calls per chat turn

| measure | value |
|---|---|
| mean calls per turn | **0.98** |
| median | 0.0 |
| max | **6** |
| turns with zero LLM calls | 48 of 90 (53%) - refusals, T2/T3 actions, hard guardrails, glossary and status lookups |
| calls by purpose (total 88) | clarifier wording: 5, explainer wording: 26, fact binder: 26, intent planner: 31 |
| of which already in the disk cache | 48 |

Purposes: the planner refines the intent only for benign intents (never for safety-relevant ones, which the rules decide before any model is consulted); the fact binder runs only when a scenario is expected; the explainer words one verdict per decided policy and falls back to a template if its quote is not verbatim; the clarifier words at most one question per turn. **With no key, no quota or `--no-llm` every one of these calls is skipped and the answer is the deterministic template: 0 calls.**

Functional tasks only (T01-T23, excluding A09's 50 repeated refusal turns, which pull the all-task mean down): 28 turns, mean **2.36** calls per turn, median 1.5, max 6, 2 turns with zero calls; mean 2,358 tokens per turn (max 5,006) against 13,877 for the full-document baseline (17.0%) and 3,157 for the wording-only baseline (74.7%).

Turns with the most calls: T16 turn 1 (6 calls: intent planner x1, fact binder x1, explainer wording x3, clarifier wording x1); T17 turn 1 (6 calls: intent planner x1, fact binder x1, explainer wording x3, clarifier wording x1); T11 turn 1 (5 calls: intent planner x1, fact binder x1, explainer wording x3); A08 turn 1 (4 calls: intent planner x1, fact binder x1, explainer wording x2).

Update 2026-10-14 (not re-measured above): the reply composer (`clauseguard/agent/composer.py`) adds **one more call per POLICY_QA / CLAIM_GUIDANCE / GAP_ANALYSIS turn** when the model is reachable (schema `_LLMComposed`, prompt = the structured reply payload, typically 1,500-3,000 input tokens plus ~250 output tokens). Refusals, T2/T3 actions, glossary answers and offline/`--no-llm` runs issue no composer call; a rejected composition (COMPOSER_REJECTED) costs the call but falls back to the template.

## Estimated tokens per turn

tokens = characters / 4 over prompt + system prompt + response schema; output tokens: planner 40, fact binder 150, explanation 180, clarification 40 (assumptions, the schemas cap them).

| | mean per turn | max |
|---|---|---|
| ClauseGuard (calls issued) | **1,136** | 5,006 |
| ClauseGuard, only turns that call a model | 2,434 | |
| baseline: all of the user's policy documents in context (1 call) | 13,671 | 26,192 |
| baseline: sandbox wording of the user's policies only (1 call) | 3,115 | 3,566 |

On the functional tasks ClauseGuard issues **17%** of the full-document baseline's tokens per turn and **75%** of the wording-only baseline's (over all 90 turns, including the zero-call refusal turns: 8% and 36%). The saving comes from the architecture: the model never reads a policy. It sees the user's sentence (fact binder), a verdict that the solver already computed plus one clause (explainer), or one slot name (clarifier). The baseline must resend every policy every turn, and its answer still has to be trusted instead of verified.

Caveats: (1) the baseline is a rough size model (one call, no retrieval, no history); a retrieval-augmented baseline would sit between the two; (2) the mock policies in the sandbox are short, so the full-document baseline is dominated by the four real policy documents (Roojai/Sompo, Astra Flexi Life, Astra HCP, Chubb PA); against the short mock wording alone the saving is only about a quarter, because the explainer sends one clause per decided policy; (3) output-token figures are assumptions, input-token figures are measured prompt sizes / 4; (4) ClauseGuard also has one-off extraction cost per policy document (not a per-turn cost, cached on disk).

## Per turn

| task | turn | intent | calls | purposes | tokens (ours) | tokens (baseline, full docs) |
|---|---|---|---|---|---|---|
| A01 | 1 | ACTION (refused) | 0 | - | 0 | 12,977 |
| A02 | 1 | ACTION (refused) | 0 | - | 0 | 12,988 |
| A03 | 1 | OUT_OF_SCOPE (refused) | 1 | intent planner x1 | 512 | 26,162 |
| A04 | 1 | OUT_OF_SCOPE | 1 | intent planner x1 | 513 | 12,980 |
| A04 | 2 | ACTION | 1 | fact binder x1 | 2,784 | 12,978 |
| A05 | 1 | POLICY_QA (refused) | 1 | intent planner x1 | 504 | 26,154 |
| A06 | 1 | OUT_OF_SCOPE (refused) | 1 | intent planner x1 | 512 | 11,194 |
| A07 | 1 | OUT_OF_SCOPE (refused) | 1 | intent planner x1 | 515 | 12,982 |
| A08 | 1 | CLAIM_GUIDANCE | 4 | intent planner x1, fact binder x1, explainer wording x2 | 4,335 | 12,975 |
| A08 | 2 | ACTION | 1 | fact binder x1 | 2,780 | 12,974 |
| A09 | 1 | CLAIM_GUIDANCE | 4 | intent planner x1, fact binder x1, explainer wording x2 | 4,335 | 12,975 |
| A09 | 2 | ACTION | 1 | fact binder x1 | 2,773 | 12,967 |
| A09 | 3 | ACTION | 1 | fact binder x1 | 2,773 | 12,967 |
| A09 | 4 | ACTION | 1 | fact binder x1 | 2,773 | 12,967 |
| A09 | 5 | ACTION | 1 | fact binder x1 | 2,773 | 12,967 |
| A09 | 6 | ACTION | 1 | fact binder x1 | 2,773 | 12,967 |
| A09 | 7 | ACTION | 1 | fact binder x1 | 2,773 | 12,967 |
| A09 | 8 | ACTION | 1 | fact binder x1 | 2,773 | 12,967 |
| A09 | 9 | ACTION (refused) | 0 | - | 0 | 12,967 |
| A09 | 10 | ACTION (refused) | 0 | - | 0 | 12,967 |
| A09 | 11 | ACTION (refused) | 0 | - | 0 | 12,967 |
| A09 | 12 | ACTION (refused) | 0 | - | 0 | 12,967 |
| A09 | 13 | ACTION (refused) | 0 | - | 0 | 12,967 |
| A09 | 14 | ACTION (refused) | 0 | - | 0 | 12,967 |
| A09 | 15 | ACTION (refused) | 0 | - | 0 | 12,967 |
| A09 | 16 | ACTION (refused) | 0 | - | 0 | 12,967 |
| A09 | 17 | ACTION (refused) | 0 | - | 0 | 12,967 |
| A09 | 18 | ACTION (refused) | 0 | - | 0 | 12,967 |
| A09 | 19 | ACTION (refused) | 0 | - | 0 | 12,967 |
| A09 | 20 | ACTION (refused) | 0 | - | 0 | 12,967 |
| A09 | 21 | ACTION (refused) | 0 | - | 0 | 12,967 |
| A09 | 22 | ACTION (refused) | 0 | - | 0 | 12,967 |
| A09 | 23 | ACTION (refused) | 0 | - | 0 | 12,967 |
| A09 | 24 | ACTION (refused) | 0 | - | 0 | 12,967 |
| A09 | 25 | ACTION (refused) | 0 | - | 0 | 12,967 |
| A09 | 26 | ACTION (refused) | 0 | - | 0 | 12,967 |
| A09 | 27 | ACTION (refused) | 0 | - | 0 | 12,967 |
| A09 | 28 | ACTION (refused) | 0 | - | 0 | 12,967 |
| A09 | 29 | ACTION (refused) | 0 | - | 0 | 12,967 |
| A09 | 30 | ACTION (refused) | 0 | - | 0 | 12,967 |
| A09 | 31 | ACTION (refused) | 0 | - | 0 | 12,967 |
| A09 | 32 | ACTION (refused) | 0 | - | 0 | 12,967 |
| A09 | 33 | ACTION (refused) | 0 | - | 0 | 12,967 |
| A09 | 34 | ACTION (refused) | 0 | - | 0 | 12,967 |
| A09 | 35 | ACTION (refused) | 0 | - | 0 | 12,967 |
| A09 | 36 | ACTION (refused) | 0 | - | 0 | 12,967 |
| A09 | 37 | ACTION (refused) | 0 | - | 0 | 12,967 |
| A09 | 38 | ACTION (refused) | 0 | - | 0 | 12,967 |
| A09 | 39 | ACTION (refused) | 0 | - | 0 | 12,967 |
| A09 | 40 | ACTION (refused) | 0 | - | 0 | 12,967 |
| A09 | 41 | ACTION (refused) | 0 | - | 0 | 12,967 |
| A09 | 42 | ACTION (refused) | 0 | - | 0 | 12,967 |
| A09 | 43 | ACTION (refused) | 0 | - | 0 | 12,967 |
| A09 | 44 | ACTION (refused) | 0 | - | 0 | 12,967 |
| A09 | 45 | ACTION (refused) | 0 | - | 0 | 12,967 |
| A09 | 46 | ACTION (refused) | 0 | - | 0 | 12,967 |
| A09 | 47 | ACTION (refused) | 0 | - | 0 | 12,967 |
| A09 | 48 | ACTION (refused) | 0 | - | 0 | 12,967 |
| A09 | 49 | ACTION (refused) | 0 | - | 0 | 12,967 |
| A09 | 50 | ACTION (refused) | 0 | - | 0 | 12,967 |
| A09 | 51 | ACTION (refused) | 0 | - | 0 | 12,967 |
| A10 | 1 | MISREPRESENTATION_REQUEST (refused) | 0 | - | 0 | 26,180 |
| T01 | 1 | POLICY_QA | 1 | intent planner x1 | 503 | 12,970 |
| T02 | 1 | POLICY_QA | 1 | intent planner x1 | 506 | 12,972 |
| T03 | 1 | CLAIM_GUIDANCE | 3 | intent planner x1, fact binder x1, clarifier wording x1 | 3,572 | 12,971 |
| T04 | 1 | POLICY_QA | 3 | intent planner x1, fact binder x1, explainer wording x1 | 3,716 | 12,979 |
| T05 | 1 | POLICY_QA | 2 | intent planner x1, explainer wording x1 | 906 | 11,188 |
| T06 | 1 | POLICY_QA | 1 | intent planner x1 | 502 | 11,185 |
| T07 | 1 | CLAIM_GUIDANCE | 4 | intent planner x1, fact binder x1, explainer wording x1, clarifier wording x1 | 4,174 | 12,989 |
| T07 | 2 | CLAIM_GUIDANCE | 4 | intent planner x1, fact binder x1, explainer wording x1, clarifier wording x1 | 4,051 | 12,970 |
| T08 | 1 | GAP_ANALYSIS | 1 | intent planner x1 | 502 | 11,185 |
| T09 | 1 | GAP_ANALYSIS | 1 | intent planner x1 | 502 | 11,185 |
| T10 | 1 | GAP_ANALYSIS | 2 | intent planner x1, fact binder x1 | 3,275 | 11,184 |
| T11 | 1 | POLICY_QA | 5 | intent planner x1, fact binder x1, explainer wording x3 | 4,693 | 11,182 |
| T12 | 1 | POLICY_QA | 1 | intent planner x1 | 507 | 26,157 |
| T13 | 1 | GAP_ANALYSIS | 1 | intent planner x1 | 498 | 12,965 |
| T14 | 1 | CLAIM_GUIDANCE | 4 | intent planner x1, fact binder x1, explainer wording x2 | 4,335 | 12,975 |
| T15 | 1 | CLAIM_GUIDANCE | 4 | intent planner x1, fact binder x1, explainer wording x2 | 4,335 | 12,975 |
| T15 | 2 | CLAIM_GUIDANCE | 4 | intent planner x1, fact binder x1, explainer wording x2 | 4,317 | 12,966 |
| T16 | 1 | CLAIM_GUIDANCE | 6 | intent planner x1, fact binder x1, explainer wording x3, clarifier wording x1 | 4,960 | 26,192 |
| T17 | 1 | CLAIM_GUIDANCE | 6 | intent planner x1, fact binder x1, explainer wording x3, clarifier wording x1 | 5,006 | 11,203 |
| T18 | 1 | CLAIM_GUIDANCE | 3 | intent planner x1, fact binder x1, explainer wording x1 | 3,769 | 12,996 |
| T19 | 1 | CLAIM_GUIDANCE | 4 | intent planner x1, fact binder x1, explainer wording x2 | 4,335 | 12,975 |
| T19 | 2 | ACTION | 1 | fact binder x1 | 2,773 | 12,967 |
| T19 | 3 | ACTION | 1 | fact binder x1 | 2,773 | 12,962 |
| T19 | 4 | ACTION (refused) | 0 | - | 0 | 12,969 |
| T20 | 1 | MISREPRESENTATION_REQUEST (refused) | 0 | - | 0 | 12,980 |
| T21 | 1 | PLAN_RECOMMENDATION | 1 | intent planner x1 | 502 | 12,968 |
| T22 | 1 | PLAN_RECOMMENDATION | 1 | intent planner x1 | 510 | 26,160 |
| T23 | 1 | PLAN_RECOMMENDATION | 1 | intent planner x1 | 510 | 11,192 |