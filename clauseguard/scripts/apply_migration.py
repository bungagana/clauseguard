"""Apply deploy/migrations/*.sql to the database in DATABASE_URL (idempotent).

Usage: python scripts/apply_migration.py [--schema NAME]
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from clauseguard.storage.postgres import Pool, StorageError  # noqa: E402


def apply(pool: Pool) -> list[str]:
    done = []
    for f in sorted((ROOT / "deploy" / "migrations").glob("*.sql")):
        sql = f.read_text(encoding="utf-8")

        def work(conn, sql=sql):
            with conn.cursor() as cur:
                cur.execute(sql)

        pool.run(work, "migrate")
        done.append(f.name)
    return done


def main(argv: list[str]) -> int:
    schema = argv[argv.index("--schema") + 1] if "--schema" in argv else None
    try:
        names = apply(Pool(schema=schema))
    except StorageError as e:
        print(f"migration failed: {e}")
        return 1
    print("applied:", ", ".join(names), f"(schema={schema or 'default'})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
