# ClauseGuard architecture

A module map and the interfaces between modules. For the method and the evaluation see
`docs/TECHNICAL_DOCUMENTATION.md`; for the security model see `SECURITY.md`.

## Design rules

1. The language model never produces a verdict, a payable amount, a permission-tier decision or
   an argument of a privileged (T2/T3) tool. Models only (a) extract documents into closed
   schemas, (b) bind user text to typed fact slots, and (c) phrase questions and explanations
   from solver output.
2. No free-text field from a document or a tool result is interpolated into the planner prompt.
   Document strings are display-only.
3. Every clause tuple and every registry value carries a `SourceTier`. Actions at tier 2 and
   above require values from `POLICY_DOC_VERIFIED`, `USER` or `USER_CONFIRMED` tiers.
4. Deterministic: temperature 0, fixtures frozen, every model call cached on disk, every run
   reproducible without an API key through rule-based fallbacks.

## Module map

```
clauseguard/
  schema.py        ClauseTuple, Qualifiers, PolicyRecord, ScenarioFacts, Slot, Verdict, SourceTier
  solver.py        evaluate / decide / decide_portfolio: deterministic verdict, verdict-sensitivity clarification
  allocation.py    claim allocation optimizer (how much each policy pays, in which order)
  rulepacks.py     coordination-of-benefits rule packs as data (ID, GENERIC)
  recourse.py      counterfactual recourse: smallest legitimate fact changes that flip a denial
  twin.py          adjudication twin: every denial ground, readiness score, document cross-checks
  timeline.py      entitlement timeline: dated events with money at risk
  portfolio.py     gap/overlap matrix, payer order, claim readiness
  catalogue.py     mock plan catalogue and the deterministic plan recommender
  plans/           cms_loader.py (CMS Exchange PUF -> PolicyRecord), selector.py (plan selection under budget)
  store.py         SQLite clause store with embedding search over evidence text
  llm.py, config.py  cached, schema-constrained model wrapper; paths and model names
  extractor/       policy_extractor.py (two-pass, quarantined), claim_doc.py (quarantined), hidden_text.py (PyMuPDF scan)
  agent/           planner.py, facts.py, facts_fallback.py, clarifier.py, explainer.py, session.py, tools.py, loop.py
  security/        labels.py, registry.py, pep.py, nonce.py, audit.py, output_guard.py, kill_switch.py
  sandbox/         db.py, seed.py, persona_policies.py, tools.py, entitlement.py, api.py (FastAPI)
bench/             public benchmark harness and the agent-level evaluations
scripts/           extract_all, run_tasks, run_adversarial, serve, verify_audit, fetch_real_data, extraction_quality
tests/             pytest suite
ui/                single-page UI served by the sandbox API (no build step)
data/              policies, personas, scripted tasks, adversarial fixtures, benchmark, real public data
evidence/          generated reports; every number in the documentation is copied from here
```

## Interfaces

### Typed clause store (`schema.py`, `store.py`)

```python
class ClauseTuple(BaseModel):  # head, relation, object, qualifiers, evidence, confidence, source_tier
class PolicyRecord(BaseModel): # id, product_type, basis, dates, grace_days, tuples, riders, extraction_coverage
class ScenarioFacts(BaseModel): # closed slot set; an unbound slot is absent, never False

class ClauseStore:
    def add_policy(self, p: PolicyRecord, owner_user_id: str | None = None) -> None
    def get_policy(self, policy_id: str) -> PolicyRecord
    def policies_for_user(self, user_id: str) -> list[PolicyRecord]
    def search_clauses(self, query: str, policy_ids: list[str] | None = None, k: int = 8) -> list[ClauseTuple]
```

`relation` is one of COVERS, EXCLUDES, EXCEPTS, CONDITIONED_ON, HAS_PERIOD, PAYS, PERMITS,
TERMINATES_IF, REQUIRES_DOCUMENT, DEFINES, REFERS_TO, HAS_RIDER. Qualifiers are typed
(amounts, per-day and per-case limits, windows, deadlines, `applies_if` conditions, basis).

### Solvers

```python
solver.evaluate(policy, facts) -> VerdictResult            # verdict, payable, trace, fired tuple ids, denial code
solver.decide(policy, facts) -> VerdictResult              # adds CLARIFY by verdict sensitivity
solver.decide_portfolio(policies, facts) -> list[VerdictResult]
allocation.optimize_allocation(policies, facts, bill, *, rule_pack="ID", as_of=None) -> AllocationResult   # payer steps, totals, greedy and single-policy baselines
recourse.find_recourse(policy, facts, *, as_of, max_changes=2, portfolio=None) -> list[RecourseOption]   # Pareto-minimal legitimate actions
twin.adjudicate_like_insurer(policy, facts, documents, *, as_of, documents_present=None, portfolio=None) -> TwinReport   # grounds, readiness score
timeline.build_timeline(policies, open_claims, as_of, *, premium_due=None) -> list[TimelineEvent]
plans.selector.select_plans(current_policies, candidate_plans, persons, ...) -> Selection
rulepacks.get_rule_pack(code) -> RulePack
portfolio.gap_overlap(policies, persons, perils) -> dict
portfolio.cob_plan(policies, facts, jurisdiction="ID") -> list[PayerStep]
portfolio.claim_readiness(policy, facts, documents_present, as_of) -> ReadinessReport
```

### Extractors (quarantined: no tools, no history, closed output schema)

```python
extractor.policy_extractor.extract_policy(path, *, policy_id, doc_id=None, source_tier=..., product_hint=None) -> PolicyRecord
extractor.claim_doc.extract_claim_document(path, *, policyholder_name) -> ClaimDocExtract
extractor.hidden_text.scan_pdf(path) -> HiddenTextReport
```

### Agent loop

```python
agent.planner.plan(user_text, session) -> Plan(intent, tool_calls, needs_facts, topics)
agent.facts.bind_facts(user_text, *, policies, as_of, prior=None) -> ScenarioFacts
agent.loop.handle_turn(session, user_text, uploads=[]) -> Reply(text, verdicts, clarification, actions_pending, audit_ids)
```

Order inside a turn: plan, enforcement check, tools, fact binding, solver and portfolio,
clarifier or explainer, output guard.

### Security layer

```python
security.registry.REGISTRY: dict[str, ToolSpec]          # name, tier 0..3, strict pydantic schema, fn, sensitive_fields
security.pep.pep_check(call: ToolCall, session) -> Decision(allow, reason, bound_args)   # rules R1..R9, pure Python
security.nonce.issue(session_id, tool, args_hash, ttl=300) -> token;  verify(token, session_id, tool, args_hash) -> bool
security.audit.append(event: dict);  security.audit.verify(path) -> (ok, first_bad_seq)
security.output_guard.scan(text, session) -> (clean_text, violations)
```

Tiers: T0 read own data; T1 compute or draft; T2 submit after a UI confirmation (server
nonce); T3 money or identity, never executed by the agent (ticket only).

### Sandbox API (`sandbox/api.py`)

`/login`, `/chat`, `/tools/{name}` (through the enforcement point), `/confirm`, `/form`,
`/upload`, `/audit`, `/audit/verify`, `/admin/kill`, `/security/status`, `/personas`,
`/policies`, `/portfolio`, `/chat/pending`, `/chat/confirm`, `/demo/*`, and the entitlement read
models `/entitlement/allocation`, `/entitlement/timeline`, `/entitlement/twin`,
`/entitlement/recourse`, `/entitlement/plans` (`sandbox/entitlement.py`). Back-office endpoints
(`/backoffice/*`) use a separate admin token and are not in the agent registry.

## Run order for a full reproduction

`scripts/extract_all.py` -> `sandbox.seed` -> `scripts/run_tasks.py` -> `scripts/run_adversarial.py`
-> `bench.run_bench` and `bench.report` -> the agent-level evaluations in `bench/` (paraphrase,
clarify, cost, recourse, plan selection, allocation). Exact commands: `docs/EXECUTION_EVIDENCE.md`.
