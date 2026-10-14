"""Clarification precision: does the agent ask exactly when a missing fact matters?

Each base scenario is a complete user message built from named fact fragments over the persona
policies (e.g. cause, dates, facility, vehicles, licence). A scenario variant removes ONE fragment.
Whether that fact is decision-relevant is decided by an independent brute-force oracle, not by the
agent's own clarifier: the fragment is replaced by each of its alternative wordings (`options`), the
complete message is run end to end, and the fact is *relevant* when the verdict vector (verdict per
policy) differs between options. Fragments whose alternatives never change any verdict are
*irrelevant* (names, doctor, bill amount, a number of days that only moves a payable, ...).

Metrics (LLM off, rule planner + rule binder + solver):
  recall            asks a question when a decision-relevant fragment was removed
  silence           stays silent when an irrelevant fragment was removed (1 - false-ask rate)
  ask precision     asked questions that were on a relevant removal / all asked questions
  slot accuracy     the asked slot is one the removed fragment carries (among questions on relevant removals)

Output: evidence/clarify_report.md (+ .json)
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

from bench.agent_harness import DEFAULT_AS_OF, disable_llm, run_turns  # noqa: E402
from clauseguard import config  # noqa: E402

TIME = {"days_since_effective", "months_since_issue", "days_since_event", "days_since_discharge", "days_since_diagnosis", "days_since_death",
        "days_since_treatment_end", "days_overdue", "premium_status", "in_force", "months_since_reinstatement"}
CAUSE = {"cause", "is_accident", "intoxicated", "disease_in_specified_list", "diagnosis_before_effective"}
FACILITY = {"facility_bpjs_partner", "facility_in_network", "is_emergency"}
SLOTS_OF = {
    "dates": TIME | {"event"}, "cause": CAUSE, "diagnosis": CAUSE | TIME, "facility": FACILITY, "emergency": {"is_emergency"} | FACILITY, "vehicles": {"vehicles_involved"},
    "work": {"work_related"}, "licence": {"license_valid"}, "employment": {"employment_active"}, "survival": {"survival_days"},
    "alive": {"survival_days"}, "days": {"days_hospitalized"}, "who": {"event"}, "event": {"event"},
}
# fragments that are expected to carry no decision-relevant fact; they only act as removal controls
NOISE = {"bill", "days", "name", "doctor", "phone", "hospital_name", "nickname", "age"}

# base: persona, message template with {fragment} holes, fragments {name: [original, alt1, alt2, ...]}
BASES: list[dict] = [
    # ---- Rizky (HCP-SOMPO-01 hospital cash, TL-ASTRA-07 life in lapse, CI-CHUBB-05, BPJS-KES-RIZKY, Jasa Raharja)
    {"id": "B01", "persona": "rizky", "text": "I was admitted with typhoid {dates} to {facility}. {emergency} {bill} {doctor} Can I claim?",
     "frag": {"dates": ["from 25 to 28 August 2026", "from 4 to 7 October 2026"],
              "facility": ["a private hospital that is not a BPJS partner", "RSUD Soetomo, a BPJS partner hospital"],
              "emergency": ["It was a planned admission.", "It was an emergency admission through the ER."],
              "bill": ["The bill was IDR 11,000,000.", "The bill was IDR 31,000,000."], "doctor": ["I was treated by Dr. Hadi.", "I was treated by Dr. Wulan."]}},
    {"id": "B02", "persona": "rizky", "text": "I fell off my motorbike and was hospitalised {dates} for {days} at {facility}. {vehicles} {phone} Can I claim?",
     "frag": {"dates": ["on 4 October 2026", "on 25 August 2026"], "days": ["2 days", "9 days"], "facility": ["RSUD Soetomo, a BPJS partner hospital", "a private hospital that is not a BPJS partner"],
              "vehicles": ["No other vehicle was involved.", "I was hit by a car."],
              "phone": ["My phone number is 0812-555-0101.", "My phone number is 0813-555-0202."]}},
    {"id": "B03", "persona": "rizky", "text": "I was diagnosed with cancer {dates} and {alive}. {doctor} Does my critical illness policy pay?",
     "frag": {"dates": ["on 1 August 2026", "on 1 July 2025"], "alive": ["I am still alive today", "I died on 10 August 2026"],
              "doctor": ["My oncologist is Dr. Hadi.", "My oncologist is Dr. Wulan."]}},
    {"id": "B04", "persona": "rizky", "text": "I died {cause} {dates}. {name} Will my life policy pay?",
     "frag": {"cause": ["of illness", "by suicide"], "dates": ["on 20 September 2026", "on 6 October 2026"],
              "name": ["My full name is Rizky Pratama.", "My full name is Rizky Pratama Putra."]}},
    {"id": "B05", "persona": "rizky", "text": "I was hospitalised {dates} for {diagnosis} at {facility}. {bill} Can I claim?",
     "frag": {"dates": ["on 4 October 2026 for 4 days", "on 25 August 2026 for 4 days"], "diagnosis": ["a hernia operation", "typhoid", "a suicide attempt"],
              "facility": ["RSUD Soetomo, a BPJS partner hospital", "a private hospital that is not a BPJS partner"],
              "bill": ["The bill was IDR 12,000,000.", "The bill was IDR 32,000,000."]}},
    # ---- Santoso family (GH-NUSA-GRP, GL-NUSA-GRP, HCP-RIDER-B, HI-INDIV-S, BPJS-KES-SANTOSO)
    {"id": "B06", "persona": "santoso", "text": "Aditya was admitted for asthma on 6 October 2026 for 4 days at {facility}. {emergency} {bill} Who pays?",
     "frag": {"facility": ["Siloam, a private non-BPJS hospital", "RSUD Soetomo, a BPJS partner hospital"],
              "emergency": ["It was a planned admission.", "It was an emergency admission."],
              "bill": ["The bill was IDR 18,000,000.", "The bill was IDR 40,000,000."]}},
    {"id": "B07", "persona": "santoso", "text": "Sari is scheduled for {diagnosis} surgery {dates}. {hospital_name} Will her individual health policy HI-INDIV-S pay?",
     "frag": {"diagnosis": ["hernia", "appendicitis", "self-harm"], "dates": ["on 20 November 2026", "on 20 February 2026"],
              "hospital_name": ["The hospital is Siloam Surabaya.", "The hospital is RS Mitra Keluarga."]}},
    {"id": "B08", "persona": "santoso", "text": "Budi died {cause} on 6 October 2026. {name} Will the group life policy GL-NUSA-GRP pay?",
     "frag": {"cause": ["of illness", "by suicide"], "name": ["His full name was Budi Santoso.", "His full name was Budi Santoso Wijaya."]}},
    {"id": "B09", "persona": "santoso", "text": "Nadia fell and was hospitalised on 4 October 2026 for {days} at {facility}. {nickname} Who pays?",
     "frag": {"days": ["2 days", "5 days"], "facility": ["RSUD Soetomo, a BPJS partner hospital", "Siloam, a private non-BPJS hospital"],
              "nickname": ["We call her Nad.", "We call her Dek Nadia."]}},
    # ---- Dewi (PA-CHUBB-03, PLATFORM-ACC, BPJS-KES-DEWI lapsed, Jasa Raharja)
    {"id": "B10", "persona": "dewi", "text": "I had an accident on 6 October 2026 {vehicles} {work} {licence} I was hospitalised for {days} at RS Bhayangkara, a BPJS partner hospital. {bill} Who pays?",
     "frag": {"vehicles": ["when another car hit me.", "when I slipped and fell alone, no other vehicle was involved."],
              "work": ["I was on an active delivery order.", "I was on a personal trip."],
              "licence": ["My licence had expired.", "My licence is valid."], "days": ["6 days", "2 days"],
              "bill": ["The bill was IDR 22,000,000.", "The bill was IDR 12,000,000."]}},
    {"id": "B11", "persona": "dewi", "text": "I was admitted with typhoid {dates} to {facility}. {name} Can I claim from BPJS?",
     "frag": {"dates": ["on 9 October 2026", "on 9 June 2026"], "facility": ["a BPJS partner hospital", "a private hospital that is not a BPJS partner"],
              "name": ["My name is Dewi Lestari.", "My name is Dewi Lestari Putri."]}},
    {"id": "B12", "persona": "dewi", "text": "I collided with a car {work} on 6 October 2026 and {licence} {phone} Will the platform cover PLATFORM-ACC pay?",
     "frag": {"work": ["while delivering an order", "on a personal trip"], "licence": ["my licence had expired.", "my licence is valid."],
              "phone": ["My phone number is 0812-555-0303.", "My phone number is 0813-555-0404."]}},
    {"id": "B13", "persona": "dewi", "text": "I had an accident on 9 October 2026 {vehicles} and {licence} {hospital_name} Will Jasa Raharja pay?",
     "frag": {"vehicles": ["when a car hit me", "when I slipped alone, no other vehicle was involved"],
              "licence": ["my licence is valid.", "my licence had expired."],
              "hospital_name": ["I went to RS Bhayangkara.", "I went to Siloam."]}},
    {"id": "B14", "persona": "santoso", "text": "Aditya fell from his bike on {dates}. {vehicles} {facility} {bill} Who pays the hospital?",
     "frag": {"dates": ["6 October 2026 and was hospitalised for 3 days"], "vehicles": ["No other vehicle was involved.", "A car hit him."],
              "facility": ["He was taken to RSUD Soetomo, a BPJS partner hospital.", "He was taken to Siloam, a private non-BPJS hospital."],
              "bill": ["The bill was IDR 15,000,000.", "The bill was IDR 25,000,000."]}},
    # ---- more bases
    {"id": "B15", "persona": "dewi", "text": "I died in a road accident {vehicles} {work} {licence} {phone} Which of my policies pay my family?",
     "frag": {"vehicles": ["when a car hit my motorbike.", "when I skidded alone, no other vehicle was involved."],
              "work": ["I was on an active delivery order.", "I was on a personal trip."],
              "licence": ["My licence was valid.", "My licence had expired."],
              "phone": ["My family contact number is 0812-555-0505.", "My family contact number is 0813-555-0606."]}},
    {"id": "B16", "persona": "rizky", "text": "I will be hospitalised {dates} {cause} at {facility}. {nickname} Will my policies pay?",
     "frag": {"dates": ["tomorrow", "on 20 October 2026"], "cause": ["for dengue", "after a suicide attempt"],
              "facility": ["RSUD Soetomo, a BPJS partner hospital", "a private hospital that is not a BPJS partner"],
              "nickname": ["My friends call me Riz.", "My friends call me Pak Pratama."]}},
    {"id": "B17", "persona": "santoso", "text": "Aditya was admitted for {diagnosis} on 6 October 2026 for 4 days at Siloam, a private non-BPJS hospital, as an emergency. {doctor} {hospital_name} Who pays?",
     "frag": {"diagnosis": ["asthma", "a broken arm after a fall"], "doctor": ["The pediatrician is Dr. Sari.", "The pediatrician is Dr. Budi."],
              "hospital_name": ["The ward is Melati.", "The ward is Mawar."]}},
    {"id": "B18", "persona": "santoso", "text": "Sari was hospitalised on 20 February 2026 for {diagnosis} at {facility}. {age} {doctor} Does her individual policy HI-INDIV-S pay?",
     "frag": {"diagnosis": ["a hernia operation", "typhoid"], "facility": ["RSUD Soetomo, a BPJS partner hospital", "a private hospital that is not a BPJS partner"],
              "age": ["She is 36 years old.", "She is 35 years old."], "doctor": ["Her doctor is Dr. Anton.", "Her doctor is Dr. Maya."]}},
    {"id": "B19", "persona": "santoso", "text": "Budi was hospitalised on 6 October 2026 for {diagnosis} at {facility}. {emergency} {age} {doctor} Who pays?",
     "frag": {"diagnosis": ["dengue", "a suicide attempt"], "facility": ["RSUD Soetomo, a BPJS partner hospital", "Siloam, a private non-BPJS hospital"],
              "emergency": ["It was a planned admission.", "It was an emergency admission."],
              "age": ["He is 38 years old.", "He is 37 years old."], "doctor": ["His doctor is Dr. Anton.", "His doctor is Dr. Maya."]}},
    {"id": "B20", "persona": "rizky", "text": "I was hospitalised in the ICU on 4 October 2026 {cause} at {facility}. {hospital_name} Can I claim?",
     "frag": {"cause": ["with dengue", "after a suicide attempt"], "facility": ["RSUD Soetomo, a BPJS partner hospital", "a private hospital that is not a BPJS partner"],
              "hospital_name": ["The ward is Melati.", "The ward is Mawar."]}},
]


def render(base: dict, choice: dict[str, int | None]) -> str:
    """choice[name] = option index, or None to drop the fragment."""
    parts = {}
    for name, opts in base["frag"].items():
        idx = choice.get(name, 0)
        parts[name] = "" if idx is None else opts[idx]
    text = base["text"].format(**parts)
    return " ".join(text.split())


def run(persona: str, text: str):
    return run_turns(persona, [text], DEFAULT_AS_OF, use_llm=False)[0]


def vector(rep) -> dict:
    return {v.policy_id: v.verdict.value for v in rep.verdicts}


def payables(rep) -> dict:
    return {v.policy_id: (str(v.payable) if v.payable is not None else None) for v in rep.verdicts}


def evaluate() -> dict:
    disable_llm()
    rows = []
    invalid = []
    for base in BASES:
        full = run(base["persona"], render(base, {}))
        if full.clarification is not None or any(v.verdict.value == "CLARIFY" for v in full.verdicts):
            invalid.append({"base": base["id"], "reason": f"the complete message already triggers a question or an open verdict ({full.clarification.slot.value if full.clarification else 'CLARIFY verdict'})", "text": render(base, {})})
            continue
        for name, opts in base["frag"].items():
            # oracle: verdict vector under each alternative wording of this fragment
            vecs, pays = [], []
            for k in range(len(opts)):
                r = run(base["persona"], render(base, {name: k}))
                vecs.append(json.dumps(vector(r), sort_keys=True))
                pays.append(json.dumps(payables(r), sort_keys=True))
            relevant = len(set(vecs)) > 1
            payable_only = (not relevant) and len(set(pays)) > 1
            variant_text = render(base, {name: None})
            rep = run(base["persona"], variant_text)
            asked = rep.clarification.slot.value if rep.clarification else None
            expected = SLOTS_OF.get(name, set())
            rows.append({
                "base": base["id"], "persona": base["persona"], "fragment": name, "relevant": relevant, "payable_only": payable_only, "oracle_vectors": sorted(set(vecs)),
                "text": variant_text, "asked_slot": asked, "slot_ok": (asked in expected) if asked else None,
                "assumed_today": "No event date was given" in rep.text, "reply_head": rep.text[:160],
            })
    return {"rows": rows, "invalid": invalid}


def summarise(res: dict) -> dict:
    rows = res["rows"]
    rel = [r for r in rows if r["relevant"]]
    irr = [r for r in rows if not r["relevant"]]
    asks = [r for r in rows if r["asked_slot"]]
    rel_asks = [r for r in rel if r["asked_slot"]]
    return {
        "n_rows": len(rows), "n_relevant": len(rel), "n_irrelevant": len(irr), "n_irrelevant_payable_only": sum(1 for r in irr if r["payable_only"]),
        "recall": len(rel_asks) / max(len(rel), 1), "silence": sum(1 for r in irr if not r["asked_slot"]) / max(len(irr), 1),
        "ask_precision": len(rel_asks) / max(len(asks), 1), "slot_accuracy": sum(1 for r in rel_asks if r["slot_ok"]) / max(len(rel_asks), 1),
        "n_asks": len(asks), "n_rel_asks": len(rel_asks), "n_slot_ok": sum(1 for r in rel_asks if r["slot_ok"]),
        "missed_assumed_today": sum(1 for r in rel if not r["asked_slot"] and r["assumed_today"]),
    }


def pct(x: float) -> str:
    return f"{100 * x:.0f}%"


def write_report(res: dict, out: Path, notes: str = "") -> dict:
    s = summarise(res)
    rows = res["rows"]
    L = ["# Clarification precision report", "",
         f"Generated {date.today().isoformat()}. `python bench/clarify_eval.py` reproduces this file (LLM off: rule planner, rule binder, solver, template wording; as-of date {DEFAULT_AS_OF.isoformat()}).", "",
         "Each of {n} base messages is a complete user message over the persona policies (3 personas) made of named fact fragments. A *variant* drops exactly one fragment. "
         "Whether the dropped fact is **decision-relevant** is decided by a brute-force oracle that does not use the agent's clarifier: the fragment is replaced by each of its alternative wordings, "
         "the complete message is run end to end, and the fact is relevant when the verdict vector (verdict per policy) differs between the alternatives. "
         "Irrelevant controls are facts that never move a verdict (names, doctor, phone, bill amount, a stay length that only moves a payable).".format(n=len(BASES) - len(res["invalid"])), "",
         "## Results", "",
         "| measure | value | counts |", "|---|---|---|",
         f"| removals of a decision-relevant fact | {s['n_relevant']} | |",
         f"| removals of an irrelevant fact | {s['n_irrelevant']} | of which payable-only: {s['n_irrelevant_payable_only']} |",
         f"| **recall** (asks when it should) | **{pct(s['recall'])}** | {s['n_rel_asks']}/{s['n_relevant']} |",
         f"| **silence** (stays silent when it should) | **{pct(s['silence'])}** | {sum(1 for r in rows if not r['relevant'] and not r['asked_slot'])}/{s['n_irrelevant']} |",
         f"| **ask precision** (asked questions that were on a relevant removal) | **{pct(s['ask_precision'])}** | {s['n_rel_asks']}/{s['n_asks']} |",
         f"| **slot accuracy** (asked slot is one the removed fact carries) | **{pct(s['slot_accuracy'])}** | {s['n_slot_ok']}/{s['n_rel_asks']} |",
         f"| relevant removals missed where the reply discloses an assumed event date | {s['missed_assumed_today']} | |", ""]
    if res["invalid"]:
        L += ["Base messages excluded because the complete message already triggers a question:", ""]
        for i in res["invalid"]:
            L.append(f"- {i['base']}: {i['reason']}")
        L.append("")
    L += ["## Per scenario", "", "| base | persona | dropped fact | oracle | asked slot | slot ok | assumed today |", "|---|---|---|---|---|---|---|"]
    for r in rows:
        L.append(f"| {r['base']} | {r['persona']} | {r['fragment']} | {'relevant' if r['relevant'] else ('irrelevant (payable only)' if r['payable_only'] else 'irrelevant')} | {r['asked_slot'] or '-'} | "
                 f"{'-' if r['slot_ok'] is None else ('yes' if r['slot_ok'] else '**no**')} | {'yes' if r['assumed_today'] else '-'} |")
    miss = [r for r in rows if r["relevant"] and not r["asked_slot"]]
    fa = [r for r in rows if not r["relevant"] and r["asked_slot"]]
    wrong = [r for r in rows if r["relevant"] and r["asked_slot"] and not r["slot_ok"]]
    L += ["", "## Misses (relevant fact dropped, no question)", ""]
    for r in miss:
        L.append(f"- {r['base']} / {r['fragment']}: `{r['text']}` - oracle verdict vectors: {r['oracle_vectors']}")
    L += ["", "## False asks (irrelevant fact dropped, question asked)", ""]
    for r in fa:
        L.append(f"- {r['base']} / {r['fragment']}: asked `{r['asked_slot']}` for `{r['text']}`")
    L += ["", "## Wrong slot (relevant fact dropped, a different slot was asked)", ""]
    for r in wrong:
        L.append(f"- {r['base']} / {r['fragment']}: asked `{r['asked_slot']}`, expected one of {sorted(SLOTS_OF.get(r['fragment'], []))} for `{r['text']}`")
    if notes and Path(notes).exists():
        L += ["", Path(notes).read_text(encoding="utf8")]
    out.write_text("\n".join(L), encoding="utf8")
    out.with_suffix(".json").write_text(json.dumps({"summary": s, **res}, indent=1, default=str), encoding="utf8")
    return s


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(config.EVIDENCE_DIR / "clarify_report.md"))
    ap.add_argument("--notes", default=str(Path(__file__).parent / "notes" / "clarify_notes.md"))
    a = ap.parse_args()
    res = evaluate()
    s = write_report(res, Path(a.out), a.notes)
    print(json.dumps(s, indent=1))
    print(f"invalid bases: {[i['base'] for i in res['invalid']]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
