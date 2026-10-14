"""icd10_lookup.lookup: curated alias -> code, exact match only, never a guess."""
from clauseguard.icd10_lookup import lookup


def test_known_aliases_resolve_case_and_whitespace_insensitively():
    assert lookup("Demam Berdarah Dengue") == "A91"
    assert lookup("  demam   berdarah dengue ") == "A91"
    assert lookup("DBD") == "A91"
    assert lookup("Acute Myocardial Infarction") == "I21"
    assert lookup("stroke iskemik") == "I63"
    assert lookup("End-Stage Renal Disease") == "N18.6"


def test_unlisted_diagnosis_is_undetermined_not_guessed():
    assert lookup("Severe tropical fatigue syndrome") is None
    assert lookup("fever") is None  # a symptom, not a named diagnosis; must not be guessed at


def test_empty_input_is_undetermined():
    assert lookup("") is None
    assert lookup(None) is None
