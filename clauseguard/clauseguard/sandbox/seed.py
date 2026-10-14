"""Seed the sandbox with the three personas and the verified policies.

Persona A  Rizky Pratama   - HCP-SOMPO-01, TL-ASTRA-07 (in grace), BPJS class 2; open dengue claim.
Persona B  Santoso family  - GH-NUSA-GRP, GL-NUSA-GRP, HCP-RIDER-B (Budi), HI-INDIV-S (Sari), BPJS class 1;
                             Aditya's asthma admission.
Persona C  Dewi Lestari    - PA-CHUBB-03, PLATFORM-ACC, BPJS class 3 (3 months arrears), Jasa Raharja statutory;
                             on-trip collision with an expired licence.

PolicyRecord JSON files live in data/personas/policies/<id>.json (written by `write_policy_files`,
loaded back by `load_policy_files`). If `clauseguard.store.ClauseStore` exists they are also
pushed into it with the owner map.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from pathlib import Path
from typing import Optional, Union

from .. import config
from ..schema import PolicyRecord
from .persona_policies import build_policy_records

POLICY_DIR = Path(config.DATA_DIR) / "personas" / "policies"

PERSONAS = {
    "rizky": {"user_id": "C-RIZKY", "household_id": "H-RIZKY", "label": "Rizky Pratama (24, graduate student)"},
    "santoso": {"user_id": "C-BUDI", "household_id": "H-SANTOSO", "label": "Santoso family (Budi, Sari, Aditya, Nadia)"},
    "dewi": {"user_id": "C-DEWI", "household_id": "H-DEWI", "label": "Dewi Lestari (29, ojek/courier)"},
}


def _h(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------- rows
CUSTOMERS = [
    # id, name, dob, sex, household, occ_declared, occ_actual, employer, bpjs_no, class, status, arrears, tk, income
    ("C-RIZKY", "Rizky Pratama", "2002-04-12", "M", "H-RIZKY", "graduate student", "graduate student", None, "0001234567890", 2, "active", 0, 0, 3500000),
    ("C-BUDI", "Budi Santoso", "1988-06-20", "M", "H-SANTOSO", "employee", "employee", "E-NUSA", "0002345678901", 1, "active", 0, 1, 12000000),
    ("C-SARI", "Sari Santoso", "1990-02-11", "F", "H-SANTOSO", "freelance designer", "freelance designer", None, "0002345678902", 1, "active", 0, 0, 5000000),
    ("C-ADITYA", "Aditya Santoso", "2019-03-05", "M", "H-SANTOSO", "child", "child", None, "0002345678903", 1, "active", 0, 0, 0),
    ("C-NADIA", "Nadia Santoso", "2023-07-19", "F", "H-SANTOSO", "child", "child", None, "0002345678904", 1, "active", 0, 0, 0),
    ("C-DEWI", "Dewi Lestari", "1997-08-30", "F", "H-DEWI", "administrative staff", "courier (ojek)", None, "0003456789012", 3, "inactive", 3, 0, 4000000),
]

POLICIES = [
    # id, customer, insurer, product_code, product_type, basis, effective, expiry, reinst, premium, freq, grace, status, cashless, network, document_id, record_id, SA
    ("HCP-SOMPO-01", "C-RIZKY", "PT Sompo Insurance Indonesia", "HCP-SOMPO", "hospital_cash", "fixed_benefit", "2026-08-20", "2027-08-19", None, 1980000, "annual", 0, "active", 0, None, "DOC-HCP-SOMPO-01", "HCP-SOMPO-01", 500000),
    ("TL-ASTRA-07", "C-RIZKY", "PT Asuransi Jiwa Astra", "FLEXI-LIFE", "term_life", "fixed_benefit", "2025-02-01", "2027-01-31", None, 103500, "monthly", 30, "grace", 0, None, "DOC-TL-ASTRA-07", "TL-ASTRA-07", 500000000),
    ("CI-CHUBB-05", "C-RIZKY", "Chubb Life Indonesia (modelled)", "ESSENTIAL-CC", "ci", "fixed_benefit", "2025-06-01", None, None, 1200000, "annual", 30, "active", 0, None, "DOC-CI-CHUBB-05", "CI-CHUBB-05", 100000000),
    ("BPJS-KES-RIZKY", "C-RIZKY", "BPJS Kesehatan", "JKN-PBPU-2", "social_bpjs_kes", "indemnity", "2024-01-01", None, None, 100000, "monthly", 0, "active", 1, "BPJS", "DOC-BPJS-KES", "BPJS-KES", None),
    ("GH-NUSA-GRP", "C-BUDI", "PT Asuransi Nusantara (mock)", "GH-NUSA", "group_health", "indemnity", "2026-01-01", "2026-12-31", None, 0, "employer", 0, "active", 1, "N1", "DOC-GH-NUSA-GRP", "GH-NUSA-GRP", 150000000),
    ("GL-NUSA-GRP", "C-BUDI", "PT Asuransi Nusantara (mock)", "GL-NUSA", "group_life", "fixed_benefit", "2026-01-01", "2026-12-31", None, 0, "employer", 0, "active", 0, None, "DOC-GL-NUSA-GRP", "GL-NUSA-GRP", 288000000),
    ("HCP-RIDER-B", "C-BUDI", "PT Asuransi Jiwa Astra (modelled)", "HCP-RIDER", "hospital_cash", "fixed_benefit", "2024-05-01", None, None, 450000, "monthly", 30, "active", 0, None, "DOC-HCP-RIDER-B", "HCP-RIDER-B", 300000),
    ("HI-INDIV-S", "C-SARI", "PT Asuransi Sehat Mandiri (mock)", "HI-SM", "health_indemnity", "indemnity", "2025-11-01", "2026-10-31", None, 6000000, "annual", 30, "active", 0, None, "DOC-HI-INDIV-S", "HI-INDIV-S", 100000000),
    ("BPJS-KES-SANTOSO", "C-BUDI", "BPJS Kesehatan", "JKN-PPU-1", "social_bpjs_kes", "indemnity", "2020-03-01", None, None, 0, "employer", 0, "active", 1, "BPJS", "DOC-BPJS-KES", "BPJS-KES", None),
    ("PA-CHUBB-03", "C-DEWI", "Chubb (modelled)", "PA-ESSENTIAL", "pa", "fixed_benefit", "2026-03-15", "2027-03-14", None, 600000, "annual", 0, "active", 0, None, "DOC-PA-CHUBB-03", "PA-CHUBB-03", 100000000),
    ("PLATFORM-ACC", "C-DEWI", "Platform group accident (mock)", "PLATFORM-ACC", "platform_accident", "fixed_benefit", "2026-01-01", None, None, 0, "platform", 0, "active", 0, None, "DOC-PLATFORM-ACC", "PLATFORM-ACC", 50000000),
    ("BPJS-KES-DEWI", "C-DEWI", "BPJS Kesehatan", "JKN-PBPU-3", "social_bpjs_kes", "indemnity", "2023-06-01", None, None, 42000, "monthly", 0, "lapsed", 1, "BPJS", "DOC-BPJS-KES", "BPJS-KES", None),
    ("JASA-RAHARJA", None, "PT Jasa Raharja (statutory)", "JR-UU33-34", "jasa_raharja", "indemnity", None, None, None, 0, "statutory", 0, "active", 1, None, "DOC-JASA-RAHARJA", "JASA-RAHARJA", None),
]

COVERAGES = [
    # id, policy, peril, person, limit, unit, max_days, ded_amt, ded_days, copay_pct, copay_cap, wait_gen, wait_spec, survival, clause_ref
    ("CV-HCP-01", "HCP-SOMPO-01", "hospital_cash_daily", "C-RIZKY", 500000, "per_day", 90, 0, 0, 0, None, 30, 365, 0, "c_hosp_daily"),
    ("CV-HCP-02", "HCP-SOMPO-01", "icu", "C-RIZKY", 1000000, "per_day", 20, 0, 0, 0, None, 30, 365, 0, "c_icu_daily"),
    ("CV-HCP-03", "HCP-SOMPO-01", "surgery", "C-RIZKY", 2500000, "per_case", None, 0, 0, 0, None, 30, 365, 0, "c_surgical"),
    ("CV-TL-01", "TL-ASTRA-07", "death_any", "C-RIZKY", 500000000, "lifetime", None, 0, 0, 0, None, 0, 0, 0, "c_death"),
    ("CV-CI-01", "CI-CHUBB-05", "critical_illness", "C-RIZKY", 100000000, "lifetime", None, 0, 0, 0, None, 90, 0, 30, "ci_cover"),
    ("CV-BPJS-R", "BPJS-KES-RIZKY", "inpatient_room", "C-RIZKY", None, "per_case", None, 0, 0, 0, None, 0, 0, 0, "c_inpatient_partner"),
    ("CV-GH-01", "GH-NUSA-GRP", "inpatient_room", "C-BUDI", 1500000, "per_day", 60, 0, 0, 0, None, 0, 0, 0, "c_room"),
    ("CV-GH-02", "GH-NUSA-GRP", "inpatient_other", "C-BUDI", 7700000, "per_case", None, 0, 0, 0, None, 0, 0, 0, "pays_other_inpatient"),
    ("CV-GH-03", "GH-NUSA-GRP", "surgery", "C-BUDI", 25000000, "per_case", None, 0, 0, 0, None, 0, 0, 0, "c_surgery"),
    ("CV-GH-04", "GH-NUSA-GRP", "inpatient_room", "C-SARI", 1500000, "per_day", 60, 0, 0, 0, None, 0, 0, 0, "c_room"),
    ("CV-GH-05", "GH-NUSA-GRP", "inpatient_room", "C-ADITYA", 1500000, "per_day", 60, 0, 0, 0, None, 0, 0, 0, "c_room"),
    ("CV-GH-06", "GH-NUSA-GRP", "inpatient_other", "C-ADITYA", 7700000, "per_case", None, 0, 0, 0, None, 0, 0, 0, "pays_other_inpatient"),
    ("CV-GH-07", "GH-NUSA-GRP", "inpatient_room", "C-NADIA", 1500000, "per_day", 60, 0, 0, 0, None, 0, 0, 0, "c_room"),
    ("CV-GL-01", "GL-NUSA-GRP", "death_any", "C-BUDI", 288000000, "lifetime", None, 0, 0, 0, None, 0, 0, 0, "c_death"),
    ("CV-HR-01", "HCP-RIDER-B", "hospital_cash_daily", "C-BUDI", 300000, "per_day", 365, 0, 0, 0, None, 30, 730, 0, "c_hosp_daily"),
    ("CV-HR-02", "HCP-RIDER-B", "hospital_cash_daily", "C-SARI", 300000, "per_day", 365, 0, 0, 0, None, 30, 730, 0, "c_hosp_daily"),
    ("CV-HR-03", "HCP-RIDER-B", "hospital_cash_daily", "C-ADITYA", 300000, "per_day", 365, 0, 0, 0, None, 30, 730, 0, "c_hosp_daily"),
    ("CV-HR-04", "HCP-RIDER-B", "hospital_cash_daily", "C-NADIA", 300000, "per_day", 365, 0, 0, 0, None, 30, 730, 0, "c_hosp_daily"),
    ("CV-HI-01", "HI-INDIV-S", "inpatient_room", "C-SARI", 800000, "per_day", None, 0, 0, 5.0, 3000000, 30, 365, 0, "c_room"),
    ("CV-HI-02", "HI-INDIV-S", "inpatient_room", "C-ADITYA", 800000, "per_day", None, 0, 0, 5.0, 3000000, 30, 365, 0, "c_room"),
    ("CV-HI-03", "HI-INDIV-S", "inpatient_room", "C-NADIA", 800000, "per_day", None, 0, 0, 5.0, 3000000, 30, 365, 0, "c_room"),
    ("CV-HI-04", "HI-INDIV-S", "inpatient_other", "C-SARI", 100000000, "per_year", None, 0, 0, 5.0, 3000000, 30, 365, 0, "c_room"),
    ("CV-PA-01", "PA-CHUBB-03", "death_accident", "C-DEWI", 100000000, "lifetime", None, 0, 0, 0, None, 0, 0, 0, "c_accidental_death"),
    ("CV-PA-02", "PA-CHUBB-03", "tpd", "C-DEWI", 100000000, "lifetime", None, 0, 0, 0, None, 0, 0, 0, "c_tpd"),
    ("CV-PA-03", "PA-CHUBB-03", "pa_weekly_income", "C-DEWI", 500000, "per_week", 364, 0, 0, 0, None, 0, 0, 0, "c_weekly_ttd"),
    ("CV-PA-04", "PA-CHUBB-03", "pa_medical", "C-DEWI", 10000000, "per_year", None, 0, 0, 0, None, 0, 0, 0, "c_accident_medical"),
    ("CV-PL-01", "PLATFORM-ACC", "death_accident", "C-DEWI", 50000000, "lifetime", None, 0, 0, 0, None, 0, 0, 0, "c_death_on_trip"),
    ("CV-PL-02", "PLATFORM-ACC", "pa_medical", "C-DEWI", 5000000, "per_case", None, 0, 0, 0, None, 0, 0, 0, "c_medical_on_trip"),
    ("CV-JR-01", "JASA-RAHARJA", "pa_medical", None, 20000000, "per_case", None, 0, 0, 0, None, 0, 0, 0, "c_medical"),
    ("CV-JR-02", "JASA-RAHARJA", "death_accident", None, 50000000, "lifetime", None, 0, 0, 0, None, 0, 0, 0, "c_death"),
]

EXCLUSIONS = [
    ("EX-HCP-1", "HCP-SOMPO-01", "pre_existing", "{}", "x_preexisting_hospitalization"),
    ("EX-HCP-2", "HCP-SOMPO-01", "specified_disease", '{"within_months":12}', "p_waiting_specified_12m"),
    ("EX-HCP-3", "HCP-SOMPO-01", "suicide", "{}", "x_suicide"),
    ("EX-HCP-4", "HCP-SOMPO-01", "intoxication", "{}", "x_intoxication"),
    ("EX-HCP-5", "HCP-SOMPO-01", "hazardous_sport", "{}", "x_hazardous"),
    ("EX-HCP-6", "HCP-SOMPO-01", "war", "{}", "x_war"),
    ("EX-HCP-7", "HCP-SOMPO-01", "congenital", "{}", "x_congenital"),
    ("EX-TL-1", "TL-ASTRA-07", "suicide", '{"within_months":24}', "p_suicide_24m"),
    ("EX-GL-1", "GL-NUSA-GRP", "suicide", '{"within_months":12}', "p_suicide_12m"),
    ("EX-GH-1", "GH-NUSA-GRP", "dental", '{"except":"accident"}', "x_dental"),
    ("EX-GH-2", "GH-NUSA-GRP", "cosmetic", "{}", "x_cosmetic"),
    ("EX-HR-1", "HCP-RIDER-B", "pre_existing", '{"within_months":12}', "x_preexisting_hospitalization"),
    ("EX-HR-2", "HCP-RIDER-B", "dental", '{"except":"accident"}', "x_dental"),
    ("EX-HR-3", "HCP-RIDER-B", "pregnancy", "{}", "x_pregnancy"),
    ("EX-HR-4", "HCP-RIDER-B", "specified_disease", '{"within_months":24,"max_days_per_year":5}', "p_specified_2y_5days"),
    ("EX-HI-1", "HI-INDIV-S", "pre_existing", '{"within_months":24}', "x_preexisting_hospitalization"),
    ("EX-HI-2", "HI-INDIV-S", "specified_disease", '{"within_months":12}', "p_specified_12m"),
    ("EX-HI-3", "HI-INDIV-S", "dental", '{"except":"accident"}', "x_dental"),
    ("EX-HI-4", "HI-INDIV-S", "pregnancy", "{}", "x_pregnancy"),
    ("EX-PA-1", "PA-CHUBB-03", "no_valid_license", "{}", "k_valid_license"),
    ("EX-PA-2", "PA-CHUBB-03", "motorcycling_commercial", '{"unless":"declared"}', "x_commercial_motorcycling"),
    ("EX-PA-3", "PA-CHUBB-03", "intoxication", "{}", "x_intoxication"),
    ("EX-PA-4", "PA-CHUBB-03", "hazardous_sport", '{"racing":true}', "x_motor_sports"),
    ("EX-PA-5", "PA-CHUBB-03", "pre_existing", "{}", "x_preexisting"),
    ("EX-JR-1", "JASA-RAHARJA", "single_vehicle", '{"vehicles_involved_lt":2}', "x_single_vehicle_medical"),
]

RIDERS = [
    ("RD-HCP-FOLLOWUP", "HCP-SOMPO-01", "follow_up_care", 0, 30, "Benefits, Art. 4 (not purchased)"),
    ("RD-HCP-B", "HCP-RIDER-B", "hospital_cash", 300000, 30, "c_hosp_daily"),
]

OTHER_INSURANCE = [
    ("HCP-SOMPO-01", "stackable", 0, 0, "d_other_insurance_stackable"),
    ("TL-ASTRA-07", "stackable", 0, 0, "c_death"),
    ("CI-CHUBB-05", "stackable", 0, 0, "ci_cover"),
    ("BPJS-KES-RIZKY", "excess", 0, 0, "d_cob_statutory"),
    ("GH-NUSA-GRP", "excess", 1, 1, "d_other_insurance_excess"),
    ("GL-NUSA-GRP", "stackable", 0, 0, "c_death"),
    ("HCP-RIDER-B", "stackable", 0, 0, "c_hosp_daily"),
    ("HI-INDIV-S", "excess", 1, 1, "d_other_insurance_excess"),
    ("BPJS-KES-SANTOSO", "excess", 0, 0, "d_cob_statutory"),
    ("PA-CHUBB-03", "stackable", 0, 0, "c_weekly_ttd"),
    ("PLATFORM-ACC", "excess", 0, 0, "c_medical_on_trip"),
    ("BPJS-KES-DEWI", "excess", 0, 0, "d_cob_statutory"),
    ("JASA-RAHARJA", "none", 0, 0, "c_medical"),
]

CLAIM_RULES = [
    # policy, notify, docs, from, late, decision_sla, payment_sla, docs_json, clause
    ("HCP-SOMPO-01", 0, 60, "treatment_end", "reject", 15, 14, json.dumps(["CLAIM_FORM", "RECEIPT_ORIGINAL_OR_LEGALISED", "RECEIPT_DETAILS", "MEDICAL_RESUME_INPATIENT", "PRESCRIPTION_COPY", "DIAGNOSTIC_RESULTS"]), "p_filing_60d"),
    ("TL-ASTRA-07", 60, 90, "death", "discretionary", 30, 30, json.dumps(["CLAIM_FORM_DEATH", "DOCTOR_STATEMENT_DEATH", "ID_AND_RELATIONSHIP_PROOF", "DEATH_CERT_ORIGINAL_OR_LEGALISED", "BENEFICIARY_BANK_BOOK_COPY", "DISCLAIMER_DEATH_BENEFIT", "POLICE_REPORT_IF_UNNATURAL"]), "p_filing_90d"),
    ("CI-CHUBB-05", 0, 90, "diagnosis", "reject", 30, 30, json.dumps(["CLAIM_FORM", "DOCTOR_STATEMENT", "PATHOLOGY_REPORT", "SPECIALIST_CONFIRMATION", "ID_CARD", "BANK_ACCOUNT"]), "ci_filing"),
    ("BPJS-KES-RIZKY", 0, 0, "discharge", "none", 0, 0, json.dumps(["BPJS_CARD_OR_JKN_APP", "ID_COPY", "REFERRAL_LETTER_OR_ER_NOTE", "SEP"]), "r_docs_inpatient"),
    ("GH-NUSA-GRP", 0, 30, "discharge", "discretionary", 14, 14, json.dumps(["CLAIM_FORM", "ITEMISED_BILL_ORIGINAL", "MEDICAL_RESUME_INPATIENT", "EMPLOYEE_ID", "ID_COPY"]), "p_filing_30d"),
    ("GL-NUSA-GRP", 0, 90, "death", "discretionary", 30, 30, json.dumps(["CLAIM_FORM_DEATH", "DEATH_CERT_ORIGINAL_OR_LEGALISED", "EMPLOYER_CONFIRMATION", "HEIR_ID_AND_RELATIONSHIP_PROOF", "POLICE_REPORT_IF_UNNATURAL"]), "p_filing_90d"),
    ("HCP-RIDER-B", 0, 90, "discharge", "discretionary", 14, 30, json.dumps(["CLAIM_FORM_INPATIENT", "DOCTOR_STATEMENT_INPATIENT", "ID_COPY", "MEDICAL_RESULTS_COPY", "ITEMISED_BILL_ORIGINAL_OR_LEGALISED", "BANK_BOOK_COPY"]), "p_filing_90d"),
    ("HI-INDIV-S", 0, 30, "discharge", "discretionary", 14, 14, json.dumps(["CLAIM_FORM", "RECEIPT_ORIGINAL_OR_LEGALISED", "ITEMISED_BILL", "MEDICAL_RESUME_INPATIENT", "ID_COPY", "COB_LETTER_FIRST_INSURER", "BANK_BOOK_COPY"]), "p_filing_30d"),
    ("BPJS-KES-SANTOSO", 0, 0, "discharge", "none", 0, 0, json.dumps(["BPJS_CARD_OR_JKN_APP", "ID_COPY", "REFERRAL_LETTER_OR_ER_NOTE", "SEP"]), "r_docs_inpatient"),
    ("PA-CHUBB-03", 30, 30, "accident", "discretionary", 14, 14, json.dumps(["CLAIM_FORM", "POLICE_REPORT", "MEDICAL_REPORT", "ITEMISED_BILL_ORIGINAL", "ID_COPY", "DRIVING_LICENSE_COPY"]), "p_filing_30d"),
    ("PLATFORM-ACC", 7, 7, "accident", "reject", 7, 14, json.dumps(["APP_CLAIM_FORM", "TRIP_LOG_SCREENSHOT", "MEDICAL_REPORT", "ITEMISED_BILL", "ID_COPY"]), "p_filing_7d"),
    ("BPJS-KES-DEWI", 0, 0, "discharge", "none", 0, 0, json.dumps(["BPJS_CARD_OR_JKN_APP", "ID_COPY", "REFERRAL_LETTER_OR_ER_NOTE", "SEP"]), "r_docs_inpatient"),
    ("JASA-RAHARJA", 0, 180, "accident", "reject", 14, 14, json.dumps(["POLICE_REPORT", "JASA_RAHARJA_CLAIM_FORM", "ID_COPY", "MEDICAL_BILL_ORIGINAL", "DOCTOR_STATEMENT"]), "p_filing_180d"),
]

FACILITIES = [
    ("F-SOETOMO", "RSUD Dr. Soetomo Surabaya", 1, "[]", "A"),
    ("F-SILOAM", "Siloam Hospitals Surabaya", 0, '["N1"]', "B"),
    ("F-BHAYANGKARA", "RS Bhayangkara Surabaya", 1, '["N1"]', "B"),
    ("F-MITRA", "RS Mitra Keluarga Surabaya", 1, '["N1","N2"]', "B"),
    ("F-KLINIK", "Klinik Pratama Sehat (FKTP)", 1, "[]", "CLINIC"),
]

TARIFFS = [  # mock INA-CBG values, labelled as such
    ("A-4-13-I", 2, 4500000, "Dengue fever, mild (mock)"),
    ("A-4-13-II", 2, 6800000, "Dengue fever, moderate (mock)"),
    ("A-4-13-III", 2, 9200000, "Dengue haemorrhagic fever, severe (mock)"),
    ("E-4-10-I", 1, 5100000, "Asthma and bronchiolitis, mild (mock)"),
    ("W-1-20-I", 3, 7600000, "Injury to lower extremity, inpatient (mock)"),
    ("A-4-13-I", 1, 5400000, "Dengue fever, mild (mock)"),
    ("A-4-14-I", 1, 4800000, "Typhoid fever, mild (mock)"),
    ("A-4-14-I", 2, 4100000, "Typhoid fever, mild (mock)"),
    ("E-4-10-I", 2, 4300000, "Asthma and bronchiolitis, mild (mock)"),
]

CLAIMS = [
    # id, policy, customer, event_type, event_date, admission, discharge, icd, cause, facility, partner, emergency, billed, claim_amount, status, rejection, filed, deadline, via
    ("CL-RIZKY-BPJS-01", "BPJS-KES-RIZKY", "C-RIZKY", "HOSPITALIZATION", "2026-10-03", "2026-10-03", "2026-10-07", "A90", "illness", "F-SOETOMO", 1, 1, 9200000, 9200000, "paid", None, "2026-10-03", None, "facility"),
    ("CL-RIZKY-HCP-01", "HCP-SOMPO-01", "C-RIZKY", "HOSPITALIZATION", "2026-10-03", "2026-10-03", "2026-10-07", "A90", "illness", "F-SOETOMO", 1, 1, 9200000, 2500000, "draft", None, None, "2026-12-06", "assistant"),
    ("CL-ADITYA-GH-01", "GH-NUSA-GRP", "C-ADITYA", "HOSPITALIZATION", "2026-09-28", "2026-09-28", "2026-10-02", "J45.9", "illness", "F-SILOAM", 0, 0, 18000000, 13700000, "approved", None, "2026-10-02", "2026-11-01", "facility"),
    ("CL-DEWI-PA-01", "PA-CHUBB-03", "C-DEWI", "ACCIDENT_MEDICAL", "2026-10-05", "2026-10-05", "2026-10-11", "S82.2", "accident_traffic_multi", "F-BHAYANGKARA", 1, 1, 22000000, None, "draft", None, None, "2026-11-04", "assistant"),
]

CLAIM_PAYMENTS = [
    ("CP-1", "CL-RIZKY-BPJS-01", "BPJS Kesehatan", 9200000, "2026-10-07"),
    ("CP-2", "CL-ADITYA-GH-01", "PT Asuransi Nusantara (mock)", 13700000, "2026-10-09"),
]

PAYMENTS = [
    ("PM-HCP-1", "HCP-SOMPO-01", "2026-08-20", "2026-08-20", 1980000),
    ("PM-TL-6", "TL-ASTRA-07", "2026-06-01", "2026-06-01", 103500),
    ("PM-TL-7", "TL-ASTRA-07", "2026-07-01", "2026-07-01", 103500),
    ("PM-TL-8", "TL-ASTRA-07", "2026-08-01", "2026-08-01", 103500),
    ("PM-TL-9", "TL-ASTRA-07", "2026-09-01", None, 103500),
    ("PM-TL-10", "TL-ASTRA-07", "2026-10-01", None, 103500),
    ("PM-CI-1", "CI-CHUBB-05", "2026-06-01", "2026-06-01", 1200000),
    ("PM-BPJS-R-9", "BPJS-KES-RIZKY", "2026-09-10", "2026-09-08", 100000),
    ("PM-BPJS-R-10", "BPJS-KES-RIZKY", "2026-10-10", "2026-10-09", 100000),
    ("PM-HR-9", "HCP-RIDER-B", "2026-09-01", "2026-09-01", 450000),
    ("PM-HR-10", "HCP-RIDER-B", "2026-10-01", "2026-10-01", 450000),
    ("PM-HI-1", "HI-INDIV-S", "2025-11-01", "2025-11-01", 6000000),
    ("PM-PA-1", "PA-CHUBB-03", "2026-03-15", "2026-03-15", 600000),
    ("PM-BPJS-D-7", "BPJS-KES-DEWI", "2026-07-10", None, 42000),
    ("PM-BPJS-D-8", "BPJS-KES-DEWI", "2026-08-10", None, 42000),
    ("PM-BPJS-D-9", "BPJS-KES-DEWI", "2026-09-10", None, 42000),
    ("PM-BPJS-D-10", "BPJS-KES-DEWI", "2026-10-10", None, 42000),
]

BENEFICIARIES = [
    ("BN-TL-1", "TL-ASTRA-07", "Siti Rahayu", "mother", 100.0, _h("3578012345670001")),
    # GL-NUSA-GRP: deliberately no nomination (gap -> estate)
]

DOCUMENTS = [
    ("DOC-HCP-SOMPO-01", "HCP-SOMPO-01", None, "riplay", "data/policies/real/roojai_hcp_en.pdf", "verified"),
    ("DOC-CI-CHUBB-05", "CI-CHUBB-05", None, "policy_wording", "data/personas/policies/CI-CHUBB-05.json", "verified"),
    ("DOC-TL-ASTRA-07", "TL-ASTRA-07", None, "riplay", "data/policies/real/astra_flexi_life.pdf", "verified"),
    ("DOC-HCP-RIDER-B", "HCP-RIDER-B", None, "riplay", "data/policies/real/astra_hcp.pdf", "verified"),
    ("DOC-PA-CHUBB-03", "PA-CHUBB-03", None, "policy_wording", "data/policies/real/chubb_my_pa.pdf", "verified"),
    ("DOC-GH-NUSA-GRP", "GH-NUSA-GRP", None, "policy_wording", "data/personas/policies/GH-NUSA-GRP.json", "verified"),
    ("DOC-GL-NUSA-GRP", "GL-NUSA-GRP", None, "policy_wording", "data/personas/policies/GL-NUSA-GRP.json", "verified"),
    ("DOC-HI-INDIV-S", "HI-INDIV-S", None, "policy_wording", "data/personas/policies/HI-INDIV-S.json", "verified"),
    ("DOC-PLATFORM-ACC", "PLATFORM-ACC", None, "policy_wording", "data/personas/policies/PLATFORM-ACC.json", "verified"),
    ("DOC-BPJS-KES", None, None, "policy_wording", "data/personas/policies/BPJS-KES.json", "verified"),
    ("DOC-JASA-RAHARJA", "JASA-RAHARJA", None, "policy_wording", "data/personas/policies/JASA-RAHARJA.json", "verified"),
    ("DOC-CL-RIZKY-1", None, "CL-RIZKY-BPJS-01", "discharge_summary", "data/personas/uploads/rizky_discharge_soetomo.pdf", "untrusted"),
    ("DOC-CL-ADITYA-1", None, "CL-ADITYA-GH-01", "invoice", "data/personas/uploads/aditya_siloam_invoice.pdf", "untrusted"),
]


def seed(conn: sqlite3.Connection) -> None:
    """Insert all persona rows (idempotent via INSERT OR REPLACE) and write the policy JSON files."""
    conn.executemany("INSERT OR REPLACE INTO customers VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", CUSTOMERS)
    conn.executemany("INSERT OR REPLACE INTO policies VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", POLICIES)
    conn.executemany("INSERT OR REPLACE INTO coverages VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", COVERAGES)
    conn.executemany("INSERT OR REPLACE INTO exclusions VALUES (?,?,?,?,?)", EXCLUSIONS)
    conn.executemany("INSERT OR REPLACE INTO riders VALUES (?,?,?,?,?,?)", RIDERS)
    conn.executemany("INSERT OR REPLACE INTO other_insurance_clauses VALUES (?,?,?,?,?)", OTHER_INSURANCE)
    conn.executemany("INSERT OR REPLACE INTO claim_rules VALUES (?,?,?,?,?,?,?,?,?)", CLAIM_RULES)
    conn.executemany(
        "INSERT OR REPLACE INTO claims(id,policy_id,customer_id,event_type,event_date,admission_date,discharge_date,"
        "diagnosis_icd,cause,facility_id,facility_is_bpjs_partner,is_emergency,billed_amount,claim_amount,status,"
        "rejection_code,filed_date,deadline_date,created_via) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        CLAIMS,
    )
    conn.executemany("INSERT OR REPLACE INTO claim_payments VALUES (?,?,?,?,?)", CLAIM_PAYMENTS)
    conn.executemany("INSERT OR REPLACE INTO payments VALUES (?,?,?,?,?)", PAYMENTS)
    conn.executemany("INSERT OR REPLACE INTO beneficiaries VALUES (?,?,?,?,?,?)", BENEFICIARIES)
    conn.executemany("INSERT OR REPLACE INTO documents(id,policy_id,claim_id,type,file_path,taint_label) VALUES (?,?,?,?,?,?)", DOCUMENTS)
    conn.executemany("INSERT OR REPLACE INTO facilities VALUES (?,?,?,?,?)", FACILITIES)
    conn.executemany("INSERT OR REPLACE INTO tariffs_ina_cbg VALUES (?,?,?,?)", TARIFFS)
    conn.commit()
    write_policy_files()
    load_into_store()


# ---------------------------------------------------------------- PolicyRecord JSON
def write_policy_files(out_dir: Optional[Union[str, Path]] = None) -> list[Path]:
    out = Path(out_dir) if out_dir else POLICY_DIR
    out.mkdir(parents=True, exist_ok=True)
    paths = []
    for pid, rec in build_policy_records().items():
        p = out / f"{pid}.json"
        text = rec.model_dump_json(indent=2)
        # atomic and idempotent: concurrent readers (other runs, tests) never see a half-written file
        if not (p.exists() and p.read_text(encoding="utf-8") == text):
            tmp = out / f".{pid}.{os.getpid()}.tmp"
            tmp.write_text(text, encoding="utf-8")
            os.replace(tmp, p)
        paths.append(p)
    return paths


def load_policy_files(in_dir: Optional[Union[str, Path]] = None) -> dict[str, PolicyRecord]:
    d = Path(in_dir) if in_dir else POLICY_DIR
    if not d.exists() or not any(d.glob("*.json")):
        write_policy_files(d)
    out: dict[str, PolicyRecord] = {}
    for p in sorted(d.glob("*.json")):
        rec = PolicyRecord.model_validate_json(p.read_text(encoding="utf-8"))
        out[rec.id] = rec
    return out


def owner_map(conn: Optional[sqlite3.Connection] = None) -> dict[str, list[str]]:
    """record_id -> [customer ids that hold it]. Statutory records (customer NULL) belong to everyone."""
    close = conn is None
    if conn is None:
        from .db import init_db

        conn = init_db(seed=False)
    rows = conn.execute("SELECT record_id, customer_id FROM policies").fetchall()
    out: dict[str, list[str]] = {}
    for r in rows:
        out.setdefault(r["record_id"], [])
        if r["customer_id"] and r["customer_id"] not in out[r["record_id"]]:
            out[r["record_id"]].append(r["customer_id"])
    if close:
        conn.close()
    return out


def load_into_store() -> bool:
    """Push the verified records into clauseguard.store.ClauseStore if the store module is importable."""
    try:
        from ..store import ClauseStore  # type: ignore
    except Exception:
        return False
    try:
        store = ClauseStore()
        for pid, rec in load_policy_files().items():
            store.add_policy(rec, owner_user_id=None)
        return True
    except Exception:
        return False


def persona_user(persona: str) -> dict:
    if persona not in PERSONAS:
        raise KeyError(f"unknown persona {persona!r}; choose one of {sorted(PERSONAS)}")
    return PERSONAS[persona]
