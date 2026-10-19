"""List and prune saved chat history in the hosted Postgres database.

  python scripts/prune_history.py list                      # every conversation, grouped by persona
  python scripts/prune_history.py keep ID1 ID2 ...          # dry run: what would be deleted
  python scripts/prune_history.py keep ID1 ID2 ... --apply  # delete everything except these ids
  python scripts/prune_history.py rename ID "New title"     # change one conversation title
  python scripts/prune_history.py setpersona USER_ID persona # fill in a missing persona for one account

Reads DATABASE_URL from the environment (or .env). Only the `conversations` table is touched.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from clauseguard.storage.postgres import default_pool  # noqa: E402


def rows():
    def work(conn):
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, user_id, persona, title, updated_at, jsonb_array_length(messages) "
                "FROM conversations ORDER BY persona, updated_at DESC")
            return cur.fetchall()
    return default_pool().run(work, "history")


def when(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, timezone.utc).strftime("%Y-%m-%d %H:%M")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["list", "keep", "rename", "setpersona"])
    ap.add_argument("ids", nargs="*")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    if a.cmd == "rename":
        cid, title = a.ids[0], a.ids[1]

        def upd(conn):
            with conn.cursor() as cur:
                cur.execute("UPDATE conversations SET title = %s WHERE id = %s", (title[:200], cid))
                return cur.rowcount
        print("renamed", default_pool().run(upd, "history"))
        return

    if a.cmd == "setpersona":
        uid, persona = a.ids[0], a.ids[1]

        def fix(conn):
            with conn.cursor() as cur:
                cur.execute("UPDATE conversations SET persona = %s WHERE user_id = %s AND persona = ''", (persona, uid))
                return cur.rowcount
        print("updated", default_pool().run(fix, "history"))
        return

    data = rows()
    print(f"{len(data)} conversations")
    for cid, uid, persona, title, upd, n in data:
        mark = "" if a.cmd == "list" else ("KEEP  " if cid in a.ids else "DELETE")
        print(f"{mark:6} {persona:12} {cid}  {when(upd)}  {n:3} msgs  user={uid[:8]}  {title[:50]}")
    if a.cmd == "list":
        return

    unknown = [i for i in a.ids if i not in {r[0] for r in data}]
    if unknown:
        sys.exit(f"unknown ids: {unknown}")
    doomed = [r[0] for r in data if r[0] not in a.ids]
    print(f"\nkeep {len(a.ids)}, delete {len(doomed)}")
    if not a.apply:
        print("dry run, nothing deleted. Add --apply to delete.")
        return

    def work(conn):
        with conn.cursor() as cur:
            cur.execute("DELETE FROM conversations WHERE id = ANY(%s)", (doomed,))
            return cur.rowcount
    print("deleted", default_pool().run(work, "history"))


if __name__ == "__main__":
    main()
