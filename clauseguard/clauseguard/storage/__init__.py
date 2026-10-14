"""Optional Postgres persistence for the evidence that must survive a restart.

Selected only when CG_STORAGE=postgres and DATABASE_URL is set; every other configuration keeps
the file/SQLite backends untouched."""
from __future__ import annotations

from .. import config
from .metrics import counters, degraded


def postgres_enabled() -> bool:
    return getattr(config, "STORAGE", "local") == "postgres" and bool(getattr(config, "DATABASE_URL", ""))


__all__ = ["postgres_enabled", "counters", "degraded"]
