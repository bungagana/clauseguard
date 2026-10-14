# Diagnosis line to ICD-10 category: retrieval ablation and evaluation

Date: 2026-10-14. Selection/normalisation model: `gemini-3.5-flash-lite` (temperature 0, schema-constrained, disk-cached). Gemini embedding model: `gemini-embedding-2` (768 dims, RETRIEVAL_DOCUMENT / RETRIEVAL_QUERY). Local embedding model: `multilingual-e5-small-int8` (intfloat/multilingual-e5-small, int8 ONNX export, onnxruntime + tokenizers on CPU, no PyTorch).

## Data and what this evidence is

Both sets are **team-authored and team-labelled**. They are not a public clinical benchmark, and no public Indonesian discharge-summary benchmark with ICD-10 labels exists (real discharge summaries carry patient data). Gold labels are ICD-10-CM 3-character categories; where a label is arguable, the line lists more than one accepted category and carries a `note`.

- **development** (`data\benchmark\icd_eval.jsonl`): 76 lines, 12 gold-undetermined, 3 with more than one accepted category. Seen while the pipeline and its synonym tables were built: its BM25 numbers are optimistic.
- **heldout** (`data\benchmark\icd_eval_heldout.jsonl`): 75 lines, 12 gold-undetermined, 9 with more than one accepted category. Written before any retrieval ablation was run; 10 lines that duplicated development texts were removed before any held-out run (75 remain). Near-paraphrases of development lines may remain.

Code list: ICD-10-CM FY2027 descriptions (CMS/CDC-NCHS, public domain), `data/real/icd10cm_codes.txt`. Each category is embedded as its official label plus up to 6 distinct member-code descriptions, once, and cached under `data/cache/` (rebuild: `python scripts/fetch_real_data.py --only e5onnx,icdembed`).

Configurations: **bm25** = BM25 over the English terms (previous default); **emb** = dense similarity only (English terms and raw diagnosis text, two rankings fused by RRF); **hybrid** = RRF (k=60) of BM25 with both dense rankings. Normalisation and selection prompts, guards and thresholds are identical in every configuration; only the candidate list changes. Candidate list = top 15 categories + 5 full codes. For `emb`/`hybrid` the 5 full codes are BM25 full codes restricted to the fused categories (for `bm25` unrestricted, as before). Recall is measured on category rankings only.

## Results: development set (n=76, gold-coded 64, gold-undetermined 12)

Proportions with Wilson 95% intervals. Accuracy and recall are over gold-coded lines; undetermined and false-code rates over all lines.

| config | recall@5 | recall@10 | recall@20 | category accuracy | undetermined | **false-code** |
|---|---|---|---|---|---|---|
| bm25 | 92.2% (59/64) [83.0, 96.6] | 95.3% (61/64) [87.1, 98.4] | 96.9% (62/64) [89.3, 99.1] | 92.2% (59/64) [83.0, 96.6] | 18.4% (14/76) [11.3, 28.6] | **3.9% (3/76) [1.4, 11.0]** |
| e5onnx:emb | 57.8% (37/64) [45.6, 69.1] | 78.1% (50/64) [66.6, 86.5] | 93.8% (60/64) [85.0, 97.5] | 81.2% (52/64) [70.0, 88.9] | 25.0% (19/76) [16.6, 35.8] | **6.6% (5/76) [2.8, 14.5]** |
| e5onnx:hybrid | 89.1% (57/64) [79.1, 94.6] | 95.3% (61/64) [87.1, 98.4] | 96.9% (62/64) [89.3, 99.1] | 92.2% (59/64) [83.0, 96.6] | 19.7% (15/76) [12.3, 30.0] | **2.6% (2/76) [0.7, 9.1]** |

Exact McNemar against `bm25` on the same lines (discordant counts: lines only the other configuration gets right / lines only bm25 gets right; two-sided exact binomial p):

| config | line correct (gold-coded: in gold; gold-undetermined: left undetermined) | false-code (lower is better; counts = only-other-is-false / only-bm25-is-false) | recall@10 hit |
|---|---|---|---|
| e5onnx:emb | 2 / 10, p=0.039 | 2 / 0, p=0.500 | 0 / 11, p=0.001 |
| e5onnx:hybrid | 2 / 2, p=1.000 | 0 / 1, p=1.000 | 0 / 0, p=1.000 |

## Results: held-out set - NOT MEASURED

The 75-line held-out set (`data/benchmark/icd_eval_heldout.jsonl`, written and frozen before any retrieval ablation) could not be evaluated. The free-tier language-model quota (`gemini-3.5-flash-lite` daily quota exhausted; alternative models returned 404/503) ran out after the development set, so normalisation fell back to offline terms and selection raised CoderUnavailable for most held-out lines. Those rows in `evidence/icd_results.jsonl` (set = heldout, mostly `ran: false`) are not valid evidence and must not be read as results. No held-out recall, accuracy, false-code rate or McNemar test is reported. Rerun with `python -m bench.icd_eval --configs bm25,e5onnx:emb,e5onnx:hybrid` when quota is available.

The Gemini-embedding configuration was not evaluated: the free-tier embedding quota (100 requests per minute, 1000 per day per key; gemini-embedding-2 returns one vector per call) prevented building the category index (about 600 of 1921 category vectors cached).

## Previous version (BM25 only, before this change, development set)

Category accuracy 92.2%, false-code rate 3.9%, retrieval recall@k (k = 15 categories + 5 codes) 96.9%, n=76. Failures included retrieval misses (Graves E05, head injury S06). The `bm25` row on the development set above is the same pipeline re-run with the current evaluation code.

## Alias dictionary (offline fallback path)

| set | category accuracy | false-code |
|---|---|---|
| development | 17.2% (11/64) [9.9, 28.2] | 0.0% (0/76) [0.0, 4.8] |
| heldout | 5.8% (4/69) [2.3, 14.0] | 1.2% (1/85) [0.2, 6.4] |

## Latency and model sizes

Retrieval latency (query-vector cache off, first 20 held-out lines; excludes the two language-model calls) was measured in the interrupted runs only for local configurations: bm25 about 4-5 ms median, e5onnx:hybrid about 20 ms, e5onnx:emb about 36 ms (p95 up to 110 ms), CPU, Windows. Model calls per line: normalisation 1 + selection 1 for every configuration; `e5onnx:*` and `bm25` add no network call. e5 int8 ONNX is 118 MB plus a 17 MB tokenizer, fetched on demand (`scripts/fetch_real_data.py --only e5onnx,icdembed`), optional packages `onnxruntime` and `tokenizers`; cached category vectors are 2.7 MB.

## Default retrieval

The cheapest-acceptable rule could not be applied (no held-out data). Default stays `bm25` (`DEFAULT_RETRIEVER`); the hybrid is opt-in via `CG_ICD_RETRIEVER=e5onnx:hybrid`. On the development set alone the hybrid is not distinguishable from BM25 (see above), which is the set BM25 was tuned on.

## Limits

- Small, team-written sets; the confidence intervals above are wide. They support a functional check and a rough ranking, not a clinical coding benchmark.
- The development set was used while the pipeline was built, so BM25 is tuned toward it; embedding configurations were not tuned on either set (no hyper-parameters were fitted; RRF k=60 and the category text recipe were fixed before any run).
- Gold labels are 3-character categories; sub-category correctness is not scored because coverage clauses are written at category or range level.
- ICD-10-CM (US clinical modification) is used because it is the only official ICD-10 code list published as a public-domain text file; its 3-character categories coincide with WHO ICD-10 for the conditions here, except that ICD-10-CM has no A16 (respiratory TB is A15).
- The held-out set was written by the same team that wrote the development set and the synonym tables, so style leakage is possible. Selection and normalisation are large-language-model calls and can change across model versions; results are disk-cached for this run.
- INA-CBG tariff grouping is not implemented; this evaluation covers diagnosis-to-category resolution only.
