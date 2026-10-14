"""Curated diagnosis-name -> ICD-10 code lookup, deterministic code only (no LLM, no fuzzy matching).

Real discharge summaries and diagnosis letters almost never carry a literal numeric ICD-10
code: doctors write the diagnosis as a name ("Demam Berdarah Dengue", "Acute Myocardial
Infarction"); the numeric code is usually assigned afterwards by hospital billing coders and
rarely appears on what the patient holds. So the document extractor pulls out the diagnosis
*name* as printed, and this module resolves that name to a code by plain dictionary lookup.

This is a small, curated subset covering only the conditions relevant to the demo's
critical-illness coverage check (see data/personas/policies/CI-CHUBB-05.json), plus dengue
hemorrhagic fever (a common Indonesian hospitalisation, not on that covered list) for the
negative-case fixture. It is NOT general medical coding or NLP. A diagnosis name with no
listed alias resolves to None ("undetermined") rather than being guessed at, consistent with
the rest of this project: never commit to a fact the evidence does not actually support.
"""
from __future__ import annotations

import re

#: alias (lowercased, whitespace-normalised) -> ICD-10 code. English and Indonesian phrasings.
_ALIASES: dict[str, str] = {
    # malignant neoplasm (WHO ICD-10 chapter II, C00-C97) -- one representative common site
    "breast cancer": "C50",
    "kanker payudara": "C50",
    "carcinoma mammae": "C50",
    "ca mammae": "C50",
    # acute myocardial infarction (heart attack)
    "acute myocardial infarction": "I21",
    "myocardial infarction": "I21",
    "heart attack": "I21",
    "infark miokard akut": "I21",
    "stemi": "I21",
    "nstemi": "I21",
    # stroke / cerebrovascular disease
    "ischemic stroke": "I63",
    "stroke iskemik": "I63",
    "cerebral infarction": "I63",
    "hemorrhagic stroke": "I61",
    "stroke hemoragik": "I61",
    "cerebrovascular accident": "I64",
    "cva": "I64",
    # end-stage renal disease / chronic kidney failure
    "end-stage renal disease": "N18.6",
    "end stage renal disease": "N18.6",
    "esrd": "N18.6",
    "gagal ginjal terminal": "N18.6",
    "chronic kidney disease stage 5": "N18.5",
    "penyakit ginjal kronik stadium 5": "N18.5",
    "gagal ginjal kronik stadium 5": "N18.5",
    # common illness NOT on CI-CHUBB-05's covered list -- kept for the negative-case fixture
    "demam berdarah dengue": "A91",
    "dbd": "A91",
    "dhf": "A91",
    "dengue hemorrhagic fever": "A91",
}


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().lower())


def english_synonyms(diagnosis_text: str) -> list[str]:
    """English alias keys sharing a code with any alias found in the line (retrieval aid for the coder's offline path)."""
    if not diagnosis_text:
        return []
    text = _norm(diagnosis_text)
    codes = {code for alias, code in _ALIASES.items() if re.search(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", text)}
    return [alias for alias, code in _ALIASES.items() if code in codes and re.fullmatch(r"[a-z0-9 -]+", alias) and len(alias) > 4]


def lookup(diagnosis_text: str) -> "str | None":
    """Whole-word alias match inside the diagnosis line; None means undetermined, never a guess.

    Discharge summaries qualify the name ("Carcinoma mammae dextra, stadium IIA"), so an alias
    is accepted when it appears as a whole word or phrase. Two aliases resolving to different
    codes make the line ambiguous and it stays undetermined.
    """
    if not diagnosis_text:
        return None
    text = _norm(diagnosis_text)
    exact = _ALIASES.get(text)
    if exact:
        return exact
    found: set[str] = set()
    for alias, code in _ALIASES.items():
        if re.search(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", text):
            found.add(code)
    return found.pop() if len(found) == 1 else None
