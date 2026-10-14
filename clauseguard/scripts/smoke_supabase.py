"""End-to-end smoke against the database in DATABASE_URL, isolated in a throwaway schema.

Creates schema smoke_<random> with the production DDL, exercises audit (4 processes), history and
claims write-through, then drops the schema so the public evidence tables are never touched.
"""
from __future__ import annotations

import json
import multiprocessing as mp
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _worker(args: tuple[str, int, int]) -> int:
    schema, wid, n = args
    from clauseguard.storage.audit_backend import ChainedAuditLog, PgAuditStore
    from clauseguard.storage.postgres import Pool

    log = ChainedAuditLog(PgAuditStore(Pool(schema=schema)))
    for i in range(n):
        log.append({"event_type": "USER_MSG", "session_id": f"smoke-{wid}", "user_id": f"w{wid}", "reason": f"event {i}"})
    return n


def main() -> int:
    from psycopg2 import sql

    from clauseguard.storage.audit_backend import ChainedAuditLog, PgAuditStore
    from clauseguard.storage.history_backend import PgHistory
    from clauseguard.storage.mirror import write_through
    from clauseguard.storage.postgres import Pool

    schema = f"smoke_{secrets.token_hex(4)}"
    admin = Pool()
    admin.run(lambda c: c.cursor().execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema))), "smoke")
    ok = True
    try:
        from scripts.apply_migration import apply

        apply(Pool(schema=schema))
        pool = Pool(schema=schema)

        with mp.get_context("spawn").Pool(4) as p:
            done = sum(p.map(_worker, [(schema, w, 5) for w in range(4)]))
        rep = ChainedAuditLog(PgAuditStore(pool)).verify_report()
        print(f"audit: wrote={done} events={rep['events']} chain_ok={rep['ok']} head_matches={rep['head_matches']}")
        ok &= rep["ok"] and rep["events"] == 20

        h = PgHistory(pool)
        msgs = json.dumps([{"role": "user", "text": "halo"}], ensure_ascii=False)
        r1 = h.upsert("u1", "budi", "conv-smoke-1", "judul", msgs, 1000, 2000, 200)
        r2 = h.upsert("u2", "budi", "conv-smoke-1", "hijack", msgs, 1000, 2000, 200)
        got = h.get("u1", "conv-smoke-1")
        stolen = h.get("u2", "conv-smoke-1")
        listed = h.list_for_user("u1")
        deleted = h.delete("u1", "conv-smoke-1")
        gone = h.get("u1", "conv-smoke-1")
        print(f"history: create={r1} cross_user_upsert={r2} get_ok={got is not None and json.loads(got['messages_json'])[0]['text']=='halo'} "
              f"cross_user_get={stolen} listed={len(listed)} deleted={deleted} after_delete={gone}")
        ok &= bool(r1 and r1["created"] and r2 is None and got and stolen is None and len(listed) == 1 and deleted and gone is None)

        wrote = write_through("claims_log", {"id": "CL-SMOKE01", "policy_id": "P1", "customer_id": "C1", "status": "submitted", "claim_amount": 1000}, pool)
        wrote2 = write_through("claims_log", {"id": "CL-SMOKE01", "policy_id": "P1", "customer_id": "C1", "status": "approved", "claim_amount": 1000}, pool)
        wt = write_through("tickets_log", {"id": "TK-SMOKE01", "customer_id": "C1", "type": "CALLBACK", "status": "OPEN"}, pool)
        status = pool.run(lambda c: _one(c, "SELECT status FROM claims_log WHERE id = 'CL-SMOKE01'"), "smoke")
        print(f"claims: first={wrote} upsert={wrote2} ticket={wt} final_status={status}")
        ok &= wrote and wrote2 and wt and status == "approved"
    finally:
        admin.run(lambda c: c.cursor().execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema))), "smoke")
        left = admin.run(lambda c: _one(c, "SELECT count(*) FROM information_schema.schemata WHERE schema_name = %s", (schema,)), "smoke")
        print(f"cleanup: schema dropped, remaining={left}")
        public_head = admin.run(lambda c: _one(c, "SELECT seq FROM public.audit_head WHERE id = 1"), "smoke")
        print(f"public.audit_head.seq={public_head}")
    print("SMOKE:", "PASSED" if ok else "FAILED")
    return 0 if ok else 1


def _one(conn, query, params=()):
    with conn.cursor() as cur:
        cur.execute(query, params)
        return cur.fetchone()[0]


if __name__ == "__main__":
    mp.freeze_support()
    raise SystemExit(main())
