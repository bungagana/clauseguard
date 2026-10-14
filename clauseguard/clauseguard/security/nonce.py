"""Confirmation nonces for T2 tools (R7).

Security guarantee: a T2 call only runs if it carries a token that the *server* issued after
the user clicked "confirm" in the UI. The token is bound to (session, tool, args-hash), is
single-use, and expires after `ttl` seconds. The planner LLM never sees the issuing path, so
it cannot fabricate one; replaying a used token or changing the arguments after
confirmation fails verification.
"""
from __future__ import annotations

import hashlib
import json
import secrets
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional

DEFAULT_TTL = 300


def args_hash(args: dict[str, Any]) -> str:
    """Canonical hash of the arguments the user confirmed (confirm_token itself excluded)."""
    clean = {k: v for k, v in args.items() if k != "confirm_token"}
    return hashlib.sha256(json.dumps(clean, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")).hexdigest()


@dataclass
class _Record:
    session_id: str
    tool: str
    args_hash: str
    expires_at: float
    used: bool = False


class NonceStore:
    def __init__(self, clock: Callable[[], float] = time.time) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        self._records: dict[str, _Record] = {}

    def issue(self, session_id: str, tool: str, args_hash: str, ttl: int = DEFAULT_TTL) -> str:
        token = secrets.token_urlsafe(24)
        with self._lock:
            self._records[token] = _Record(session_id, tool, args_hash, self._clock() + ttl)
        return token

    def verify(self, token: Optional[str], session_id: str, tool: str, args_hash: str) -> bool:
        """True exactly once per token, only for the same (session, tool, args) and before expiry."""
        if not token:
            return False
        with self._lock:
            rec = self._records.get(token)
            if rec is None or rec.used:
                return False
            if self._clock() > rec.expires_at:
                del self._records[token]
                return False
            if rec.session_id != session_id or rec.tool != tool or rec.args_hash != args_hash:
                return False
            rec.used = True  # single use
            return True

    def purge(self) -> int:
        now = self._clock()
        with self._lock:
            dead = [t for t, r in self._records.items() if r.used or r.expires_at < now]
            for t in dead:
                del self._records[t]
        return len(dead)


_DEFAULT = NonceStore()


def issue(session_id: str, tool: str, args_hash: str, ttl: int = DEFAULT_TTL) -> str:
    return _DEFAULT.issue(session_id, tool, args_hash, ttl)


def verify(token: Optional[str], session_id: str, tool: str, args_hash: str) -> bool:
    return _DEFAULT.verify(token, session_id, tool, args_hash)
