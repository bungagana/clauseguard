"""One source of truth for the persona policies, and the task suites that run on it."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from clauseguard.agent import demo_fixtures
from clauseguard.agent.tools import PolicySource
from clauseguard.agent.session import Session
from clauseguard.sandbox import db as sdb, persona_policies as pp, seed as sseed, tools as sb

ROOT = Path(__file__).resolve().parents[1]
USER = {"rizky": "C-RIZKY", "santoso": "C-BUDI", "dewi": "C-DEWI"}


@pytest.fixture()
def temp_db(tmp_path):
    conn = sdb.init_db(seed=True, path=tmp_path / "t.sqlite")
    sb.set_connection(conn)
    yield conn
    sb.set_connection(None)


def _load_run_tasks():
    spec = importlib.util.spec_from_file_location("run_tasks_mod", ROOT / "scripts" / "run_tasks.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["run_tasks_mod"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_holdings_table_matches_the_sandbox_policy_rows(temp_db):
    for persona, user in USER.items():
        rows = sb.owned_policy_rows(user)
        db = sorted((r["id"], r["record_id"], r["status"]) for r in rows)
        assert db == sorted(pp.PERSONA_HOLDINGS[persona]), persona


def test_persona_meta_keys_are_real_policy_ids_and_payments_match_the_db(temp_db):
    for persona, user in USER.items():
        held = {pid for pid, _r, _s in pp.PERSONA_HOLDINGS[persona]}
        meta = pp.PERSONA_META[persona]
        assert set(meta["insured"]) <= held and meta["bpjs"]["policy_id"] in held
        for pid, pay in meta["payments"].items():
            unpaid = [r for r in sb._rows("SELECT due_date, paid_date FROM payments WHERE policy_id=? ORDER BY due_date", pid) if r["paid_date"] is None]
            if pay.get("paid_date") is None:
                assert unpaid and unpaid[0]["due_date"] == pay["due_date"], pid
            else:
                assert not unpaid, pid


def test_database_and_database_free_policy_sources_agree(temp_db):
    for persona, user in USER.items():
        with_db = PolicySource(mode="sandbox").policies_for(Session(user, persona))
        no_db = PolicySource(mode="fixtures").policies_for(Session(persona, persona))
        assert [p.id for p in with_db] == [p.id for p in no_db]
        assert [p.model_dump_json() for p in with_db] == [p.model_dump_json() for p in no_db]


def test_every_persona_policy_has_a_json_record_and_ci_is_seeded(temp_db):
    assert {"CI-CHUBB-05"} <= set(pp.build_policy_records())
    assert any(r["id"] == "CI-CHUBB-05" and r["customer_id"] == "C-RIZKY" for r in sb.owned_policy_rows("C-RIZKY"))
    assert (sseed.POLICY_DIR / "CI-CHUBB-05.json").exists()


def test_demo_fixtures_is_a_thin_reexport_of_the_persona_records():
    assert demo_fixtures.PERSONA_META is pp.PERSONA_META
    assert demo_fixtures.hcp_sompo().model_dump_json() == pp.hcp_sompo_01().model_dump_json()
    b = demo_fixtures.bpjs_kes("BPJS-KES-X", "lapsed")
    assert b.id == "BPJS-KES-X" and b.status == "lapsed" and all(t.policy_id == "BPJS-KES-X" for t in b.tuples)
    assert [p.id for p in demo_fixtures.persona_policies("dewi")] == ["PA-CHUBB-03", "PLATFORM-ACC", "BPJS-KES-DEWI", "JASA-RAHARJA"]
    assert demo_fixtures.platform_acc().product_type == "platform_accident"  # non-group flag (not a group scheme)


def test_run_tasks_source_fixtures_is_an_alias_of_sandbox(tmp_path, monkeypatch):
    rt = _load_run_tasks()
    from clauseguard import llm

    real = llm.generate_json
    monkeypatch.setitem(rt.SUITES, "main", (rt.TASK_DIR, tmp_path / "r.md", tmp_path / "r.jsonl"))
    monkeypatch.setattr(sys, "argv", ["run_tasks.py", "--no-llm", "--source", "fixtures", "--only", "T01", "T21"])
    try:
        assert rt.main() == 0
    finally:
        llm.generate_json = real
        sb.set_connection(None)
    report = (tmp_path / "r.md").read_text(encoding="utf8")
    assert "2/2 tasks passed" in report and "policy source: sandbox" in report


@pytest.mark.parametrize("suite, expected_n", [("main", 33), ("off_script", 15), ("holdout", 10)])
def test_scripted_suites_pass_on_the_sandbox_source(suite, expected_n, tmp_path):
    rt = _load_run_tasks()
    from clauseguard import llm

    real = llm.generate_json
    llm.generate_json = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("LLM disabled for this test"))
    conn = sdb.init_db(seed=True, path=tmp_path / "suite.sqlite")
    sb.set_connection(conn)
    try:
        tasks = rt.load_tasks(None, rt.SUITES[suite][0])
        assert len(tasks) == expected_n
        results = [rt.run_task(t, use_llm=False, source_mode="sandbox") for t in tasks]
    finally:
        llm.generate_json = real
        sb.set_connection(None)
    failed = [(r["id"], r["fails"]) for r in results if not r["passed"]]
    assert not failed, failed
