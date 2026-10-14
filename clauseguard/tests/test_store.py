"""ClauseStore: SQLite round-trip, owner map, cosine search over evidence text (embeddings mocked)."""
from __future__ import annotations

import pytest

from clauseguard import llm
from clauseguard.schema import ClauseTuple, Evidence, PolicyRecord, Qualifiers, Relation
from clauseguard.store import ClauseStore


def _policy(pid: str, texts: list[str]) -> PolicyRecord:
    tuples = [
        ClauseTuple(id=f"{pid}-t{i}", policy_id=pid, head=pid, relation=Relation.COVERS, object="DEATH",
                    qualifiers=Qualifiers(), evidence=Evidence(doc_id="d", section="S", text=t))
        for i, t in enumerate(texts)
    ]
    return PolicyRecord(id=pid, doc_id="d", insurer="X", product_name="P", product_type="term_life", tuples=tuples)


@pytest.fixture
def store(tmp_path, monkeypatch):
    # deterministic fake embeddings: bag of a few keywords
    vocab = ["suicide", "grace", "hospital", "death", "loan"]

    def fake_embed(texts, **kw):
        return [[float(w in t.lower()) for w in vocab] + [0.01] for t in texts]

    calls = {"n": 0}

    def counting(texts, **kw):
        calls["n"] += len(texts)
        return fake_embed(texts)

    monkeypatch.setattr(llm, "embed", counting)
    s = ClauseStore(tmp_path / "t.sqlite")
    s.calls = calls
    return s


def test_round_trip_and_owners(store):
    p = _policy("P1", ["Suicide within two years: premiums refunded.", "Grace period of 31 days."])
    store.add_policy(p, owner_user_id="u1")
    store.add_policy(_policy("P2", ["Hospital cash 500,000 per day."]), owner_user_id="u2")
    assert store.get_policy("P1") == p
    assert [x.id for x in store.policies_for_user("u1")] == ["P1"]
    assert [x.id for x in store.all_policies()] == ["P1", "P2"]
    assert store.get_tuple("P2-t0").evidence.text.startswith("Hospital")
    with pytest.raises(KeyError):
        store.get_policy("nope")
    # re-adding replaces tuples (idempotent)
    store.add_policy(_policy("P1", ["Grace period of 31 days."]), owner_user_id="u1")
    assert len(store.get_policy("P1").tuples) == 1


def test_search_cosine_and_cache(store):
    store.add_policy(_policy("P1", ["Suicide within two years: premiums refunded.", "Grace period of 31 days."]), "u1")
    store.add_policy(_policy("P2", ["Hospital cash 500,000 per day."]), "u2")
    r = store.search_clauses("suicide clause", k=1)
    assert r[0].evidence.text.startswith("Suicide")
    n = store.calls["n"]
    r2 = store.search_clauses("grace period", policy_ids=["P1"], k=2)
    assert r2[0].evidence.text.startswith("Grace") and all(t.policy_id == "P1" for t in r2)
    # only the new query text needed an embedding call; tuple texts were cached in the table
    assert store.calls["n"] == n + 1
    assert store.search_clauses("anything", policy_ids=["none"]) == []
