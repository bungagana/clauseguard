import glob
from pathlib import Path

import pytest

from clauseguard.privacy.layout import Heading, cross_check, detect_headings, slice_by_headings

ROOT = Path(__file__).resolve().parents[1]


def _make_pdf(tmp_path):
    import pymupdf

    doc = pymupdf.open()
    page = doc.new_page()
    y = 72
    plan = [
        ("BAB I KETENTUAN UMUM", "hebo", 16),
        ("Pasal 1 Definisi", "hebo", 13),
        ("Tertanggung adalah orang yang namanya tercantum dalam jadwal polis dan dilindungi.", "helv", 10),
        ("Polis ini berlaku selama periode yang tercantum dalam jadwal polis.", "helv", 10),
        ("Pasal 2 Manfaat", "hebo", 13),
        ("Manfaat rawat inap dibayarkan sesuai tabel manfaat yang berlaku saat klaim diajukan.", "helv", 10),
        ("Santunan harian dibayarkan mulai hari kedua perawatan di rumah sakit rekanan.", "helv", 10),
    ]
    for text, font, size in plan:
        page.insert_text((72, y), text, fontname=font, fontsize=size)
        y += size + 14
    page2 = doc.new_page()
    page2.insert_text((72, 72), "Pasal 3 Pengecualian", fontname="hebo", fontsize=13)
    page2.insert_text((72, 100), "Kondisi bawaan tidak dijamin selama masa tunggu dua belas bulan.", fontname="helv", fontsize=10)
    path = tmp_path / "g.pdf"
    doc.save(str(path))
    doc.close()
    return path


def test_detects_known_headings_and_levels(tmp_path):
    hs = detect_headings(_make_pdf(tmp_path))
    assert [h.text for h in hs] == ["BAB I KETENTUAN UMUM", "Pasal 1 Definisi", "Pasal 2 Manfaat", "Pasal 3 Pengecualian"]
    assert hs[0].level == 1 and hs[1].level == 2
    assert hs[3].page == 2 and hs[0].bold


def test_slice_by_headings(tmp_path):
    import pymupdf

    path = _make_pdf(tmp_path)
    hs = detect_headings(path)
    with pymupdf.open(str(path)) as d:
        pages = [p.get_text("text") for p in d]
    secs = slice_by_headings(pages, hs)
    assert [s.heading.text for s in secs] == [h.text for h in hs]
    s2 = next(s for s in secs if s.heading.text == "Pasal 2 Manfaat")
    assert "Santunan harian" in s2.text and "Pasal 3" not in s2.text
    assert secs[-1].page_start == 2


def test_cross_check_fuzzy():
    det = [Heading("Pasal 1 Definisi", 1, 2, 13, True), Heading("Pasal 2 Manfaat", 1, 2, 13, True),
           Heading("Lampiran", 2, 1, 13, True)]
    cc = cross_check(["PASAL 1: DEFINISI", "Pasal 2 - Manfaat Asuransi", "Pasal 9 Hantu"], det)
    assert [m[0] for m in cc.matched] == ["PASAL 1: DEFINISI", "Pasal 2 - Manfaat Asuransi"]
    assert cc.unmatched_llm == ["Pasal 9 Hantu"]
    assert [h.text for h in cc.unmatched_detected] == ["Lampiran"]


REAL = sorted(glob.glob(str(ROOT / "data" / "policies" / "real" / "*.pdf")) + glob.glob(str(ROOT / "data" / "real" / "riplay" / "*.pdf")))


@pytest.mark.skipif(not REAL, reason="third-party real PDFs not present")
def test_real_pdfs_yield_headings():
    counts = {Path(p).name: len(detect_headings(p)) for p in REAL[:6]}
    assert all(c >= 3 for c in counts.values()), counts
