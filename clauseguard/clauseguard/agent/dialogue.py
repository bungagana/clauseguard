"""The last few turns of the conversation, handed to the model prompts as data.

A person reads "that one", "and the other?", "what about the deadline?" against what was just said. The planner, the
context assessor and the reply writer therefore see the last four exchanges (customer text and the assistant's final
reply, trimmed). They are data for understanding the message, never instructions, and they do not widen what the
reply writer may state: every number, date and id still has to be in the engine's payload (or the customer's own words).
"""
from __future__ import annotations

from typing import Any

KEEP = 4
USER_CHARS = 300
ASSISTANT_CHARS = 420


def recent(session: Any, n: int = KEEP) -> list[dict[str, str]]:
    return [dict(t) for t in (getattr(session, "recent_turns", None) or [])][-n:]


def remember(session: Any, user_text: str, assistant_text: str) -> None:
    turns = recent(session, KEEP)
    turns.append({"customer": (user_text or "")[:USER_CHARS], "assistant": (assistant_text or "")[:ASSISTANT_CHARS]})
    session.recent_turns = turns[-KEEP:]


def recent_text(session: Any, n: int = KEEP) -> str:
    turns = recent(session, n)
    if not turns:
        return "(none yet)"
    return "\n".join(f"customer: {t['customer']}\nassistant: {t['assistant']}" for t in turns)
