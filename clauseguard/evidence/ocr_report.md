# Local OCR evaluation

Synthetic documents (3 texts) rendered with PIL and degraded per condition; ground truth is the rendered text. Regenerate with `python data/demo/gen_ocr_samples.py --eval`. CER and WER are Levenshtein distances over whitespace-normalised text, averaged over the 3 documents (n=3 per cell, so treat differences as indicative).

Engines detected: rapidocr. Tesseract binary on PATH: no.
needs_retake rule: mean confidence below 0.7 or fewer than 15 characters, or OCR unavailable.

## Engine: rapidocr

| Condition | CER | CER ignoring spaces | WER | Mean confidence | needs_retake | Latency per image (s) |
|---|---|---|---|---|---|---|
| clean | 0.034 | 0.000 | 0.340 | 0.985 | 0/3 | 2.17 |
| rotated3 | 0.013 | 0.000 | 0.128 | 0.989 | 0/3 | 2.66 |
| blur | 0.112 | 0.000 | 1.000 | 0.989 | 0/3 | 2.90 |
| lowcontrast | 0.024 | 0.000 | 0.242 | 0.987 | 0/3 | 2.80 |
| jpeg_phone | 0.097 | 0.000 | 0.901 | 0.980 | 0/3 | 2.85 |
| severe | 0.958 | 0.965 | 1.000 | 0.588 | 3/3 | 4.24 |

Scanned PDFs (3 image-only pages, rasterised at 200 dpi): methods ['ocr'], mean CER 0.022, 9.07 s per page including rasterisation.

## Limitations

- RapidOCR drops inter-word spaces on many lines ("PemegangPolis:BudiSantoso"), which inflates WER while the space-insensitive CER stays low. Confidence stayed near 0.98 for blurred and JPEG samples whose WER was high, so confidence alone does not detect space loss or mild blur; it only flagged the severe condition. The redaction label patterns tolerate missing spaces for this reason.
- Three short synthetic documents set in one sans-serif font; real scans have stamps, tables, handwriting, and mixed fonts that are harder. These numbers are a smoke benchmark, not a field estimate.
- Degradations are simulated (blur, contrast, rotation, JPEG, noise), not captured with a real phone camera.
- Digits matter most for redaction: a single misread digit in a NIK defeats the structural validator, so pages with low confidence should be retaken rather than trusted.
