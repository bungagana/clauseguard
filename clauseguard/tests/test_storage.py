from __future__ import annotations

import json
import os
import secrets
from datetime import datetime, timezone

import pytest

from clauseguard import config
from clauseguard.security import audit
from clauseguard.storage import postgres_enabled
from clauseguard.storage.audit_backend import ChainedAuditLog, DegradingAuditLog, MemoryAuditStore, verify_events
from clauseguard.storage.postgres import StorageError

EVENTS = [
    {"event_type": "LOGIN", "session_id": "S-1", "user_id": "u1", "decision": "OK", "reason": "budi"},
    {"event_type": "USER_MSG", "session_id": "S-1", "user_id": "u1", "args_hash": "ab" * 32},
    {"event_type": "TOOL_ALLOW", "session_id": "S-1", "user_id": "u1", "tool": "gap_analysis", "tier": 1, "arg_labels": {"a": "USER_UPLOAD"}, "reason": "café — ok"},
]


class _Fixed(datetime):
    @classmethod
    def now(cls, tz=None):
        return datetime(2026, 10, 14, 1, 2, 3, 456000, tzinfo=timezone.utc)


@pytest.fixture
def fixed_clock(monkeypatch):
    monkeypatch.setattr(audit, "datetime", _Fixed)


def test_file_and_postgres_style_backends_produce_identical_hashes(tmp_path, fixed_clock):
    file_log = audit.AuditLog(tmp_path / "a.jsonl")
    mem_log = ChainedAuditLog(MemoryAuditStore())
    a = [file_log.append(dict(e)) for e in EVENTS]
    b = [mem_log.append(dict(e)) for e in EVENTS]
    assert [x["hash"] for x in a] == [x["hash"] for x in b]
    assert [x["prev_hash"] for x in a] == [x["prev_hash"] for x in b]
    assert verify_events(mem_log.read(), mem_log.store.head())["ok"]
    assert audit.verify(tmp_path / "a.jsonl") == (True, None)


def test_tampered_stored_event_is_detected():
    log = ChainedAuditLog(MemoryAuditStore())
    for e in EVENTS:
        log.append(dict(e))
    evs = log.read()
    evs[1]["decision"] = "APPROVED-BY-ATTACKER"
    rep = verify_events(evs, log.store.head())
    assert not rep["ok"] and rep["first_bad_seq"] == 2


def test_tail_truncation_is_detected_through_head():
    log = ChainedAuditLog(MemoryAuditStore())
    for e in EVENTS:
        log.append(dict(e))
    rep = verify_events(log.read()[:-1], log.store.head())
    assert not rep["ok"] and rep["head_matches"] is False


class _Flaky(MemoryAuditStore):
    def __init__(self):
        super().__init__()
        self.down = False

    def append_chained(self, event):
        if self.down:
            raise StorageError("down")
        return super().append_chained(event)

    def read_all(self):
        if self.down:
            raise StorageError("down")
        return super().read_all()


def test_outage_falls_back_locally_and_gap_is_anchored_on_recovery(tmp_path):
    store = _Flaky()
    log = DegradingAuditLog(store, tmp_path / "audit.jsonl")
    log.append(dict(EVENTS[0]))
    store.down = True
    log.append(dict(EVENTS[1]))
    log.append(dict(EVENTS[2]))
    assert len(log.read()) == 2
    store.down = False
    rep = log.verify_report()
    assert rep["ok"] is False and rep["unreported_local_events"] == 2
    log.append(dict(EVENTS[1]))
    rep = log.verify_report()
    assert rep["ok"] and rep["unreported_local_events"] == 0
    assert len(rep["gaps"]) == 1 and "2 events held in local fallback chain" in rep["gaps"][0]["detail"]
    events = store.read_all()
    assert [e["event_type"] for e in events] == ["LOGIN", "AUDIT_GAP", "USER_MSG"]
    local_head = json.loads(next((tmp_path).glob("audit.jsonl.pgfallback.reported-*")).read_text().splitlines()[-1])["hash"]
    assert local_head in events[1]["reason"]


def test_default_is_local_without_config(monkeypatch):
    monkeypatch.setattr(config, "STORAGE", "local")
    monkeypatch.setattr(config, "DATABASE_URL", "postgresql://x")
    assert not postgres_enabled()
    monkeypatch.setattr(config, "STORAGE", "postgres")
    monkeypatch.setattr(config, "DATABASE_URL", "")
    assert not postgres_enabled()


def test_mirror_is_noop_when_local(sandbox_db, monkeypatch):
    from clauseguard.storage import mirror

    called = []
    monkeypatch.setattr(mirror, "write_through", lambda *a, **k: called.append(a))
    mirror.mirror_claim(sandbox_db, "anything")
    assert called == []


def test_mirror_failure_never_raises(sandbox_db, monkeypatch):
    from clauseguard.storage import mirror

    monkeypatch.setattr(config, "STORAGE", "postgres")
    monkeypatch.setattr(config, "DATABASE_URL", "postgresql://u:p@127.0.0.1:1/x")
    from clauseguard.storage import postgres

    monkeypatch.setattr(postgres, "_default", postgres.Pool(url="postgresql://u:p@127.0.0.1:1/x"))
    sandbox_db.execute("INSERT INTO tickets(id,customer_id,type,status) VALUES ('TK-T1','c','CALLBACK','OPEN')")
    mirror.mirror_ticket(sandbox_db, "TK-T1")
    from clauseguard.storage import counters

    assert counters().get("storage_degraded", 0) >= 1


PG = bool(config.DATABASE_URL) and os.getenv("CG_RUN_PG_TESTS") == "1"


@pytest.mark.skipif(not PG, reason="needs DATABASE_URL and CG_RUN_PG_TESTS=1")
def test_postgres_chain_matches_file_hashes_in_throwaway_schema(tmp_path, fixed_clock):
    from psycopg2 import sql

    from clauseguard.storage.audit_backend import PgAuditStore
    from clauseguard.storage.postgres import Pool
    from scripts.apply_migration import apply

    schema = f"test_{secrets.token_hex(4)}"
    admin = Pool()
    admin.run(lambda c: c.cursor().execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema))), "test")
    try:
        pool = Pool(schema=schema)
        apply(pool)
        pg = ChainedAuditLog(PgAuditStore(pool))
        file_log = audit.AuditLog(tmp_path / "f.jsonl")
        a = [file_log.append(dict(e))["hash"] for e in EVENTS]
        b = [pg.append(dict(e))["hash"] for e in EVENTS]
        assert a == b
        assert pg.verify_report()["ok"]
        assert [e["hash"] for e in pg.read()] == a
    finally:
        admin.run(lambda c: c.cursor().execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema))), "test")
