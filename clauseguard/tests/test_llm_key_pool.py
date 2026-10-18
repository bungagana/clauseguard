"""A key the API rejects as invalid is skipped, not fatal: the call is retried on the next key."""
from __future__ import annotations

from types import SimpleNamespace

from clauseguard import config, llm


class _Models:
    def __init__(self, key):
        self.key = key

    def generate_content(self, **kw):
        if self.key == "bad":
            raise RuntimeError("400 INVALID_ARGUMENT. {'error': {'message': 'API key not valid. Please pass a valid API key.'}}")
        return SimpleNamespace(text='{"ok": true}')


def test_invalid_key_rotates_to_the_next_one(monkeypatch):
    monkeypatch.setattr(config, "GEMINI_API_KEYS", ["bad", "good"])
    monkeypatch.setattr(llm, "_key_index", 0)
    monkeypatch.setattr(llm, "_exhausted", {})
    monkeypatch.setattr(llm, "client", lambda: SimpleNamespace(models=_Models(llm._keys()[llm._key_index % 2])))
    monkeypatch.delenv("CG_OFFLINE", raising=False)
    assert llm.generate_json("hi", use_cache=False) == {"ok": True}
    assert llm._exhausted["bad"] > 0  # kept out of rotation


def test_a_per_minute_limit_rests_a_key_for_about_a_minute_not_an_hour():
    per_minute = "429 RESOURCE_EXHAUSTED. Quota exceeded ... 'Request limit per minute for a region'. Please retry in 41.5s"
    assert 40 < llm._quota_cooldown(per_minute) < 50
    assert llm._quota_cooldown("429 RESOURCE_EXHAUSTED") == 65.0
    assert llm._quota_cooldown("Quota exceeded for metric ... PerDay") == 3600.0
