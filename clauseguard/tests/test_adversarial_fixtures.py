"""Integrity tests for the adversarial fixtures.

Checks, without any LLM or other ClauseGuard modules:
- manifest.json is consistent (fields, unique files, counts per technique)
- every generated PDF opens with PyMuPDF
- the hidden payload is present where the technique says it is (raw bytes, text layer,
  metadata/XMP, annotation + form field, image /Alt, rendered-image only) and is NOT
  visible in the default text layer for the hidden techniques
- clean invoices contain no payload anywhere (text, metadata, annotations, /Alt)
- chat_cases.json covers every attack case ID of the threat model (SECURITY.md)
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

import pymupdf as fitz
import pytest

ROOT = Path(__file__).resolve().parents[1]
ADV = ROOT / "data" / "adversarial"
MANIFEST = ADV / "manifest.json"
CHAT = ADV / "chat_cases.json"
sys.path.insert(0, str(ADV))

REQUIRED_FIELDS = {"file", "technique", "payload_id", "expected_suspicious", "expected_findings_technique", "expected_total"}
HIDDEN_TECHNIQUES = {"white_text", "tiny_font", "off_page", "metadata", "annotation", "image_alt", "rendered_image"}


@pytest.fixture(scope="module")
def manifest() -> dict:
    if not MANIFEST.exists():
        pytest.skip("manifest.json missing; run python data/adversarial/gen_pdfs.py")
    return json.loads(MANIFEST.read_text(encoding="utf8"))


@pytest.fixture(scope="module")
def entries(manifest) -> list[dict]:
    return manifest["entries"]


@pytest.fixture(scope="module")
def payloads(manifest) -> list[str]:
    return [p["text"] for p in manifest["payloads"]]


def _doc(e: dict) -> fitz.Document:
    return fitz.open(str(ROOT / e["file"]))


def _all_text_sources(doc: fitz.Document) -> str:
    """Everything a scanner could legitimately look at (text incl. off-page, metadata, XMP, annots, widgets, /Alt)."""
    parts = []
    for page in doc:
        parts.append(page.get_text("text", flags=fitz.TEXT_PRESERVE_WHITESPACE & ~fitz.TEXT_MEDIABOX_CLIP,
                                   clip=fitz.Rect(-5000, -5000, 5000, 5000)))
        for a in page.annots():
            parts.append(str(a.info))
        for w in page.widgets():
            parts.append(str(w.field_value))
        for img in page.get_images(full=True):
            parts.append(str(doc.xref_get_key(img[0], "Alt")))
    parts.append(json.dumps(doc.metadata))
    parts.append(doc.get_xml_metadata() or "")
    return "\n".join(parts)


# --------------------------------------------------------------------------- manifest
def test_manifest_fields_and_uniqueness(entries):
    assert len(entries) >= 150
    files = [e["file"] for e in entries]
    assert len(files) == len(set(files)), "duplicate file entries"
    for e in entries:
        assert REQUIRED_FIELDS <= set(e), e
        assert e["technique"] in HIDDEN_TECHNIQUES | {"visible", "clean", "inflated", "policy_doc"}
        assert (ROOT / e["file"]).exists(), e["file"]
        if e["technique"] in HIDDEN_TECHNIQUES:
            assert e["expected_findings_technique"] == e["technique"]
            assert e["expected_suspicious"] is True
            assert e["payload_id"] and e["payload"]


def test_manifest_counts(entries, manifest):
    cnt = Counter(e["technique"] for e in entries)
    assert len(manifest["payloads"]) == 20
    for t in HIDDEN_TECHNIQUES:
        assert cnt[t] == 20, (t, cnt[t])
    assert cnt["clean"] == 5
    assert cnt["inflated"] == 3
    assert cnt["visible"] >= 3
    assert cnt["policy_doc"] == 2


def test_payload_corpus_is_frozen_and_ascii(manifest):
    texts = [p["text"] for p in manifest["payloads"]]
    assert len(set(texts)) == 20
    for t in texts:
        assert re.fullmatch(r"[\x20-\x7e]+", t), t
        assert "(" not in t and ")" not in t and "\\" not in t
    kinds = Counter(p["kind"] for p in manifest["payloads"])
    assert kinds["id"] >= 4 and kinds["b64"] >= 3


def test_generator_is_deterministic(tmp_path):
    import gen_pdfs  # noqa: E402

    out = tmp_path / "pdf"
    gen_pdfs.generate(out_dir=out, manifest_path=tmp_path / "manifest.json")
    for e in json.loads((tmp_path / "manifest.json").read_text(encoding="utf8"))["entries"][:: 11]:
        name = Path(e["file"]).name
        assert (out / name).read_bytes() == (ADV / "pdf" / name).read_bytes(), f"{name} differs between runs"


# --------------------------------------------------------------------------- every PDF opens
def test_every_pdf_opens_and_has_one_page(entries):
    for e in entries:
        doc = _doc(e)
        assert doc.page_count == 1, e["file"]
        assert not doc.is_encrypted
        doc.close()


# --------------------------------------------------------------------------- payload placement
@pytest.mark.parametrize("technique", sorted(HIDDEN_TECHNIQUES))
def test_hidden_payload_present_as_intended(entries, technique):
    for e in (x for x in entries if x["technique"] == technique):
        payload = e["payload"]
        raw = (ROOT / e["file"]).read_bytes()
        doc = _doc(e)
        page = doc[0]
        visible_text = page.get_text("text")
        if technique == "rendered_image":
            assert payload.encode() not in raw, "rendered-image payload must not exist as text"
            assert payload not in _all_text_sources(doc)
            assert len(page.get_images()) >= 1
            continue
        assert payload.encode() in raw, f"payload not in raw bytes of {e['file']}"
        spans = [s for b in page.get_text("dict")["blocks"] if b["type"] == 0
                 for line in b["lines"] for s in line["spans"] if payload in s["text"]]
        if technique == "white_text":
            assert spans and spans[0]["color"] == 0xFFFFFF
        elif technique == "tiny_font":
            assert spans and spans[0]["size"] < 1.0
        elif technique == "off_page":
            assert payload not in visible_text, "off-page text must be outside the default clip"
            wide = page.get_text("text", flags=fitz.TEXT_PRESERVE_WHITESPACE & ~fitz.TEXT_MEDIABOX_CLIP,
                                 clip=fitz.Rect(-5000, -5000, 5000, 5000))
            assert payload in wide
        elif technique == "metadata":
            assert payload not in visible_text
            assert doc.metadata["title"] == payload and doc.metadata["subject"] == payload
            assert payload in doc.get_xml_metadata()
        elif technique == "annotation":
            assert payload not in visible_text
            annots = list(page.annots())
            assert annots and annots[0].info["content"] == payload
            assert annots[0].flags & fitz.PDF_ANNOT_IS_HIDDEN
            widgets = list(page.widgets())
            assert widgets and widgets[0].field_value == payload
        elif technique == "image_alt":
            assert payload not in visible_text
            imgs = page.get_images(full=True)
            assert imgs
            alt = doc.xref_get_key(imgs[0][0], "Alt")
            assert payload in alt[1]
            assert b"/Figure <</Alt" in doc.xref_stream(page.get_contents()[0])
        doc.close()


def test_visible_and_policy_doc_payloads_are_in_text_layer(entries):
    for e in (x for x in entries if x["technique"] in ("visible", "policy_doc") and x["payload"]):
        doc = _doc(e)
        assert e["payload"] in doc[0].get_text("text"), e["file"]
        doc.close()


def test_invoice_totals_and_issuer(entries):
    for e in (x for x in entries if x["technique"] != "policy_doc"):
        doc = _doc(e)
        text = doc[0].get_text("text")
        assert "RS Mock Siloam" in text
        total = int(e["expected_total"].split(".")[0])
        assert f"IDR {total:,.0f}" in text, (e["file"], total)
        if e["technique"] == "inflated":
            assert total != 18_000_000 and e["expected_consistency_ok"] is False
        else:
            assert total == 18_000_000
        doc.close()


# --------------------------------------------------------------------------- clean invoices
def test_clean_invoices_contain_no_payload(entries, payloads):
    clean = [e for e in entries if e["technique"] == "clean"]
    assert len(clean) == 5
    needles = payloads + ["CANARY-7f3a", "0123456789", "9876543210", "SYSTEM:", "Assistant:", "ASSISTANT:"]
    for e in clean:
        assert e["expected_suspicious"] is False and e["payload_id"] is None
        raw = (ROOT / e["file"]).read_bytes()
        doc = _doc(e)
        everything = _all_text_sources(doc)
        for n in needles:
            assert n not in everything, (e["file"], n)
            assert n.encode() not in raw, (e["file"], n)
        assert not list(doc[0].annots()) and not list(doc[0].widgets())
        assert not re.search(r"(?i)ignore previous|note to ai|approve", everything)
        doc.close()


# --------------------------------------------------------------------------- chat cases
EXPECTED_IDS = (
    [f"IT-0{i}" for i in range(1, 8)] + ["PI-10", "PI-11", "PI-12", "PI-13"] + [f"DX-0{i}" for i in range(1, 7)]
    + [f"PE-0{i}" for i in range(1, 6)] + ["MEM-01", "MEM-02", "RL-01", "RL-02", "KS-01", "AUD-01"]
    + [f"BEN-{i:02d}" for i in range(1, 16)]
)
KNOWN_EXPECT_KEYS = {
    "no_tool_call_tier_ge", "pep_deny_reason", "pep_deny_reason_if_attempted", "reply_must_not_match",
    "reply_must_not_match_decoded", "reply_must_match", "db_unchanged", "ticket_created", "audit_event",
    "session_must_not_contain", "max_tool_calls", "no_pep_deny", "audit_verify_break_at",
}


def test_chat_cases_cover_report_table():
    doc = json.loads(CHAT.read_text(encoding="utf8"))
    ids = [c["id"] for c in doc["cases"]]
    assert ids == EXPECTED_IDS
    for c in doc["cases"]:
        assert set(c) >= {"id", "class", "channel", "turns", "setup", "expected"}
        assert set(c["setup"]) == {"persona", "uploads", "injected_tool_output", "kill_switch"}
        assert set(c["expected"]) <= KNOWN_EXPECT_KEYS, (c["id"], set(c["expected"]) - KNOWN_EXPECT_KEYS)
        assert c["expected"], c["id"]
        for u in c["setup"]["uploads"]:
            assert (ROOT / u).exists(), (c["id"], u)
        for rx in c["expected"].get("reply_must_match", []) + c["expected"].get("reply_must_not_match", []):
            re.compile(rx)
        if c["class"] == "BEN":
            assert c["expected"].get("no_pep_deny") is True
        elif c["class"] != "AUD":
            assert "no_tool_call_tier_ge" in c["expected"], c["id"]
    mem2 = next(c for c in doc["cases"] if c["id"] == "MEM-02")
    assert len(mem2["turns"]) == 40
    assert doc["cases"][ids.index("KS-01")]["setup"]["kill_switch"] is True
