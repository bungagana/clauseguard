"""Shared harness for the end-to-end agent evaluations (off-script, paraphrase, clarification, cost).

Everything runs against the single policy source (sandbox records seeded into a temporary DB) and
can run with the LLM fully off (`use_llm=False`: rule planner, rule binder, template wording), which
is the default so no API quota is spent.
"""
from __future__ import annotations

import sys
import tempfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from clauseguard import llm  # noqa: E402
from clauseguard.agent.loop import Reply, handle_turn  # noqa: E402
from clauseguard.agent.session import Session  # noqa: E402
from clauseguard.agent.tools import PolicySource, ToolRouter  # noqa: E402

SANDBOX_USER = {"rizky": "C-RIZKY", "santoso": "C-BUDI", "dewi": "C-DEWI"}
DEFAULT_AS_OF = date(2026, 10, 11)
_ready = False


def setup_sandbox() -> None:
    """Point the sandbox tools at a fresh temporary DB seeded from sandbox/seed.py (once per process)."""
    global _ready
    if _ready:
        return
    from clauseguard.sandbox import db as sdb, tools as sb

    path = Path(tempfile.mkdtemp(prefix="cg_eval_")) / "eval.sqlite"
    sb.set_connection(sdb.init_db(seed=True, path=path))
    _ready = True


def disable_llm() -> None:
    def _no_llm(*a, **k):
        raise RuntimeError("LLM disabled for this run")

    llm.generate_json = _no_llm  # every LLM path falls back to its deterministic template


def new_session(persona: str, as_of: date = DEFAULT_AS_OF) -> tuple[Session, ToolRouter]:
    setup_sandbox()
    return Session(SANDBOX_USER[persona], persona, as_of=as_of), ToolRouter(PolicySource(mode="sandbox"))


def run_turns(persona: str, turns: list[str], as_of: date = DEFAULT_AS_OF, *, use_llm: bool = False) -> list[Reply]:
    s, router = new_session(persona, as_of)
    out = []
    for t in turns:
        try:
            out.append(handle_turn(s, t, router=router, use_llm=use_llm))
        except Exception as e:  # noqa: BLE001
            out.append(Reply(text=f"EXCEPTION: {type(e).__name__}: {e}", intent="OUT_OF_SCOPE", refused=True, refusal_reason="EXCEPTION"))
    return out


def ask(persona: str, text: str, as_of: date = DEFAULT_AS_OF, *, use_llm: bool = False) -> Reply:
    return run_turns(persona, [text], as_of, use_llm=use_llm)[0]


def signature(rep: Reply) -> dict:
    """The decision-relevant part of a reply: verdicts, payable, clarification slot, refusal."""
    return {
        "verdicts": {v.policy_id: (v.verdict.value, str(v.payable) if v.payable is not None else None) for v in rep.verdicts},
        "clarify": rep.clarification.slot.value if rep.clarification else None,
        "intent": rep.intent.value,
        "refused": bool(rep.refused),
        "cob": {s.payer_policy_id: (s.status, str(s.expected_amount)) for s in rep.cob},
        "deadline": rep.deadline.isoformat() if rep.deadline else None,
    }
