"""Global kill switch (R6).

Security guarantee: when the flag file at `config.KILL_SWITCH_PATH` exists (or the env var
CG_AGENT_HALT=1 is set), the PEP refuses every tool above T0 and the agent replies with the
"assistant paused" template. The flag is checked on every call, so activation takes
effect immediately for all sessions without a restart. Activation paths: this module's
`activate()`, the `/admin/kill` endpoint (admin token, not in the agent registry) and the
CLI `python -m clauseguard.security.kill_switch on|off|status`.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Union

from .. import config

ENV_FLAG = "CG_AGENT_HALT"
PAUSED_REPLY = "The assistant is paused by the operator. Only read-only information is available right now."


def _path(path: Optional[Union[str, Path]] = None) -> Path:
    return Path(path) if path is not None else Path(config.KILL_SWITCH_PATH)


def is_active(path: Optional[Union[str, Path]] = None) -> bool:
    if os.getenv(ENV_FLAG, "") in ("1", "true", "TRUE", "yes"):
        return True
    return _path(path).exists()


def activate(reason: str = "", actor: str = "admin", path: Optional[Union[str, Path]] = None) -> None:
    p = _path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"{datetime.now(timezone.utc).isoformat()} {actor}: {reason}\n", encoding="utf-8")
    _log("KILL_SWITCH", "ACTIVATE", reason, actor)


def deactivate(actor: str = "admin", path: Optional[Union[str, Path]] = None) -> None:
    p = _path(path)
    if p.exists():
        p.unlink()
    _log("KILL_SWITCH", "DEACTIVATE", "", actor)


def _log(event_type: str, decision: str, reason: str, actor: str) -> None:
    try:
        from . import audit

        audit.append({"event_type": event_type, "decision": decision, "reason": reason[:200], "user_id": actor})
    except Exception:  # the switch must work even if the log is unavailable
        pass


def main(argv: Optional[list[str]] = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    cmd = argv[0] if argv else "status"
    if cmd == "on":
        activate(" ".join(argv[1:]) or "cli")
        print("kill switch ACTIVE")
    elif cmd == "off":
        deactivate()
        print("kill switch cleared")
    else:
        print("ACTIVE" if is_active() else "inactive")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
