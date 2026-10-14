"""Paraphrase consistency: the same coverage situation worded three ways must give the same decision.

20 scenarios over the persona policies x 3 paraphrases (formal English, colloquial / Indonesian-English
mix, relative dates). Each paraphrase runs END TO END (user text -> planner -> facts binder -> solver ->
reply) in a fresh session. A scenario is consistent when all three paraphrases produce an identical
signature: verdict per policy, payable per policy, COB payers/amounts, deadline, intent and the
clarification slot (if any).

Modes
  rules (default)  LLM fully off: rule planner + rule binder + template wording. No API calls.
  --live N         additionally run N scenarios (3 paraphrases each) with the LLM fact binder ON (one
                   FactSheet call per turn; planner/explainer/clarifier stay deterministic). Live calls are
                   capped by CG_LLM_LIVE_CAP (persistent counter) and the run stops at the first quota error.

Output: evidence/paraphrase_report.md (+ .json)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import date
from pathlib import Path

os.environ.setdefault("CG_AUDIT_PATH", str(Path(tempfile.mkdtemp(prefix="cg_audit_")) / "audit.jsonl"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bench.agent_harness import DEFAULT_AS_OF, disable_llm, run_turns, signature  # noqa: E402
from clauseguard import config, llm  # noqa: E402

AS_OF = DEFAULT_AS_OF  # 2026-10-11


def D(y: int, m: int, d: int) -> date:
    return date(y, m, d)


def ago(d: date) -> str:
    n = (AS_OF - d).days
    return f"{n} days ago" if n != 1 else "yesterday"


MON_EN = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
MON_ID = ["jan", "feb", "mar", "apr", "mei", "jun", "jul", "agu", "sep", "okt", "nov", "des"]


def en(d: date) -> str:
    return f"{d.day} {MON_EN[d.month - 1]} {d.year}"


def idn(d: date) -> str:
    return f"{d.day} {MON_ID[d.month - 1]} {d.year}"


# Each scenario: id, persona, description, three wordings, optional ground truth {policy: (verdict, payable|None)}.
SCENARIOS: list[dict] = []


def scenario(sid, persona, desc, wordings, expect=None):
    SCENARIOS.append({"id": sid, "persona": persona, "desc": desc, "paraphrases": wordings, "expect": expect})


a1, d1 = D(2026, 10, 5), D(2026, 10, 8)
scenario("P01", "rizky", "dengue stay 5-8 Oct", [
    f"I was hospitalised with dengue from {en(a1)} to {en(d1)}. Am I entitled to a benefit under my hospital cash plan?",
    f"kena dbd, opname {a1.day}-{d1.day} {MON_ID[9]}, bisa cair dari hospital cash ga?",
    f"I was admitted with dengue {ago(a1)} and discharged {ago(d1)}. Will my hospital cash plan pay?"],
    {"HCP-SOMPO-01": ("COVERED", "2000000")})
a2 = D(2026, 10, 1)
scenario("P02", "rizky", "6-day typhoid stay from 1 Oct", [
    f"I was admitted to hospital with typhoid on {en(a2)} and stayed 6 days. What will the hospital cash plan pay?",
    f"opname tifus 6 hari mulai {idn(a2)}, berapa yg dibayar hospital cash?",
    f"admitted with typhoid {ago(a2)}, 6 days in hospital. how much does my hospital cash plan pay?"],
    {"HCP-SOMPO-01": ("COVERED", "3000000")})
s3 = D(2026, 11, 20)
scenario("P03", "rizky", "future hernia surgery inside the 12-month specified-disease wait", [
    f"I am scheduled for hernia surgery on {en(s3)}. Will my hospital cash plan cover it?",
    f"mau operasi hernia tgl {idn(s3)}, hospital cash saya nanggung ga?",
    f"I'm having hernia surgery in {(s3 - AS_OF).days} days. Is it covered by my hospital cash plan?"],
    {"HCP-SOMPO-01": ("DENIED", None)})
a4 = D(2026, 8, 25)
scenario("P04", "rizky", "illness admission inside the 30-day waiting period", [
    f"I was hospitalised with typhoid on {en(a4)} for 3 days. Does my hospital cash plan pay?",
    f"opname tifus {idn(a4)} 3 hari, hospital cash saya bisa cair ga?",
    f"I got admitted with typhoid {ago(a4)}, stayed 3 days. Is my hospital cash plan going to pay?"],
    {"HCP-SOMPO-01": ("DENIED", None)})
a5 = D(2026, 10, 3)
scenario("P05", "rizky", "accident admission (waiting period exempt)", [
    f"I fell from my motorbike and was hospitalised on {en(a5)} for 2 days. Is that covered by my hospital cash plan?",
    f"jatuh dari motor, dirawat {idn(a5)} 2 hari. hospital cash saya cover ga?",
    f"I had an accident, fell off my bike, and was hospitalised {ago(a5)} for 2 days. Does my hospital cash plan pay?"])
a6 = D(2026, 10, 9)
scenario("P06", "rizky", "death of illness, life policy in lapse", [
    f"I passed away from illness on {en(a6)}. Would my life policy pay out?",
    f"kalo saya meninggal karena sakit tgl {idn(a6)}, polis jiwa saya cair ga?",
    f"If I die of illness, {ago(a6)} say, does my life policy still pay?"])
a7 = D(2026, 8, 1)
scenario("P07", "rizky", "critical illness diagnosis", [
    f"I was diagnosed with cancer on {en(a7)}. Does my critical illness policy pay?",
    f"didiagnosis kanker tgl {idn(a7)}, polis critical illness saya cair ga?",
    f"I was diagnosed with cancer {ago(a7)}. Will my critical illness cover pay?"])
a8 = D(2026, 10, 6)
scenario("P08", "santoso", "Aditya asthma admission, non-partner hospital, bill 18M", [
    f"Aditya was admitted for asthma on {en(a8)} for 4 days at Siloam, a non-BPJS hospital. The bill is IDR 18,000,000. Who pays what?",
    f"aditya asma opname 4 hari {idn(a8)} di siloam (non bpjs), tagihan 18 juta. siapa yg bayar?",
    f"My son Aditya was admitted for asthma {ago(a8)}, 4 days in a private non-BPJS hospital, bill IDR 18M. Which insurer pays first?"])
s9 = D(2026, 11, 20)
scenario("P09", "santoso", "Sari hernia surgery after the 12-month wait", [
    f"Sari is scheduled for hernia surgery on {en(s9)}. Will her individual health policy pay?",
    f"sari mau operasi hernia tgl {idn(s9)}, asuransi individunya (HI-INDIV-S) nanggung ga?",
    f"Sari has hernia surgery in {(s9 - AS_OF).days} days. Is her individual health plan going to pay?"],
    {"HI-INDIV-S": ("COVERED", None)})
a10 = D(2026, 10, 5)
scenario("P10", "santoso", "Budi dies of illness: group life", [
    f"Budi passed away from illness on {en(a10)}. Does the group life policy pay?",
    f"budi meninggal karena sakit tgl {idn(a10)}, asuransi jiwa grup dari kantor cair ga?",
    f"Budi died of illness {ago(a10)}. Will the group life through work pay out?"],
    {"GL-NUSA-GRP": ("COVERED", "288000000")})
a11 = D(2026, 10, 3)
scenario("P11", "santoso", "Nadia accident admission", [
    f"Nadia fell and was hospitalised on {en(a11)} for 2 days. Which policies cover this?",
    f"nadia jatuh, dirawat {idn(a11)} 2 hari. polis mana yg nanggung?",
    f"Nadia had an accident, a fall, and was in hospital {ago(a11)} for 2 days. What is covered?"])
scenario("P12", "santoso", "elective dental implant", [
    "Does my group health plan cover an elective dental implant?",
    "implan gigi (elective) ditanggung asuransi kantor ga?",
    "pls check, is a planned dental implant covered by my company health insurance?"],
    {"GH-NUSA-GRP": ("DENIED", None)})
a13 = D(2026, 11, 11)
scenario("P13", "santoso", "resign then die: group life", [
    f"If I resign on {en(a13)} and die afterwards, will the group life policy still pay my family?",
    f"kalo saya resign tgl {idn(a13)} terus meninggal, asuransi jiwa grup masih bayar ga?",
    f"If I quit my job in {(a13 - AS_OF).days} days and then die, does the group life still pay?"],
    {"GL-NUSA-GRP": ("DENIED", None)})
a14 = D(2026, 10, 5)
scenario("P14", "dewi", "car collision on an order, licence expired", [
    f"I collided with a car while on an active delivery order on {en(a14)}. My driving licence had expired. I was in hospital 6 days, the bill is IDR 22,000,000. Who pays?",
    f"nabrak mobil pas lagi order {idn(a14)}, SIM saya mati. opname 6 hari, tagihan 22 juta. siapa yg bayar?",
    f"{ago(a14)} I crashed into a car during a delivery order, my licence was expired, 6 days in hospital, bill IDR 22M. Who pays first?"],
    {"PA-CHUBB-03": ("DENIED", None)})
a15 = D(2026, 10, 9)
scenario("P15", "dewi", "single-vehicle slip, licence valid", [
    f"I slipped on my motorbike alone on {en(a15)}, no other vehicle was involved, and my licence is valid. Does Jasa Raharja pay?",
    f"jatuh sendiri naik motor {idn(a15)}, ga ada kendaraan lain, SIM saya masih berlaku. Jasa Raharja bayar ga?",
    f"I skidded off my bike by myself {ago(a15)}, nobody else involved, valid licence. Is Jasa Raharja going to pay?"],
    {"JASA-RAHARJA": ("DENIED", None)})
a16 = D(2026, 10, 9)
scenario("P16", "dewi", "crash with a car on an order, platform deadline", [
    f"I crashed with a car during an order on {en(a16)}. What is the deadline for the platform claim?",
    f"nabrak mobil pas lagi order tgl {idn(a16)}. batas waktu klaim platform kapan?",
    f"I had a collision with a car while on an order {ago(a16)}. By when must I file the platform claim?"],
    {"PLATFORM-ACC": ("COVERED", None)})
a17 = D(2026, 10, 9)
scenario("P17", "dewi", "BPJS in arrears, ordinary admission", [
    f"I was hospitalised with typhoid on {en(a17)}. Can I use BPJS Kesehatan for the hospital?",
    f"opname tifus {idn(a17)}, BPJS saya masih bisa dipake ga?",
    f"I was admitted with typhoid {ago(a17)}. Is my BPJS usable for the hospital?"])
a18 = D(2026, 10, 9)
scenario("P18", "dewi", "off-duty crash with a car", [
    f"I was hit by a car on {en(a18)} while off duty, on a personal trip. Does the platform cover apply?",
    f"ditabrak mobil tgl {idn(a18)} pas lagi nggak narik, perjalanan pribadi. asuransi platform berlaku ga?",
    f"{ago(a18)} I was hit by a car on a personal trip, not working. Is the platform accident cover valid?"])
a19 = D(2026, 8, 30)
scenario("P19", "rizky", "dengue admission 10 days after the policy start", [
    f"I was hospitalised with dengue on {en(a19)} for 3 days. Will my hospital cash plan pay?",
    f"opname dbd {idn(a19)} 3 hari, hospital cash saya cair ga?",
    f"I got admitted with dengue {ago(a19)} for 3 days. Does my hospital cash plan pay?"],
    {"HCP-SOMPO-01": ("DENIED", None)})
scenario("P20", "rizky", "life policy status", [
    "Is my life insurance policy still in force? I may have missed a premium payment.",
    "polis asuransi jiwa saya masih aktif ga? kayaknya saya nunggak premi.",
    "my life policy - still active? think i skipped a payment a while back"])


def _run(items: list[dict], use_llm: bool) -> list[dict]:
    out = []
    for sc in items:
        runs = []
        for text in sc["paraphrases"]:
            rep = run_turns(sc["persona"], [text], AS_OF, use_llm=use_llm)[0]
            runs.append({"text": text, "sig": signature(rep), "facts": rep.facts, "intent": rep.intent.value, "reply_head": rep.text[:200]})
        out.append({**{k: sc[k] for k in ("id", "persona", "desc", "expect")}, "runs": runs})
    return out


def run_rules() -> list[dict]:
    disable_llm()
    return _run(SCENARIOS, use_llm=False)


def run_live(n_scenarios: int) -> tuple[list[dict], dict]:
    """LLM fact binder ON, everything else deterministic.

    A scenario counts as an LLM sample only if every binder call it made succeeded (live or cache replay);
    if any call failed (quota, live-call cap, cache miss in replay-only mode) the loop silently fell back to
    the rule binder for that turn, so the scenario is reported as incomplete instead."""
    stats = {"binder_calls_attempted": 0, "binder_calls_failed": 0, "blocked_non_binder_calls": 0, "scenarios_incomplete": [], "scenarios_without_binder_call": []}
    real = llm.generate_json

    def only_binder(prompt, *a, **kw):
        if getattr(kw.get("schema"), "__name__", "") != "FactSheet":
            stats["blocked_non_binder_calls"] += 1
            raise RuntimeError("non-binder LLM call disabled in this run")
        stats["binder_calls_attempted"] += 1
        try:
            return real(prompt, *a, **kw)
        except Exception as e:  # noqa: BLE001
            stats["binder_calls_failed"] += 1
            stats.setdefault("failure_reasons", {}).setdefault(str(e)[:80], 0)
            stats["failure_reasons"][str(e)[:80]] += 1
            raise

    llm.generate_json = only_binder
    out = []
    try:
        for sc in SCENARIOS[:n_scenarios]:
            att, fail = stats["binder_calls_attempted"], stats["binder_calls_failed"]
            res = _run([sc], use_llm=True)[0]
            if stats["binder_calls_failed"] > fail:
                stats["scenarios_incomplete"].append(sc["id"])
                continue
            if stats["binder_calls_attempted"] == att:
                stats["scenarios_without_binder_call"].append(sc["id"])
            res["binder_calls"] = stats["binder_calls_attempted"] - att
            out.append(res)
    finally:
        llm.generate_json = real
    stats.update({"live_calls": llm.STATS["live_calls"], "cache_hits": llm.STATS["cache_hits"], "quota_errors": llm.STATS["quota_errors"]})
    return out, stats


def consistent(item: dict) -> bool:
    return len({json.dumps(r["sig"], sort_keys=True) for r in item["runs"]}) == 1


def correct(item: dict):
    if not item.get("expect"):
        return None
    for r in item["runs"]:
        for pid, (verdict, payable) in item["expect"].items():
            got = r["sig"]["verdicts"].get(pid)
            if got is None or got[0] != verdict or (payable is not None and got[1] != payable):
                return False
    return True


def slot_diffs(item: dict) -> list[str]:
    keys = sorted({k for r in item["runs"] for k in r["facts"]})
    out = []
    for k in keys:
        vals = [str(r["facts"].get(k)) for r in item["runs"]]
        if len(set(vals)) > 1:
            out.append(f"{k}: " + " | ".join(vals))
    return out


def sig_diffs(item: dict) -> list[str]:
    out = []
    for field in ("intent", "clarify", "verdicts", "cob", "deadline", "refused"):
        vals = [json.dumps(r["sig"][field], sort_keys=True) for r in item["runs"]]
        if len(set(vals)) > 1:
            out.append(f"{field}: " + " || ".join(vals))
    return out


def section(title: str, items: list[dict], note: str = "") -> list[str]:
    n = len(items)
    ok = sum(1 for i in items if consistent(i))
    cor = [correct(i) for i in items if correct(i) is not None]
    lines = [f"## {title}", ""]
    if note:
        lines += [note, ""]
    lines.append(f"**Consistent: {ok}/{n} scenarios ({100 * ok / max(n, 1):.0f}%).** Correct on all three wordings, for the scenarios with a stated ground truth: {sum(1 for c in cor if c)}/{len(cor)}.")
    lines += ["", "| id | persona | situation | consistent | correct | decision signature (wording 1) |", "|---|---|---|---|---|---|"]
    for i in items:
        c = correct(i)
        s = i["runs"][0]["sig"]
        brief = f"{s['intent']}; verdicts {s['verdicts']}; clarify {s['clarify']}" + (f"; COB {s['cob']}" if s["cob"] else "")
        lines.append(f"| {i['id']} | {i['persona']} | {i['desc']} | {'yes' if consistent(i) else '**NO**'} | {'-' if c is None else ('yes' if c else '**NO**')} | {brief[:200]} |")
    bad = [i for i in items if not consistent(i)]
    lines += ["", "### Disagreements", ""]
    if not bad:
        lines.append("None.")
    for i in bad:
        lines.append(f"**{i['id']} ({i['persona']}) {i['desc']}**")
        for k, r in enumerate(i["runs"], 1):
            lines.append(f"- wording {k}: `{r['text']}`")
        for d in sig_diffs(i):
            lines.append(f"  - signature differs in {d[:700]}")
        for d in slot_diffs(i):
            lines.append(f"  - bound slot differs: {d[:300]}")
        lines.append("")
    return lines


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", type=int, default=0, help="also run N scenarios (x3 wordings) with the LLM fact binder on")
    ap.add_argument("--out", default=str(config.EVIDENCE_DIR / "paraphrase_report.md"))
    ap.add_argument("--notes", default=str(Path(__file__).parent / "notes" / "paraphrase_notes.md"), help="markdown file with the hand-written root-cause section to append")
    a = ap.parse_args()
    live: list[dict] = []
    stats: dict = {}
    if a.live:
        live, stats = run_live(a.live)  # first, while generate_json is still the real function
    rules = run_rules()
    lines = ["# Paraphrase consistency report", "",
             f"Generated {date.today().isoformat()} (as-of date for relative expressions: {AS_OF.isoformat()}). 20 coverage scenarios over the three personas' policy records, "
             "3 wordings each (formal English; colloquial / Indonesian-English mix with typos; relative dates such as '6 days ago' or 'in 40 days'). "
             "Each wording runs end to end (text -> planner -> facts binder -> solver -> reply) in its own fresh session. `python bench/paraphrase.py [--live N]` reproduces this file.", "",
             "A scenario is **consistent** when all three wordings give an identical decision signature: verdict and payable per policy, COB payers and amounts, deadline, "
             "clarification slot and intent. 'Correct' compares the wordings with a hand-derived expected decision for the scenarios where one is stated.", ""]
    lines += section("Rule binder only (LLM off)", rules, "Planner, fact binder and wording are the deterministic fallbacks; no API calls were made.")
    if a.live:
        lines += [""] + section("LLM fact binder on (live sample)", live,
                                f"First {a.live} scenarios requested ({len(live)} completed without a quota error). LLM stats: `{json.dumps(stats)}`. Only the fact binder calls the model; planner, explainer and clarifier stay deterministic.")
        if stats.get("quota_stop"):
            lines += ["", "**The live run stopped on a quota error (429 / RESOURCE_EXHAUSTED); scenarios after that point were not run with the LLM binder.**"]
    if a.notes and Path(a.notes).exists():
        lines += ["", Path(a.notes).read_text(encoding="utf8")]
    Path(a.out).write_text("\n".join(lines), encoding="utf8")
    Path(a.out).with_suffix(".json").write_text(json.dumps({"rules": rules, "live": live, "live_stats": stats}, indent=1, default=str), encoding="utf8")
    ok = sum(consistent(i) for i in rules)
    print(f"rules: {ok}/{len(rules)} consistent -> {a.out}")
    for i in rules:
        print(f"  {i['id']} {'OK  ' if consistent(i) else 'DIFF'} correct={correct(i)} {i['desc']}")
    if a.live:
        print(f"live: {sum(consistent(i) for i in live)}/{len(live)} consistent; {stats}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
