"""Hash-chained audit log in Postgres, plus the degraded-mode wrapper used when it is unreachable.

Hashing is delegated to security.audit (`_hash_event`, `canonical_json`) so a given event sequence
yields byte-identical hashes in the file and Postgres backends.

Degraded mode: when Postgres cannot be reached an event is appended to a local file chain
(`<audit path>.pgfallback`, its own genesis-rooted chain). On the next successful Postgres append the
wrapper first writes one AUDIT_GAP event into the Postgres chain recording the local segment's
count, first/last seq and head hash, then archives the local file. The Postgres chain therefore never
forks and the gap is a visible, hash-covered event; `verify_report` lists every gap and flags any
local events not yet anchored.
"""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Optional, Protocol

from .metrics import degraded
from .postgres import Pool, StorageError, default_pool

FALLBACK_SUFFIX = ".pgfallback"


class AuditStore(Protocol):
    def append_chained(self, event: dict[str, Any]) -> dict[str, Any]: ...
    def read_all(self) -> list[dict[str, Any]]: ...
    def head(self) -> tuple[int, str]: ...


def _stamp(event: dict[str, Any], seq: int, prev: str) -> dict[str, Any]:
    from ..security import audit

    ev: dict[str, Any] = {k: None for k in audit.FIELDS}
    ev.update(event)
    ev["seq"] = seq
    ev["ts_utc"] = audit.datetime.now(audit.timezone.utc).isoformat(timespec="milliseconds")
    ev["prev_hash"] = prev
    ev["hash"] = audit._hash_event(ev)
    return ev


class MemoryAuditStore:
    """In-process implementation of the same contract; used by the always-on tests."""

    def __init__(self) -> None:
        self._events: list[dict[str, Any]] = []
        self._lock = threading.Lock()

    def append_chained(self, event: dict[str, Any]) -> dict[str, Any]:
        from ..security import audit

        with self._lock:
            seq, prev = (self._events[-1]["seq"], self._events[-1]["hash"]) if self._events else (0, audit.GENESIS)
            ev = _stamp(event, seq + 1, prev)
            self._events.append(json.loads(audit.canonical_json(ev)))
            return ev

    def read_all(self) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(e) for e in self._events]

    def head(self) -> tuple[int, str]:
        from ..security import audit

        with self._lock:
            return (self._events[-1]["seq"], self._events[-1]["hash"]) if self._events else (0, audit.GENESIS)


class PgAuditStore:
    """The audit chain in Postgres, written behind the request.

    An event is chained in memory at once (sequence number and hash come from the head this process holds), so the
    caller never waits for the database. A single writer thread stores the queued events in order, in one
    transaction per batch, and only if the stored head still equals the batch's starting point. If another process
    advanced the chain meanwhile, the head is re-read and the still-queued events are chained again on top of it, so
    the chain in Postgres never forks. Reads flush the queue first; a process that is stopped flushes on the way out."""

    BATCH = 200

    def __init__(self, pool: Optional[Pool] = None) -> None:
        self._pool = pool
        self._head: Optional[tuple[int, str]] = None
        self._lock = threading.Lock()
        self._queue: list[dict[str, Any]] = []
        self._wake = threading.Event()
        self._drained = threading.Event()
        self._drained.set()
        self._writer: Optional[threading.Thread] = None

    @property
    def pool(self) -> Pool:
        return self._pool or default_pool()

    # -- hooks the tests replace
    def _read_head(self) -> tuple[int, str]:
        def work(conn):
            with conn.cursor() as cur:
                cur.execute("SELECT seq, hash FROM audit_head WHERE id = 1")
                r = cur.fetchone()
                if r is None:
                    raise StorageError("audit_head missing; apply migrations")
                return (int(r[0]), r[1])

        return self.pool.run(work, "audit")

    def _write_batch(self, batch: list[dict[str, Any]]) -> bool:
        """Store a batch whose first event chains onto the stored head. False if the stored head moved."""
        from psycopg2.extras import Json, execute_values

        from ..security import audit

        first, last = batch[0], batch[-1]

        def work(conn):
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE audit_head SET seq = %s, hash = %s WHERE id = 1 AND seq = %s AND hash = %s",
                    (last["seq"], last["hash"], first["seq"] - 1, first["prev_hash"]),
                )
                if cur.rowcount != 1:
                    return False
                execute_values(
                    cur,
                    "INSERT INTO audit_events (seq, prev_hash, hash, event, ts) VALUES %s",
                    [(e["seq"], e["prev_hash"], e["hash"], Json(e, dumps=audit.canonical_json), e["ts_utc"]) for e in batch],
                    template="(%s, %s, %s, %s, %s::timestamptz)",
                )
                return True

        return bool(self.pool.run(work, "audit"))

    # -- chain in memory, write behind
    def append_chained(self, event: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            if self._head is None:
                self._head = self._read_head()  # first event of this process: one blocking read
            seq, prev = self._head
            ev = _stamp(event, seq + 1, prev)
            self._head = (ev["seq"], ev["hash"])
            self._queue.append(ev)
            self._drained.clear()
            self._start_writer()
        self._wake.set()
        return ev

    def _start_writer(self) -> None:
        if self._writer is None or not self._writer.is_alive():
            self._writer = threading.Thread(target=self._run, name="audit-writer", daemon=True)
            self._writer.start()
            import atexit

            atexit.register(self.flush, 15.0)

    def _run(self) -> None:
        while True:
            self._wake.wait()
            with self._lock:
                batch = self._queue[: self.BATCH]
                if not batch:
                    self._wake.clear()
                    self._drained.set()
                    continue
            try:
                stored = self._write_batch(batch)
            except Exception as e:  # noqa: BLE001 - keep the events and try again; the database may be briefly unreachable
                degraded("audit", e)
                time.sleep(2.0)
                continue
            try:
                with self._lock:
                    if stored:
                        del self._queue[: len(batch)]
                    else:
                        self._rechain_locked()
                    if not self._queue:
                        self._wake.clear()
                        self._drained.set()
            except Exception as e:  # noqa: BLE001 - the head could not be re-read; the queue is kept and retried
                degraded("audit", e)
                time.sleep(2.0)

    def _rechain_locked(self) -> None:
        """Another process advanced the stored chain: chain the queued events again on top of it."""
        from ..security import audit

        seq, prev = self._read_head()
        for ev in self._queue:
            seq += 1
            ev["seq"], ev["prev_hash"] = seq, prev
            ev["hash"] = audit._hash_event(ev)
            prev = ev["hash"]
        self._head = (seq, prev)

    def flush(self, timeout: float = 60.0) -> bool:
        """Wait until everything queued is stored. True when the queue is empty."""
        return self._drained.wait(timeout)

    def read_all(self) -> list[dict[str, Any]]:
        self.flush()

        def work(conn):
            with conn.cursor() as cur:
                cur.execute("SELECT event FROM audit_events ORDER BY seq")
                return [r[0] for r in cur.fetchall()]

        return self.pool.run(work, "audit")

    def head(self) -> tuple[int, str]:
        self.flush()
        return self._read_head()


def verify_events(events: list[dict[str, Any]], head: Optional[tuple[int, str]] = None) -> dict[str, Any]:
    from ..security import audit

    prev = audit.GENESIS
    gaps: list[dict[str, Any]] = []
    for i, ev in enumerate(events, start=1):
        if ev.get("seq") != i or ev.get("prev_hash") != prev or audit._hash_event(ev) != ev.get("hash"):
            return {"ok": False, "first_bad_seq": i, "events": len(events), "gaps": gaps, "head_matches": None}
        if ev.get("event_type") == "AUDIT_GAP":
            gaps.append({"seq": i, "detail": ev.get("reason")})
        prev = ev["hash"]
    head_ok = None if head is None else head == (len(events), prev)
    ok = head_ok is not False
    return {"ok": ok, "first_bad_seq": None if ok else len(events) + 1, "events": len(events), "gaps": gaps, "head_matches": head_ok}


class ChainedAuditLog:
    def __init__(self, store: AuditStore) -> None:
        self.store = store

    def append(self, event: dict[str, Any]) -> dict[str, Any]:
        from ..security import audit

        if event.get("event_type") not in audit.EVENT_TYPES:
            raise ValueError(f"unknown event_type {event.get('event_type')!r}")
        return self.store.append_chained(event)

    def read(self) -> list[dict[str, Any]]:
        return self.store.read_all()

    def verify_report(self) -> dict[str, Any]:
        # The head is read BEFORE the events: reading thousands of rows is slow and other writers may append meanwhile.
        # The chain is walked over everything read, and the head taken earlier must be the hash of the event at its seq.
        head = self.store.head()
        events = self.store.read_all()
        rep = verify_events(events, None)
        rep["last_hash"] = events[-1]["hash"] if events else None
        if rep["ok"]:
            seq, hsh = head
            rep["head_matches"] = len(events) >= seq and (seq == 0 or events[seq - 1]["hash"] == hsh)
            if not rep["head_matches"]:
                rep["ok"] = False
                rep["first_bad_seq"] = min(seq, len(events)) or 1
        return rep


class DegradingAuditLog(ChainedAuditLog):
    """Postgres chain with a local-file fallback; see module docstring."""

    def __init__(self, store: AuditStore, local_path: Path) -> None:
        super().__init__(store)
        self.path = Path(local_path)
        self._fb_path = self.path.with_suffix(self.path.suffix + FALLBACK_SUFFIX)
        self._fb_lock = threading.Lock()

    def _fallback_log(self):
        from ..security import audit

        return audit.AuditLog(self._fb_path)

    def _report_gap(self) -> None:
        if not self._fb_path.exists():
            return
        local = self._fallback_log().read()
        if not local:
            return
        first, last = local[0], local[-1]
        archive = self._fb_path.with_name(self._fb_path.name + f".reported-{int(time.time() * 1000)}")
        try:
            os.replace(self._fb_path, archive)
        except OSError:
            return
        try:
            self.store.append_chained({
                "event_type": "AUDIT_GAP", "user_id": "system", "decision": "DISCONTINUITY",
                "doc_id": f"local:{first['seq']}-{last['seq']}",
                "reason": f"postgres unreachable; {len(local)} events held in local fallback chain, head={last['hash']}, first_ts={first['ts_utc']}, last_ts={last['ts_utc']}",
            })
        except Exception:
            try:
                os.replace(archive, self._fb_path)
            except OSError:
                pass
            raise

    def append(self, event: dict[str, Any]) -> dict[str, Any]:
        from ..security import audit

        if event.get("event_type") not in audit.EVENT_TYPES:
            raise ValueError(f"unknown event_type {event.get('event_type')!r}")
        with self._fb_lock:
            try:
                self._report_gap()
                return self.store.append_chained(event)
            except StorageError as e:
                degraded("audit", e)
                return self._fallback_log().append(event)

    def read(self) -> list[dict[str, Any]]:
        try:
            return self.store.read_all()
        except StorageError:
            return self._fallback_log().read()

    def verify_report(self) -> dict[str, Any]:
        rep = super().verify_report()
        pending = self._fallback_log().read() if self._fb_path.exists() else []
        rep["unreported_local_events"] = len(pending)
        if pending:
            rep["ok"] = False
            rep["reason"] = "events held only in the local fallback chain; not yet anchored in Postgres"
        return rep
