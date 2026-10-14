"""Post-extraction refinement: evidence verification, recall cross-check and the open UNMODELED_RULE relation.

Three generic stages, none of which knows any contract:
  verify_tuples   deterministic: typed qualifiers must be literally supported by the tuple's own evidence text
                  (numbers, window units, slot-domain values, object cue words); unsupported fields are repaired
                  from the evidence or dropped, unsupported tuples are removed.
  uncovered_rule_sentences   deterministic: sentences of the source text that carry rule cue words but are not
                  contained in any tuple's evidence.
  recall_pass     one cheap LLM call over only those sentences: convert them to closed tuples, or emit
                  UNMODELED_RULE (verbatim evidence + free-text label) when the closed relations cannot express them.
"""
from __future__ import annotations

import logging
import re
from typing import Callable, Optional

from pydantic import BaseModel, ConfigDict, Field

from ..schema import SLOT_DOMAINS, ClauseTuple, Condition, Evidence, Op, Qualifiers, Relation, Slot, TimeUnit

log = logging.getLogger("clauseguard.refine")

_WS = re.compile(r"\s+")
_NUM_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
              "eleven": 11, "twelve": 12, "fifteen": 15, "eighteen": 18, "twenty": 20, "thirty": 30, "sixty": 60, "ninety": 90}
_NUM_RE = re.compile(r"\b(\d[\d,]*(?:\.\d+)?|" + "|".join(_NUM_WORDS) + r")\b", re.I)

OBJECT_CUES: dict[tuple[str, str], re.Pattern] = {
    ("PERMITS", "CONVERSION"): re.compile(r"convert|conversion", re.I),
    ("PERMITS", "POLICY_LOAN"): re.compile(r"loan|borrow|advance", re.I),
    ("PERMITS", "SURRENDER"): re.compile(r"surrender|cash value|cash surrender|account value", re.I),
    ("PERMITS", "PARTIAL_WITHDRAWAL"): re.compile(r"withdraw", re.I),
    ("PERMITS", "REINSTATEMENT"): re.compile(r"reinstat|revive|restor", re.I),
    ("PERMITS", "FREE_LOOK"): re.compile(r"free.?look|examin|cancel|return the policy|right to return", re.I),
    ("PERMITS", "PREMIUM_WAIVER"): re.compile(r"waiv", re.I),
    ("PERMITS", "RETURN_OF_PREMIUM"): re.compile(r"return of premium|refund|premiums? (?:paid )?(?:will be )?returned|return(?:ed)? (?:of )?(?:the )?premium", re.I),
    ("EXCLUDES", "SUICIDE"): re.compile(r"suicid|self.?inflict|self.?destruct", re.I),
    ("EXCLUDES", "WAR"): re.compile(r"\bwar\b|military|hostilit|armed forces|combat|terroris", re.I),
    ("EXCLUDES", "AVIATION"): re.compile(r"aviation|aircraft|pilot|flight|aeroplane|airplane", re.I),
    ("EXCLUDES", "INTOXICATION"): re.compile(r"alcohol|intoxic|drug|narcotic|influence", re.I),
}

RULE_CUES = re.compile(
    r"\b(shall not|will not|does not|do not|not covered|not be covered|except|unless|exclu\w+|no benefit|only if|provided that|"
    r"limited to|not (?:be )?(?:payable|eligible|paid)|terminat\w+|laps\w+|void|cannot|may not|ineligible|no longer|"
    r"waiting period|waiv\w+|within \d+|within (?:one|two|three|six|ten|thirty|sixty|ninety)|convert\w*|reinstat\w+|"
    r"we (?:will|may|can) (?:pay|deny|contest|cancel)|incontestab\w+|contest\w*|surrender\w*|nonforfeiture|non-forfeiture|"
    r"exten\w+ term|paid.up|automatic\w*)\b", re.I)

_ALIAS_DOMAIN_SLOTS = {s: [str(v) for v in d] for s, d in SLOT_DOMAINS.items() if d and all(isinstance(v, str) for v in d)}


def _norm(s: str) -> str:
    return _WS.sub(" ", s).strip().lower()


def _numbers(text: str) -> set[float]:
    out: set[float] = set()
    for m in _NUM_RE.finditer(text):
        tok = m.group(1).lower()
        try:
            out.add(float(_NUM_WORDS[tok]) if tok in _NUM_WORDS else float(tok.replace(",", "")))
        except ValueError:
            continue
    return out


def _supported_number(val: Optional[float], nums: set[float], *, unit_scale: bool = False) -> bool:
    if val is None:
        return True
    cands = {float(val)}
    if unit_scale:
        cands |= {float(val) / 12, float(val) * 12, float(val) / 30.4, float(val) / 365}
    return any(abs(c - n) < 1e-6 for c in cands for n in nums)


_UNIT_RE = re.compile(r"\b(\d[\d,]*|" + "|".join(_NUM_WORDS) + r")\s*(?:\(\d+\))?[\s-]*(day|month|year|hari|bulan|tahun)s?\b", re.I)
_UNIT_DAYS = {"day": 1.0, "hari": 1.0, "month": 30.4, "bulan": 30.4, "year": 365.0, "tahun": 365.0}


def _window_supported(length: int, unit: Optional[TimeUnit], text: str) -> bool:
    per_day = {TimeUnit.DAYS: 1.0, TimeUnit.MONTHS: 30.4, TimeUnit.YEARS: 365.0}
    want = float(length) * per_day.get(unit or TimeUnit.MONTHS, 30.4)
    for m in _UNIT_RE.finditer(text):
        tok = m.group(1).lower()
        n = _NUM_WORDS[tok] if tok in _NUM_WORDS else float(tok.replace(",", ""))
        if abs(n * _UNIT_DAYS[m.group(2).lower()] - want) <= 0.05 * want:
            return True
    nums = _numbers(text)
    low = text.lower()
    for u, words in ((TimeUnit.DAYS, ("day", "hari")), (TimeUnit.MONTHS, ("month", "bulan")), (TimeUnit.YEARS, ("year", "tahun"))):
        cand = want / per_day[u]
        if abs(cand - round(cand)) < 0.05 * max(cand, 1) and round(cand) in nums and any(w in low for w in words):
            return True
    return False


def _repair_domain_value(slot: Slot, v: str) -> list[str]:
    dom = _ALIAS_DOMAIN_SLOTS.get(slot)
    if not dom:
        return [v]
    u = str(v).upper().replace(" ", "_")
    if u in dom:
        return [u]
    near = [d for d in dom if u in d or d in u]
    return near


def _fix_conditions(t: ClauseTuple) -> tuple[ClauseTuple, list[str]]:
    notes: list[str] = []
    conds: list[Condition] = []
    for c in t.qualifiers.applies_if:
        val = c.value
        if c.slot in _ALIAS_DOMAIN_SLOTS and val is not None:
            vals = val if isinstance(val, list) else [val]
            fixed: list[str] = []
            for v in vals:
                fixed.extend(_repair_domain_value(c.slot, str(v)))
            fixed = list(dict.fromkeys(fixed))
            if fixed != [str(v) for v in vals]:
                notes.append(f"condition {c.slot.value}: {vals} -> {fixed}")
                if not fixed:
                    notes.append(f"condition {c.slot.value} dropped (no value in slot domain)")
                    continue
                if isinstance(val, list):
                    c = Condition(slot=c.slot, op=c.op, value=fixed)
                else:
                    c = Condition(slot=c.slot, op=Op.IN if len(fixed) > 1 and c.op == Op.EQ else c.op,
                                  value=fixed if len(fixed) > 1 and c.op == Op.EQ else fixed[0])
        conds.append(c)
    if notes:
        q = t.qualifiers.model_copy(update={"applies_if": conds})
        t = t.model_copy(update={"qualifiers": q, "confidence": min(t.confidence, 0.6)})
    return t, notes


def _fix_numbers(t: ClauseTuple, window_from_text: Callable[[str], Optional[tuple[int, TimeUnit]]]) -> tuple[ClauseTuple, list[str]]:
    q = t.qualifiers
    nums = _numbers(t.evidence.text)
    upd: dict = {}
    notes: list[str] = []
    if q.window_len is not None and not _window_supported(q.window_len, q.window_unit, t.evidence.text):
        w = window_from_text(t.evidence.text)
        if w:
            upd.update(window_len=w[0], window_unit=w[1])
            notes.append(f"window {q.window_len} {q.window_unit} -> {w[0]} {w[1]} from evidence")
        else:
            upd.update(window_len=None, window_unit=None, window_from=None)
            notes.append(f"window {q.window_len} not in evidence: dropped")
    for f in ("waiting_days", "age_max", "age_min", "deadline_days", "max_days"):
        v = getattr(q, f)
        if v is not None and not _supported_number(v, nums, unit_scale=(f in ("waiting_days", "deadline_days"))):
            upd[f] = None
            notes.append(f"{f}={v} not in evidence: dropped")
    if q.amount is not None and not _supported_number(float(q.amount), nums):
        upd["amount"] = None
        notes.append(f"amount={q.amount} not in evidence: dropped")
    if notes:
        t = t.model_copy(update={"qualifiers": q.model_copy(update=upd), "confidence": min(t.confidence, 0.6)})
    return t, notes


def object_supported(t: ClauseTuple) -> bool:
    cue = OBJECT_CUES.get((t.relation.value, t.object))
    return cue is None or bool(cue.search(t.evidence.text))


def verify_tuples(tuples: list[ClauseTuple], window_from_text: Callable[[str], Optional[tuple[int, TimeUnit]]]) -> tuple[list[ClauseTuple], list[dict]]:
    kept: list[ClauseTuple] = []
    log_rows: list[dict] = []
    removed: set[str] = set()
    for t in tuples:
        if t.relation == Relation.UNMODELED_RULE:
            kept.append(t)
            continue
        if not object_supported(t):
            removed.add(t.id)
            log_rows.append({"id": t.id, "action": "removed", "why": f"evidence has no cue for {t.relation.value} {t.object}"})
            continue
        t, n1 = _fix_conditions(t)
        t, n2 = _fix_numbers(t, window_from_text)
        for n in n1 + n2:
            log_rows.append({"id": t.id, "action": "repaired", "why": n})
        kept.append(t)
    if removed:
        kept = [t for t in kept if not (t.relation in (Relation.EXCEPTS, Relation.REFERS_TO) and t.object in removed)]
    return kept, log_rows


_NEW_ITEM = re.compile(r"^(?:\d+(?:\.\d+)*[.)]?\s|\([a-z0-9ivx]+\)\s|[-*•□☐]\s*|[A-Z][A-Za-z/ ]{0,40}:)")


def _paragraphs(text: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    heading = ""
    cur = ""
    for line in text.splitlines():
        s = line.strip()
        if not s:
            if cur:
                out.append((heading, cur))
                cur = ""
            continue
        is_heading = len(s) < 90 and (s.isupper() or re.match(r"^(?:SECTION|ARTICLE|PART|CHAPTER)\b", s, re.I) or re.match(r"^\d+(?:\.\d+)*\.?\s+[A-Z][A-Z \-&/]+$", s))
        if is_heading:
            if cur:
                out.append((heading, cur))
                cur = ""
            heading = s
            continue
        if cur and _NEW_ITEM.match(s):
            out.append((heading, cur))
            cur = s
        else:
            cur = f"{cur} {s}".strip()
    if cur:
        out.append((heading, cur))
    return out


def rule_sentences(text: str) -> list[tuple[str, str]]:
    """(heading context, sentence) for every sentence carrying a rule cue."""
    out: list[tuple[str, str]] = []
    for heading, para in _paragraphs(text):
        for sent in re.split(r"(?<=[.;])\s+(?=[A-Z(])", para):
            sent = sent.strip()
            if len(sent) >= 25 and RULE_CUES.search(sent):
                out.append((heading, sent))
    return out


def uncovered_rule_sentences(text: str, tuples: list[ClauseTuple], min_overlap: float = 0.75) -> list[tuple[str, str]]:
    ev_norm = [_norm(t.evidence.text) for t in tuples]
    big = " \n ".join(ev_norm)
    ev_tokens = [set(re.findall(r"[a-z0-9$%]+", e)) for e in ev_norm]
    res = []
    for heading, sent in rule_sentences(text):
        n = _norm(sent)
        if n in big:
            continue
        toks = set(re.findall(r"[a-z0-9$%]+", n))
        if toks and any(len(toks & et) / len(toks) >= min_overlap for et in ev_tokens):
            continue
        res.append((heading, sent))
    return res


RECALL_PROMPT = """These sentences come from an insurance policy and were NOT converted by the first extraction pass. Convert each sentence that states a rule (coverage, exclusion, exception, condition, time period, permitted action, termination, required document).

Rules:
- If a closed relation fits (COVERS, EXCLUDES, EXCEPTS, CONDITIONED_ON, HAS_PERIOD, PAYS, PERMITS, TERMINATES_IF, REQUIRES_DOCUMENT, DEFINES, HAS_RIDER) emit it with the same typed fields and closed vocabularies as before; head = POLICY or a rider id.
- COVERS accepts every EventCode, including LAPSE: use it for what the policy provides when it lapses (non-forfeiture options, automatic extended term or paid-up insurance, automatic payout of cash value) and TERMINAL_ILLNESS / CHRONIC_ILLNESS for accelerated benefits.
- If the rule is real but cannot be expressed by those relations and fields (e.g. a schedule, a formula, an election, a ranking, an automatic transformation of the contract), emit relation UNMODELED_RULE with object = a short UPPER_SNAKE_CASE label you propose, proposed_label = the same label in plain words, entity_types = the kinds of things it relates (free text).
- Skip sentences that are only definitions, administration or marketing, and sentences that merely repeat an earlier rule.
- evidence_text must be the sentence copied verbatim. Never invent a rule, number or unit that the sentence does not state.

Known riders: {riders}
Glossary: {glossary}

<sentences>
{sentences}
</sentences>"""


class RecallRow(BaseModel):
    model_config = ConfigDict(extra="forbid")
    head: str = "POLICY"
    relation: str
    object: str
    section: str = ""
    evidence_text: str
    confidence: float = Field(ge=0, le=1, default=0.8)
    proposed_label: Optional[str] = None
    entity_types: list[str] = Field(default_factory=list)
    amount: Optional[float] = None
    pct_of_sum_assured: Optional[float] = None
    max_days: Optional[int] = None
    waiting_days: Optional[int] = None
    window_len: Optional[int] = None
    window_unit: Optional[TimeUnit] = None
    window_from: Optional[str] = None
    deadline_days: Optional[int] = None
    age_min: Optional[int] = None
    age_max: Optional[int] = None
    benefit_type: Optional[str] = None
    period_kind: Optional[str] = None
    applies_if: list[dict] = Field(default_factory=list)


class RecallBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tuples: list[RecallRow]


RECALL_SCHEMA = {
    "type": "object",
    "properties": {"tuples": {"type": "array", "items": {
        "type": "object",
        "properties": {
            "head": {"type": "string"}, "relation": {"type": "string"}, "object": {"type": "string"}, "section": {"type": "string"},
            "evidence_text": {"type": "string"}, "confidence": {"type": "number"},
            "proposed_label": {"type": "string"}, "entity_types": {"type": "array", "items": {"type": "string"}},
            "amount": {"type": "number"}, "pct_of_sum_assured": {"type": "number"}, "max_days": {"type": "integer"},
            "waiting_days": {"type": "integer"}, "window_len": {"type": "integer"}, "window_unit": {"type": "string", "enum": ["DAYS", "MONTHS", "YEARS"]},
            "window_from": {"type": "string"}, "deadline_days": {"type": "integer"}, "age_min": {"type": "integer"}, "age_max": {"type": "integer"},
            "benefit_type": {"type": "string"}, "period_kind": {"type": "string"},
            "applies_if": {"type": "array", "items": {"type": "object", "properties": {"slot": {"type": "string"}, "op": {"type": "string"}, "value": {"type": "string"}}, "required": ["slot", "op"]}},
        },
        "required": ["relation", "object", "evidence_text"],
    }}},
    "required": ["tuples"],
}


def build_recall_prompt(sentences: list[tuple[str, str]], riders: str, glossary: str) -> str:
    body = "\n".join(f"[{h or '-'}] {s}" for h, s in sentences)
    return RECALL_PROMPT.format(riders=riders or "(none)", glossary=glossary or "(none)", sentences=body)


def chunk_sentences(sentences: list[tuple[str, str]], max_chars: int = 7000) -> list[list[tuple[str, str]]]:
    out, cur, n = [], [], 0
    for h, s in sentences:
        if cur and n + len(s) > max_chars:
            out.append(cur)
            cur, n = [], 0
        cur.append((h, s))
        n += len(s) + len(h) + 4
    if cur:
        out.append(cur)
    return out


_GENERIC = {"DEATH", "OTHER", "BENEFIT", "COVERAGE", "RIDER", "BASIC", "LEVEL", "ADDITIONAL", "OPTION", "PAYMENT", "PAYOUT"}


def map_event_code(raw: str) -> Optional[str]:
    """Closest EventCode for an out-of-vocabulary object by shared distinguishing tokens (None if nothing specific matches)."""
    from ..schema import EventCode

    toks = {t for t in re.split(r"[^A-Z0-9]+", raw.upper()) if t}
    best: tuple[int, int, str] | None = None
    for name in EventCode.__members__:
        mt = set(name.split("_"))
        if len(mt) < 2 or name == "OTHER":
            continue
        shared = (toks & mt) - _GENERIC
        if shared and (best is None or (len(shared), len(mt)) > best[:2]):
            best = (len(shared), len(mt), name)
    if best:
        return best[2]
    singles = [n for n in EventCode.__members__ if "_" not in n and n not in _GENERIC and n in toks]
    return singles[0] if len(singles) == 1 else None


def unmodeled_tuple(row: RecallRow, *, tid: str, policy_id: str, doc_id: str, head: str, tier, lang: str, version: str) -> ClauseTuple:
    label = re.sub(r"[^A-Z0-9_]", "", (row.object or row.proposed_label or "UNMODELED").upper().replace(" ", "_"))[:40] or "UNMODELED"
    return ClauseTuple(
        id=tid, policy_id=policy_id, head=head, relation=Relation.UNMODELED_RULE, object=label,
        qualifiers=Qualifiers(proposed_label=(row.proposed_label or label)[:80], entity_types=[e[:40] for e in row.entity_types[:6]]),
        evidence=Evidence(doc_id=doc_id, section=row.section or "recall", text=row.evidence_text[:1200]),
        confidence=min(row.confidence, 0.7), source_tier=tier, extractor_version=version, language=lang,
    )
