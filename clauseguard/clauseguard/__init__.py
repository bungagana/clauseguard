"""ClauseGuard — an insurance assistant in which the language model never decides.

Pipeline: policy PDF -> quarantined extractor -> typed clause tuples -> deterministic
solver (verdict + fired clauses) -> clarification only on verdict-changing unbound slots
-> explainer. Security: permission tiers T0-T3 enforced in code at the tool boundary.
"""

__version__ = "0.1.0"
