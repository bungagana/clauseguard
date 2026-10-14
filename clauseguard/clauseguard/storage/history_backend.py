from __future__ import annotations

import json
from typing import Any, Optional

from .postgres import Pool, default_pool


class PgHistory:
    def __init__(self, pool: Optional[Pool] = None) -> None:
        self._pool = pool

    @property
    def pool(self) -> Pool:
        return self._pool or default_pool()

    def list_for_user(self, user_id: str) -> list[dict[str, Any]]:
        def work(conn):
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, persona, title, created_at, updated_at, jsonb_array_length(messages) FROM conversations "
                    "WHERE user_id = %s ORDER BY updated_at DESC, id DESC", (user_id,))
                return [dict(id=r[0], persona=r[1], title=r[2], created_at=r[3], updated_at=r[4], message_count=r[5]) for r in cur.fetchall()]

        return self.pool.run(work, "history")

    def get(self, user_id: str, conversation_id: str) -> Optional[dict[str, Any]]:
        def work(conn):
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, persona, title, created_at, updated_at, messages FROM conversations WHERE id = %s AND user_id = %s",
                    (conversation_id, user_id))
                r = cur.fetchone()
                if r is None:
                    return None
                return dict(id=r[0], persona=r[1], title=r[2], created_at=r[3], updated_at=r[4], messages_json=json.dumps(r[5], ensure_ascii=False))

        return self.pool.run(work, "history")

    def upsert(self, user_id: str, persona: str, conversation_id: str, title: str, messages_json: str,
               created_at: int, updated_at: int, max_per_user: int) -> Optional[dict[str, Any]]:
        def work(conn):
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO conversations (id, user_id, persona, title, created_at, updated_at, messages) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb) "
                    "ON CONFLICT (id) DO UPDATE SET persona = EXCLUDED.persona, title = EXCLUDED.title, "
                    "updated_at = EXCLUDED.updated_at, messages = EXCLUDED.messages WHERE conversations.user_id = EXCLUDED.user_id "
                    "RETURNING (xmax = 0)",
                    (conversation_id, user_id, persona, title, created_at, updated_at, messages_json))
                r = cur.fetchone()
                if r is None:
                    return None
                cur.execute(
                    "DELETE FROM conversations WHERE user_id = %s AND id IN ("
                    "SELECT id FROM conversations WHERE user_id = %s ORDER BY updated_at DESC, id DESC OFFSET %s)",
                    (user_id, user_id, max_per_user))
                return {"created": bool(r[0]), "evicted": cur.rowcount}

        return self.pool.run(work, "history")

    def rename(self, user_id: str, conversation_id: str, title: str) -> bool:
        def work(conn):
            with conn.cursor() as cur:
                cur.execute("UPDATE conversations SET title = %s WHERE id = %s AND user_id = %s", (title, conversation_id, user_id))
                return cur.rowcount > 0

        return self.pool.run(work, "history")

    def delete(self, user_id: str, conversation_id: str) -> bool:
        def work(conn):
            with conn.cursor() as cur:
                cur.execute("DELETE FROM conversations WHERE id = %s AND user_id = %s", (conversation_id, user_id))
                return cur.rowcount > 0

        return self.pool.run(work, "history")

    def clear(self, user_id: str) -> int:
        def work(conn):
            with conn.cursor() as cur:
                cur.execute("DELETE FROM conversations WHERE user_id = %s", (user_id,))
                return cur.rowcount

        return self.pool.run(work, "history")
