"""A malformed/corrupt PDF must never hang the server or bubble a 500: it returns the same
clean "could not parse" result used for any other failed/ambiguous extraction, within the
parse timeout, and never reaches the LLM."""
from __future__ import annotations

import time

import pymupdf as fitz
import pytest
from fastapi.testclient import TestClient

from clauseguard.extractor import claim_doc, hidden_text
from clauseguard.sandbox import api


@pytest.fixture
def client(sandbox_db):
    api.SESSIONS.clear()
    with TestClient(api.app) as c:
        yield c


def login(client, persona="rizky"):
    r = client.post("/login", json={"persona": persona})
    assert r.status_code == 200, r.text
    return {"X-Session-Token": r.json()["session_token"]}


def _write(tmp_path, name, data):
    p = tmp_path / name
    p.write_bytes(data)
    return p


def _forbid_llm(monkeypatch):
    """Any extraction LLM call on a malformed document is a bug: the preflight check must reject
    the document before it ever reaches the model."""
    def _boom(*a, **k):
        raise AssertionError("LLM must not be called for an unparseable PDF")

    monkeypatch.setattr(claim_doc.llm, "generate_json", _boom)


# --------------------------------------------------------------------- claim_doc extractor


def test_zero_byte_pdf_claim_doc(tmp_path, monkeypatch):
    _forbid_llm(monkeypatch)
    p = _write(tmp_path, "zero.pdf", b"")
    t0 = time.perf_counter()
    out = claim_doc.extract_claim_document(p, policyholder_name="Test User")
    assert time.perf_counter() - t0 < claim_doc.PDF_PARSE_TIMEOUT_S + 5
    assert out.doc_type == claim_doc.DocType.UNKNOWN
    assert out.extract_quality == claim_doc.ExtractQuality.LOW


def test_truncated_pdf_claim_doc(tmp_path, monkeypatch):
    _forbid_llm(monkeypatch)
    # valid header, truncated body (no xref/trailer) -> pymupdf opens it with 0 pages
    p = _write(tmp_path, "trunc.pdf", b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n")
    out = claim_doc.extract_claim_document(p, policyholder_name="Test User")
    assert out.doc_type == claim_doc.DocType.UNKNOWN
    assert out.extract_quality == claim_doc.ExtractQuality.LOW


def test_text_file_renamed_pdf_claim_doc(tmp_path, monkeypatch):
    _forbid_llm(monkeypatch)
    p = _write(tmp_path, "notapdf.pdf", b"this is just plain text, not a pdf at all\n" * 10)
    out = claim_doc.extract_claim_document(p, policyholder_name="Test User")
    assert out.doc_type == claim_doc.DocType.UNKNOWN
    assert out.extract_quality == claim_doc.ExtractQuality.LOW


def test_password_protected_pdf_claim_doc(tmp_path, monkeypatch):
    _forbid_llm(monkeypatch)
    doc = fitz.open()
    doc.new_page()
    p = tmp_path / "locked.pdf"
    doc.save(str(p), encryption=fitz.PDF_ENCRYPT_AES_256, owner_pw="owner", user_pw="secret")
    doc.close()
    out = claim_doc.extract_claim_document(p, policyholder_name="Test User")
    assert out.doc_type == claim_doc.DocType.UNKNOWN
    assert out.extract_quality == claim_doc.ExtractQuality.LOW


def test_zero_page_pdf_claim_doc(tmp_path, monkeypatch):
    _forbid_llm(monkeypatch)
    # pymupdf refuses to *save* a zero-page document, but it will *open* a well-formed-looking
    # but bodiless PDF (valid header, a catalog object, no pages) with page_count == 0.
    p = _write(tmp_path, "nopages.pdf", b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n")
    out = claim_doc.extract_claim_document(p, policyholder_name="Test User")
    assert out.doc_type == claim_doc.DocType.UNKNOWN
    assert out.extract_quality == claim_doc.ExtractQuality.LOW


# --------------------------------------------------------------------- hidden_text helpers


def test_check_pdf_readable_reasons(tmp_path):
    with pytest.raises(hidden_text.PdfUnreadable) as e1:
        hidden_text.check_pdf_readable(_write(tmp_path, "zero.pdf", b""))
    assert e1.value.args[0] == hidden_text.REASON_CORRUPT

    p = _write(tmp_path, "nopages.pdf", b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n")
    with pytest.raises(hidden_text.PdfUnreadable) as e2:
        hidden_text.check_pdf_readable(p)
    assert e2.value.args[0] == hidden_text.REASON_ZERO_PAGE


def test_scan_pdf_safe_never_raises_and_reports_fixed_reason(tmp_path):
    p = _write(tmp_path, "zero.pdf", b"")
    report = hidden_text.scan_pdf_safe(p, timeout_s=5)
    assert report.suspicious is True
    findings = [f for f in report.findings if f.technique == "parse_error"]
    assert len(findings) == 1
    # fixed vocabulary only: never the raw exception text (which can carry the server file path)
    assert findings[0].snippet == hidden_text.REASON_CORRUPT
    assert str(p) not in findings[0].snippet


def test_scan_pdf_safe_times_out_without_waiting_for_the_hang(tmp_path, monkeypatch):
    """Simulate a pathological scan with a tight Python busy-loop (no sleep/no I/O, so it never
    yields the GIL voluntarily) to show the caller gets control back at ~timeout_s regardless."""
    def _hang(path):
        end = time.perf_counter() + 4  # long enough to outlast the 1s timeout below, short enough not to leak CPU
        x = 0
        while time.perf_counter() < end:
            x += 1
        return x

    monkeypatch.setattr(hidden_text, "scan_pdf", _hang)
    doc = fitz.open()
    doc.new_page()
    p = tmp_path / "valid_one_page.pdf"
    doc.save(str(p))
    doc.close()
    t0 = time.perf_counter()
    report = hidden_text.scan_pdf_safe(p, timeout_s=1)
    elapsed = time.perf_counter() - t0
    assert elapsed < 5, f"caller blocked for {elapsed}s waiting on the hung thread"
    assert report.suspicious is True
    assert report.findings[0].snippet == hidden_text.REASON_TIMEOUT


# --------------------------------------------------------------------- /policies/upload endpoint


def test_policies_upload_malformed_pdf_rejected_cleanly(client, monkeypatch):
    """Must not reach extract_policy/the LLM, must not 500, must return a clear 4xx."""
    from clauseguard.extractor import policy_extractor as pe

    def _boom(*a, **k):
        raise AssertionError("extract_policy must not run for an unparseable PDF")

    monkeypatch.setattr(pe, "extract_policy", _boom)
    h = login(client)
    r = client.post(
        "/policies/upload",
        files={"file": ("broken.pdf", b"%PDF-1.4\nnot a real pdf body", "application/pdf")},
        headers=h,
    )
    assert r.status_code == 400, r.text
    assert "could not parse" in r.json()["detail"].lower()


def test_policies_upload_zero_byte_rejected_before_parsing(client):
    h = login(client)
    r = client.post("/policies/upload", files={"file": ("zero.pdf", b"", "application/pdf")}, headers=h)
    assert r.status_code == 400
    assert "empty" in r.json()["detail"].lower()


# --------------------------------------------------------------------- full /upload -> /tools/extract_document


@pytest.mark.parametrize("name,data", [
    ("zero.pdf", b""),
    ("truncated.pdf", b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n"),
    ("notapdf.pdf", b"this is just plain text, not a pdf at all\n" * 10),
])
def test_upload_then_extract_document_tool_never_500s(client, monkeypatch, name, data):
    _forbid_llm(monkeypatch)
    h = login(client)
    r = client.post("/upload", files={"file": (name, data, "application/pdf")}, headers=h)
    assert r.status_code == 200, r.text
    doc_handle = r.json()["handle"]
    t0 = time.perf_counter()
    r = client.post("/tools/extract_document", json={"args": {"doc_handle": doc_handle}}, headers=h)
    elapsed = time.perf_counter() - t0
    assert elapsed < claim_doc.PDF_PARSE_TIMEOUT_S + 10, f"took {elapsed}s"
    assert r.status_code == 200, r.text
    assert r.json()["result"]["doc_type"] == "UNKNOWN"
