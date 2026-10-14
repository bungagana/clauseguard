"""Optional call hook, replay-only mode and live-call cap of clauseguard.llm (all off by default)."""
from __future__ import annotations

import json

import pytest

from clauseguard import config, llm


@pytest.fixture(autouse=True)
def reset(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(llm, "_call_hook", None)
    for k in llm.STATS:
        llm.STATS[k] = 0
    yield
    llm.set_call_hook(None)


def test_hook_sees_sizes_and_cache_state_and_replay_miss_raises(monkeypatch):
    seen = []
    llm.set_call_hook(seen.append)
    monkeypatch.setattr(llm, "REPLAY_ONLY", True)
    with pytest.raises(RuntimeError, match="replay-only"):
        llm.generate_json("hello world", system="sys", schema={"type": "object"})
    assert seen == [{"model": config.MODEL_FAST, "schema": "dict", "prompt_chars": 11, "system_chars": 3, "schema_chars": 18, "max_output_tokens": 8192, "cached": False}]
    key = llm._cache_key("gen", config.MODEL_FAST, "sys", "hello world", {"type": "object"}, None, 8192, 0)
    key.write_text(json.dumps({"ok": 1}), encoding="utf8")
    assert llm.generate_json("hello world", system="sys", schema={"type": "object"}) == {"ok": 1}
    assert seen[-1]["cached"] is True and llm.STATS["cache_hits"] == 1 and llm.STATS["live_calls"] == 0


def test_live_cap_stops_before_any_network_call(monkeypatch):
    monkeypatch.setattr(llm, "REPLAY_ONLY", False)
    monkeypatch.setattr(llm, "LIVE_CAP", 2)
    llm.STATS["live_calls"] = 2
    with pytest.raises(RuntimeError, match="live-call cap"):
        llm.generate_json("never sent")
