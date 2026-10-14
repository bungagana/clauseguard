# PII redaction evaluation

Dataset: `data/benchmark/pii_eval.jsonl` - 63 PII snippets, 29 must-survive snippets, 24 adversarial snippets. Written by the project team, synthetic and fictional, not a public benchmark.
All intervals are Wilson 95%. A gold span counts as detected when same-type findings cover at least 80% of its characters. Regenerate with `python -m bench.pii_eval`.

## Span recall per type (PII snippets, labelled contexts unless noted)

| Type | Recall (same type) | Covered by any placeholder |
|---|---|---|
| ALAMAT | 1.000 [0.722, 1.000] (10/10) | 1.000 [0.722, 1.000] (10/10) |
| EMAIL | 1.000 [0.741, 1.000] (11/11) | 1.000 [0.741, 1.000] (11/11) |
| KARTU | 1.000 [0.566, 1.000] (5/5) | 1.000 [0.566, 1.000] (5/5) |
| NAMA | 1.000 [0.932, 1.000] (53/53) | 1.000 [0.932, 1.000] (53/53) |
| NAMA (no label) | 0.500 [0.237, 0.763] (5/10) | 0.500 [0.237, 0.763] (5/10) |
| NIK | 1.000 [0.806, 1.000] (16/16) | 1.000 [0.806, 1.000] (16/16) |
| NO_POLIS | 1.000 [0.816, 1.000] (17/17) | 1.000 [0.816, 1.000] (17/17) |
| NPWP | 1.000 [0.566, 1.000] (5/5) | 1.000 [0.566, 1.000] (5/5) |
| REKENING | 1.000 [0.722, 1.000] (10/10) | 1.000 [0.722, 1.000] (10/10) |
| TELP | 1.000 [0.862, 1.000] (24/24) | 1.000 [0.862, 1.000] (24/24) |
| TGL_LAHIR | 1.000 [0.806, 1.000] (16/16) | 1.000 [0.806, 1.000] (16/16) |
| TGL_LAHIR (no label) | 1.000 [0.207, 1.000] (1/1) | 1.000 [0.207, 1.000] (1/1) |
| **All labelled** | 1.000 [0.978, 1.000] (167/167) | |
| **All unlabelled** | 0.545 [0.280, 0.787] (6/11) | |

## Precision of emitted placeholders (PII snippets)

| Type | Precision | |
|---|---|---|
| ALAMAT | 1.000 [0.722, 1.000] (10/10) | |
| EMAIL | 1.000 [0.741, 1.000] (11/11) | |
| KARTU | 1.000 [0.566, 1.000] (5/5) | |
| NAMA | 1.000 [0.938, 1.000] (58/58) | |
| NIK | 1.000 [0.806, 1.000] (16/16) | |
| NO_POLIS | 1.000 [0.816, 1.000] (17/17) | |
| NPWP | 1.000 [0.566, 1.000] (5/5) | |
| REKENING | 1.000 [0.722, 1.000] (10/10) | |
| TELP | 1.000 [0.862, 1.000] (24/24) | |
| TGL_LAHIR | 1.000 [0.816, 1.000] (17/17) | |
| **All** | 1.000 [0.978, 1.000] (173/173) | |

## Over-redaction on must-survive items

Items that must survive (clause numbers, amounts, dates of events, ICD codes, hospital and product names) and were touched by a placeholder: **0.000 [0.000, 0.047] (0/78)**. Findings emitted on must-survive snippets: 0. final_gate violations on must-survive snippets (false blocks): 0.000 [0.000, 0.117] (0/29).

## final_gate

Catch rate on raw PII snippets that contain a NIK/phone/email/card or a known name: 1.000 [0.937, 1.000] (57/57).

Adversarial (hidden or obfuscated) cases, gate run on the raw text:

| Variant | Gate catch rate |
|---|---|
| ALL | 0.917 [0.742, 0.977] (22/24) |
| card_dashed | 1.000 [0.207, 1.000] (1/1) |
| card_spaced | 1.000 [0.207, 1.000] (1/1) |
| dashed_nik | 1.000 [0.207, 1.000] (1/1) |
| digits_as_words | 0.000 [0.000, 0.793] (0/1) |
| dotted_nik | 1.000 [0.342, 1.000] (2/2) |
| email_plain | 1.000 [0.207, 1.000] (1/1) |
| name_comma | 1.000 [0.207, 1.000] (1/1) |
| name_concat | 1.000 [0.207, 1.000] (1/1) |
| name_hyphen | 1.000 [0.207, 1.000] (1/1) |
| name_initial | 1.000 [0.207, 1.000] (1/1) |
| name_lower | 1.000 [0.207, 1.000] (1/1) |
| name_split_lines | 1.000 [0.342, 1.000] (2/2) |
| name_upper | 1.000 [0.207, 1.000] (1/1) |
| nik_in_sentence | 1.000 [0.207, 1.000] (1/1) |
| nik_newline | 0.000 [0.000, 0.793] (0/1) |
| o_zero | 1.000 [0.438, 1.000] (3/3) |
| phone_intl | 1.000 [0.207, 1.000] (1/1) |
| phone_spaced | 1.000 [0.207, 1.000] (1/1) |
| spaced_digits | 1.000 [0.342, 1.000] (2/2) |

End-to-end leak rate on adversarial cases (redaction missed a span AND the gate on the redacted text passed): **0.042 [0.007, 0.202] (1/24)**.

Redaction recall on adversarial spans: EMAIL 1.000 [0.207, 1.000] (1/1); KARTU 1.000 [0.342, 1.000] (2/2); NIK 0.889 [0.565, 0.980] (8/9); TELP 1.000 [0.438, 1.000] (3/3)

Adversarial cases the gate did NOT catch:

- `adv-022` (nik_newline): 'NIK: 3578 1245\n0990 0001'
- `adv-023` (digits_as_words): 'NIK tiga lima tujuh delapan satu dua empat lima nol sembilan sembilan '

Throughput: about 13.83 ms per 1000 characters for `redact` (single thread).

## Limitations

- Names without a label or honorific cannot be reliably detected by deterministic rules; the unlabelled row above measures exactly that gap. Only the caller-supplied known account-holder name is guaranteed to be caught anywhere in free text.
- The known-name gate protects the user's own name, not third parties (spouse, dependants, doctors, relatives) that appear without a label.
- Dates of birth are only found near a birth label; an unlabelled date is treated as an event date on purpose, because it carries coverage meaning.
- Rules were adjusted after a first run on this set (labels such as 'Rekening penerima', 'No. Kartu Peserta', landlines, the order of NPWP/VA versus NIK/Luhn), so the figures are in-sample and optimistic; the two adversarial misses (digits split by a line break, digits written as words) were added afterwards and were deliberately left unfixed.
- Bank account numbers are only redacted when labelled; unlabelled digit strings that are not NIK, phone, NPWP or Luhn-valid cards pass through.
- The final gate checks NIK, phone, email, card and known names only; addresses, policy numbers and dates of birth rely on the redaction pass.
- Token-level matching of known names (tokens of 4+ letters) can over-block text that contains a common word equal to part of the user's name.
- The evaluation set was authored by the same team that wrote the rules, so recall is optimistic relative to real documents. It is not a public benchmark and the intervals reflect sampling error only, not distribution shift.
- Scanned documents depend on OCR quality; OCR errors in digits can defeat the structural validators (see `evidence/ocr_report.md`).
