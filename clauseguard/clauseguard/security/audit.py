"""Hash-chained JSONL audit log.

Security guarantee: tamper-*evidence*. Every event carries `prev_hash` (hash of the previous
line, genesis = 64 zeros) and `hash = sha256(prev_hash + canonical_json(fields except hash))`.
Editing, deleting or reordering any line breaks the chain at that `seq`, which
`verify()` (and scripts/verify_audit.py) reports. Raw PII never enters the log: arguments
are stored as `args_hash`, labels as names.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Union

from .. import config

GENESIS = "0" * 64

EVENT_TYPES = {
    "USER_MSG", "PLAN", "TOOL_ALLOW", "TOOL_DENY", "TOOL_RESULT", "CONFIRM_ISSUED", "CONFIRM_USED",
    "DOC_INGEST", "DOC_SUSPICIOUS", "REPLY", "OUTPUT_GUARD", "COMPOSER_REJECTED", "KILL_SWITCH", "ESCALATE", "DX_ATTEMPT", "LOGIN",
    "HISTORY_SAVE", "HISTORY_READ", "HISTORY_DELETE", "HISTORY_CLEAR", "CLAIM_PLAN", "APPEAL", "INSURER_DECISION", "DIGEST", "AUDIT_GAP",
    "PII_BLOCKED", "PII_REDACTION_DEGRADED", "ADMIN_ACTION", "EXPORT_PDF", "AUTONOMY_SET", "CLOCK_MOVED",
}

FIELDS = (
    "seq", "ts_utc", "session_id", "user_id", "event_type", "tool", "tier", "args_hash", "arg_labels",
    "decision", "reason", "doc_id", "model", "prompt_hash", "prev_hash",
)


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)


def _hash_event(ev: dict[str, Any]) -> str:
    body = {k: v for k, v in ev.items() if k != "hash"}
    return hashlib.sha256((ev["prev_hash"] + canonical_json(body)).encode("utf-8")).hexdigest()


class _ProcessLock:
    """Cross-process advisory lock (a thread lock alone lets two processes interleave lines
    and silently break the hash chain). msvcrt on Windows, fcntl elsewhere."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._fh = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = open(self.path, "a+b")
        deadline = time.time() + 30
        while True:
            try:
                if os.name == "nt":
                    import msvcrt

                    self._fh.seek(0)
                    msvcrt.locking(self._fh.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(self._fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                return self
            except OSError:
                if time.time() > deadline:
                    raise TimeoutError("audit log lock timeout")
                time.sleep(0.01)

    def __exit__(self, *exc):
        try:
            if os.name == "nt":
                import msvcrt

                self._fh.seek(0)
                msvcrt.locking(self._fh.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self._fh.fileno(), fcntl.LOCK_UN)
        finally:
            self._fh.close()


class AuditLog:
    def __init__(self, path: Union[str, Path]) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()

    def _last(self) -> tuple[int, str]:
        if not self.path.exists():
            return 0, GENESIS
        last_line = None
        with self.path.open("rb") as f:
            for raw in f:
                if raw.strip():
                    last_line = raw
        if last_line is None:
            return 0, GENESIS
        ev = json.loads(last_line.decode("utf-8"))
        return int(ev["seq"]), ev["hash"]

    def append(self, event: dict[str, Any]) -> dict[str, Any]:
        """Append one event; unknown keys are kept (extra context), standard fields are always present."""
        et = event.get("event_type")
        if et not in EVENT_TYPES:
            raise ValueError(f"unknown event_type {et!r}")
        with self._lock, _ProcessLock(self.path.with_suffix(self.path.suffix + ".lock")):
            seq, prev = self._last()
            ev: dict[str, Any] = {k: None for k in FIELDS}
            ev.update(event)
            ev["seq"] = seq + 1
            ev["ts_utc"] = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
            ev["prev_hash"] = prev
            ev["hash"] = _hash_event(ev)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as f:
                f.write(canonical_json(ev) + "\n")
            return ev

    def read(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        out = []
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    out.append(json.loads(line))
        return out


def verify(path: Union[str, Path]) -> tuple[bool, Optional[int]]:
    """Re-walk the chain. Returns (ok, first_bad_seq). A missing/empty file is OK (seq None)."""
    p = Path(path)
    if _use_postgres() and p == Path(config.AUDIT_PATH):
        rep = get_default().verify_report()
        return rep["ok"], rep["first_bad_seq"]
    if not p.exists():
        return True, None
    prev = GENESIS
    expected_seq = 1
    with p.open("r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, start=1):
            if not line.strip():
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                return False, expected_seq
            if ev.get("seq") != expected_seq or ev.get("prev_hash") != prev:
                return False, expected_seq
            if _hash_event(ev) != ev.get("hash"):
                return False, expected_seq
            prev = ev["hash"]
            expected_seq += 1
    return True, None


_default: Optional[AuditLog] = None


def get_default() -> AuditLog:
    global _default
    if _default is None or _default.path != Path(config.AUDIT_PATH):
        if _use_postgres():
            from ..storage.audit_backend import DegradingAuditLog, PgAuditStore

            _default = DegradingAuditLog(PgAuditStore(), Path(config.AUDIT_PATH))
        else:
            _default = AuditLog(config.AUDIT_PATH)
    return _default


def _use_postgres() -> bool:
    from .. import storage

    return storage.postgres_enabled()


def append(event: dict[str, Any]) -> dict[str, Any]:
    return get_default().append(event)
