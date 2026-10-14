"""icd10_coder: BM25 retrieval over the official list, constrained selection, code-side guards. LLM stubbed."""
from __future__ import annotations

import pytest

from clauseguard import icd10_coder as coder
from clauseguard import llm

pytestmark = pytest.mark.skipif(not coder.CODES_PATH.exists(), reason="data/real/icd10cm_codes.txt not downloaded")


def _cats(cands):
    return [c.code for c in cands if c.level == "category"]


@pytest.mark.parametrize(
    "line,gold",
    [
        ("Carcinoma mammae dextra (kanker payudara), stadium IIA", "C50"),
        ("Demam Berdarah Dengue (DBD) derajat II", "A91"),
        ("infark miokard akut (STEMI) anterior", "I21"),
        ("Stroke iskemik, hemiparesis sinistra", "I63"),
        ("gagal ginjal terminal", "N18"),
        ("Demam tifoid", "A01"),
        ("Apendisitis akut perforasi", "K35"),
        ("COVID-19 terkonfirmasi, pneumonia berat", "U07"),
    ],
)
def test_bm25_puts_gold_category_in_top_k_with_offline_terms(line, gold):
    cands = coder.retrieve(coder.offline_terms(line))
    assert gold in _cats(cands)
    assert len(_cats(cands)) <= coder.TOP_K_CATEGORIES


def test_category_labels_come_from_the_official_descriptions():
    cl = coder.code_list()
    assert cl.category_label["A91"] == "Dengue hemorrhagic fever"
    assert cl.category_label["I21"].lower().startswith("acute myocardial infarction")
    assert "breast" in cl.category_label["C50"].lower()
    assert cl.codes["U071"] == "COVID-19"
    assert coder.dotted("C50911") == "C50.911" and coder.dotted("A91") == "A91"


@pytest.fixture
def stub_select(monkeypatch):
    """Normalisation is forced offline; the selection answer is whatever the test sets."""
    state = {"answer": None, "prompts": []}

    def fake(prompt, **kw):
        if kw.get("schema") is coder._Normalised:
            raise RuntimeError("normaliser off")
        state["prompts"].append(prompt)
        if isinstance(state["answer"], Exception):
            raise state["answer"]
        return dict(state["answer"])

    monkeypatch.setattr(llm, "generate_json", fake)
    return state


TEXT = "Demam Berdarah Dengue (DBD) derajat II"


def test_select_accepts_candidate_with_verified_phrase(stub_select):
    stub_select["answer"] = {"code": "A91", "matched_phrase": "demam  berdarah dengue", "confidence": 0.93}
    r = coder.resolve(TEXT)
    assert r.determined and r.category == "A91" and r.code == "A91"
    assert r.matched_phrase == "demam berdarah dengue" and r.confidence == 0.93
    assert r.normalisation == "offline"
    assert "A91" in stub_select["prompts"][0] and "<diagnosis>" in stub_select["prompts"][0]


def test_select_rejects_code_outside_candidate_list(stub_select):
    stub_select["answer"] = {"code": "C50", "matched_phrase": "Demam Berdarah Dengue", "confidence": 0.95}
    r = coder.resolve(TEXT)
    assert not r.determined and r.reject_reason.startswith("not_in_candidates")


def test_select_rejects_phrase_not_in_text(stub_select):
    stub_select["answer"] = {"code": "A91", "matched_phrase": "dengue hemorrhagic fever", "confidence": 0.95}
    r = coder.resolve(TEXT)
    assert not r.determined and r.reject_reason == "phrase_not_in_text"


def test_select_rejects_low_confidence(stub_select):
    stub_select["answer"] = {"code": "A91", "matched_phrase": "Demam Berdarah Dengue", "confidence": coder.CONFIDENCE_THRESHOLD - 0.01}
    r = coder.resolve(TEXT)
    assert not r.determined and r.reject_reason.startswith("low_confidence")


def test_model_null_is_respected(stub_select):
    stub_select["answer"] = {"code": None, "matched_phrase": "", "confidence": 0.2}
    r = coder.resolve(TEXT)
    assert not r.determined and r.reject_reason == "model_null"
    assert len(stub_select["prompts"]) == 1


def test_no_candidates_means_no_selection_call(stub_select):
    r = coder.resolve("Demam")
    assert not r.determined and r.reject_reason == "no_candidates" and stub_select["prompts"] == []


def test_full_code_resolves_to_its_category(stub_select):
    line = "Carcinoma mammae dextra (kanker payudara), stadium IIA"
    full = next(c.code for c in coder.retrieve(coder.offline_terms(line)) if c.level == "code" and c.code.startswith("C50."))
    stub_select["answer"] = {"code": full, "matched_phrase": "Carcinoma mammae dextra", "confidence": 0.9}
    r = coder.resolve(line)
    assert r.code == full and r.category == "C50" and "." in full


def test_model_unavailable_raises_not_guesses(stub_select):
    stub_select["answer"] = RuntimeError("LLM disabled (CG_OFFLINE=1)")
    with pytest.raises(coder.CoderUnavailable):
        coder.resolve(TEXT)


def test_schema_garbage_is_undetermined(stub_select):
    stub_select["answer"] = {"doc_type": "LETTER"}
    r = coder.resolve(TEXT)
    assert not r.determined and r.reject_reason.startswith("schema")


def test_empty_text_is_undetermined_without_any_call(stub_select):
    r = coder.resolve("   ")
    assert not r.determined and stub_select["prompts"] == []


# --------------------------------------------------------------------------- #
# dense retrieval, fusion and evaluation statistics (offline: deterministic fake embeddings)
# --------------------------------------------------------------------------- #
import hashlib  # noqa: E402

import numpy as np  # noqa: E402

from bench import icd_eval  # noqa: E402
from clauseguard import config as cg_config  # noqa: E402
from clauseguard import icd10_embed as emb  # noqa: E402


class FakeBackend:
    """Bag-of-hashed-tokens embedding: texts sharing tokens are close. Counts calls."""

    name = "gemini"
    model = "fake-bow-64"

    def __init__(self):
        self.calls = {"document": 0, "query": 0}
        self.fail_queries = False

    def embed(self, texts, kind):
        self.calls[kind] += 1
        if kind == "query" and self.fail_queries:
            raise emb.EmbeddingUnavailable("api down")
        m = np.zeros((len(texts), 64), dtype=np.float32)
        for i, t in enumerate(texts):
            for tok in coder.tokenize(t):
                m[i, int(hashlib.md5(tok.encode()).hexdigest(), 16) % 64] += 1.0
        return emb._normalise_rows(m + 1e-6)


@pytest.fixture
def fake_dense(tmp_path, monkeypatch):
    monkeypatch.setattr(cg_config, "CACHE_DIR", tmp_path)
    monkeypatch.setenv("CG_ICD_RETRIEVER", "bm25")
    fake = FakeBackend()
    emb.set_backend("gemini", fake)
    coder.reset_embeddings()
    yield fake
    emb.set_backend("gemini", None)
    coder.reset_embeddings()


def _docs():
    cl = coder.code_list()
    return emb.category_documents(cl.codes, cl.category_label)


def test_rrf_toy_example_matches_hand_computation():
    fused = dict(emb.rrf([["a", "b", "c"], ["b", "c", "d"]], k=60))
    assert fused["a"] == pytest.approx(1 / 61)
    assert fused["b"] == pytest.approx(1 / 62 + 1 / 61)
    assert fused["c"] == pytest.approx(1 / 63 + 1 / 62)
    assert fused["d"] == pytest.approx(1 / 63)
    assert [d for d, _ in emb.rrf([["a", "b", "c"], ["b", "c", "d"]])] == ["b", "c", "a", "d"]
    assert emb.RRF_K == 60


def test_rrf_ties_break_by_id_and_single_list_keeps_order():
    assert [d for d, _ in emb.rrf([["x", "y"], ["y", "x"]])] == ["x", "y"]
    assert [d for d, _ in emb.rrf([["q", "p", "r"]])] == ["q", "p", "r"]


def test_category_documents_use_official_label_and_member_descriptions():
    docs = _docs()
    assert docs["A91"].startswith("Dengue hemorrhagic fever")
    assert len(docs) == coder.code_list().n_categories
    assert all(len(d) <= 500 for d in docs.values())


def test_cache_miss_builds_once_then_hits(fake_dense):
    docs = _docs()
    assert emb.load_index(fake_dense, docs) is None
    idx = emb.build_index(fake_dense, docs)
    built = fake_dense.calls["document"]
    assert built >= 1 and idx.matrix.shape == (len(docs), 64)
    again = emb.build_index(fake_dense, docs)
    assert fake_dense.calls["document"] == built
    assert np.allclose(again.matrix, idx.matrix) and again.ids == idx.ids


def test_cache_is_keyed_by_text_hash_and_model(fake_dense):
    docs = _docs()
    emb.build_index(fake_dense, docs)
    changed = dict(docs, A91=docs["A91"] + " extra")
    assert emb.load_index(fake_dense, changed) is None
    other = FakeBackend()
    other.model = "another-model"
    assert emb.load_index(other, docs) is None


def test_corrupt_cache_is_a_miss_not_an_error(fake_dense):
    docs = _docs()
    emb.build_index(fake_dense, docs)
    emb.index_path(fake_dense, docs).write_bytes(b"not an npz")
    assert emb.load_index(fake_dense, docs) is None


def test_no_cached_embeddings_falls_back_to_bm25_only(fake_dense):
    r = coder.ranked_categories(coder.offline_terms(TEXT), TEXT, "gemini:hybrid")
    assert r[1] == "bm25"
    assert fake_dense.calls["query"] == 0
    assert [c for c, _ in r[0]] == [c for c, _ in coder.ranked_categories(coder.offline_terms(TEXT), TEXT, "bm25")[0]]


def test_hybrid_uses_dense_when_cache_present_and_bounds_candidates(fake_dense):
    emb.build_index(fake_dense, _docs())
    coder.reset_embeddings()
    terms = coder.offline_terms(TEXT)
    cands, used, ranked = coder._retrieve(terms, 15, 5, TEXT, "gemini:hybrid")
    assert used == "gemini:hybrid"
    assert len(cands) <= 20 and len([c for c in cands if c.level == "category"]) == 15
    assert len(ranked) == coder.RANK_DEPTH
    cats = {c.code for c in cands if c.level == "category"}
    assert all(coder.category_of(c.code) in cats for c in cands if c.level == "code")


def test_query_time_embedding_failure_degrades_to_bm25(fake_dense):
    emb.build_index(fake_dense, _docs())
    coder.reset_embeddings()
    fake_dense.fail_queries = True
    _, used = coder.ranked_categories(coder.offline_terms(TEXT), TEXT, "gemini:hybrid")
    assert used == "bm25"


def test_emb_only_differs_from_hybrid_ranking_source(fake_dense):
    emb.build_index(fake_dense, _docs())
    coder.reset_embeddings()
    terms = coder.offline_terms(TEXT)
    assert coder.ranked_categories(terms, TEXT, "gemini:emb")[1] == "gemini:emb"
    assert coder.ranked_categories(terms, TEXT, "gemini:hybrid")[1] == "gemini:hybrid"


@pytest.mark.parametrize("answer,reason", [
    ({"code": "C50", "matched_phrase": "Demam Berdarah Dengue", "confidence": 0.95}, "not_in_candidates"),
    ({"code": "A91", "matched_phrase": "dengue hemorrhagic fever", "confidence": 0.95}, "phrase_not_in_text"),
    ({"code": "A91", "matched_phrase": "Demam Berdarah Dengue", "confidence": 0.3}, "low_confidence"),
    ({"code": None, "matched_phrase": "", "confidence": 0.1}, "model_null"),
])
def test_guards_still_enforced_with_hybrid_retriever(fake_dense, stub_select, answer, reason):
    emb.build_index(fake_dense, _docs())
    coder.reset_embeddings()
    stub_select["answer"] = answer
    r = coder.resolve(TEXT, retriever="gemini:hybrid")
    assert not r.determined and r.reject_reason.startswith(reason)
    assert r.retriever == "gemini:hybrid"


def test_hybrid_accepts_a_verified_candidate(fake_dense, stub_select):
    emb.build_index(fake_dense, _docs())
    coder.reset_embeddings()
    stub_select["answer"] = {"code": "A91", "matched_phrase": "Demam Berdarah Dengue", "confidence": 0.9}
    r = coder.resolve(TEXT, retriever="gemini:hybrid")
    assert r.category == "A91" and r.ranked_categories


def test_wilson_interval_known_values():
    lo, hi = icd_eval.wilson(5, 10)
    assert (lo, hi) == pytest.approx((0.2366, 0.7634), abs=5e-4)
    lo, hi = icd_eval.wilson(0, 10)
    assert lo == 0.0 and hi == pytest.approx(0.2775, abs=5e-4)
    lo, hi = icd_eval.wilson(10, 10)
    assert hi == pytest.approx(1.0) and lo == pytest.approx(0.7225, abs=5e-4)
    lo, hi = icd_eval.wilson(8, 10)
    assert (lo, hi) == pytest.approx((0.4902, 0.9433), abs=5e-4)


def test_exact_mcnemar_known_values():
    assert icd_eval.binom_two_sided(0, 5) == pytest.approx(0.0625)
    assert icd_eval.binom_two_sided(1, 9) == pytest.approx(0.021484375)
    assert icd_eval.binom_two_sided(3, 3) == 1.0
    assert icd_eval.binom_two_sided(0, 0) == 1.0
    r = icd_eval.mcnemar([True, True, False, False, True], [True, False, True, True, True])
    assert (r["a_only"], r["b_only"]) == (1, 2) and r["p"] == pytest.approx(1.0)


def test_eval_sets_are_well_formed_and_disjoint():
    dev = icd_eval.load_set(icd_eval.SETS["development"])
    held = icd_eval.load_set(icd_eval.SETS["heldout"])
    assert len(held) >= 60 and sum(1 for r in held if not r["gold"]) >= 12
    assert not ({r["text"].lower() for r in dev} & {r["text"].lower() for r in held})
    assert len({r["id"] for r in dev + held}) == len(dev) + len(held)
