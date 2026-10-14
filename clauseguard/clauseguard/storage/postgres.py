from __future__ import annotations

import re
import threading
import time
from typing import Any, Callable, Optional

from .. import config
from .metrics import degraded

CONNECT_TIMEOUT_S = 5
COOLDOWN_S = 20
MAX_CONNS = 4
_SCHEMA_RE = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")


class StorageError(RuntimeError):
    """Postgres unavailable or failed. Never carries the connection string."""


def _transient(e: BaseException) -> bool:
    import psycopg2

    return isinstance(e, (psycopg2.OperationalError, psycopg2.InterfaceError))


class Pool:
    def __init__(self, schema: Optional[str] = None, url: Optional[str] = None) -> None:
        if schema is not None and not _SCHEMA_RE.match(schema):
            raise ValueError("invalid schema name")
        self.schema = schema
        self.url = url
        self._idle: list = []
        self._lock = threading.Lock()
        self._sem = threading.BoundedSemaphore(MAX_CONNS)
        self._down_until = 0.0

    def _dsn(self) -> str:
        url = self.url or config.DATABASE_URL
        if not url:
            raise StorageError("DATABASE_URL not set")
        return url

    def _open(self):
        import psycopg2
        from psycopg2 import sql

        try:
            conn = psycopg2.connect(self._dsn(), connect_timeout=CONNECT_TIMEOUT_S, sslmode="require", application_name="clauseguard")
            if self.schema:
                with conn.cursor() as cur:
                    cur.execute(sql.SQL("SET search_path TO {}, public").format(sql.Identifier(self.schema)))
                conn.commit()
            return conn
        except psycopg2.Error as e:
            raise StorageError(f"connect failed: {type(e).__name__}") from None

    def _take(self):
        with self._lock:
            if self._idle:
                return self._idle.pop()
        return self._open()

    def _give(self, conn) -> None:
        with self._lock:
            self._idle.append(conn)

    @staticmethod
    def _drop(conn) -> None:
        try:
            conn.close()
        except Exception:
            pass

    def run(self, fn: Callable[[Any], Any], component: str = "pg") -> Any:
        if time.time() < self._down_until:
            raise StorageError("postgres in cooldown")
        last: Optional[BaseException] = None
        for attempt in (1, 2):
            self._sem.acquire()
            conn = None
            try:
                conn = self._take()
                try:
                    out = fn(conn)
                    conn.commit()
                except BaseException:
                    try:
                        conn.rollback()
                    except Exception:
                        pass
                    raise
                self._give(conn)
                return out
            except StorageError as e:
                last = e
                if conn is not None:
                    self._drop(conn)
                if attempt == 1:
                    continue
                break
            except BaseException as e:
                if conn is not None:
                    self._drop(conn)
                if _transient(e) and attempt == 1:
                    last = e
                    continue
                if _transient(e):
                    last = e
                    break
                raise
            finally:
                self._sem.release()
        self._down_until = time.time() + COOLDOWN_S
        degraded(component, last or "unknown")
        raise StorageError(f"postgres unavailable: {type(last).__name__ if last else 'unknown'}")

    def close(self) -> None:
        with self._lock:
            for c in self._idle:
                self._drop(c)
            self._idle.clear()


_default: Optional[Pool] = None
_default_lock = threading.Lock()


def default_pool() -> Pool:
    global _default
    with _default_lock:
        if _default is None:
            _default = Pool()
        return _default


def reset_default() -> None:
    global _default
    with _default_lock:
        if _default is not None:
            _default.close()
        _default = None
