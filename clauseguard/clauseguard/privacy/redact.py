from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

PROVINCES = {
    11, 12, 13, 14, 15, 16, 17, 18, 19, 21, 31, 32, 33, 34, 35, 36, 51, 52, 53,
    61, 62, 63, 64, 65, 71, 72, 73, 74, 75, 76, 81, 82, 91, 92, 93, 94, 95, 96,
}

PLACEHOLDER_TYPES = (
    "NAMA", "NIK", "REKENING", "TELP", "EMAIL", "TGL_LAHIR", "NO_POLIS",
    "ALAMAT", "NPWP", "KARTU",
)

_PRIORITY = ["EMAIL", "NPWP", "REKENING", "NIK", "KARTU", "TELP", "NO_POLIS",
             "TGL_LAHIR", "ALAMAT", "NAMA"]

_DIGLIKE = str.maketrans({"O": "0", "o": "0", "I": "1", "l": "1"})

_MONTHS = (
    "januari|februari|maret|april|mei|juni|juli|agustus|september|oktober|november|desember|"
    "january|february|march|may|june|july|august|october|december|"
    "jan|feb|mar|apr|jun|jul|agu|aug|ags|sep|sept|okt|oct|nov|des|dec"
)
_DATE = (
    r"(?:\d{1,2}\s*[-/.]\s*\d{1,2}\s*[-/.]\s*\d{2,4}|\d{4}-\d{1,2}-\d{1,2}|"
    rf"\d{{1,2}}\s+(?i:{_MONTHS})\.?,?\s+\d{{2,4}}|(?i:{_MONTHS})\s+\d{{1,2}},?\s+\d{{4}})"
)

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}")
_NPWP_RE = re.compile(r"(?<!\d)\d{2}\.\d{3}\.\d{3}\.\d-\d{3}\.\d{3}(?!\d)")
_NPWP_LABEL_RE = re.compile(r"(?i)npwp[^\n\d]{0,12}$")
_RUN_RE = re.compile(r"[0-9OoIl](?:[ .\-]?[0-9OoIl]){9,24}")
_LANDLINE_RE = re.compile(
    r"(?<![\w/\-])(?:\(0\d{2,3}\)\s?\d{3,4}[ .\-]?\d{3,5}|0(?:21|22|24|31|61|251|274|341)[ .\-]\d{3,4}[ .\-]?\d{3,4})(?!\d)"
)
_REK_LABEL_RE = re.compile(
    r"(?i)\b(?:no\.?\s*rek(?:ening)?\.?|rek\b\.?|nomor\s*rekening|rekening(?:\s*(?:penerima|tujuan|pembayaran))?|account\s*(?:no\.?|number|num\.?)?|a/c(?:\s*no\.?)?|virtual\s*account|va)"
    r"\s*[:\-#]?\s*(?:[A-Za-z]{2,12}\s*)?"
)
_POLIS_LABEL_RE = re.compile(
    r"(?i)\b(?:no\.?\s*polis|nomor\s*polis|policy\s*(?:no\.?|number|#)|nomor\s*peserta|no\.?\s*peserta|"
    r"member\s*(?:no\.?|number|id)|no\.?\s*kartu(?:\s*peserta)?|nomor\s*kartu(?:\s*peserta)?|certificate\s*no\.?)\s*[:\-#]?\s*"
)
_POLIS_VAL_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9\-/\.]{3,}")
_DOB_LABEL_RE = re.compile(r"(?i)\b(?:tgl\.?\s*lahir|tanggal\s*lahir|date\s*of\s*birth|d\.?o\.?b\b\.?|lahir|born)\b")
_DATE_RE = re.compile(_DATE)
_ADDR_RE = re.compile(r"(?i)\b(?:alamat(?:\s*rumah|\s*korespondensi|\s*surat)?|address)\s*[:\-]\s*([^\n]+)")
_NAME_LABEL_RE = re.compile(
    r"(?i)\b(?:nama(?:\s*lengkap|\s*tertanggung|\s*peserta|\s*pasien|\s*pemegang\s*polis)?|tertanggung|pemegang\s*polis|"
    r"peserta|pasien|insured(?:\s*name)?|policy\s?holder(?:\s*name)?|patient(?:\s*name)?|account\s*holder|atas\s*nama|a/n)"
    r"\s*[:\-–]\s*"
)
_HONORIFIC_RE = re.compile(r"\b(?:Tn|Ny|Nn|Bpk|Mr|Mrs|Ms|Bapak|Ibu)\b\.?[ \t]+(?=[A-Z])")
_TOKEN_RE = re.compile(r"(?:[A-Z][A-Za-z'’\.\-]*|bin|binti|van|de|al)")
_NAME_STOP = {"NIK", "NO", "TGL", "TANGGAL", "ALAMAT", "DOB", "UMUR", "USIA", "JENIS", "PRODUK", "DIAGNOSA",
              "RUMAH", "SAKIT", "POLIS", "TELP", "HP", "EMAIL", "NPWP", "STATUS", "HUBUNGAN", "PLAN", "PAKET"}
_NO_NAME_PREFIX = re.compile(r"(?i)(?:nomor|no\.?|number|member|policy|id|kartu)\s*$")
_WS = re.compile(r"[ \t]+")


@dataclass(frozen=True)
class Finding:
    type: str
    start: int
    end: int
    token: str


@dataclass
class RedactionResult:
    text_clean: str
    mapping: dict = field(default_factory=dict, repr=False)
    findings: list = field(default_factory=list)

    def counts(self) -> dict:
        out: dict = {}
        for f in self.findings:
            out[f.type] = out.get(f.type, 0) + 1
        return out


def luhn_ok(digits: str) -> bool:
    if not digits.isdigit() or not 13 <= len(digits) <= 19:
        return False
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def _real_date(y: int, m: int, d: int) -> bool:
    try:
        date(y, m, d)
        return True
    except ValueError:
        return False


def valid_nik(digits: str) -> bool:
    if len(digits) != 16 or not digits.isdigit():
        return False
    if int(digits[:2]) not in PROVINCES:
        return False
    if digits[2:4] == "00" or digits[4:6] == "00" or digits[12:] == "0000":
        return False
    day, month, yy = int(digits[6:8]), int(digits[8:10]), int(digits[10:12])
    if day > 40:
        day -= 40
    if not 1 <= month <= 12 or not 1 <= day <= 31:
        return False
    return _real_date(1900 + yy, month, day) or _real_date(2000 + yy, month, day)


def nik_gender(digits: str) -> str | None:
    if not valid_nik(digits):
        return None
    return "F" if int(digits[6:8]) > 40 else "M"


def valid_npwp(s: str) -> bool:
    if _NPWP_RE.fullmatch(s):
        return True
    d = re.sub(r"\D", "", s)
    return len(d) in (15, 16)


def _digits_of(run: str) -> str | None:
    d = re.sub(r"[ .\-]", "", run).translate(_DIGLIKE)
    if not d.isdigit():
        return None
    if sum(c.isdigit() for c in run) < 0.7 * len(d):
        return None
    return d


def _is_phone(d: str) -> bool:
    if d.startswith("08") and 10 <= len(d) <= 13:
        return True
    return d.startswith("628") and 11 <= len(d) <= 14


def _bounded(text: str, s: int, e: int) -> bool:
    if s > 0 and (text[s - 1].isalnum() or text[s - 1] in "-/"):
        return False
    if e < len(text) and (text[e].isalnum() or text[e] in "-/"):
        return False
    return True


def _money_before(text: str, s: int) -> bool:
    return bool(re.search(r"(?i)(?:rp|idr|usd|sgd|myr|\$)\.?\s*$", text[max(0, s - 6):s]))


def _scan_runs(text: str) -> list[tuple[int, int, str, str]]:
    out = []
    for m in _RUN_RE.finditer(text):
        s, e = m.start(), m.end()
        if not _bounded(text, s, e) or _money_before(text, s):
            continue
        d = _digits_of(m.group())
        if d is None:
            continue
        plus = s > 0 and text[s - 1] == "+"
        if plus:
            s -= 1
        if len(d) in (15, 16) and _NPWP_LABEL_RE.search(text[max(0, s - 20):s]):
            out.append((s, e, "NPWP", d))
        elif len(d) == 16 and valid_nik(d):
            out.append((s, e, "NIK", d))
        elif _is_phone(d) or (plus and d.startswith("62") and 10 <= len(d) <= 14):
            out.append((s, e, "TELP", d))
        elif luhn_ok(d):
            out.append((s, e, "KARTU", d))
    for m in _LANDLINE_RE.finditer(text):
        out.append((m.start(), m.end(), "TELP", re.sub(r"\D", "", m.group())))
    return out


def _read_name(text: str, pos: int) -> tuple[int, int] | None:
    i, end, n_tok = pos, pos, 0
    while n_tok < 5:
        m = _TOKEN_RE.match(text, i)
        if not m:
            break
        tok = m.group()
        if tok.strip(".").upper() in _NAME_STOP and n_tok > 0:
            break
        if re.match(r"\s*:", text[m.end():m.end() + 3]):
            break
        if m.end() < len(text) and text[m.end()].isalnum():
            break
        end = m.end()
        n_tok += 1
        nxt = _WS.match(text, end)
        if not nxt:
            break
        i = nxt.end()
    if n_tok == 0:
        return None
    while end > pos and text[end - 1] in ".-":
        if text[end - 1] == "." and re.search(r"\b(?:Tn|Ny|Nn|Dr|Ir|Hj|H|Prof)\.$", text[pos:end]):
            break
        end -= 1
    return (pos, end) if end > pos else None


def _name_spans(text: str) -> list[tuple[int, int, str, str]]:
    out = []
    for m in _NAME_LABEL_RE.finditer(text):
        if _NO_NAME_PREFIX.search(text[max(0, m.start() - 12):m.start()]):
            continue
        r = _read_name(text, m.end())
        if r:
            out.append((r[0], r[1], "NAMA", text[r[0]:r[1]]))
    for m in _HONORIFIC_RE.finditer(text):
        r = _read_name(text, m.end())
        if r:
            out.append((m.start(), r[1], "NAMA", text[m.start():r[1]]))
    return out


def _known_spans(text: str, known_names) -> list[tuple[int, int, str, str]]:
    out = []
    for name in known_names or ():
        toks = [t for t in re.split(r"\s+", name.strip()) if t]
        if not toks:
            continue
        pats = [r"[\s,.\-]*".join(re.escape(t) for t in toks)]
        if len(toks) > 1:
            pats += [re.escape(t) for t in toks if len(t) >= 4]
        for p in pats:
            for m in re.finditer(rf"(?i)(?<![A-Za-z]){p}(?![A-Za-z])", text):
                out.append((m.start(), m.end(), "NAMA", m.group()))
    return out


def _label_spans(text: str) -> list[tuple[int, int, str, str]]:
    out = []
    for m in _EMAIL_RE.finditer(text):
        out.append((m.start(), m.end(), "EMAIL", m.group()))
    for m in _NPWP_RE.finditer(text):
        out.append((m.start(), m.end(), "NPWP", m.group()))
    for m in _REK_LABEL_RE.finditer(text):
        rm = _RUN_RE.match(text, m.end())
        if rm:
            d = _digits_of(rm.group())
            if d and 8 <= len(d) <= 18 and _bounded(text, rm.start(), rm.end()):
                out.append((rm.start(), rm.end(), "REKENING", d))
    for m in _POLIS_LABEL_RE.finditer(text):
        vm = _POLIS_VAL_RE.match(text, m.end())
        if vm:
            v = vm.group().rstrip(".-/")
            if any(c.isdigit() for c in v):
                out.append((vm.start(), vm.start() + len(v), "NO_POLIS", v))
    for m in _DOB_LABEL_RE.finditer(text):
        tail = text[m.end():m.end() + 60]
        gap = re.match(r"[^\n\d]{0,40}?(?=" + _DATE + ")", tail)
        dm = _DATE_RE.match(tail, gap.end()) if gap else None
        if dm:
            out.append((m.end() + dm.start(), m.end() + dm.end(), "TGL_LAHIR", dm.group()))
    for m in _ADDR_RE.finditer(text):
        v = m.group(1).rstrip()
        if v:
            out.append((m.start(1), m.start(1) + len(v), "ALAMAT", v))
    return out


def _collect(text: str, known_names) -> list[tuple[int, int, str, str]]:
    cands = _label_spans(text) + _scan_runs(text) + _name_spans(text) + _known_spans(text, known_names)
    order = {t: i for i, t in enumerate(_PRIORITY)}
    cands.sort(key=lambda c: (order[c[2]], c[0], -(c[1] - c[0])))
    taken: list[tuple[int, int, str, str]] = []
    for c in cands:
        if all(c[1] <= t[0] or c[0] >= t[1] for t in taken):
            taken.append(c)
    taken.sort(key=lambda c: c[0])
    return taken


def redact(text: str, known_names=()) -> RedactionResult:
    spans = _collect(text, known_names)
    counters: dict = {}
    by_value: dict = {}
    mapping: dict = {}
    findings: list = []
    parts: list = []
    cur = 0
    for s, e, typ, _v in spans:
        surface = text[s:e]
        key = (typ, surface)
        if key not in by_value:
            counters[typ] = counters.get(typ, 0) + 1
            tok = f"[{typ}_{counters[typ]}]"
            by_value[key] = tok
            mapping[tok] = surface
        tok = by_value[key]
        parts.append(text[cur:s])
        parts.append(tok)
        findings.append(Finding(typ, s, e, tok))
        cur = e
    parts.append(text[cur:])
    return RedactionResult("".join(parts), mapping, findings)


def restore(text: str, mapping: dict) -> str:
    for tok in sorted(mapping, key=len, reverse=True):
        text = text.replace(tok, mapping[tok])
    return text


def _norm_words(s: str) -> str:
    return " " + re.sub(r"[^a-z0-9]+", " ", s.lower()).strip() + " "


def final_gate(text: str, known_names=()) -> list[str]:
    violations: list[str] = []
    for m in _EMAIL_RE.finditer(text):
        violations.append(f"EMAIL@{m.start()}")
    for s, _e, typ, _d in _scan_runs(text):
        if typ in ("NIK", "KARTU", "TELP"):
            violations.append(f"{typ}@{s}")
    for m in _NPWP_RE.finditer(text):
        violations.append(f"NPWP@{m.start()}")
    norm = _norm_words(text)
    collapsed = re.sub(r"[^a-z]+", "", text.lower())
    for i, name in enumerate(known_names or ()):
        n = _norm_words(name)
        if len(n.strip()) < 3:
            continue
        words = n.split()
        toks = [t for t in words if len(t) >= 4] if len(words) > 1 else words
        hit = n in norm or any(f" {t} " in norm for t in toks)
        c = re.sub(r"[^a-z]+", "", name.lower())
        if not hit and len(c) >= 8 and c in collapsed:
            hit = True
        if hit:
            violations.append(f"NAME#{i}")
    return violations
