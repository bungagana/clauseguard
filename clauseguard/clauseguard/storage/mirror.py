"""Best-effort write-through of claims and tickets to Postgres (execution evidence).

The local SQLite row stays authoritative for the running demo; a Postgres failure is logged,
counted as `storage_degraded`, and never raised into the request."""
from __future__ import annotations

from typing import Any, Optional

from .metrics import degraded
from .postgres import Pool, StorageError, default_pool

CLAIM_COLS = (
    "id", "policy_id", "customer_id", "event_type", "event_date", "admission_date", "discharge_date", "diagnosis_icd", "cause",
    "facility_id", "facility_is_bpjs_partner", "is_emergency", "billed_amount", "claim_amount", "status", "rejection_code",
    "filed_date", "deadline_date", "created_via",
)
TICKET_COLS = ("id", "customer_id", "type", "status", "created_at", "payload_hash", "requested_via", "note", "session_id")
PAYMENT_COLS = ("id", "claim_id", "payer", "amount", "paid_date")


_TABLE_COLS = {"claims_log": CLAIM_COLS, "tickets_log": TICKET_COLS, "claim_payments_log": PAYMENT_COLS}


def _upsert_sql(table: str, cols: tuple[str, ...]) -> str:
    names = ", ".join(cols)
    marks = ", ".join(["%s"] * len(cols))
    sets = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols[1:])
    return f"INSERT INTO {table} ({names}) VALUES ({marks}) ON CONFLICT (id) DO UPDATE SET {sets}, updated_at = now()"


def write_through(table: str, row: dict[str, Any], pool: Optional[Pool] = None) -> bool:
    cols = _TABLE_COLS[table]
    values = tuple(row.get(c) for c in cols)

    def work(conn):
        with conn.cursor() as cur:
            cur.execute(_upsert_sql(table, cols), values)

    try:
        (pool or default_pool()).run(work, table)
        return True
    except StorageError as e:
        degraded(table, e)
        return False
    except Exception as e:
        degraded(table, e)
        return False


def _row(conn, table: str, row_id: str) -> Optional[dict[str, Any]]:
    r = conn.execute(f"SELECT * FROM {table} WHERE id = ?", (row_id,)).fetchone()
    return dict(r) if r is not None else None


def mirror_claim(conn, claim_id: str) -> None:
    from . import postgres_enabled

    if not postgres_enabled():
        return
    row = _row(conn, "claims", claim_id)
    if row is not None:
        write_through("claims_log", row)


def mirror_ticket(conn, ticket_id: str) -> None:
    from . import postgres_enabled

    if not postgres_enabled():
        return
    row = _row(conn, "tickets", ticket_id)
    if row is not None:
        write_through("tickets_log", row)


def mirror_payment(conn, payment_id: str) -> None:
    from . import postgres_enabled

    if not postgres_enabled():
        return
    row = _row(conn, "claim_payments", payment_id)
    if row is not None:
        write_through("claim_payments_log", row)
