"""Per-user conversation history, in its own SQLite file (never the sandbox DB, never seeded or reset).

Every read and write takes the owning `user_id` and filters on it in SQL; a row that belongs to
someone else is indistinguishable from a row that does not exist.
"""
from __future__ import annotations

import re
import sqlite3
import threading
import time
from contextlib import closing
from pathlib import Path
from typing import Any, Optional

from .. import config

MAX_TITLE_CHARS = 200
MAX_MESSAGES_BYTES = 2 * 1024 * 1024
MAX_PER_USER = 200
ID_RE = re.compile(r"^[A-Za-z0-9_-]{6,64}$")

_LOCK = threading.Lock()

_SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    persona TEXT NOT NULL,
    title TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    messages_json TEXT NOT NULL,
    sample INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_conversations_user_updated ON conversations (user_id, updated_at DESC);
"""


def valid_id(conversation_id: str) -> bool:
    return bool(ID_RE.match(conversation_id))


def _path() -> Path:
    return Path(config.HISTORY_DB_PATH)


def _connect() -> sqlite3.Connection:
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=15, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.executescript(_SCHEMA)
    return conn


def _now_ms() -> int:
    return int(time.time() * 1000)


_MISS = object()


def _via_pg(method: str, *args: Any) -> Any:
    from .. import storage

    if not storage.postgres_enabled():
        return _MISS
    from ..storage.history_backend import PgHistory
    from ..storage.postgres import StorageError

    try:
        return getattr(PgHistory(), method)(*args)
    except StorageError:
        return _MISS


def list_for_user(user_id: str) -> list[dict[str, Any]]:
    r = _via_pg("list_for_user", user_id)
    if r is not _MISS:
        return r
    with _LOCK, closing(_connect()) as conn:
        rows = conn.execute(
            "SELECT id, persona, title, created_at, updated_at, json_array_length(messages_json) AS message_count "
            "FROM conversations WHERE user_id = ? ORDER BY updated_at DESC, id DESC",
            (user_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def get(user_id: str, conversation_id: str) -> Optional[dict[str, Any]]:
    r = _via_pg("get", user_id, conversation_id)
    if r is not _MISS:
        return r
    with _LOCK, closing(_connect()) as conn:
        row = conn.execute(
            "SELECT id, persona, title, created_at, updated_at, messages_json FROM conversations WHERE id = ? AND user_id = ?",
            (conversation_id, user_id),
        ).fetchone()
    return dict(row) if row else None


def upsert(
    user_id: str,
    persona: str,
    conversation_id: str,
    title: str,
    messages_json: str,
    created_at: Optional[int] = None,
    updated_at: Optional[int] = None,
) -> Optional[dict[str, Any]]:
    """Returns {"created": bool, "evicted": int}, or None when the id belongs to another user."""
    now = _now_ms()
    updated = min(updated_at, now + 86_400_000) if updated_at else now
    r = _via_pg("upsert", user_id, persona, conversation_id, title, messages_json, created_at or updated, updated, MAX_PER_USER)
    if r is not _MISS:
        return r
    with _LOCK, closing(_connect()) as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            owner = conn.execute("SELECT user_id FROM conversations WHERE id = ?", (conversation_id,)).fetchone()
            if owner is not None and owner["user_id"] != user_id:
                conn.execute("ROLLBACK")
                return None
            if owner is None:
                conn.execute(
                    "INSERT INTO conversations (id, user_id, persona, title, created_at, updated_at, messages_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (conversation_id, user_id, persona, title, created_at or updated, updated, messages_json),
                )
            else:
                conn.execute(
                    "UPDATE conversations SET persona = ?, title = ?, updated_at = ?, messages_json = ? WHERE id = ? AND user_id = ?",
                    (persona, title, updated, messages_json, conversation_id, user_id),
                )
            evicted = conn.execute(
                "DELETE FROM conversations WHERE user_id = ? AND id IN ("
                "SELECT id FROM conversations WHERE user_id = ? ORDER BY updated_at DESC, id DESC LIMIT -1 OFFSET ?)",
                (user_id, user_id, MAX_PER_USER),
            ).rowcount
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
    return {"created": owner is None, "evicted": evicted}


def rename(user_id: str, conversation_id: str, title: str) -> bool:
    r = _via_pg("rename", user_id, conversation_id, title)
    if r is not _MISS:
        return r
    with _LOCK, closing(_connect()) as conn:
        cur = conn.execute("UPDATE conversations SET title = ? WHERE id = ? AND user_id = ?", (title, conversation_id, user_id))
        return cur.rowcount > 0


def delete(user_id: str, conversation_id: str) -> bool:
    r = _via_pg("delete", user_id, conversation_id)
    if r is not _MISS:
        return r
    with _LOCK, closing(_connect()) as conn:
        cur = conn.execute("DELETE FROM conversations WHERE id = ? AND user_id = ?", (conversation_id, user_id))
        return cur.rowcount > 0


def clear(user_id: str) -> int:
    r = _via_pg("clear", user_id)
    if r is not _MISS:
        return r
    with _LOCK, closing(_connect()) as conn:
        return conn.execute("DELETE FROM conversations WHERE user_id = ?", (user_id,)).rowcount
