"""PII redaction evaluation: span recall per type, over-redaction on must-survive items, final_gate catch rate.

Run: python -m bench.pii_eval [--out evidence/pii_report.md]
"""
from __future__ import annotations

import argparse
import json
import math
import re
import time
from collections import defaultdict
from pathlib import Path

from clauseguard.privacy.redact import final_gate, redact

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "benchmark" / "pii_eval.jsonl"
COVER = 0.8


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float, float]:
    if n == 0:
        return float("nan"), float("nan"), float("nan")
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return p, max(0.0, c - h), min(1.0, c + h)


def fmt(k: int, n: int) -> str:
    p, lo, hi = wilson(k, n)
    if n == 0:
        return "n/a (0)"
    return f"{p:.3f} [{lo:.3f}, {hi:.3f}] ({k}/{n})"


def _cover(span: tuple[int, int], findings, same_type: str | None) -> float:
    s, e = span
    covered = set()
    for f in findings:
        if same_type is not None and f.type != same_type:
            continue
        covered.update(range(max(s, f.start), min(e, f.end)))
    return len(covered) / max(1, e - s)


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def load(path: Path = DATA) -> list[dict]:
    return [json.loads(l) for l in path.read_text(encoding="utf8").splitlines() if l.strip()]


def evaluate(rows: list[dict]) -> dict:
    rec = defaultdict(lambda: [0, 0])
    rec_any = defaultdict(lambda: [0, 0])
    tp_f = defaultdict(int)
    all_f = defaultdict(int)
    keep_hit = [0, 0]
    survive_fp_findings = 0
    gate_raw = [0, 0]
    gate_adv = defaultdict(lambda: [0, 0])
    gate_on_clean_survive = [0, 0]
    leak = [0, 0]
    t_red = 0.0
    chars = 0
    for r in rows:
        text, kn = r["text"], r.get("known_names", [])
        t0 = time.perf_counter()
        res = redact(text, kn)
        t_red += time.perf_counter() - t0
        chars += len(text)
        spans = r.get("spans", [])
        if r["kind"] in ("pii", "adversarial"):
            for sp in spans:
                key = sp["type"] if sp.get("labelled", True) else sp["type"] + " (no label)"
                if r["kind"] == "adversarial":
                    key = "ADV:" + sp["type"]
                ok = _cover((sp["start"], sp["end"]), res.findings, sp["type"]) >= COVER
                ok_any = _cover((sp["start"], sp["end"]), res.findings, None) >= COVER
                rec[key][1] += 1
                rec[key][0] += ok
                rec_any[key][1] += 1
                rec_any[key][0] += ok_any
        if r["kind"] == "pii":
            for f in res.findings:
                all_f[f.type] += 1
                if any(s["type"] == f.type and s["start"] < f.end and s["end"] > f.start for s in spans):
                    tp_f[f.type] += 1
            gate_raw[1] += 1
            gate_raw[0] += bool(final_gate(text, kn)) if any(
                s["type"] in ("NIK", "TELP", "EMAIL", "KARTU") for s in spans) or kn else 0
            if not (any(s["type"] in ("NIK", "TELP", "EMAIL", "KARTU") for s in spans) or kn):
                gate_raw[1] -= 1
        if r["kind"] == "survive":
            for k in r["keep"]:
                keep_hit[1] += 1
                keep_hit[0] += any(f.start < k["end"] and f.end > k["start"] for f in res.findings)
            survive_fp_findings += len(res.findings)
            gate_on_clean_survive[1] += 1
            gate_on_clean_survive[0] += bool(final_gate(text, kn))
        if r["kind"] == "adversarial":
            v = r["variant"]
            gate_adv[v][1] += 1
            gate_adv[v][0] += bool(final_gate(text, kn))
            gate_adv["ALL"][1] += 1
            gate_adv["ALL"][0] += bool(final_gate(text, kn))
            gold = [text[s["start"]:s["end"]] for s in spans] or list(kn)
            leaked_after_redact = any(
                (_cover((s["start"], s["end"]), res.findings, None) < COVER) for s in spans
            ) if spans else any(_norm(n) in _norm(res.text_clean) for n in kn)
            blocked = bool(final_gate(res.text_clean, kn))
            leak[1] += 1
            leak[0] += bool(leaked_after_redact and not blocked)
            r["_leaked_redact"] = leaked_after_redact
            r["_gold"] = gold
    return {
        "recall": dict(rec), "recall_any": dict(rec_any), "tp_f": dict(tp_f), "all_f": dict(all_f),
        "over": keep_hit, "survive_fp_findings": survive_fp_findings, "gate_raw": gate_raw,
        "gate_adv": dict(gate_adv), "gate_clean_survive": gate_on_clean_survive, "leak": leak,
        "ms_per_kchar": 1000 * t_red / max(1, chars) * 1000, "rows": rows,
    }


def render(m: dict) -> str:
    rows = m["rows"]
    n_pii = sum(r["kind"] == "pii" for r in rows)
    n_keep = sum(r["kind"] == "survive" for r in rows)
    n_adv = sum(r["kind"] == "adversarial" for r in rows)
    L = ["# PII redaction evaluation", "",
         f"Dataset: `data/benchmark/pii_eval.jsonl` - {n_pii} PII snippets, {n_keep} must-survive snippets, "
         f"{n_adv} adversarial snippets. Written by the project team, synthetic and fictional, not a public benchmark.",
         "All intervals are Wilson 95%. A gold span counts as detected when same-type findings cover at least "
         f"{int(COVER * 100)}% of its characters. Regenerate with `python -m bench.pii_eval`.", "",
         "## Span recall per type (PII snippets, labelled contexts unless noted)", "",
         "| Type | Recall (same type) | Covered by any placeholder |", "|---|---|---|"]
    keys = sorted(k for k in m["recall"] if not k.startswith("ADV:"))
    for k in keys:
        a, b = m["recall"][k], m["recall_any"][k]
        L.append(f"| {k} | {fmt(*a)} | {fmt(*b)} |")
    tot = [sum(m["recall"][k][0] for k in keys if "(no label)" not in k), sum(m["recall"][k][1] for k in keys if "(no label)" not in k)]
    totu = [sum(m["recall"][k][0] for k in keys if "(no label)" in k), sum(m["recall"][k][1] for k in keys if "(no label)" in k)]
    L += [f"| **All labelled** | {fmt(*tot)} | |", f"| **All unlabelled** | {fmt(*totu)} | |", "",
          "## Precision of emitted placeholders (PII snippets)", "", "| Type | Precision | |", "|---|---|---|"]
    for t in sorted(m["all_f"]):
        L.append(f"| {t} | {fmt(m['tp_f'].get(t, 0), m['all_f'][t])} | |")
    tp, af = sum(m["tp_f"].values()), sum(m["all_f"].values())
    L += [f"| **All** | {fmt(tp, af)} | |", "",
          "## Over-redaction on must-survive items", "",
          f"Items that must survive (clause numbers, amounts, dates of events, ICD codes, hospital and product names) "
          f"and were touched by a placeholder: **{fmt(*m['over'])}**. Findings emitted on must-survive snippets: "
          f"{m['survive_fp_findings']}. final_gate violations on must-survive snippets (false blocks): "
          f"{fmt(*m['gate_clean_survive'])}.", "",
          "## final_gate", "",
          f"Catch rate on raw PII snippets that contain a NIK/phone/email/card or a known name: {fmt(*m['gate_raw'])}.", "",
          "Adversarial (hidden or obfuscated) cases, gate run on the raw text:", "",
          "| Variant | Gate catch rate |", "|---|---|"]
    for v in sorted(m["gate_adv"]):
        L.append(f"| {v} | {fmt(*m['gate_adv'][v])} |")
    L += ["", f"End-to-end leak rate on adversarial cases (redaction missed a span AND the gate on the redacted "
          f"text passed): **{fmt(*m['leak'])}**.", ""]
    adv_rec = [k for k in m["recall"] if k.startswith("ADV:")]
    if adv_rec:
        L += ["Redaction recall on adversarial spans: " + "; ".join(f"{k[4:]} {fmt(*m['recall'][k])}" for k in sorted(adv_rec)), ""]
    miss = []
    for r in rows:
        if r["kind"] == "adversarial" and not final_gate(r["text"], r.get("known_names", [])):
            miss.append(f"- `{r['id']}` ({r['variant']}): {r['text'][:70]!r}")
    if miss:
        L += ["Adversarial cases the gate did NOT catch:", ""] + miss + [""]
    L += [f"Throughput: about {m['ms_per_kchar']:.2f} ms per 1000 characters for `redact` (single thread).", "",
          "## Limitations", "",
          "- Names without a label or honorific cannot be reliably detected by deterministic rules; the unlabelled "
          "row above measures exactly that gap. Only the caller-supplied known account-holder name is guaranteed "
          "to be caught anywhere in free text.",
          "- The known-name gate protects the user's own name, not third parties (spouse, dependants, doctors, "
          "relatives) that appear without a label.",
          "- Dates of birth are only found near a birth label; an unlabelled date is treated as an event date "
          "on purpose, because it carries coverage meaning.",
          "- Rules were adjusted after a first run on this set (labels such as 'Rekening penerima', 'No. Kartu Peserta', "
          "landlines, the order of NPWP/VA versus NIK/Luhn), so the figures are in-sample and optimistic; the "
          "two adversarial misses (digits split by a line break, digits written as words) were added afterwards "
          "and were deliberately left unfixed.",
          "- Bank account numbers are only redacted when labelled; unlabelled digit strings that are not NIK, "
          "phone, NPWP or Luhn-valid cards pass through.",
          "- The final gate checks NIK, phone, email, card and known names only; addresses, policy numbers and "
          "dates of birth rely on the redaction pass.",
          "- Token-level matching of known names (tokens of 4+ letters) can over-block text that contains a common "
          "word equal to part of the user's name.",
          "- The evaluation set was authored by the same team that wrote the rules, so recall is optimistic "
          "relative to real documents. It is not a public benchmark and the intervals reflect sampling error only, "
          "not distribution shift.",
          "- Scanned documents depend on OCR quality; OCR errors in digits can defeat the structural validators "
          "(see `evidence/ocr_report.md`).", ""]
    return "\n".join(L)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "evidence" / "pii_report.md"))
    ap.add_argument("--data", default=str(DATA))
    a = ap.parse_args()
    m = evaluate(load(Path(a.data)))
    md = render(m)
    Path(a.out).write_text(md, encoding="utf8")
    print(md)


if __name__ == "__main__":
    main()
