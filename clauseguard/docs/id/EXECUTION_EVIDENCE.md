# ClauseGuard: Indeks Bukti Eksekusi

Tanggal status: 2026-10-11. Semua berkas berada di `evidence/` kecuali jika dicatat lain. Setiap angka dalam dokumen lain disalin dari salah satu berkas ini; nama berkas dicantumkan di sebelah angka tersebut.

## 1. Indeks

| Berkas | Apa yang ditunjukkan | Diproduksi oleh | Status |
|---|---|---|---|
| `task_report.md`, `task_runs.jsonl` | 33 tugas berskrip (T01-T23, A01-A10), lulus atau gagal, transkrip | `python scripts/run_tasks.py --no-llm` | Hadir: 33/33, mode deterministik, catatan sandbox |
| `offscript_report.md`, `offscript_runs.jsonl` | 15 pertanyaan di luar skrip (kelompok pengembangan pertama) | `python scripts/run_tasks.py --no-llm --suite off_script` | Hadir: 15/15 setelah perbaikan (6/15 pada pemeriksaan awal) |
| `offscript_holdout_report.md`, `offscript_holdout_runs.jsonl` | 10 pertanyaan (kelompok pengembangan kedua) | `... --suite holdout` | Hadir: 10/10 setelah perbaikan (5/10 pada pemeriksaan awal) |
| `offscript_blind_report.md`, `offscript_blind_runs.jsonl` | 14 pertanyaan yang ditulis dan dijalankan sekali sebelum perbaikan apa pun | `... --suite blind` | Hadir: 3/14, angka di luar sampel (out-of-sample) |
| `adversarial_report.md`, `adversarial_results.json` | Rangkaian serangan chat dengan penegakan aktif dan non-aktif, pemeriksaan penegakan langsung, deteksi teks tersembunyi, pemeriksaan acak ekstraktor | `python scripts/run_adversarial.py --no-guard` | Hadir: dihasilkan 2026-10-11 19:42; serangan 0/27 yang dibela, 1/27 tidak dibela; jinak 0/15 |
| `paraphrase_report.md`, `paraphrase_report.json` | Konsistensi keputusan di antara tiga penamaan, pengikat aturan dan pengikat model | `python bench/paraphrase.py [--live N]` | Hadir: 20/20 pengikat aturan; 7/8 sampel langsung pengikat model |
| `clarify_report.md`, `clarify_report.json` | Recall klarifikasi, keheningan, presisi pertanyaan, akurasi slot terhadap orakel brute-force | `python bench/clarify_eval.py` | Hadir: 87% / 100% / 100% / 100% |
| `cost_report.md`, `cost_report.json` | Pemanggilan model dan estimasi token per putaran chat terhadap baseline konteks panjang | `python bench/cost_eval.py` | Hadir: rata-rata 0,98 pemanggilan per putaran |
| `recourse_report.md`, `recourse_eval.json` | Upaya hukum (recourse) pada setiap putusan yang ditolak dari tugas berskrip; pemutaran ulang ombudsman (Bagian B) | `python -m bench.recourse_eval` | Hadir: 4/6 penolakan dengan upaya hukum; Bagian B belum dijalankan saat dihasilkan |
| `plan_selection_report.md` | Pemilihan paket berdasarkan anggaran: pengoptimal vs termurah vs logam tertinggi (834 paket CMS) dan vs termahal (katalog campuran), 100 rumah tangga | `python -m bench.plan_selection_eval --households 100 --seed 7` | Hadir: 73/100 dan 79/100 pada katalog campuran; pilihan identik pada CMS |
| `allocation_report.md` | Pengoptimal alokasi klaim vs baseline serakah (greedy) dan kebijakan tunggal | `python -m bench.allocation_eval` | hadir |
| `bench_report.md` | Tabel tolok ukur publik: akurasi, makro-F1, rasio NA ke DENIED, perolehan bukti, McNemar, akurasi per skenario | `python -m bench.report` di atas berkas-berkas `bench_*.jsonl` | Hadir: b4 390 dari 580 label; b0 dan b0cw pada C1, C2, C7 saja |
| `bench_b0.jsonl`, `bench_b0cw.jsonl` | Catatan mentah untuk baseline konteks panjang | `python -m bench.run_bench --system b0 --contracts C1,C2,C7` dan `--system b0cw ...` | Hadir |
| `bench_b4.jsonl` | Catatan mentah, tupel yang diekstrak + solver | `python scripts/extract_all.py` lalu `python -m bench.run_bench --system b4` | Hadir |
| `bench_b4oracle.jsonl`, `bench_b4oracle_v2.jsonl` | Catatan mentah, tupel anotasi-emas + solver (laporan membaca yang pertama; v2 adalah jalankan ulang yang disimpan untuk referensi) | `python -m bench.abox_to_tuples` lalu `python -m bench.run_bench --system b4oracle` | Hadir |
| `extraction_quality.md` | Presisi dan recall nilai yang diekstrak terhadap anotasi emas tolok ukur | `python scripts/extraction_quality.py` | Hadir |
| `audit_log.jsonl` | Audit log berantai-hash yang ditulis oleh sistem yang berjalan | Sistem yang berjalan | Berisi sesi pengembangan; hasilkan yang bersih untuk demo (bagian 3) |
| `claims_desk_run.md` | Satu operasi sandbox yang lengkap: empat dokumen klaim diunggah, formulir perusahaan asuransi disiapkan, klaim dikirimkan setelah konfirmasi, disetujui di meja dengan catatan, dan keputusan dikembalikan kepada pelanggan, dengan nomor urut audit | `python scripts/claims_desk_evidence.py` terhadap backend yang berjalan | Hadir: dihasilkan 2026-10-15 |
| Pemeriksaan RLS Supabase (keluaran konsol) | Setiap tabel Postgres menolak REST API database ke kunci yang dapat dipublikasikan | `python scripts/check_supabase_rls.py` | Dijalankan 2026-10-15: enam tabel, semuanya DENIED |

Rangkaian pengujian: `python -m pytest -q`; jumlah saat ini ada di `README.md`.

## 2. Urutan reproduksi

```bash
python -m pytest -q
python scripts/run_tasks.py --no-llm
python scripts/run_tasks.py --no-llm --suite off_script
python scripts/run_tasks.py --no-llm --suite holdout
python scripts/run_tasks.py --no-llm --suite blind
python scripts/run_adversarial.py --no-guard
python bench/paraphrase.py
python bench/clarify_eval.py
python bench/cost_eval.py
python -m bench.recourse_eval
python -m bench.plan_selection_eval --households 100 --seed 7
python -m bench.allocation_eval
python scripts/fetch_real_data.py          # real public data into data/real/ (resumable; manifest with hashes)
python scripts/extract_all.py
python scripts/extraction_quality.py
python -m bench.abox_to_tuples
python -m bench.run_bench --system b4oracle
python -m bench.run_bench --system b0cw --contracts C1,C2,C7
python -m bench.run_bench --system b0 --contracts C1,C2,C7
python -m bench.run_bench --system b4
python -m bench.report
```

Perintah tolok ukur dan ekstraksi memerlukan data pihak ketiga yang diambil dan kunci API dengan kuota yang cukup; catatan dapat dilanjutkan (resumable) dan di-cache pada disk. Segala sesuatu yang lain berjalan tanpa kunci.

Peringatan: `scripts/run_adversarial.py` selalu menulis `evidence/adversarial_results.json`, bahkan ketika `--out` dilewatkan untuk laporan. Salin berkas bukti akhir sebelum menjalankan pengujian cepat.

</markdown>
## 3. Menghasilkan audit log yang bersih untuk demo

`scripts/serve.py --fresh` melakukan pengisian ulang (re-seed) basis data tetapi tidak menghapus audit log. Gunakan berkas audit baru untuk setiap proses yang menghasilkan bukti; `CG_AUDIT_PATH` dibaca oleh `clauseguard/config.py`.

1. Pilih jalur baru, contohnya `evidence/audit_demo.jsonl`. Berkas tersebut belum boleh ada.
2. Jalankan server dengan jalur baru dan basis data yang bersih.

   Windows PowerShell:
   ```powershell
   $env:CG_AUDIT_PATH = "$PWD\evidence\audit_demo.jsonl"
   python scripts/serve.py --fresh --release-kill-switch
   ```
   Git Bash:
   ```bash
   CG_AUDIT_PATH="$PWD/evidence/audit_demo.jsonl" python scripts/serve.py --fresh --release-kill-switch
   ```
3. Jalankan demo (`ui/DEMO.md`) atau task runner di shell yang sama, kemudian hentikan server.
4. Pastikan rantai terverifikasi: `python scripts/verify_audit.py evidence/audit_demo.jsonl` mencetak `OK (n events)`.
5. Render log yang dapat dibaca (urutan, waktu, peristiwa, alat, tingkat, keputusan, alasan):
   ```bash
   python -c "import json,sys; [print(e['seq'], e['ts_utc'][:19], e['event_type'], e.get('tool') or '-', e.get('tier') if e.get('tier') is not None else '-', e.get('decision') or '-', (e.get('reason') or '')[:60], sep=' | ') for e in map(json.loads, open('evidence/audit_demo.jsonl', encoding='utf8')) if e]" > evidence/sandbox_operations.txt
   ```
6. Hitung peristiwa berdasarkan jenis:
   ```bash
   python -c "import json,collections; print(collections.Counter(json.loads(l)['event_type'] for l in open('evidence/audit_demo.jsonl', encoding='utf8') if l.strip()))"
   ```
7. Untuk tugas yang dibuat dengan skrip dan rangkaian adversarial, ulangi dengan jalur audit yang berbeda setiap kalinya agar setiap log memetakan ke satu perintah.
8. Simpan video demo dan log-nya secara bersamaan: video tersebut menampilkan tab audit dan log berisi sesi yang sama.

Jangan menyunting log secara manual. Demo perusakan (tamper) di UI bekerja pada salinannya.
## 4. Apa yang tidak ditunjukkan oleh bukti

- Tidak ada red team eksternal, tidak ada data penanggung nyata, tidak ada pengguna nyata.
- Uji coba scripted, off-script, paraphrase, clarification, recourse, dan allocation berada dalam mode deterministik (tidak ada panggilan model); perilaku dengan model planner dan binder yang aktif hanya diukur untuk sampel langsung paraphrase.
- Baris benchmark untuk b0 dan b0cw hanya mencakup tiga kontrak; b4 mencakup 390 dari 580 label.
- Eksperimen pemilihan rencana CMS dijalankan tanpa premi (basis out-of-pocket), sehingga semua metode bertepatan di sana.
- Pemutaran ulang ombudsman (recourse Bagian B) belum dijalankan saat `recourse_report.md` dibuat.
