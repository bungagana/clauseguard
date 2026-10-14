"""SQLite schema for the mock insurer.

`init_db(seed=True)` creates the tables (idempotent) and loads the three personas.
Connections are plain sqlite3 with row_factory=Row; the data is tiny and deterministic.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional, Union

from .. import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS customers(
  id TEXT PRIMARY KEY, name TEXT NOT NULL, dob TEXT, sex TEXT, household_id TEXT,
  occupation_declared TEXT, occupation_actual TEXT, employer_id TEXT,
  bpjs_kes_no TEXT, bpjs_kes_class INTEGER, bpjs_kes_status TEXT, bpjs_kes_arrears_months INTEGER DEFAULT 0,
  bpjs_tk_member INTEGER DEFAULT 0, income_monthly_idr INTEGER
);
CREATE TABLE IF NOT EXISTS policies(
  id TEXT PRIMARY KEY, customer_id TEXT, insurer TEXT, product_code TEXT, product_type TEXT, basis TEXT,
  effective_date TEXT, expiry_date TEXT, reinstatement_date TEXT, premium_idr INTEGER, premium_frequency TEXT,
  grace_days INTEGER, status TEXT, cashless INTEGER DEFAULT 0, network_id TEXT, document_id TEXT,
  record_id TEXT, sum_assured_idr INTEGER
);
CREATE TABLE IF NOT EXISTS coverages(
  id TEXT PRIMARY KEY, policy_id TEXT, peril TEXT, insured_person_id TEXT, limit_amount INTEGER, limit_unit TEXT,
  max_days_per_year INTEGER, deductible_amount INTEGER DEFAULT 0, deductible_days INTEGER DEFAULT 0,
  copay_pct REAL DEFAULT 0, copay_cap_idr INTEGER, waiting_days_general INTEGER DEFAULT 0,
  waiting_days_specified INTEGER DEFAULT 0, survival_days INTEGER DEFAULT 0, clause_ref TEXT
);
CREATE TABLE IF NOT EXISTS exclusions(
  id TEXT PRIMARY KEY, policy_id TEXT, code TEXT, qualifier_json TEXT, clause_ref TEXT
);
CREATE TABLE IF NOT EXISTS riders(
  id TEXT PRIMARY KEY, policy_id TEXT, rider_type TEXT, limit_amount INTEGER, waiting_days INTEGER, clause_ref TEXT
);
CREATE TABLE IF NOT EXISTS other_insurance_clauses(
  policy_id TEXT PRIMARY KEY, kind TEXT, requires_cob_letter INTEGER DEFAULT 0, requires_legalised_copy INTEGER DEFAULT 0, clause_ref TEXT
);
CREATE TABLE IF NOT EXISTS claim_rules(
  policy_id TEXT PRIMARY KEY, notify_within_days INTEGER, docs_within_days INTEGER, from_event TEXT,
  late_filing_effect TEXT, insurer_decision_sla_days INTEGER, payment_sla_days INTEGER, required_documents_json TEXT, clause_ref TEXT
);
CREATE TABLE IF NOT EXISTS claims(
  id TEXT PRIMARY KEY, policy_id TEXT, customer_id TEXT, event_type TEXT, event_date TEXT, admission_date TEXT,
  discharge_date TEXT, diagnosis_icd TEXT, cause TEXT, facility_id TEXT, facility_is_bpjs_partner INTEGER,
  is_emergency INTEGER, billed_amount INTEGER, claim_amount INTEGER, status TEXT, rejection_code TEXT,
  filed_date TEXT, deadline_date TEXT, created_via TEXT, form_json TEXT, decided_at TEXT, decision_note TEXT
);
CREATE TABLE IF NOT EXISTS claim_payments(
  id TEXT PRIMARY KEY, claim_id TEXT, payer TEXT, amount INTEGER, paid_date TEXT
);
CREATE TABLE IF NOT EXISTS payments(
  id TEXT PRIMARY KEY, policy_id TEXT, due_date TEXT, paid_date TEXT, amount INTEGER
);
CREATE TABLE IF NOT EXISTS beneficiaries(
  id TEXT PRIMARY KEY, policy_id TEXT, name TEXT, relation TEXT, share_pct REAL, id_number_hash TEXT
);
CREATE TABLE IF NOT EXISTS documents(
  id TEXT PRIMARY KEY, policy_id TEXT, claim_id TEXT, type TEXT, file_path TEXT, taint_label TEXT DEFAULT 'untrusted',
  extracted_json TEXT, uploaded_by TEXT, uploaded_at TEXT
);
CREATE TABLE IF NOT EXISTS facilities(
  id TEXT PRIMARY KEY, name TEXT, bpjs_partner INTEGER, network_ids_json TEXT, class_available TEXT
);
CREATE TABLE IF NOT EXISTS tariffs_ina_cbg(
  code TEXT, class INTEGER, amount INTEGER, description TEXT, PRIMARY KEY(code, class)
);
CREATE TABLE IF NOT EXISTS tickets(
  id TEXT PRIMARY KEY, customer_id TEXT, type TEXT, status TEXT, created_at TEXT, payload_hash TEXT,
  requested_via TEXT, note TEXT, session_id TEXT
);
CREATE TABLE IF NOT EXISTS audit_log(
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, actor TEXT, action TEXT, tier INTEGER, input_hash TEXT,
  decision TEXT, prev_hash TEXT, hash TEXT
);
"""

TABLES = [
    "customers", "policies", "coverages", "exclusions", "riders", "other_insurance_clauses", "claim_rules", "claims",
    "claim_payments", "payments", "beneficiaries", "documents", "facilities", "tariffs_ina_cbg", "tickets", "audit_log",
]


def connect(path: Optional[Union[str, Path]] = None) -> sqlite3.Connection:
    p = Path(path) if path is not None else Path(config.DB_PATH)
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


CLAIM_COLUMNS_ADDED = (("form_json", "TEXT"), ("decided_at", "TEXT"), ("decision_note", "TEXT"))


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    # databases created before these columns existed are upgraded in place
    have = {row[1] for row in conn.execute("PRAGMA table_info(claims)").fetchall()}
    for col, typ in CLAIM_COLUMNS_ADDED:
        if col not in have:
            conn.execute(f"ALTER TABLE claims ADD COLUMN {col} {typ}")
    conn.commit()


def reset(conn: sqlite3.Connection) -> None:
    for t in TABLES:
        conn.execute(f"DELETE FROM {t}")
    conn.commit()


def init_db(seed: bool = True, path: Optional[Union[str, Path]] = None, fresh: bool = False) -> sqlite3.Connection:
    """Create schema; optionally (re)load the personas. `fresh=True` wipes existing rows first."""
    conn = connect(path)
    create_schema(conn)
    if fresh:
        reset(conn)
    if seed:
        n = conn.execute("SELECT COUNT(*) FROM customers").fetchone()[0]
        if n == 0:
            from . import seed as _seed

            _seed.seed(conn)
    return conn
