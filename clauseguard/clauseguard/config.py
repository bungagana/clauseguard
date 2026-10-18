"""Central configuration. Reads .env (never committed)."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
# Optional pool of free-tier keys (comma separated). The wrapper rotates to the next key on a
# 429 quota error so daily per-project limits add up instead of blocking a run.
GEMINI_API_KEYS: list = [k.strip() for k in (os.getenv("GEMINI_API_KEYS", "") or GEMINI_API_KEY).split(",") if k.strip()]
if GEMINI_API_KEY and GEMINI_API_KEY not in GEMINI_API_KEYS:
    GEMINI_API_KEYS.insert(0, GEMINI_API_KEY)
LLM_TIMEOUT_MS: int = int(os.getenv("CG_LLM_TIMEOUT_MS", "120000"))

# Model roles. Extraction is offline (once per document) -> stronger model.
# Query-time steps (fact extraction from the user's message, explanation) -> cheap model.
MODEL_EXTRACT: str = os.getenv("CG_MODEL_EXTRACT", "gemini-3.6-flash")
MODEL_FAST: str = os.getenv("CG_MODEL_FAST", "gemini-3.5-flash-lite")
# Claim documents (invoice, discharge summary) are short and structured: the cheap model reads them; the
# extraction model is only the fallback when it is unavailable.
MODEL_CLAIM_DOC: str = os.getenv("CG_MODEL_CLAIM_DOC", MODEL_FAST)
MODEL_EMBED: str = os.getenv("CG_MODEL_EMBED", "gemini-embedding-001")

DATA_DIR = ROOT / "data"
CACHE_DIR = DATA_DIR / "cache"
EVIDENCE_DIR = ROOT / "evidence"
DB_PATH = ROOT / os.getenv("CG_DB_PATH", "data/sandbox.sqlite")
HISTORY_DB_PATH = ROOT / os.getenv("CG_HISTORY_DB_PATH", "data/history.sqlite")
AUDIT_PATH = ROOT / os.getenv("CG_AUDIT_PATH", "evidence/audit_log.jsonl")
KILL_SWITCH_PATH = ROOT / os.getenv("CG_KILL_SWITCH_PATH", "evidence/AGENT_HALT")
CLAIM_AMOUNT_CAP_IDR: int = int(os.getenv("CG_CLAIM_AMOUNT_CAP_IDR", "100000000"))

# Back-office/admin credential (gates /admin/kill and /backoffice/*). No default: unset means
# admin features are disabled (401/403), not open with a guessable default. Set a real value in
# .env before any admin/backoffice demo.
ADMIN_TOKEN: str = os.getenv("CG_ADMIN_TOKEN", "")

# Account sign-in. CG_AUTH=supabase turns on real accounts: /login then needs a Supabase access token for a
# confirmed email, and the persona/guest shortcuts are closed. Unset keeps the open sandbox login that the
# tests, the evidence scripts and a local clone use.
AUTH_MODE: str = os.getenv("CG_AUTH", "").strip().lower()
SUPABASE_URL: str = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
SUPABASE_PUBLISHABLE_KEY: str = os.getenv("SUPABASE_PUBLISHABLE_KEY", "").strip()
# email=persona pairs: these confirmed accounts open a seeded persona; any other account starts empty
DEMO_ACCOUNTS: str = os.getenv("CG_DEMO_ACCOUNTS", "rizky@demo.clauseguard.id=rizky,santoso@demo.clauseguard.id=santoso,dewi@demo.clauseguard.id=dewi")

STORAGE: str = os.getenv("CG_STORAGE", "local").strip().lower()
DATABASE_URL: str = os.getenv("DATABASE_URL", "")

for _d in (CACHE_DIR, EVIDENCE_DIR, DATA_DIR / "personas", DATA_DIR / "scripted_tasks", DATA_DIR / "adversarial"):
    _d.mkdir(parents=True, exist_ok=True)

# Deterministic decoding everywhere. The LLM never decides, but we still want reproducibility.
TEMPERATURE: float = 0.0
