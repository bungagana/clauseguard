"""Confirm the publishable (anon) key cannot read the evidence tables through Supabase's REST API.

Reads SUPABASE_URL and SUPABASE_PUBLISHABLE_KEY from .env; never prints them.
Exit 0 only if every table returns an empty array or a permission error.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

TABLES = ("audit_events", "audit_head", "conversations", "claims_log", "tickets_log", "schema_migrations")


def probe(base: str, key: str, table: str) -> tuple[int, str]:
    req = urllib.request.Request(f"{base}/rest/v1/{table}?select=*&limit=5", headers={"apikey": key, "Authorization": f"Bearer {key}"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            body = r.read().decode("utf-8", "replace")
            return r.status, body
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


def main() -> int:
    load_dotenv(ROOT / ".env")
    base = os.getenv("SUPABASE_URL", "").rstrip("/")
    key = os.getenv("SUPABASE_PUBLISHABLE_KEY", "")
    if not base or not key:
        print("SUPABASE_URL / SUPABASE_PUBLISHABLE_KEY not set")
        return 2
    bad = 0
    for t in TABLES:
        status, body = probe(base, key, t)
        verdict = "UNKNOWN"
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            data = None
        if status in (401, 403) or (isinstance(data, dict) and data.get("code") in ("42501", "PGRST205", "PGRST301")):
            verdict = "DENIED"
        elif status == 200 and data == []:
            verdict = "EMPTY (RLS deny-all)"
        elif status == 404:
            verdict = "NOT EXPOSED"
        else:
            verdict = "LEAK"
            bad += 1
        code = data.get("code") if isinstance(data, dict) else "-"
        print(f"{t:18s} http={status} code={code} -> {verdict}")
    print("RLS CHECK:", "FAILED" if bad else "PASSED")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
