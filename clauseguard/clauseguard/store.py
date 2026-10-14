"""Typed clause store: SQLite persistence for PolicyRecords + embedding search over evidence text.

Tables (prefixed `clause_` so they never collide with the sandbox insurer DB that shares
config.DB_PATH):
  clause_policies(policy_id PK, doc_id, json)       -- PolicyRecord.model_dump_json()
  clause_tuples(tuple_id PK, policy_id, relation, object, json)
  clause_owners(policy_id, user_id)                 -- owner map (a policy may have several owners)
  clause_embeddings(text_hash PK, model, vec_json)  -- cache of llm.embed over evidence.text

Search is cosine similarity between the query embedding and each candidate tuple's
evidence.text embedding. Embeddings are computed lazily (first search) and cached both in
the table and on disk by llm.embed.
"""
from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import threading
from pathlib import Path
from typing import Optional

import numpy as np

from . import config, llm
from .schema import ClauseTuple, PolicyRecord

log = logging.getLogger("clauseguard.store")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS clause_policies (
    policy_id TEXT PRIMARY KEY,
    doc_id    TEXT NOT NULL,
    json      TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS clause_tuples (
    tuple_id  TEXT PRIMARY KEY,
    policy_id TEXT NOT NULL,
    relation  TEXT NOT NULL,
    object    TEXT NOT NULL,
    json      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_clause_tuples_policy ON clause_tuples(policy_id);
CREATE TABLE IF NOT EXISTS clause_owners (
    policy_id TEXT NOT NULL,
    user_id   TEXT NOT NULL,
    PRIMARY KEY (policy_id, user_id)
);
CREATE TABLE IF NOT EXISTS clause_embeddings (
    text_hash TEXT NOT NULL,
    model     TEXT NOT NULL,
    vec_json  TEXT NOT NULL,
    PRIMARY KEY (text_hash, model)
);
"""


def _h(text: str) -> str:
    return hashlib.sha256(text.encode("utf8")).hexdigest()


class ClauseStore:
    """SQLite-backed store of PolicyRecords and their ClauseTuples."""

    def __init__(self, db_path: Optional[str | Path] = None, *, embed_model: Optional[str] = None):
        self.db_path = Path(db_path) if db_path else Path(config.DB_PATH)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.embed_model = embed_model or config.MODEL_EMBED
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        with self._conn:
            self._conn.executescript(_SCHEMA)

    # ------------------------------------------------------------------ write
    def add_policy(self, p: PolicyRecord, owner_user_id: str | None = None) -> None:
        """Insert or replace a policy and all of its tuples. Idempotent."""
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO clause_policies(policy_id, doc_id, json) VALUES (?,?,?)",
                (p.id, p.doc_id, p.model_dump_json()),
            )
            self._conn.execute("DELETE FROM clause_tuples WHERE policy_id=?", (p.id,))
            self._conn.executemany(
                "INSERT OR REPLACE INTO clause_tuples(tuple_id, policy_id, relation, object, json) VALUES (?,?,?,?,?)",
                [(t.id, p.id, t.relation.value, t.object, t.model_dump_json()) for t in p.tuples],
            )
            if owner_user_id:
                self._conn.execute(
                    "INSERT OR IGNORE INTO clause_owners(policy_id, user_id) VALUES (?,?)", (p.id, owner_user_id)
                )

    def set_owner(self, policy_id: str, user_id: str) -> None:
        with self._lock, self._conn:
            self._conn.execute("INSERT OR IGNORE INTO clause_owners(policy_id, user_id) VALUES (?,?)", (policy_id, user_id))

    def remove_policy(self, policy_id: str) -> None:
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM clause_policies WHERE policy_id=?", (policy_id,))
            self._conn.execute("DELETE FROM clause_tuples WHERE policy_id=?", (policy_id,))
            self._conn.execute("DELETE FROM clause_owners WHERE policy_id=?", (policy_id,))

    # ------------------------------------------------------------------ read
    def get_policy(self, policy_id: str) -> PolicyRecord:
        row = self._conn.execute("SELECT json FROM clause_policies WHERE policy_id=?", (policy_id,)).fetchone()
        if row is None:
            raise KeyError(f"unknown policy_id {policy_id!r}")
        return PolicyRecord.model_validate_json(row[0])

    def has_policy(self, policy_id: str) -> bool:
        return self._conn.execute("SELECT 1 FROM clause_policies WHERE policy_id=?", (policy_id,)).fetchone() is not None

    def policies_for_user(self, user_id: str) -> list[PolicyRecord]:
        rows = self._conn.execute(
            "SELECT p.json FROM clause_policies p JOIN clause_owners o ON o.policy_id=p.policy_id "
            "WHERE o.user_id=? ORDER BY p.policy_id",
            (user_id,),
        ).fetchall()
        return [PolicyRecord.model_validate_json(r[0]) for r in rows]

    def all_policies(self) -> list[PolicyRecord]:
        rows = self._conn.execute("SELECT json FROM clause_policies ORDER BY policy_id").fetchall()
        return [PolicyRecord.model_validate_json(r[0]) for r in rows]

    def policy_ids(self) -> list[str]:
        return [r[0] for r in self._conn.execute("SELECT policy_id FROM clause_policies ORDER BY policy_id")]

    def get_tuple(self, tuple_id: str) -> ClauseTuple:
        row = self._conn.execute("SELECT json FROM clause_tuples WHERE tuple_id=?", (tuple_id,)).fetchone()
        if row is None:
            raise KeyError(f"unknown tuple_id {tuple_id!r}")
        return ClauseTuple.model_validate_json(row[0])

    def owners_of(self, policy_id: str) -> list[str]:
        return [r[0] for r in self._conn.execute("SELECT user_id FROM clause_owners WHERE policy_id=?", (policy_id,))]

    # ------------------------------------------------------------------ search
    def _embeddings_for(self, texts: list[str]) -> list[np.ndarray]:
        """Cached embeddings (table first, then llm.embed which also has a disk cache)."""
        out: dict[str, np.ndarray] = {}
        hashes = {t: _h(t) for t in texts}
        uniq = list(dict.fromkeys(texts))
        missing: list[str] = []
        for t in uniq:
            row = self._conn.execute(
                "SELECT vec_json FROM clause_embeddings WHERE text_hash=? AND model=?", (hashes[t], self.embed_model)
            ).fetchone()
            if row:
                out[t] = np.asarray(json.loads(row[0]), dtype=np.float32)
            else:
                missing.append(t)
        if missing:
            vecs = llm.embed(missing, model=self.embed_model)
            with self._lock, self._conn:
                for t, v in zip(missing, vecs):
                    out[t] = np.asarray(v, dtype=np.float32)
                    self._conn.execute(
                        "INSERT OR REPLACE INTO clause_embeddings(text_hash, model, vec_json) VALUES (?,?,?)",
                        (hashes[t], self.embed_model, json.dumps(v)),
                    )
        return [out[t] for t in texts]

    def search_clauses(self, query: str, policy_ids: list[str] | None = None, k: int = 8) -> list[ClauseTuple]:
        """Top-k tuples by cosine similarity between `query` and evidence.text."""
        if policy_ids:
            marks = ",".join("?" * len(policy_ids))
            rows = self._conn.execute(f"SELECT json FROM clause_tuples WHERE policy_id IN ({marks})", tuple(policy_ids)).fetchall()
        else:
            rows = self._conn.execute("SELECT json FROM clause_tuples").fetchall()
        tuples = [ClauseTuple.model_validate_json(r[0]) for r in rows]
        if not tuples or k <= 0:
            return []
        texts = [t.evidence.text for t in tuples]
        qv = self._embeddings_for([query])[0]
        mat = np.stack(self._embeddings_for(texts))
        qn = np.linalg.norm(qv) or 1.0
        norms = np.linalg.norm(mat, axis=1)
        norms[norms == 0] = 1.0
        sims = (mat @ qv) / (norms * qn)
        order = np.argsort(-sims)[:k]
        return [tuples[int(i)] for i in order]

    def close(self) -> None:
        self._conn.close()
