"""Shared fixtures: isolate the audit log, kill switch and sandbox DB in a temp directory."""
from __future__ import annotations

import pytest

from clauseguard import config
from clauseguard.security import audit, kill_switch


@pytest.fixture
def isolated_paths(tmp_path, monkeypatch):
    """Point audit/kill-switch/DB at tmp so tests never touch evidence/ or data/sandbox.sqlite."""
    monkeypatch.setattr(config, "AUDIT_PATH", tmp_path / "audit.jsonl")
    monkeypatch.setattr(config, "KILL_SWITCH_PATH", tmp_path / "AGENT_HALT")
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "sandbox.sqlite")
    monkeypatch.setattr(config, "STORAGE", "local")  # tests always isolate to tmp_path, never the real Postgres/Supabase audit
    monkeypatch.delenv(kill_switch.ENV_FLAG, raising=False)
    audit._default = None
    yield tmp_path
    audit._default = None


@pytest.fixture
def sandbox_db(isolated_paths):
    from clauseguard.sandbox import db, tools

    conn = db.init_db(seed=True, path=isolated_paths / "sandbox.sqlite", fresh=True)
    tools.set_connection(conn)
    yield conn
    tools.set_connection(None)
    conn.close()


@pytest.fixture(autouse=True)
def _never_touch_the_real_kill_switch(tmp_path, monkeypatch):
    """Every test gets a private kill-switch flag and a cleared CG_AGENT_HALT. The real flag
    (evidence/AGENT_HALT) is shared with the live backend and with scripts/run_tasks.py, so a
    test that activates it, or that runs while an operator has it on, would leak across processes."""
    monkeypatch.setattr(config, "KILL_SWITCH_PATH", tmp_path / "AGENT_HALT_autouse")
    monkeypatch.delenv(kill_switch.ENV_FLAG, raising=False)
    yield


@pytest.fixture(autouse=True)
def _test_admin_token(monkeypatch):
    """Tests get a fixed, test-only admin token instead of relying on a production default."""
    monkeypatch.setattr(config, "ADMIN_TOKEN", "test-only-admin-token")


@pytest.fixture(autouse=True)
def _never_write_the_evidence_audit_log(tmp_path, monkeypatch):
    """The agent-loop tests append audit events; keep them out of evidence/audit_log.jsonl (that file is a
    hash chain shared with other runs, and concurrent appenders from several processes interleave and break it)."""
    monkeypatch.setattr(config, "AUDIT_PATH", tmp_path / "audit_autouse.jsonl")
    audit._default = None
    yield
    audit._default = None
