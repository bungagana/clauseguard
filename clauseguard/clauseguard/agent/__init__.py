"""Agent layer: planner (fast model, closed schema), clarifier, explainer and the turn loop.

The language model never produces a verdict, an amount, a tier decision or a privileged
tool argument. It classifies intent, binds user text to typed facts (agent/facts.py),
phrases one clarification question and explains a solver trace while quoting evidence that
`explainer.verify_citations` checks by string match.
"""
