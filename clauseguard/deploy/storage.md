# Storage on the Hugging Face Space

The Space filesystem is ephemeral. Persistence is opt-in and limited to evidence that must outlive a restart.

| Data | Local (default) | Postgres (`CG_STORAGE=postgres` + `DATABASE_URL`) |
|---|---|---|
| Audit log | `evidence/audit_log.jsonl`, hash chain | `audit_events` + `audit_head` |
| Conversation history | `data/history.sqlite` | `conversations` |
| Claims written by agent actions or the insurer simulator | `data/sandbox.sqlite` | `claims_log` (write-through, upsert by id) |
| Tickets (appeals, callbacks, account-change requests) | `data/sandbox.sqlite` | `tickets_log` (write-through, upsert by id) |
| Personas, policies, coverages | re-seeded at boot from `sandbox/seed.py` | not migrated |
| Sessions | in-memory dict (web client re-logs on 401) | unchanged |
| Uploads | `data/uploads`, needed only during extraction | unchanged |

Postgres is selected only when both variables are set. Tests and fresh clones stay on local backends.

## Schema

`deploy/migrations/001_init.sql`, applied with `python scripts/apply_migration.py` (idempotent, uses `DATABASE_URL`).
Every table has row level security enabled with no policies and all privileges revoked from `anon` and `authenticated`,
so the Supabase REST API returns a permission error to the publishable key. The backend connects with `DATABASE_URL`
(privileged, bypasses RLS) and never uses the publishable key. `audit_events` also has a trigger rejecting UPDATE and DELETE.
`conversations.created_at/updated_at` are epoch milliseconds, matching the SQLite store.

## Audit chain

Appends run in one transaction: `SELECT ... FROM audit_head FOR UPDATE`, insert the event, advance the head. The row lock
serialises writers across processes and instances, so the chain cannot fork. Hashes come from `security/audit.py`
(`canonical_json`, `_hash_event`), identical to the file backend (`tests/test_storage.py` proves it).
`verify()` re-walks the chain and also compares the last event with `audit_head`, which exposes tail truncation.

### Postgres unavailable

Availability is preferred over fail-closed. The connection helper retries once, then opens a 20 s cooldown. During an outage:

1. Events are appended to a local chain `<audit path>.pgfallback` (its own genesis, verifiable with the file verifier).
2. `storage_degraded` is incremented and a warning is logged.
3. On the next successful append, an `AUDIT_GAP` event is written first into the Postgres chain. Its `reason` carries the
   number of local events, first/last timestamps and the local chain head hash; `doc_id` is `local:<first seq>-<last seq>`.
   The local file is then archived as `.pgfallback.reported-<ms>`.
4. `verify_report()` lists every `AUDIT_GAP`, and reports `ok=false` with `unreported_local_events > 0` while a local
   segment has not been anchored yet.

The gap is therefore visible and hash-covered rather than a silent fork. If the Space restarts during an outage before
recovery, the unanchored local events are lost; that loss is bounded by the outage and not hidden, because the sequence of
the Postgres chain stays intact. A retried append whose first attempt actually committed can leave a duplicate event, never a break.

History falls back to the local SQLite store for the failing operation. Claims and tickets keep the local row and skip the mirror.
Neither raises into the request.

## Pre-demo check

```
python scripts/apply_migration.py
python scripts/check_supabase_rls.py        # every table must be DENIED or EMPTY
python scripts/smoke_supabase.py            # throwaway schema, dropped afterwards
python scripts/verify_audit.py --postgres   # OK (n events, k declared gaps)
```

Optional pytest against the database: `CG_RUN_PG_TESTS=1 python -m pytest tests/test_storage.py` (throwaway schema).

## Space variables

Secrets: `DATABASE_URL`. Variables: `CG_STORAGE=postgres`. Do not set `SUPABASE_PUBLISHABLE_KEY` on the Space.
