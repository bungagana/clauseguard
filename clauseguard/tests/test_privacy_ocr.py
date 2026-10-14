import io

import pytest
from PIL import Image, ImageDraw, ImageFont

from clauseguard.privacy import ocr


def _png(text="Nama: Budi Santoso", size=(700, 120)):
    img = Image.new("RGB", size, "white")
    try:
        font = ImageFont.truetype("arial.ttf", 36)
    except OSError:
        font = ImageFont.load_default()
    ImageDraw.Draw(img).text((20, 30), text, fill="black", font=font)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def no_engine(monkeypatch):
    monkeypatch.setattr(ocr, "available_engines", lambda: [])


def test_unavailable_is_typed_not_exception(no_engine):
    res = ocr.ocr_image(_png())
    assert res.available is False and res.text == "" and res.error
    assert ocr.needs_retake(res)


def test_garbage_bytes_never_raise():
    res = ocr.ocr_image(b"not an image")
    assert isinstance(res, ocr.OcrResult)


def _pdf(tmp_path, embedded, scanned):
    import pymupdf

    doc = pymupdf.open()
    if embedded:
        p = doc.new_page()
        p.insert_text((72, 100), "Pasal 4.2 manfaat rawat inap Rp 1.500.000 per hari selama tiga puluh hari.")
    if scanned:
        p = doc.new_page(width=595, height=200)
        p.insert_image(p.rect, stream=_png())
    path = tmp_path / "x.pdf"
    doc.save(str(path))
    doc.close()
    return path


def test_pdf_embedded_page_skips_ocr(tmp_path, no_engine):
    pages = ocr.pdf_pages_text(_pdf(tmp_path, True, False))
    assert pages[0].method == "embedded" and not pages[0].needs_retake and "Pasal 4.2" in pages[0].text


def test_pdf_scanned_page_without_engine_flags_retake(tmp_path, no_engine):
    pages = ocr.pdf_pages_text(_pdf(tmp_path, True, True))
    assert [p.method for p in pages] == ["embedded", "ocr"]
    assert pages[1].needs_retake and pages[1].ocr_available is False


def test_black_out_regions_synthetic():
    img = Image.new("RGB", (100, 60), "white")
    out = ocr.black_out_regions(img, [(10, 10, 40, 30)], pad=0)
    assert out.getpixel((20, 20)) == (0, 0, 0)
    assert out.getpixel((80, 50)) == (255, 255, 255)
    raw = io.BytesIO()
    img.save(raw, format="PNG")
    data = ocr.black_out_regions(raw.getvalue(), [(0, 0, 20, 20)])
    assert Image.open(io.BytesIO(data)).getpixel((5, 5)) == (0, 0, 0)


def test_flagged_line_boxes_selects_only_pii_lines():
    lines = [ocr.OcrLine("Total Rp 1.500.000", 0.9, (0, 0, 10, 10)),
             ocr.OcrLine("NIK: 3578124509900001", 0.9, (0, 20, 10, 30)),
             ocr.OcrLine("Pasal 4.2", 0.9, (0, 40, 10, 50))]
    res = ocr.OcrResult("\n".join(l.text for l in lines), 0.9, lines, "fake")
    assert ocr.flagged_line_boxes(res) == [(0, 20, 10, 30)]


def test_real_engine_reads_text_if_installed():
    if not ocr.available_engines():
        pytest.skip("no OCR engine installed")
    res = ocr.ocr_image(_png())
    assert res.available and "Budi" in res.text
    assert res.mean_confidence > 0.5
