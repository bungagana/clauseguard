"""Render synthetic documents under degradations with known ground truth, and optionally evaluate local OCR.

Run: python data/demo/gen_ocr_samples.py [--eval]
Samples land in data/demo/ocr_samples/. --eval also writes evidence/ocr_report.md.
"""
from __future__ import annotations

import argparse
import io
import random
import re
import statistics
import sys
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUT = HERE / "ocr_samples"

DOCS = {
    "invoice": [
        "RS Siloam Lippo Village - Invoice 2025/11/00123",
        "Nama Pasien: Putri Maharani",
        "No. Peserta: PSR-998877",
        "Tanggal masuk 12 Maret 2025, keluar 15 Maret 2025",
        "Kamar VIP 3 hari Rp 4.800.000 per hari",
        "Obat dan alat kesehatan Rp 1.235.000",
        "Diagnosa K35.8 apendisitis akut",
        "Total tagihan Rp 18.450.000",
        "Ditanggung polis sesuai Pasal 4.2",
    ],
    "schedule": [
        "JADWAL POLIS KESEHATAN PRIME CARE PLUS",
        "Pemegang Polis: Budi Santoso",
        "NIK: 3578124509900001",
        "Telp: 0812-3456-7890",
        "Limit tahunan Rp 1.000.000.000",
        "Masa tunggu 30 hari untuk penyakit umum",
        "Periode polis 01/01/2025 sampai 31/12/2025",
        "Pengecualian: kondisi bawaan lihat Pasal 12",
    ],
    "claimform": [
        "CLAIM FORM - HOSPITALISATION",
        "Patient Name: Michael Tan",
        "Date of Birth: 14/03/1985",
        "Policy No: AIA/HS/2023/778812",
        "Diagnosis: J18.9 pneumonia",
        "Admitted 05 November 2025 discharged 09 November 2025",
        "Total billed IDR 18,450,000",
        "Signature of claimant",
    ],
}

CONDITIONS = ["clean", "rotated3", "blur", "lowcontrast", "jpeg_phone", "severe"]


def _font(size: int) -> ImageFont.ImageFont:
    for name in ("arial.ttf", "Arial.ttf", "DejaVuSans.ttf", "LiberationSans-Regular.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def render(lines: list[str], width: int = 1240, size: int = 30) -> Image.Image:
    font = _font(size)
    lh = int(size * 1.9)
    img = Image.new("RGB", (width, lh * (len(lines) + 2)), "white")
    d = ImageDraw.Draw(img)
    for i, line in enumerate(lines):
        d.text((60, lh * (i + 1)), line, fill="black", font=font)
    return img


def degrade(img: Image.Image, cond: str, seed: int = 7) -> tuple[Image.Image, str]:
    rng = random.Random(seed)
    fmt = "PNG"
    if cond == "rotated3":
        img = img.rotate(3, expand=True, fillcolor="white", resample=Image.BICUBIC)
    elif cond == "blur":
        img = img.filter(ImageFilter.GaussianBlur(1.6))
    elif cond == "lowcontrast":
        img = ImageEnhance.Contrast(img).enhance(0.28)
    elif cond == "jpeg_phone":
        img = img.rotate(1.2, expand=True, fillcolor="white", resample=Image.BICUBIC)
        img = img.resize((int(img.width * 0.62), int(img.height * 0.62)), Image.BILINEAR)
        img = ImageEnhance.Brightness(img).enhance(0.88)
        fmt = "JPEG"
    elif cond == "severe":
        img = img.filter(ImageFilter.GaussianBlur(3.8))
        img = ImageEnhance.Contrast(img).enhance(0.3)
        px = img.load()
        for _ in range(img.width * img.height // 6):
            x, y = rng.randrange(img.width), rng.randrange(img.height)
            v = rng.randrange(0, 255)
            px[x, y] = (v, v, v)
        fmt = "JPEG"
    return img, fmt


def encode(img: Image.Image, fmt: str) -> bytes:
    buf = io.BytesIO()
    if fmt == "JPEG":
        img.save(buf, format="JPEG", quality=30)
    else:
        img.save(buf, format="PNG")
    return buf.getvalue()


def generate() -> list[dict]:
    OUT.mkdir(parents=True, exist_ok=True)
    items = []
    for name, lines in DOCS.items():
        truth = "\n".join(lines)
        (OUT / f"{name}.txt").write_text(truth, encoding="utf8")
        base = render(lines)
        for cond in CONDITIONS:
            img, fmt = degrade(base, cond)
            ext = "jpg" if fmt == "JPEG" else "png"
            p = OUT / f"{name}_{cond}.{ext}"
            p.write_bytes(encode(img, fmt))
            items.append({"doc": name, "cond": cond, "path": p, "truth": truth})
        _scanned_pdf(OUT / f"{name}_scanned.pdf", base)
    return items


def _scanned_pdf(path: Path, img: Image.Image) -> None:
    import pymupdf

    doc = pymupdf.open()
    page = doc.new_page(width=595, height=int(595 * img.height / img.width))
    page.insert_image(page.rect, stream=encode(img, "PNG"))
    doc.save(str(path))
    doc.close()


def _lev(a, b) -> int:
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        cur = [i]
        for j, y in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (x != y)))
        prev = cur
    return prev[-1]


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def cer(ref: str, hyp: str) -> float:
    r, h = _norm(ref), _norm(hyp)
    return _lev(r, h) / max(1, len(r))


def cer_nospace(ref: str, hyp: str) -> float:
    r, h = re.sub(r"\s+", "", ref), re.sub(r"\s+", "", hyp)
    return _lev(r, h) / max(1, len(r))


def wer(ref: str, hyp: str) -> float:
    r, h = _norm(ref).split(), _norm(hyp).split()
    return _lev(r, h) / max(1, len(r))


def evaluate(items: list[dict]) -> str:
    sys.path.insert(0, str(ROOT))
    from clauseguard.privacy import ocr

    engines = ocr.available_engines()
    L = ["# Local OCR evaluation", "",
         "Synthetic documents (3 texts) rendered with PIL and degraded per condition; ground truth is the rendered text. "
         "Regenerate with `python data/demo/gen_ocr_samples.py --eval`. CER and WER are Levenshtein distances over "
         "whitespace-normalised text, averaged over the 3 documents (n=3 per cell, so treat differences as indicative).", "",
         f"Engines detected: {', '.join(engines) if engines else 'none'}. "
         f"Tesseract binary on PATH: {'yes' if __import__('shutil').which('tesseract') else 'no'}.",
         f"needs_retake rule: mean confidence below {ocr.RETAKE_CONFIDENCE} or fewer than {ocr.RETAKE_MIN_CHARS} characters, "
         "or OCR unavailable.", ""]
    if not engines:
        L += ["No OCR engine is installed, so no accuracy numbers could be produced. `ocr_image` returns a typed "
              "`available=False` result and `pdf_pages_text` flags scanned pages with `needs_retake=True`.", ""]
    for eng in engines:
        L += [f"## Engine: {eng}", "", "| Condition | CER | CER ignoring spaces | WER | Mean confidence | needs_retake | Latency per image (s) |",
              "|---|---|---|---|---|---|---|"]
        ocr.ocr_image(items[0]["path"].read_bytes(), eng)
        for cond in CONDITIONS:
            rows = [i for i in items if i["cond"] == cond]
            cs, cns, ws, confs, rt, lat = [], [], [], [], 0, []
            for it in rows:
                t0 = time.perf_counter()
                res = ocr.ocr_image(it["path"].read_bytes(), eng)
                lat.append(time.perf_counter() - t0)
                cs.append(cer(it["truth"], res.text))
                cns.append(cer_nospace(it["truth"], res.text))
                ws.append(wer(it["truth"], res.text))
                confs.append(res.mean_confidence)
                rt += ocr.needs_retake(res)
            L.append(f"| {cond} | {statistics.mean(cs):.3f} | {statistics.mean(cns):.3f} | {statistics.mean(ws):.3f} | "
                     f"{statistics.mean(confs):.3f} | {rt}/{len(rows)} | {statistics.mean(lat):.2f} |")
        L.append("")
        pdfs = sorted(OUT.glob("*_scanned.pdf"))
        if pdfs:
            t0 = time.perf_counter()
            pages = [p for f in pdfs for p in ocr.pdf_pages_text(f, engine=eng)]
            dt = (time.perf_counter() - t0) / max(1, len(pages))
            truth = {f.stem.replace("_scanned", ""): (OUT / f"{f.stem.replace('_scanned', '')}.txt").read_text(encoding="utf8") for f in pdfs}
            pc = [cer(truth[f.stem.replace("_scanned", "")], pt.text) for f in pdfs for pt in ocr.pdf_pages_text(f, engine=eng)]
            L += [f"Scanned PDFs ({len(pages)} image-only pages, rasterised at {ocr.OCR_DPI} dpi): methods "
                  f"{sorted({p.method for p in pages})}, mean CER {statistics.mean(pc):.3f}, "
                  f"{dt:.2f} s per page including rasterisation.", ""]
    L += ["## Limitations", "",
          "- RapidOCR drops inter-word spaces on many lines (\"PemegangPolis:BudiSantoso\"), which inflates WER while the "
          "space-insensitive CER stays low. Confidence stayed near 0.98 for blurred and JPEG samples whose WER was high, "
          "so confidence alone does not detect space loss or mild blur; it only flagged the severe condition. "
          "The redaction label patterns tolerate missing spaces for this reason.",
          "- Three short synthetic documents set in one sans-serif font; real scans have stamps, tables, handwriting, "
          "and mixed fonts that are harder. These numbers are a smoke benchmark, not a field estimate.",
          "- Degradations are simulated (blur, contrast, rotation, JPEG, noise), not captured with a real phone camera.",
          "- Digits matter most for redaction: a single misread digit in a NIK defeats the structural validator, "
          "so pages with low confidence should be retaken rather than trusted.", ""]
    return "\n".join(L)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--eval", action="store_true")
    a = ap.parse_args()
    items = generate()
    print(f"wrote {len(items)} images to {OUT}")
    if a.eval:
        md = evaluate(items)
        (ROOT / "evidence").mkdir(exist_ok=True)
        (ROOT / "evidence" / "ocr_report.md").write_text(md, encoding="utf8")
        print(md)


if __name__ == "__main__":
    main()
