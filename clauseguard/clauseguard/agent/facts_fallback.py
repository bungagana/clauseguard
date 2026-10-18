"""Rule-based fact binder + per-policy derivation of time slots.

`bind_rules(user_text, as_of)` is the standalone fallback for `agent.facts.bind_facts`:
regexes over the user's sentence produce only closed enums, dates, booleans and numbers.
The loop merges its output with the model-based binder when that module is importable.

`derive_for_policy(...)` is used in every case: slots such as days_since_effective or
diagnosis_before_effective depend on the policy's own dates, so they are computed in code
per policy from the typed event dates the binder found (never by the model).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from ..schema import PeriodKind, PolicyRecord, Relation, ScenarioFacts, Slot

MONTHS = {m: i + 1 for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}
MONTHS.update({"mei": 5, "agu": 8, "agt": 8, "okt": 10, "des": 12})  # Indonesian month abbreviations that differ from English
_MON = r"(jan|feb|mar|apr|may|mei|jun|jul|aug|agu|agt|sep|sept|oct|okt|nov|dec|des)[a-z]*\.?"
_D = r"(\d{1,2})(?:st|nd|rd|th)?"
_Y = r"(\d{4})"

DIAGNOSES = {
    "dengue": "DENGUE", "dbd": "DENGUE", "asthma": "ASTHMA", "asma": "ASTHMA", "typhoid": "TYPHOID", "tifus": "TYPHOID",
    "demam berdarah": "DENGUE", "hernia": "HERNIA", "cataract": "CATARACT", "tonsil": "TONSILS", "hemorrhoid": "HEMORRHOIDS", "haemorrhoid": "HEMORRHOIDS",
    "kidney stone": "KIDNEY_STONE", "tuberculosis": "TUBERCULOSIS", "tbc": "TUBERCULOSIS", "appendicitis": "APPENDICITIS",
    "pneumonia": "PNEUMONIA", "covid": "COVID19", "flu": "INFLUENZA", "fracture": "FRACTURE", "broken": "FRACTURE",
    "bronchitis": "BRONCHITIS", "bronkitis": "BRONCHITIS", "gastroenteritis": "DIARRHOEA", "diarrhoea": "DIARRHOEA", "diarrhea": "DIARRHOEA", "diare": "DIARRHOEA",
    "usus buntu": "APPENDICITIS", "tipes": "TYPHOID", "tipus": "TYPHOID", "tonsillectomy": "TONSILS", "amandel": "TONSILS", "katarak": "CATARACT",
    "batu ginjal": "KIDNEY_STONE", "wasir": "HEMORRHOIDS", "ambeien": "HEMORRHOIDS", "radang paru": "PNEUMONIA", "diabetes": "DIABETES", "hypertension": "HYPERTENSION", "cancer": "CANCER", "stroke": "STROKE", "heart attack": "HEART_ATTACK",
}
CORRECTION = re.compile(r"\b(sorry|actually|correction|i meant|i mean|not .* but|instead|rather than|wrong|mistake|koreksi|maaf|salah|ralat|sebenarnya)\b", re.I)
PERSON_WORDS = {"aditya": "aditya", "nadia": "nadia", "sari": "sari", "budi": "budi", "my son": "aditya", "my daughter": "nadia",
                "my wife": "sari", "my husband": "budi", "rizky": "rizky", "dewi": "dewi"}


@dataclass
class Extras:
    """Typed per-turn extras that are not ScenarioFacts slots."""

    dates: dict[str, date] = field(default_factory=dict)  # admission, discharge, accident, diagnosis, death, effective, license_expiry
    diagnosis: Optional[str] = None
    person: Optional[str] = None
    effective_override: Optional[date] = None
    correction: bool = False
    bound: set = field(default_factory=set)  # slots the rules bound from this sentence
    all_documents: bool = False  # "I have all the documents": the user attests the checklist is complete
    retracted: set[str] = field(default_factory=set)  # "hospitalization": the user says the stay never happened
    documents_present: list[str] = field(default_factory=list)


def _mon(s: str) -> int:
    return MONTHS[s[:3].lower()]


def parse_dates(text: str, as_of: date) -> list[tuple[int, date, Optional[date]]]:
    """Returns [(position, start_date, end_date_or_None)] for every date expression found."""
    out: list[tuple[int, date, Optional[date]]] = []
    t = text
    # ranges: 3-7 Oct 2026 / 3 to 7 October 2026 / 3–7 Oct
    for m in re.finditer(_D + r"\s*(?:-|–|—|to|until|till|sampai(?: dengan)?|hingga|s/d|sd)\s*" + _D + r"\s+" + _MON + r"(?:\s+" + _Y + ")?", t, flags=re.I):
        y = int(m.group(4)) if m.group(4) else as_of.year
        mo = _mon(m.group(3))
        try:
            out.append((m.start(), date(y, mo, int(m.group(1))), date(y, mo, int(m.group(2)))))
        except ValueError:
            pass
    for m in re.finditer(r"\b(\d{4})-(\d{2})-(\d{2})\s*(?:-|–|—|to|until|till|sampai(?: dengan)?|hingga|s/d|sd)\s*(\d{4})-(\d{2})-(\d{2})\b", t, flags=re.I):
        try:
            out.append((m.start(), date(int(m.group(1)), int(m.group(2)), int(m.group(3))), date(int(m.group(4)), int(m.group(5)), int(m.group(6)))))
        except ValueError:
            pass
    iso_ranges = [(p, e) for p, _s, e in out if e is not None]
    # ISO
    for m in re.finditer(r"\b(\d{4})-(\d{2})-(\d{2})\b", t):
        if any(p <= m.start() < p + 40 for p, _e in iso_ranges):
            continue
        try:
            out.append((m.start(), date(int(m.group(1)), int(m.group(2)), int(m.group(3))), None))
        except ValueError:
            pass
    # 1 March 2026 / 25 Sep / 25th September 2026
    for m in re.finditer(r"\b" + _D + r"\s+" + _MON + r"(?:,?\s+" + _Y + r")?\b", t, flags=re.I):
        if any(p <= m.start() < p + 40 for p, _, e in out if e is not None):
            continue  # part of a range already captured
        y = int(m.group(3)) if m.group(3) else as_of.year
        try:
            out.append((m.start(), date(y, _mon(m.group(2)), int(m.group(1))), None))
        except ValueError:
            pass
    # March 1, 2026 / Sept 1 2026
    for m in re.finditer(r"\b" + _MON + r"\s+" + _D + r"(?:,?\s+" + _Y + r")?\b", t, flags=re.I):
        if re.match(r"\d", t[max(0, m.start() - 2):m.start()].strip() or "x"):
            continue
        y = int(m.group(3)) if m.group(3) else as_of.year
        try:
            d = date(y, _mon(m.group(1)), int(m.group(2)))
        except ValueError:
            continue
        if all(abs(d.toordinal() - s.toordinal()) > 0 or p != m.start() for p, s, _ in out):
            out.append((m.start(), d, None))
    # relative
    rel = {"next week": 7, "minggu depan": 7, "yesterday": -1, "kemarin": -1, "kmrn": -1, "kemaren": -1, "today": 0, "hari ini": 0, "last week": -7, "minggu lalu": -7,
           "last month": -30, "bulan lalu": -30, "next month": 30, "bulan depan": 30, "tomorrow": 1, "besok": 1, "last night": -1, "semalam": -1}
    for m in re.finditer(r"\b(" + "|".join(re.escape(k) for k in sorted(rel, key=len, reverse=True)) + r")\b", t, flags=re.I):
        out.append((m.start(), as_of + timedelta(days=rel[m.group(1).lower()]), None))
    unit_days = {"day": 1, "days": 1, "hari": 1, "week": 7, "weeks": 7, "minggu": 7, "month": 30, "months": 30, "bulan": 30}
    for m in re.finditer(r"\b(in|after|dalam|sekitar|about)\s+(\d{1,3})\s+(days?|weeks?|months?|hari|minggu|bulan)\b", t, flags=re.I):
        if m.group(1).lower() in ("in", "dalam", "about", "sekitar"):
            out.append((m.start(), as_of + timedelta(days=int(m.group(2)) * unit_days[m.group(3).lower()]), None))
    for m in re.finditer(r"\b(\d{1,3})\s+(days?|weeks?|months?|hari|minggu|bulan)\s+(ago|lalu|yang lalu)\b", t, flags=re.I):
        out.append((m.start(), as_of - timedelta(days=int(m.group(1)) * unit_days[m.group(2).lower()]), None))
    out.sort(key=lambda x: x[0])
    return out


def _context(text: str, pos: int, width: int = 60) -> str:
    return text[max(0, pos - width):pos].lower()


_ROLE_PATTERNS = [
    ("effective", r"(started|start(s|ed)? on|effective|began|commenced|inception|policy date|issued|took out|bought|mulai berlaku|beli)"),
    ("discharge", r"(discharged|discharge|left hospital|released|pulang|keluar rs|keluar rumah sakit|keluar dari rs|keluar dari rumah sakit)"),
    ("diagnosis", r"(diagnos)"),
    ("death", r"(died|death|passed away|deceased|meninggal|wafat)"),
    ("accident", r"(accident|crash|collision|injur|fell|slipped|skidded|kecelakaan|jatuh|tabrak)"),
    ("license_expiry", r"(expired|expiry|licen[cs]e|sim mati|kadaluarsa)"),
    ("admission", r"(admitted|hospitali|admission|went to hospital|went in|checked in|get hospitali|opname|dirawat|rawat inap|masuk rs|masuk rumah sakit|\bmasuk\b)"),
]


def _role_after(text_after: str) -> Optional[str]:
    """When nothing before a date names its role ("Kemarin saya keluar dari RS"), the first role keyword right after it does."""
    best, best_start = None, 10 ** 6
    for role, pat in _ROLE_PATTERNS:
        if role in ("effective", "license_expiry"):
            continue
        m = re.search(pat, text_after)
        if m and m.start() < best_start:
            best, best_start = role, m.start()
    return best


def _role(ctx: str) -> Optional[str]:
    """The keyword closest to the date (largest end position) decides what the date is."""
    best, best_end = None, -1
    for role, pat in _ROLE_PATTERNS:
        for m in re.finditer(pat, ctx):
            if m.end() > best_end:
                best, best_end = role, m.end()
    return best


_MILLION_UNITS = ("m", "jt", "jut", "juta", "million", "millio", "mill")
_THOUSAND_UNITS = ("k", "rb", "rib", "ribu")


def _money(text: str) -> Optional[Decimal]:
    units = "|".join(_MILLION_UNITS + _THOUSAND_UNITS)
    m = re.search(rf"(?:idr|rp\.?|rupiah)\s*([\d.,]+)\s*({units})?\b", text, flags=re.I)
    if not m:
        m = re.search(rf"\b([\d.,]+)\s*({units})\b(?!\w)", text, flags=re.I)
        if not m:
            return None
    num = m.group(1).replace(",", "").rstrip(".")
    if num.count(".") > 1:
        num = num.replace(".", "")
    try:
        v = Decimal(num)
    except Exception:  # noqa: BLE001
        return None
    unit = (m.group(2) or "").lower()
    if unit in _MILLION_UNITS:
        v *= 1_000_000
    elif unit in _THOUSAND_UNITS:
        v *= 1_000
    return v.quantize(Decimal("1"))


_UNCERTAIN = re.compile(
    r"\b(not sure|unsure|don'?t know|no idea|not certain|can you help|could you help|help me (find|check)|"
    r"i('m| am)? not sure|tidak tahu|nggak tahu|ga tau|gatau|kurang yakin|belum tahu|belum yakin|bisa bantu)\b",
    re.I,
)


def bind_rules(user_text: str, as_of: date, prior: Optional[ScenarioFacts] = None) -> tuple[ScenarioFacts, Extras]:
    """Regex binder. Returns facts with only the slots the sentence actually states, plus typed extras."""
    t = user_text
    low = t.lower()
    uncertain = bool(_UNCERTAIN.search(low))  # a question echoing the fact's own keywords back is not an assertion of it
    v: dict[Slot, object] = {}
    ex = Extras()

    # ---- event
    if re.search(r"\b(hospitali[sz]ed|hospitali[sz]ation|admitted|inpatient|in hospital|days in (the )?hospital|admission|rawat inap|opname|dirawat|masuk rs|masuk rumah sakit)\b", low):
        v[Slot.EVENT] = "HOSPITALIZATION"
    if re.search(r"\b(surgery|operation|operated|operasi|bedah)\b", low) and Slot.EVENT not in v:
        v[Slot.EVENT] = "SURGERY"
    if re.search(r"\b(cosmetic|plastic surgery|nose job|rhinoplasty|botox|aesthetic|facelift|operasi plastik)\b", low):
        v[Slot.EVENT] = "COSMETIC"
    if re.search(r"\b(dental|tooth|teeth|implant|implan|gigi)\b", low):
        v[Slot.EVENT] = "DENTAL"
    if re.search(r"\b(ivf|fertility|in[- ]vitro)\b", low):
        v[Slot.EVENT] = "OTHER"
    if re.search(r"\b(critical illness|ci claim|survival period)\b", low):
        v[Slot.EVENT] = "CRITICAL_ILLNESS"
    elif re.search(r"\b(cancer|kanker|stroke|heart attack|serangan jantung|kidney failure|gagal ginjal)\b", low) and Slot.EVENT not in v:
        v[Slot.EVENT] = "CRITICAL_ILLNESS"  # a named critical illness without a stated admission is a critical-illness question
    if re.search(r"\b(if i die|i die|then die|and die|die|died|death|pass(ed)? away|dies|meninggal|wafat)\b", low) and Slot.EVENT not in v:
        v[Slot.EVENT] = "DEATH"
    if re.search(r"\b(weekly (income|benefit)|unable to work|off work|cannot work|temporary (total )?disab)", low) and Slot.EVENT not in v:
        v[Slot.EVENT] = "TEMPORARY_DISABILITY"

    # ---- cause / accident
    accident = bool(re.search(r"\b(accident|crash(ed)?|collision|collided|hit by|fell|fall|slipped|skidded|injur(y|ed)|fracture|broke my|kecelakaan|jatuh|ditabrak|nabrak|tabrakan)\b", low))
    illness = bool(re.search(r"\b(illness|sick|ill|disease|fever|infection|(?<!rumah )sakit|demam|penyakit|" + "|".join(re.escape(k) for k in DIAGNOSES) + r")\b", low))
    traffic = bool(re.search(r"\b(car|truck|bus|motorbike|motorcycle|motor ?bike|bike|scooter|moped|vehicle|traffic|road|lorry|van|taxi|ojek|mobil|motor|truk|sepeda motor|vespa)\b", low)) and accident
    if accident and not illness:
        v[Slot.IS_ACCIDENT] = True
        v[Slot.CAUSE] = "ACCIDENT_TRAFFIC" if traffic else "ACCIDENT"
        if Slot.EVENT not in v and re.search(r"\b(hospital|medical|treatment|bill)\b", low):
            v[Slot.EVENT] = "HOSPITALIZATION"
    elif illness and not accident:
        v[Slot.IS_ACCIDENT] = False
        v[Slot.CAUSE] = "ILLNESS"
    if v.get(Slot.CAUSE) == "ACCIDENT" and Slot.VEHICLES_INVOLVED not in v:
        pass  # decided after the vehicle patterns below (a non-traffic accident involves no vehicle)
    if re.search(r"\b(suicide|self-harm|self harm)\b", low):
        v[Slot.CAUSE] = "SUICIDE"
    if v.get(Slot.EVENT) == "DENTAL" and not accident and re.search(r"\b(implant|implan|cosmetic|elective|crown|braces|behel|whitening|planned|rencana)\b", low):
        v[Slot.IS_ACCIDENT] = False  # elective dental work: the accident exception cannot apply
        v[Slot.CAUSE] = "ILLNESS"
    if v.get(Slot.EVENT) == "CRITICAL_ILLNESS" and Slot.CAUSE not in v and not accident:
        v[Slot.CAUSE] = "ILLNESS"
        v[Slot.IS_ACCIDENT] = False
    if not uncertain and re.search(r"\b(drunk|intoxicated|under the influence|alcohol)\b", low):
        # "not sure if I was drunk" must not bind a denial-deciding verdict from an open question
        v[Slot.INTOXICATED] = not bool(re.search(r"\b(not|no|wasn'?t|never)\b.{0,15}\b(drunk|intoxicated|under the influence|alcohol)", low))
    if re.search(r"\b(emergency|er visit|ambulance|igd|ugd|darurat|gawat darurat)\b", low):
        v[Slot.IS_EMERGENCY] = not bool(re.search(r"\b(not|non|no)[- ]?(an )?emergency\b|\b(bukan|tidak) (kondisi |keadaan )?(gawat )?darurat\b", low))
    elif re.search(r"\b(planned|elective|scheduled)\b", low):
        v[Slot.IS_EMERGENCY] = False

    # ---- vehicles / licence / work / facility
    if re.search(r"\b(another|a|the) (car|truck|bus|lorry|van|taxi|motorbike|motorcycle|vehicle) (hit|struck|rammed|bumped|crashed into|collided with|knocked) (me|my|him|her|us)\b", low):
        v[Slot.VEHICLES_INVOLVED] = 2
    elif re.search(r"\b(single[- ]vehicle|on my own|by myself|alone|(no|without|not) (any )?(other|another|second) (car|vehicle|motorbike|motorcycle|vehicles)|nobody else|slipped|skidded|tunggal|sendirian|sendiri)\b", low):
        v[Slot.VEHICLES_INVOLVED] = 1  # negations ("no other vehicle") are checked before the positive pattern below
    elif re.search(r"\b(with|by|into|hit by|against|hit) (a|an|another|the) (car|truck|bus|motorbike|motorcycle|vehicle|lorry|van|taxi)\b", low) or re.search(r"\b(another|other|two|2) vehicles?\b", low) or re.search(r"\b(ditabrak|nabrak|menabrak|tabrakan|bertabrakan)\b", low):
        v[Slot.VEHICLES_INVOLVED] = 2
    if (v.get(Slot.CAUSE) == "ACCIDENT" and Slot.VEHICLES_INVOLVED not in v and re.search(r"\b(fell|fall|tripped|stairs|bathroom|kitchen|at home|jatuh)\b", low)
            and not re.search(r"\b(order|delivery|riding|driving|road|highway|traffic|trip|journey|commut|ojek|jalan|motor|vehicle|kendaraan)\b", low)):
        v[Slot.VEHICLES_INVOLVED] = 0  # a plain fall at home / non-road accident: Jasa Raharja (road traffic) cannot apply
    if not uncertain and re.search(r"\b(licen[cs]e|sim)\b", low):
        if re.search(r"\b(expired|no licen[cs]e|without (a )?(valid )?licen[cs]e|not valid|isn'?t valid|invalid|lapsed|suspended|mati|kadaluarsa)\b", low):
            v[Slot.LICENSE_VALID] = False
        elif re.search(r"\b(valid|still valid|current|renewed|masih berlaku|hidup)\b", low):
            v[Slot.LICENSE_VALID] = True
    if not uncertain:
        if re.search(r"\b(off[- ]duty|not working|wasn'?t working|not on (an )?order|personal trip|off work at the time|nggak narik|ga narik|tidak narik|libur|perjalanan pribadi|bukan (saat|waktu|pas) (sedang )?(bekerja|kerja|narik)|tidak sedang (bekerja|kerja|narik))\b", low):
            v[Slot.WORK_RELATED] = False
        elif re.search(r"\b(on (an |my )?(active )?(order|trip|delivery|shift)|(during|in the middle of|doing) (an |my |a )?(active )?(order|trip|delivery|shift)|while (delivering|working|on duty)|delivering|at work|work accident|during work|(lagi|pas|saat|sedang|waktu|lg) (lagi |saya )?(sedang )?(ngojek|antar|narik|order|ngorder|bekerja|kerja|kerjain)|ada order)\b", low):
            v[Slot.WORK_RELATED] = True
        if re.search(r"\b(non[- ]?bpjs|not (a )?bpjs|private hospital|non[- ]partner|not a partner|bukan (rs |rumah sakit |faskes )?mitra|swasta non)\b", low):
            v[Slot.FACILITY_BPJS_PARTNER] = False
        elif re.search(r"\b(bpjs[- ]partner|rsud|soetomo|public hospital|puskesmas|government hospital|(rs |rumah sakit(nya)? |faskes )?mitra bpjs|rekanan bpjs)\b", low):
            v[Slot.FACILITY_BPJS_PARTNER] = True
    if not uncertain and re.search(r"\b(left (my|the) (job|company)|resign(ed)?|no longer employed|laid[- ]?off|unemployed|quit|(lets?|let|letting) me go|get fired|got fired|get dismissed|got dismissed|terminated|lose my job|lost my job|phk|di-?phk|dipecat|berhenti kerja|kehilangan pekerjaan)\b", low):
        # "not sure if I quit" must not bind employment status from an open question either
        v[Slot.EMPLOYMENT_ACTIVE] = False

    # ---- numbers
    _NEG_BEFORE = r"\b(not|bukan|instead of|rather than|no)\s*$"
    stay_context = bool(re.search(r"\b(hospital\w*|admitted|inpatient|stay|stayed|ward|icu|opname|dirawat|rawat inap|rs)\b", low))
    if not stay_context and prior is not None and prior.has(Slot.EVENT) and prior.get(Slot.EVENT) == "HOSPITALIZATION":
        stay_context = bool(CORRECTION.search(low))  # "correction: 5 days, not 3" continues the stay
    m = next((x for x in re.finditer(r"\b(\d{1,3})\s*(?:days?|hari)\b", low)
              if not re.match(r"\s*(ago|lalu|yang lalu|later|after)\b", low[x.end():]) and not re.search(r"\b(in|within|dalam|after|sekitar|about)\s*$", low[max(0, x.start() - 10):x.start()])
              and not re.search(_NEG_BEFORE, low[max(0, x.start() - 12):x.start()])), None)
    if m and stay_context:
        v[Slot.DAYS_HOSPITALIZED] = int(m.group(1))
    money = _money(t)
    if money is not None and not uncertain and re.search(r"\b(bill|billed|cost|invoice|charged|expenses?|total|tagihan)\b", low):
        v[Slot.BILLED_AMOUNT] = int(money)

    # ---- diagnosis / person
    for k, code in DIAGNOSES.items():
        hit = next((x for x in re.finditer(r"\b" + re.escape(k), low) if not re.search(r"\b(not|bukan|instead of|rather than|no)\s+(a\s+|an\s+)?$", low[max(0, x.start() - 16):x.start()])), None)
        if hit:
            ex.diagnosis = code
            break
    if re.search(r"\b(never|wasn'?t|was not|were not|didn'?t|did not|not actually|tidak pernah|belum pernah|nggak pernah|gak pernah|tidak jadi)\b.{0,25}\b(admitted|hospitali[sz]ed|go to (the )?hospital|stay in (the )?hospital|dirawat|rawat inap|opname|masuk rs|masuk rumah sakit)\b", low) \
            or re.search(r"\b(no hospital stay|no hospitali[sz]ation|not hospitali[sz]ed|tidak dirawat|tidak rawat inap|tidak opname)\b", low):
        ex.retracted.add("hospitalization")
    for k, pid in PERSON_WORDS.items():
        if re.search(r"\b" + re.escape(k) + r"\b", low):
            ex.person = pid
            break

    # ---- dates with roles
    corrects = bool(CORRECTION.search(low))
    parsed = parse_dates(t, as_of)
    for pos, d1, d2 in parsed:
        if (len(parsed) > 1 and re.match(r"(today|hari ini)\b", t[pos:pos + 9], flags=re.I)
                and _role(_context(t, pos, 20)) not in ("discharge", "admission")):
            continue  # "... still alive today": 'today' is a reference point here, not the event date, when a real date is also given
        ctx = _context(t, pos)
        if d2 is not None:
            ex.dates.setdefault("admission", d1)
            ex.dates.setdefault("discharge", d2)
            continue
        role = _role(ctx)
        if role is None:
            role = _role_after(t[pos:pos + 45].lower())
        if role == "effective":
            ex.dates["effective"] = d1
            ex.effective_override = d1
        elif role in ("discharge", "diagnosis", "death", "accident", "license_expiry"):
            ex.dates[role] = d1
        elif role == "admission" or Slot.EVENT in v or (corrects and prior is not None and prior.get(Slot.EVENT) == "HOSPITALIZATION"):
            ex.dates.setdefault("admission", d1)
        else:
            ex.dates.setdefault("event", d1)
    if re.search(r"\b(still alive|i am alive|i'm alive|am alive|is alive|survived|masih hidup|masih bertahan)\b", low):
        ex.dates["alive_on"] = as_of  # survival so far = as_of - diagnosis date
    if "license_expiry" in ex.dates and Slot.LICENSE_VALID not in v:
        ref = ex.dates.get("accident") or ex.dates.get("admission") or as_of
        v[Slot.LICENSE_VALID] = ex.dates["license_expiry"] >= ref
    if CORRECTION.search(low):
        ex.correction = True

    # ---- documents the user says they have
    for code, pat in {
        "CLAIM_FORM": r"claim form", "DOCTOR_STATEMENT": r"doctor'?s? (statement|letter|resume)|medical (report|resume)",
        "MEDICAL_RESUME_INPATIENT": r"medical (report|resume)|doctor'?s? (statement|letter|resume)|resume medis",
        "ITEMISED_BILL": r"(itemi[sz]ed )?bill|invoice|receipt", "RECEIPT_DETAILS": r"itemi[sz]ed (bill|receipt)|receipt details|rincian",
        "RECEIPT_ORIGINAL_OR_LEGALISED": r"receipts?|kuitansi", "PRESCRIPTION_COPY": r"prescriptions?|resep",
        "DIAGNOSTIC_RESULTS": r"(lab|laboratory|diagnostic|test) (results?|reports?)|hasil lab",
        "DISCHARGE_SUMMARY": r"discharge summary|resume medis",
        "ID_CARD": r"\bktp\b|id card|identity card", "POLICE_REPORT": r"police report|\bbap\b", "BANK_ACCOUNT": r"bank (account|details)",
    }.items():
        if re.search(r"\b(i (only |just |now )?have|i've got|i got|attached|here is|here are|with me|already have|saya (hanya |cuma )?punya|sudah ada)\b.{0,80}" + pat, low) or re.search(pat + r".{0,30}\b(attached|ready|in hand|siap|sudah ada)\b", low):
            ex.documents_present.append(code)
    if re.search(r"\b(i have|i've got|i got|got|have|saya punya|sudah (punya|lengkap))\b.{0,12}\b(all|every|semua|lengkap)\b.{0,25}\b(documents?|papers|paperwork|dokumen|berkas)\b|\b(documents?|dokumen|berkas)\b.{0,20}\b(complete|all ready|all attached|lengkap)\b", low):
        ex.all_documents = True

    ex.bound = set(v)
    merged = dict(prior.values) if prior else {}
    merged.update(v)
    return ScenarioFacts(values=merged, as_of=as_of), ex


# --------------------------------------------------------------------------- derivation
def _months_between(a: date, b: date) -> int:
    return (b.year - a.year) * 12 + (b.month - a.month) - (1 if b.day < a.day else 0)


def derive_for_policy(
    facts: ScenarioFacts,
    policy: PolicyRecord,
    *,
    dates: dict[str, date],
    as_of: date,
    diagnosis: Optional[str] = None,
    diagnosis_dates: Optional[dict[str, date]] = None,
    effective_override: Optional[date] = None,
    payment: Optional[dict] = None,
    employment_active: Optional[bool] = None,
) -> ScenarioFacts:
    """Compute policy-relative slots in code. Never overrides a slot the user bound explicitly."""
    v = dict(facts.values)
    eff = effective_override or policy.effective_date
    issue = effective_override or policy.issue_date or policy.effective_date
    event_date = dates.get("admission") or dates.get("accident") or dates.get("death") or dates.get("diagnosis") or dates.get("event")

    def setd(slot: Slot, val) -> None:
        if slot not in v and val is not None:
            v[slot] = val

    if event_date and eff:
        setd(Slot.DAYS_SINCE_EFFECTIVE, (event_date - eff).days)
    if event_date and issue:
        setd(Slot.MONTHS_SINCE_ISSUE, _months_between(issue, event_date))
    if policy.reinstatement_date and event_date:
        setd(Slot.MONTHS_SINCE_REINSTATEMENT, _months_between(policy.reinstatement_date, event_date))
    if "discharge" in dates:
        setd(Slot.DAYS_SINCE_DISCHARGE, (as_of - dates["discharge"]).days)
        setd(Slot.DAYS_SINCE_TREATMENT_END, (as_of - dates["discharge"]).days)
        if "admission" in dates:
            setd(Slot.DAYS_HOSPITALIZED, (dates["discharge"] - dates["admission"]).days + 1 if (dates["discharge"] - dates["admission"]).days >= 0 else None)
    if "accident" in dates:
        setd(Slot.DAYS_SINCE_EVENT, (as_of - dates["accident"]).days)
    elif event_date:
        setd(Slot.DAYS_SINCE_EVENT, (as_of - event_date).days)
    if "death" in dates:
        setd(Slot.DAYS_SINCE_DEATH, (as_of - dates["death"]).days)
        if "diagnosis" in dates:
            setd(Slot.SURVIVAL_DAYS, (dates["death"] - dates["diagnosis"]).days)
    if "diagnosis" in dates:
        setd(Slot.DAYS_SINCE_DIAGNOSIS, (as_of - dates["diagnosis"]).days)
        if "alive_on" in dates and "death" not in dates:
            setd(Slot.SURVIVAL_DAYS, (dates["alive_on"] - dates["diagnosis"]).days)

    # diagnosis-derived
    diag_date = dates.get("diagnosis")
    if diag_date is None and diagnosis and diagnosis_dates and diagnosis in diagnosis_dates:
        diag_date = diagnosis_dates[diagnosis]
    if (diagnosis or v.get(Slot.IS_ACCIDENT) is True) and Slot.DIAGNOSIS_BEFORE_EFFECTIVE not in v:  # a discrete accident is not a pre-existing condition
        if diag_date is not None and eff is not None:
            v[Slot.DIAGNOSIS_BEFORE_EFFECTIVE] = diag_date < eff
        elif event_date is not None and eff is not None and event_date >= eff:
            # a diagnosis made at this admission, with no earlier history known to us
            v[Slot.DIAGNOSIS_BEFORE_EFFECTIVE] = False
    if v.get(Slot.IS_ACCIDENT) is True and Slot.DISEASE_IN_SPECIFIED_LIST not in v:
        v[Slot.DISEASE_IN_SPECIFIED_LIST] = False  # the specified-disease list names illnesses, never an accidental injury
    if diagnosis and Slot.DISEASE_IN_SPECIFIED_LIST not in v:
        listed: set[str] = set()
        for t in policy.tuples_by(Relation.HAS_PERIOD):
            if t.qualifiers.period_kind == PeriodKind.WAITING_SPECIFIED or t.object == PeriodKind.WAITING_SPECIFIED.value:
                listed |= set(t.qualifiers.diseases)
        v[Slot.DISEASE_IN_SPECIFIED_LIST] = diagnosis in listed

    # premium / employment
    if payment:
        due = payment.get("due_date")
        paid = payment.get("paid_date")
        if isinstance(due, str):
            due = date.fromisoformat(due)
        ref = event_date or as_of  # premium status is judged at the date of the event, not today
        if due and not paid and ref >= due:
            overdue = (ref - due).days
            grace = policy.grace_days or 0
            setd(Slot.DAYS_OVERDUE, overdue)
            setd(Slot.PREMIUM_STATUS, "LAPSED" if overdue > grace else "OVERDUE")
        else:
            setd(Slot.PREMIUM_STATUS, "PAID")
    if employment_active is not None:
        setd(Slot.EMPLOYMENT_ACTIVE, employment_active)
    return ScenarioFacts(values=v, as_of=as_of)
