"""Thin, cached, retrying wrapper around the Gemini API (google-genai SDK).

Design rules (security-relevant):
- Every call is schema-constrained JSON (response_schema) when a schema is given.
- temperature=0, thinking disabled for extraction (reproducible fixtures).
- Disk cache keyed by (model, prompt, schema, file hash) so re-runs are free.
- No conversation history is ever passed to the quarantined extractor: one prompt, one answer.
"""
from __future__ import annotations

import contextvars
import hashlib
import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel

from . import config

log = logging.getLogger("clauseguard.llm")

# ---- optional instrumentation (cost reports, quota-safe evaluation runs). All off by default.
_call_hook: Optional[Any] = None          # fn(dict) called once per generate_json call: prompt/system sizes, cached or not
REPLAY_ONLY = os.getenv("CG_LLM_REPLAY_ONLY", "") == "1"   # cache hits only; a miss raises before any network call
LIVE_CAP = int(os.getenv("CG_LLM_LIVE_CAP", "0") or 0)      # max live API attempts (0 = unlimited); counted per process, or across processes when CG_LLM_COUNTER_FILE is set
# Persistent counter only when CG_LLM_COUNTER_FILE is set (so concurrent runs of other jobs never share a budget);
# otherwise the cap applies to the live calls made by this process.
_counter_env = os.getenv("CG_LLM_COUNTER_FILE", "")
LIVE_COUNTER_PATH = Path(_counter_env) if _counter_env else None
STATS: dict[str, int] = {"live_calls": 0, "cache_hits": 0, "quota_errors": 0}


def set_call_hook(fn: Optional[Any]) -> None:
    """Register fn(info: dict) called for every generate_json call (see CALL INFO in generate_json)."""
    global _call_hook
    _call_hook = fn


def _live_total() -> int:
    if LIVE_COUNTER_PATH is None:
        return STATS["live_calls"]
    try:
        return int(json.loads(LIVE_COUNTER_PATH.read_text(encoding="utf8")).get("total", 0))
    except Exception:  # noqa: BLE001
        return 0


def _bump_live_total() -> int:
    if LIVE_COUNTER_PATH is None:
        return STATS["live_calls"]
    n = _live_total() + 1
    try:
        LIVE_COUNTER_PATH.parent.mkdir(parents=True, exist_ok=True)
        LIVE_COUNTER_PATH.write_text(json.dumps({"total": n}), encoding="utf8")
    except Exception:  # noqa: BLE001
        pass
    return n


# A customer's own Gemini key, for the request being served only. It lives in the request context (never a global,
# never written to disk or the audit log), so another customer's request can never use it.
_user_key: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("cg_user_key", default=None)
# Why the last call of this request failed ("quota" | "invalid" | "error"), so the reply can tell the customer in plain words.
_last_failure: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("cg_llm_failure", default=None)


def use_user_key(key: Optional[str]) -> contextvars.Token:
    return _user_key.set(key or None)


def reset_user_key(token: contextvars.Token) -> None:
    _user_key.reset(token)


def last_failure() -> Optional[str]:
    return _last_failure.get()


def reset_failure() -> None:
    _last_failure.set(None)


_clients: dict[str, Any] = {}
_key_index = 0
_exhausted: dict[str, float] = {}  # key -> time until which it is out of rotation (per process)


def _keys() -> list[str]:
    keys = list(config.GEMINI_API_KEYS) or ([config.GEMINI_API_KEY] if config.GEMINI_API_KEY else [])
    if not keys:
        raise RuntimeError("GEMINI_API_KEY missing; copy .env.example to .env")
    return keys


def client():
    """Client for the current key of the pool (see rotate_key)."""
    from google import genai

    key = _user_key.get() or _keys()[_key_index % len(_keys())]
    if key not in _clients:
        _clients[key] = genai.Client(api_key=key, http_options={"timeout": config.LLM_TIMEOUT_MS})
    return _clients[key]


def add_runtime_key(key: str) -> int:
    """Add a key to the live pool (in-memory only; not written to .env, so it does not survive a
    restart) and make it the one tried next. Returns the pool size after adding."""
    global _key_index
    key = key.strip()
    existing = list(config.GEMINI_API_KEYS)
    if key not in existing:
        existing.append(key)
        config.GEMINI_API_KEYS = existing
    _exhausted.pop(key, None)
    _key_index = existing.index(key)
    return len(existing)


def _quota_cooldown(msg: str) -> float:
    """How long a key that hit a quota error should rest: a per-minute limit clears in about a minute, a daily one much later."""
    if re.search(r"per ?day|PerDay|daily", msg, re.I):
        return 3600.0
    m = re.search(r"retry in (\d+(?:\.\d+)?)s", msg, re.I) or re.search(r"retryDelay[^0-9]*(\d+)", msg)
    if m:
        return min(float(m.group(1)) + 2.0, 3600.0)
    return 65.0  # no hint: assume the per-minute limit


_INVALID_KEY_MARKERS = ("API key not valid", "API_KEY_INVALID", "API key expired", "API key was reported as leaked")


def rotate_key(invalid: bool = False, cooldown: float = 3600.0) -> bool:
    """Take the current key out of rotation and move to the next one. False if none is available.
    A per-minute limit is back after about a minute, a daily one after about an hour, and a key the API rejects
    as invalid is kept out for a day."""
    global _key_index
    keys = _keys()
    _exhausted[keys[_key_index % len(keys)]] = time.time() + (86400 if invalid else cooldown)
    for _ in range(len(keys)):
        _key_index = (_key_index + 1) % len(keys)
        k = keys[_key_index]
        if time.time() >= _exhausted.get(k, 0):
            log.warning("LLM quota: rotated to key #%d", _key_index + 1)
            return True
    return False


def pool_status() -> dict[str, Any]:
    """Snapshot of key-pool health, for a status endpoint only (never used to gate a decision).

    `available` is a best-effort estimate from calls already made this process: it is False only
    once every key in the pool has been marked exhausted within the last hour. It does not make a
    network call, so it cannot detect a key that is bad for a reason other than quota (e.g. revoked).
    """
    try:
        keys = _keys()
    except RuntimeError:
        return {"configured": False, "available": False, "pool_size": 0, "active_key_index": 0}
    now = time.time()
    live_exhausted = sum(1 for k in keys if _exhausted.get(k, 0) > now)
    return {
        "configured": True,
        "available": live_exhausted < len(keys),
        "pool_size": len(keys),
        "active_key_index": _key_index % len(keys),
    }


def _cache_key(*parts: Any) -> Path:
    h = hashlib.sha256()
    for p in parts:
        h.update(json.dumps(p, sort_keys=True, default=str).encode("utf8"))
        h.update(b"\x00")
    return config.CACHE_DIR / f"{h.hexdigest()}.json"


def _schema_dict(schema: Any) -> Optional[dict]:
    if schema is None:
        return None
    if isinstance(schema, dict):
        return schema
    if isinstance(schema, type) and issubclass(schema, BaseModel):
        return schema.model_json_schema()
    raise TypeError("schema must be a dict or a pydantic model class")


def generate_json(
    prompt: str,
    *,
    model: Optional[str] = None,
    schema: Any = None,
    system: Optional[str] = None,
    pdf_bytes: Optional[bytes] = None,
    max_output_tokens: int = 8192,
    thinking_budget: int = 0,
    use_cache: bool = True,
    retries: int = 5,
) -> Any:
    """Single-shot JSON generation. Returns parsed JSON (dict/list).

    `pdf_bytes` lets the extractor send a whole PDF (handles two-column RIPLAY layouts
    far better than text extraction). The document is DATA: the prompt must say so.
    """
    import os

    if os.getenv("CG_OFFLINE") == "1":
        # Deterministic mode (tests, security suite, keyless demo): callers fall back to templates / rule binders.
        raise RuntimeError("LLM disabled (CG_OFFLINE=1)")

    from google.genai import types as gt

    model = model or config.MODEL_FAST
    sd = _schema_dict(schema)
    file_hash = hashlib.sha256(pdf_bytes).hexdigest() if pdf_bytes else None
    key = _cache_key("gen", model, system, prompt, sd, file_hash, max_output_tokens, thinking_budget)
    cached = bool(use_cache and key.exists())
    if _call_hook is not None:
        try:
            _call_hook({"model": model, "schema": getattr(schema, "__name__", None) or ("dict" if sd else None), "prompt_chars": len(prompt or ""),
                        "system_chars": len(system or ""), "schema_chars": len(json.dumps(sd)) if sd else 0, "max_output_tokens": max_output_tokens, "cached": cached})
        except Exception:  # noqa: BLE001 - instrumentation must never break a call
            pass
    if cached:
        STATS["cache_hits"] += 1
        return json.loads(key.read_text(encoding="utf8"))
    if REPLAY_ONLY:
        raise RuntimeError("LLM replay-only mode: cache miss")

    parts: list[Any] = []
    if pdf_bytes:
        parts.append(gt.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"))
    parts.append(prompt)

    cfg_kwargs: dict[str, Any] = dict(
        temperature=config.TEMPERATURE,
        max_output_tokens=max_output_tokens,
        response_mime_type="application/json",
    )
    if sd is not None:
        cfg_kwargs["response_json_schema"] = sd
    if system:
        cfg_kwargs["system_instruction"] = system
    try:
        cfg_kwargs["thinking_config"] = gt.ThinkingConfig(thinking_budget=thinking_budget)
    except Exception:  # model families without thinking config
        pass

    delay = 4.0
    last_err: Optional[Exception] = None
    attempt = 0
    swaps = 0
    budget = max(retries, 8)  # quota (429) errors get a longer backoff budget than other transient errors
    while attempt < budget:
        if LIVE_CAP and _live_total() >= LIVE_CAP:
            raise RuntimeError(f"LLM live-call cap reached ({LIVE_CAP})")
        try:
            STATS["live_calls"] += 1
            _bump_live_total()
            resp = client().models.generate_content(
                model=model, contents=parts, config=gt.GenerateContentConfig(**cfg_kwargs)
            )
            text = resp.text or ""
            data = _parse_json(text)
            if use_cache:
                key.write_text(json.dumps(data, ensure_ascii=False), encoding="utf8")
            return data
        except Exception as e:  # noqa: BLE001
            last_err = e
            msg = str(e)
            own_key = _user_key.get() is not None
            if any(m in msg for m in _INVALID_KEY_MARKERS) and not own_key and len(_keys()) > 1 and rotate_key(invalid=True):
                log.error("LLM key rejected as invalid; moved to the next key in the pool")
                continue  # one bad key in the pool must not turn every answer into a template
            quota = "429" in msg or "RESOURCE_EXHAUSTED" in msg
            if quota:
                STATS["quota_errors"] += 1
            transient = quota or any(t in msg for t in ("503", "500", "UNAVAILABLE", "timeout", "Deadline"))
            if ("thinking" in msg.lower() or "INVALID_ARGUMENT" in msg) and "thinking_config" in cfg_kwargs and swaps < 2:
                # Gemini 3.x rejects thinking_budget=0 (400 INVALID_ARGUMENT); the equivalent is
                # thinking_level="minimal". Fall back to that once, then to no thinking config.
                # A swap does not consume a retry.
                swaps += 1
                tc = cfg_kwargs.pop("thinking_config")
                if thinking_budget == 0 and getattr(tc, "thinking_budget", None) == 0:
                    try:
                        cfg_kwargs["thinking_config"] = gt.ThinkingConfig(thinking_level="minimal")
                    except Exception:
                        pass
                continue
            if quota and not own_key and len(_keys()) > 1 and rotate_key(cooldown=_quota_cooldown(msg)):
                continue  # another key in the pool: retry immediately, no backoff, no attempt consumed
            attempt += 1
            if not transient or attempt >= (budget if quota else retries):
                break
            m = re.search(r"retry in (\d+(?:\.\d+)?)s", msg, re.I) or re.search(r"retryDelay[^0-9]*(\d+)", msg)
            hinted = float(m.group(1)) if m else None
            if hinted is not None and hinted > 600:
                # a multi-hour retry hint means the daily free-tier quota is gone: fail fast, let callers resume later
                log.error("LLM daily quota exhausted for %s (server asks to retry in %.0fs)", model, hinted)
                break
            wait = min(max(delay, hinted + 1), 65) if hinted is not None else delay
            log.warning("LLM transient error (%s); retry in %.0fs", msg[:120], wait)
            time.sleep(wait)
            delay = min(delay * 2, 65)
    _msg = str(last_err or "")
    _last_failure.set("invalid" if any(m in _msg for m in _INVALID_KEY_MARKERS) else
                      "quota" if ("429" in _msg or "RESOURCE_EXHAUSTED" in _msg) else "error")
    raise RuntimeError(f"LLM call failed after {attempt} attempts: {last_err}")


def _parse_json(text: str) -> Any:
    raw = text.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:]
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        start, end = raw.find("{"), raw.rfind("}")
        s2, e2 = raw.find("["), raw.rfind("]")
        if s2 != -1 and (start == -1 or s2 < start):
            start, end = s2, e2
        if start != -1 and end > start:
            return json.loads(raw[start : end + 1])
        raise


def embed(texts: list[str], *, model: Optional[str] = None, use_cache: bool = True) -> list[list[float]]:
    model = model or config.MODEL_EMBED
    out: list[list[float]] = []
    pending: list[tuple[int, str]] = []
    for i, t in enumerate(texts):
        key = _cache_key("emb", model, t)
        if use_cache and key.exists():
            out.append(json.loads(key.read_text(encoding="utf8")))
        else:
            out.append([])
            pending.append((i, t))
    for i, t in pending:
        resp = client().models.embed_content(model=model, contents=t)
        vec = list(resp.embeddings[0].values)
        out[i] = vec
        if use_cache:
            _cache_key("emb", model, t).write_text(json.dumps(vec), encoding="utf8")
    return out


def test_key(key: str) -> str:
    """Try a key once with the smallest possible call. 'ok' | 'invalid' | 'quota' | 'error'."""
    try:
        from google import genai
        from google.genai import types as gt

        c = genai.Client(api_key=key, http_options={"timeout": 15000})  # keep the client alive for the call
        c.models.generate_content(model=config.MODEL_FAST, contents="ok", config=gt.GenerateContentConfig(max_output_tokens=4))
        return "ok"
    except Exception as e:  # noqa: BLE001
        msg = str(e)
        if any(m in msg for m in _INVALID_KEY_MARKERS):
            return "invalid"
        if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
            return "quota"
        return "error"
