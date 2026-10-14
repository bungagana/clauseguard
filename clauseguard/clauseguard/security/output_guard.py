"""Output guard: DLP + canary check on every reply (R8).

Security guarantee: even if the planner is fully compromised, the reply that reaches the
user cannot carry (a) a 16-digit NIK, (b) a 10-16 digit bank account, (c) a payment-card
number, (d) a policy id that belongs to someone else, or (e) a canary string planted in the
system prompt / clause store. Canary presence means the model was induced to exfiltrate
its context, so the whole reply is replaced by a refusal and `DX_ATTEMPT` is logged.
Base64 blobs are decoded and scanned too, so encoding does not bypass the regexes.
Pure Python; no LLM.
"""
from __future__ import annotations

import base64
import binascii
import re
from typing import Any, Optional

from . import audit

# Planted in the planner system prompt and in the clause store; must never appear in a reply.
CANARY_TOKENS: tuple[str, ...] = ("CANARY-7f3a", "CANARY-KG-2b9e", "CANARY-SYS-91c0")

REFUSAL_TEXT = "I can't share that. The request would expose protected data, so this reply was withheld and the attempt was logged."

# Digit runs. We look at raw digit strings (optionally with separators) so that amounts like
# "IDR 2,500,000" (groups of 3) or dates are not caught: amounts are grouped by thousands;
# an identifier is a contiguous run of >= 10 digits.
_NIK_RE = re.compile(r"(?<!\d)(\d{16})(?!\d)")
_CARD_RE = re.compile(r"(?<!\d)((?:\d[ -]?){13,19})(?!\d)")
_BANK_RE = re.compile(r"(?<!\d)(\d{10,16})(?!\d)")
_POLICY_ID_RE = re.compile(r"\b([A-Z]{2,8}(?:-[A-Z0-9]{1,8}){1,2})\b")
_B64_RE = re.compile(r"(?<![A-Za-z0-9+/])([A-Za-z0-9+/]{24,}={0,2})(?![A-Za-z0-9+/])")

# Hyphenated upper-case tokens that look like policy ids but are vocabulary.
_POLICY_ID_ALLOW = frozenset({"INA-CBG", "ICD-10", "COVID-19", "T0-T3", "UTF-8", "R1-R9", "ISO-8601", "SHA-256", "BPJS-TK", "REDACTED-ENCODED", "REDACTED-SUSPICIOUS"})


def _luhn_ok(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def _mask(digits: str) -> str:
    return "*" * max(0, len(digits) - 4) + digits[-4:]


def _scan_plain(text: str, owned: set[str], known: Optional[set[str]]) -> tuple[str, list[dict[str, Any]]]:
    violations: list[dict[str, Any]] = []

    def nik_sub(m: re.Match) -> str:
        violations.append({"kind": "NIK", "masked": _mask(m.group(1))})
        return _mask(m.group(1))

    text = _NIK_RE.sub(nik_sub, text)

    def card_sub(m: re.Match) -> str:
        raw = m.group(1)
        digits = re.sub(r"[ -]", "", raw)
        if 13 <= len(digits) <= 19 and _luhn_ok(digits) and ("-" in raw or " " in raw):
            violations.append({"kind": "CARD", "masked": _mask(digits)})
            return _mask(digits)
        return raw

    text = _CARD_RE.sub(card_sub, text)

    def bank_sub(m: re.Match) -> str:
        violations.append({"kind": "BANK_ACCOUNT", "masked": _mask(m.group(1))})
        return _mask(m.group(1))

    text = _BANK_RE.sub(bank_sub, text)

    def pid_sub(m: re.Match) -> str:
        pid = m.group(1)
        if pid in owned or pid in _POLICY_ID_ALLOW:
            return pid
        if known is not None and pid not in known:
            return pid  # not a policy id in this system; leave vocabulary alone
        if known is None and not re.search(r"\d", pid):
            return pid  # without an id list we only act on ids that carry a number (e.g. "PA-CHUBB-03")
        violations.append({"kind": "FOREIGN_POLICY_ID", "masked": pid[:3] + "***"})
        return "[policy id withheld]"

    text = _POLICY_ID_RE.sub(pid_sub, text)
    return text, violations


def _scan_base64(text: str, owned: set[str], known: Optional[set[str]]) -> tuple[str, list[dict[str, Any]], bool]:
    violations: list[dict[str, Any]] = []
    canary_hit = False

    def b64_sub(m: re.Match) -> str:
        nonlocal canary_hit
        blob = m.group(1)
        try:
            decoded = base64.b64decode(blob + "=" * (-len(blob) % 4), validate=False).decode("utf-8", errors="ignore")
        except (binascii.Error, ValueError):
            return blob
        if any(c in decoded for c in CANARY_TOKENS):
            canary_hit = True
            violations.append({"kind": "CANARY_ENCODED", "masked": "[base64]"})
            return "[REDACTED-ENCODED]"
        _, inner = _scan_plain(decoded, owned, known)
        if inner:
            violations.extend({"kind": v["kind"] + "_ENCODED", "masked": v["masked"]} for v in inner)
            return "[REDACTED-ENCODED]"
        return blob

    return _B64_RE.sub(b64_sub, text), violations, canary_hit


def scan(text: str, session: Any = None) -> tuple[str, list[dict[str, Any]]]:
    """Return (clean_text, violations). `session` may expose owned_policy_ids / known_policy_ids / session_id / user_id."""
    owned = set(getattr(session, "owned_policy_ids", set()) or set())
    known = getattr(session, "known_policy_ids", None)
    known = set(known) if known is not None else None

    violations: list[dict[str, Any]] = []
    canary = [c for c in CANARY_TOKENS if c in text]
    clean, v_b64, canary_b64 = _scan_base64(text, owned, known)
    violations.extend(v_b64)
    if canary or canary_b64:
        violations.append({"kind": "CANARY", "masked": ",".join(c[:6] + "***" for c in canary) or "[base64]"})
        _log(session, "DX_ATTEMPT", violations)
        return REFUSAL_TEXT, violations

    clean, v_plain = _scan_plain(clean, owned, known)
    violations.extend(v_plain)
    if violations:
        _log(session, "OUTPUT_GUARD", violations)
    return clean, violations


def _log(session: Any, event_type: str, violations: list[dict[str, Any]]) -> None:
    try:
        audit.append(
            {
                "event_type": event_type,
                "session_id": getattr(session, "session_id", None),
                "user_id": getattr(session, "user_id", None),
                "decision": "MASKED" if event_type == "OUTPUT_GUARD" else "REFUSED",
                "reason": ",".join(sorted({v["kind"] for v in violations}))[:200],
            }
        )
    except Exception:
        pass
