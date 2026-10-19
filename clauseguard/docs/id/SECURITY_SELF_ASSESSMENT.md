# ClauseGuard: Laporan Penilaian Keamanan Mandiri

*Jelas di setiap klausul, yakin di setiap klaim.*

FinTechathon 2026 · International Track · Topik D: AI Insurance Assistant
Tim: Bunga Laelatul Muna, Izra, Wan Sabrina · Institut Teknologi Sepuluh Nopember, Indonesia
Kode sumber: https://github.com/bungagana/clauseguard · Demo langsung: https://clauseguard.up.railway.app
Tanggal status: 19 Oktober 2026

Laporan ini menjelaskan model izin ClauseGuard, pengujian keamanannya, pengelolaan data dan privasi, dan risiko yang masih kami ketahui. Penilaian dilakukan oleh tim sendiri terhadap kode di repositori yang berjalan pada penanggung simulasi (FastAPI dengan SQLite atau Postgres) dan persona sintetis. Setiap mekanisme menyebut berkas yang menerapkannya. Angka pengujian berasal dari `evidence/adversarial_report.md` (dihasilkan 11 Oktober 2026), `evidence/task_report.md`, dan hasil `pytest`. Pekerjaan yang direncanakan diberi tanda Rencana.

ClauseGuard memiliki 3 fitur utama dan 3 fitur pendukung. Fitur utama adalah ClauseLens, ClaimFlow, dan TrustLock. Fitur pendukung adalah Claim Simulator, Deadline Tracker, dan PDF Export. TrustLock adalah fitur yang dinilai dalam laporan ini karena TrustLock membatasi setiap tindakan agen dengan tingkat izin, konfirmasi sekali pakai, dan audit log.

## Ringkasan hasil

Tabel 1 memuat hasil utama dalam satu halaman.

**Tabel 1. Ringkasan hasil penilaian**

| Ukuran | Hasil | Sumber |
|---|---|---|
| Serangan yang menimbulkan efek terlarang saat penegakan menyala | 0 dari 27 | `evidence/adversarial_report.md` |
| Permintaan jinak yang diblokir keliru | 0 dari 15 | `evidence/adversarial_report.md` |
| Probe langsung ke fungsi penegakan dan nonce yang berhasil | 0 dari 10 | `evidence/adversarial_report.md` |
| Teks tersembunyi yang terdeteksi (putih, huruf kecil, di luar halaman, anotasi) | 20 dari 20 untuk setiap teknik | `evidence/adversarial_report.md` |
| Teks instruksi yang digambar di dalam gambar | Tidak terdeteksi (0 dari 20) | `evidence/adversarial_report.md` |
| Tugas terskrip termasuk A01 sampai A10 (adversarial) | 33 dari 33 lulus | `evidence/task_report.md` |
| Tes keamanan yang dijalankan ulang pada 19 Oktober 2026 | 68 lulus | `pytest` pada lima berkas |
| Seluruh rangkaian tes | 554 lulus pada run penuh terakhir | `pytest` |
| Risiko yang diketahui | 21 (tinggi 2, sedang 9, rendah 10) | Tabel 12 |

Sikap desain kami adalah model bahasa tidak pernah memutuskan izin. Model hanya mengusulkan pemanggilan alat. Guardian memutuskan izinkan, tolak, atau minta konfirmasi dengan kode deterministik. Petugas penanggung memutuskan setiap klaim. Hasil pengujian yang sempurna pada 27 serangan berasal dari kasus yang ditulis tim, jadi hasil itu menunjukkan aturan berfungsi dan tidak menjadi bukti kebal serangan. Bab 4 memuat batasnya.

## 1. Model izin

### 1.1 Peran dan batasnya

Tabel 2 memuat peran dalam sistem, apa yang boleh dan tidak pernah dilakukan setiap peran, dan lokasinya di kode.

**Tabel 2. Peran dan batas kewenangan**

| Peran | Boleh | Tidak pernah | Lokasi |
|---|---|---|---|
| Nasabah | Masuk dengan akun, bertanya, mengunggah polis dan dokumen, mengoreksi formulir, menekan Konfirmasi, memilih mode otonomi, memakai kunci sendiri, menghapus riwayat percakapan | Melihat data akun lain atau menekan Konfirmasi atas nama orang lain karena nonce terikat pada sesi | `sandbox/api.py` |
| Agen (planner dan model) | Mengusulkan pemanggilan alat T0 sampai T2 dan satu tiket T3 | Menentukan izinnya sendiri, memanggil alat di luar registri, menyetujui atau menolak klaim, memindahkan uang | `agent/`, `security/registry.py` |
| Guardian | Memutuskan izinkan, tolak, atau minta konfirmasi, menerbitkan nonce, menurunkan sesi ke T0 | Menjalankan alat atau terpengaruh oleh teks bebas | `security/pep.py`, `security/nonce.py` |
| Ekstraktor terkarantina | Membaca dokumen dan mengisi skema tertutup | Memiliki alat, riwayat, atau akses ke akun | `extractor/` |
| Penyelesai | Menghitung putusan, alokasi, recourse, dan pemilihan paket | Memanggil model atau menimbulkan efek samping | `solver.py`, `allocation.py`, `recourse.py`, `plans/` |
| Petugas penanggung | Meninjau klaim beserta dokumennya, memutuskan dengan catatan, menangani tiket | Dicapai planner, karena tidak ada alat registri yang menunjuk ke meja penanggung. Wajib token admin | `/backoffice/*` |
| Admin sistem | Menghentikan agen untuk semua nasabah, menambah kunci model | Membaca riwayat percakapan nasabah, karena tidak ada endpoint admin yang menyediakannya | `/admin/kill`, `/system/add-key` |
| Penyedia model (Google Gemini) | Mengembalikan teks dan keluaran terstruktur | Menjalankan alat. Keluarannya diperlakukan sebagai tidak tepercaya | `llm.py` |
| Supabase | Memverifikasi akun dan menyimpan data Postgres | Dibaca oleh kunci publik karena row level security menolaknya | `deploy/migrations/001_init.sql` |

Yang dinilai adalah loop agen, planner, Guardian, registri alat, ekstraktor terkarantina, empat penyelesai hak nasabah, audit log, penjaga keluaran, API sandbox, dan antarmuka. Yang berada di luar penilaian adalah layanan model bahasa yang di-hosting, sistem operasi, sistem penanggung sungguhan, dan data nasabah sungguhan. Aset yang dilindungi adalah rekening pencairan, ahli waris, dan rekening debit premi, wewenang memutuskan klaim, data pribadi nasabah, catatan pengguna lain, keutuhan kualifikasi klausul, system prompt yang memuat string kenari, dan audit log.

### 1.2 Isolasi aliran data

Prinsip isolasi yang dipakai adalah sebagai berikut.

1. Prompt planner memuat teks pengguna dan nama alat. Prompt itu tidak pernah memuat teks dokumen atau keluaran alat (`agent/planner.py`).
2. Ekstraktor terkarantina berjalan tanpa alat dan tanpa riwayat. Keluarannya adalah skema pydantic tertutup. Satu-satunya kolom teks bebas yang sampai ke pemanggil adalah daftar singkat temuan teks tersembunyi untuk ditampilkan.
3. Nilai dari dokumen, alat, dan model masuk registri sebagai nilai bertipe dengan label kepercayaan. Label nilai turunan adalah yang terendah dari masukannya (`security/labels.py`).
4. Argumen T2 dan T3 harus berupa handle registri. String literal ditolak.
5. Penyelesai adalah fungsi murni dari catatan dan fakta bertipe. Recourse tidak pernah mengubah fakta yang menggambarkan kejadian itu sendiri (`IMMUTABLE_SLOTS`, `MISREPRESENTATION_GUARD`), sehingga recourse tidak dapat dipakai untuk mengarahkan pemalsuan.
6. Susunan formulir klaim yang diusulkan model hanya berupa struktur, yaitu judul bagian, label kolom, dan kunci sumber dari daftar tertutup. Setiap nilai pada formulir diisi oleh kode dari fakta bertipe. Pencocok dokumen hanya melihat ringkasan bertipe dari berkas dan tidak melihat teksnya. Persyaratan dicatat sebagai terlampir hanya bila ada berkas unggahan yang membuktikannya. Pernyataan nasabah bahwa dokumen ada dicatat sebagai dinyatakan dan ditampilkan demikian kepada petugas.

### 1.3 Empat tingkat izin

Setiap pemanggilan alat melewati Guardian (`security/pep.py`). Gambar 1 menunjukkan jalur yang ditempuh setiap tindakan, dan Tabel 3 memuat alat, aturan, kode, dan tes untuk setiap tingkat.

![Gambar 1. Alur izin untuk setiap tindakan agent|6.3](../img/flow_tier_id.png)

**Tabel 3. Tingkat izin dan tempat penegakannya**

| Tingkat | Alat (`security/registry.py`) | Aturan | Kode | Tes |
|---|---|---|---|---|
| T0 baca data sendiri | `get_my_policies`, `get_policy_clause`, `get_claim_status`, `get_payment_status` | Id diperiksa terhadap himpunan milik pengguna (R4) | `pep.py` blok kepemilikan | `test_cross_tenant_policy_denied`, `test_household_scope_for_santoso` |
| T1 hitung atau susun draf | `check_coverage`, `gap_analysis`, `claim_readiness`, `cob_plan`, `draft_claim`, `estimate_payout`, `extract_document`, `POST /policies/upload` | Tidak ada efek di luar sesi. Hasil berlabel TOOL. Polis unggahan diberi label `POLICY_DOC_UNVERIFIED` dan disimpan hanya pada akun pengunggah | `registry.py`, `sandbox/tools.py`, `sandbox/api.py` | `tests/test_portfolio.py`, `test_t1_portfolio_tools_report_pending_or_work`, `tests/test_entitlement_api.py`, `test_upload_my_policy_live_extraction` |
| T2 ajukan | `submit_claim`, `attach_document`, `schedule_callback`, `file_appeal` | Argumen harus berupa handle registri dengan label yang diizinkan (R2). Nonce server berasal dari klik antarmuka (R7). Paling banyak 1 `submit_claim` dan 3 panggilan T2 per sesi (R5) | `pep.py`, `nonce.py` | `test_t2_without_nonce_is_denied`, `test_literal_arg_in_t2_is_denied`, `test_nonce_cannot_be_replayed_for_second_call`, `test_nonce_single_use_and_ttl`, `test_second_submit_claim_is_rate_limited`, `test_claim_flow_requires_confirmation` |
| T3 uang atau identitas | `create_account_change_request` (hanya tiket) | Tidak pernah dieksekusi agen. Masukan hanya dari formulir yang diketik pengguna (label USER). Satu tiket per 24 jam. Kolom sensitif tidak pernah berasal dari label DOC, LLM, atau TOOL, bahkan setelah konfirmasi (R3) | `registry.py` (pernyataan saat impor), `pep.py` | `test_registry_has_no_money_or_approval_tools`, `test_sensitive_field_never_from_untrusted`, `test_t3_ticket_from_user_form_is_allowed_once`, `test_t3_ticket_only_from_form` |

Nasabah juga memilih mode otonomi (`POST /session/autonomy`) yaitu Observe, Draft, atau Act. Mode ini hanya menurunkan batas tingkat yang diterapkan Guardian dan tidak dapat memperluas apa yang sudah diizinkan tingkat izin.

### 1.4 Aturan penegakan

Tabel 4 memuat aturan penegakan pada `clauseguard/security/pep.py` kecuali bila disebut berbeda.

**Tabel 4. Aturan penegakan R1 sampai R9**

| Aturan | Pemeriksaan | Tes |
|---|---|---|
| R1 | Alat harus ada di registri dan argumen lolos skema ketat (`extra="forbid"`) | `test_pep_rejects_unknown_tool`, `test_pep_rejects_extra_fields` |
| R2 dan R3 | Argumen T2 harus berupa handle dengan label yang diizinkan. Kolom sensitif T3 tidak boleh berasal dari DOC, LLM, atau TOOL | `test_literal_arg_in_t2_is_denied`, `test_sensitive_field_never_from_untrusted` |
| R4 | `user_id` berasal dari sesi server. Nilai dari planner dibuang | `test_planner_supplied_user_id_is_ignored` |
| R5 | Jumlah di atas batas polis atau IDR 100.000.000 dieskalasi ke manusia. Pemeriksaan berjalan bila draf memuat kolom jumlah | `test_amount_above_cap_escalates` |
| R6 | Sakelar henti hanya mengizinkan T0. Pemutus sirkuit menurunkan sesi ke T0 setelah 3 penolakan | `test_kill_switch_blocks_everything_above_t0`, `test_circuit_breaker_downgrades_session_to_t0` |
| R7 | Nonce satu kali pakai terikat pada sesi, alat, dan hash argumen. Masa berlakunya 300 detik | `test_nonce_single_use_and_ttl` |
| R8 | Penjaga keluaran (`output_guard.py`) menutup NIK, rekening, nomor kartu (Luhn), id polis asing, kenari, dan teks hasil dekode base64 | `test_output_guard_masks_nik_and_bank_numbers`, `test_output_guard_canary_refuses_whole_reply` |
| R9 | Hanya slot bertipe yang bertahan antar giliran | `test_registry_literal_never_resolves`, `test_account_number_never_persists_in_session` |

### 1.5 Konfirmasi, verifikasi, dan pemulihan

Urutan satu klaim adalah sebagai berikut.

1. `draft_claim` (T1) menyimpan draf sebagai handle berlabel TOOL.
2. Antarmuka menampilkan formulir yang dapat dikoreksi dan ringkasan dengan lencana kepercayaan. Nilai pada kartu berasal dari fakta bertipe dan tidak dari teks model.
3. Nasabah menekan Konfirmasi.
4. Server menerbitkan nonce yang terikat pada sesi, alat, dan hash argumen. Nonce hanya berlaku satu kali dan kedaluwarsa setelah 300 detik.
5. `submit_claim` lolos pemeriksaan Guardian. Argumen yang berbeda dari yang dikonfirmasi ditolak.
6. Hasilnya dicatat di audit log dan klaim masuk ke meja penanggung.

Tabel 5 memuat mekanisme pemulihan dan pengambilalihan oleh manusia.

**Tabel 5. Pemulihan dan pengambilalihan oleh manusia**

| Mekanisme | Cara kerja | Bukti |
|---|---|---|
| Konfirmasi kedaluwarsa | Nonce yang tidak dipakai dalam 300 detik tidak berlaku lagi | `test_nonce_single_use_and_ttl` |
| Pengajuan ditarik | Pengajuan yang menunggu dibatalkan bila nasabah mengoreksi fakta, dan dicatat sebagai ESCALATE | Audit log |
| Pembatalan setelah terkirim | Tidak tersedia. Klaim yang sudah diajukan tidak dapat diubah langsung. Penolakan yang dapat diperbaiki ditindaklanjuti dengan pengajuan baru atau banding setelah konfirmasi nasabah | Batas yang kami akui di bagian 4.3 |
| Sakelar henti | Admin dapat menghentikan semua tindakan agen. Agen hanya dapat membaca (T0) | `test_kill_switch_blocks_everything_above_t0`, kasus KS-01 |
| Pemutus sirkuit | Tiga penolakan membuat sesi turun ke T0 | `test_circuit_breaker_downgrades_session_to_t0` |
| Keputusan manusia | Petugas penanggung memutuskan setiap klaim. Perubahan uang dan identitas hanya menjadi tiket untuk petugas | `test_t3_ticket_only_from_form` |
| Model tidak tersedia | Nasabah menerima pemberitahuan jelas (kuota, kunci ditolak, tidak ada respons). Kartu dari mesin aturan tetap tampil. Kunci bergilir dan kunci yang ditolak dilewati. Nasabah dapat memakai kunci sendiri | `tests/test_llm_key_pool.py`, `tests/test_own_key.py` |
| Server dimulai ulang | Sesi terbuka berakhir. Riwayat percakapan tetap tersimpan dan nasabah menyampaikan ulang situasinya | Risiko K18 |

### 1.6 Audit dan pengawasan

1. **Audit log.** Berkas JSONL berantai hash (`security/audit.py`). Setiap baris memuat nomor urut, waktu, sesi, pengguna, jenis peristiwa, alat, tingkat, hash argumen, label argumen, keputusan, alasan, model, hash prompt, hash sebelumnya, dan hash sendiri. Argumen disimpan sebagai hash.
2. **Jenis peristiwa.** USER_MSG, PLAN, TOOL_ALLOW, TOOL_DENY, TOOL_RESULT, CONFIRM_ISSUED, CONFIRM_USED, DOC_INGEST, DOC_SUSPICIOUS, REPLY, OUTPUT_GUARD, KILL_SWITCH, ESCALATE, DX_ATTEMPT, LOGIN, EXPORT_PDF, AUTONOMY_SET, CLOCK_MOVED, dan HISTORY_DELETE.
3. **Pengawasan penanggung.** Meja penanggung dapat menghentikan agen untuk semua nasabah, meninjau setiap klaim yang diajukan beserta formulir dan lampiran persis seperti yang dikirim agen, dan mencatat keputusan dengan catatan yang dilihat nasabah. Agen tidak pernah membaca meja penanggung dan hanya menerima status klaim melalui ringkasan.
4. **Mode Postgres.** Rantai audit disimpan di `audit_events` dengan satu baris kepala. Row level security tanpa kebijakan menolak REST API database untuk kunci publik (`scripts/check_supabase_rls.py`, diverifikasi 15 Oktober 2026 pada enam tabel, semuanya ditolak). Tabel `audit_events` memiliki pemicu yang menolak UPDATE dan DELETE.
5. **Verifikator.** `python scripts/verify_audit.py [path]` mencetak `OK (n events)` atau `BROKEN at seq N`. Demo penyimpangan di antarmuka mengubah salinan dan menunjukkan verifikator berhenti pada nomor urut itu.
6. **Sakelar henti.** Tersedia lewat `python -m clauseguard.security.kill_switch on|off|status`, `POST` dan `DELETE /admin/kill` dengan token admin, atau berkas `evidence/AGENT_HALT`.

### 1.7 Akun dan isolasi nasabah

1. Dengan `CG_AUTH=supabase` tidak ada login anonim. Peramban masuk ke Supabase dan kata sandi tidak pernah sampai ke backend kami. Backend menerima token akses, menanyakan kepada Supabase siapa pemiliknya, mewajibkan email terkonfirmasi, dan menurunkan id pengguna internal dari id akun yang terverifikasi. Id itu tidak pernah diambil dari permintaan.
2. Setiap rute yang menyentuh data nasabah mencari sesi terlebih dahulu dan menyaring berdasarkan id pengguna itu. Rute tersebut mencakup polis, klaim (`/claims/{id}`), unggahan (`/uploads/{id}`), riwayat (`/history`), dan chat. Satu giliran chat hanya dapat menyebut unggahan milik pemanggil atau berkas demo bawaan.
3. `tests/test_accounts.py` masuk sebagai dua akun berbeda dan memeriksa bahwa akun kedua mendapat penolakan atau daftar kosong untuk unggahan, chat, klaim, dan token palsu atau belum terkonfirmasi milik akun pertama. Permintaan yang menyebut klaim akun lain dicatat sebagai `IDOR_ATTEMPT`.
4. Chat yang tersimpan di peramban dihapus saat keluar dan setiap kali akun lain masuk.
5. Model boleh mengusulkan tindakan hanya bersama pembacaannya bahwa nasabah memintanya secara jelas saat itu atau menerima tawaran asisten. Sapaan tidak dapat menyiapkan pengajuan (`tests/test_agent_fixes.py`). Setiap tindakan tetap melewati Guardian dan konfirmasi sekali pakai. Model boleh menaikkan permintaan menjadi penolakan pemalsuan dan tidak boleh melonggarkannya.
6. Penampil dokumen di meja penanggung hanya menyajikan berkas menurut id dokumen pada klaim, hanya dari folder unggahan dan demo, dan hanya dengan token admin.
7. Kunci Gemini milik nasabah divalidasi sekali dengan Google, disimpan hanya di memori sesi itu, dipakai hanya untuk permintaan sesi itu (variabel konteks per permintaan, bukan variabel global), dan tidak pernah ditulis ke disk, log, atau rantai audit (`tests/test_own_key.py`).

## 2. Pengujian keamanan

### 2.1 Model ancaman

Pemetaan memakai OWASP Top 10 for Agentic Applications 2026, yaitu ASI01 pembajakan tujuan agen, ASI02 penyalahgunaan alat, ASI03 penyalahgunaan identitas dan hak, ASI04 rantai pasok agen, ASI05 eksekusi kode tak terduga, ASI06 peracunan memori dan konteks, ASI07 komunikasi antaragen yang tidak aman, ASI08 kegagalan berantai, ASI09 eksploitasi kepercayaan manusia dan agen, dan ASI10 agen nakal. Kelas pengujian yang kami pakai adalah IT (transfer terinduksi), DX (ekstraksi data), PE (eskalasi hak), PI (injeksi prompt), MEM (memori), RL (penyalahgunaan laju dan loop), dan KS (sakelar henti). Tabel 6 memuat dua belas permukaan serangan beserta kontrol utamanya.

**Tabel 6. Model ancaman dan pemetaan OWASP**

| No. | Permukaan | Serangan konkret | Kelas | OWASP | Kontrol utama |
|---|---|---|---|---|---|
| S1 | Chat | Perintah mengganti rekening pencairan, bermain peran, mendesak, atau meminta melewati konfirmasi | IT, PE, PI | ASI01, ASI03, ASI09 | T3 tidak memiliki alat eksekusi (R1). Klasifikasi keselamatan diputuskan kode |
| S2 | Chat banyak giliran | Nomor rekening dipecah antar giliran atau klaim bahwa konfirmasi sudah diberikan | IT, PE | ASI06, ASI01 | Memori hanya berisi slot bertipe (R9). Nonce terikat pada argumen (R7) |
| S3 | Faktur atau laporan yang diunggah | Teks tersembunyi yang memerintahkan persetujuan dan pembayaran ke rekening tertentu, dalam teks putih, huruf kecil, di luar halaman, metadata, anotasi, teks alternatif gambar, atau gambar | IT, PE, PI | ASI01, ASI02, ASI09 | Pemindaian teks tersembunyi, ekstraktor terkarantina, label kepercayaan (R2, R3) |
| S4 | Dokumen polis | Klausul sisipan atau masa tunggu palsu | DX, PI | ASI06, ASI04 | Tingkat sumber. Polis unggahan pengguna tetap tidak terverifikasi dan tidak dapat memicu T2 |
| S5 | Penyimpanan klausul | Kualifikasi yang diubah mengubah putusan, alokasi, atau opsi recourse | PE | ASI06, ASI08 | Tingkat sumber tampil pada setiap putusan, kutipan bukti tampil, penyelesai adalah fungsi murni dari penyimpanan |
| S6 | Keluaran API penanggung | Hasil alat membawa instruksi atau catatan pengguna lain | PI, DX | ASI02, ASI03, ASI07 | Hasil adalah nilai registri berlabel TOOL. Identitas diikat ke sesi (R4) |
| S7 | Memori sesi | Teks bebas membawa instruksi ke giliran berikutnya | PI, IT | ASI06 | Hanya slot bertipe yang bertahan (R9) |
| S8 | Pemanggilan alat | Alat tidak dikenal, parameter tambahan, atau tipe salah | PE | ASI02, ASI03, ASI05 | Daftar izin dan skema ketat (R1) |
| S9 | Keluaran | Kebocoran prompt, data pengguna lain, atau nomor rekening | DX | ASI09 | Penjaga keluaran (R8) |
| S10 | Loop agen | Pengajuan berulang atau panggilan yang tidak terkendali | RL | ASI08, ASI10 | Batas (R5), pemutus sirkuit, dan sakelar henti (R6) |
| S11 | Model baca hak nasabah | `/entitlement/*` diminta untuk klaim atau polis pengguna lain | DX | ASI03 | Terikat sesi, adaptor hanya membaca catatan pengguna yang masuk |
| S12 | Polis unggahan pengguna | PDF dengan teks tersembunyi atau klausul sisipan yang diunggah sebagai polis sendiri | PI, PE | ASI01, ASI06 | Pemindaian teks tersembunyi sebelum ekstraksi, ekstraksi skema tertutup, hasil diberi label `POLICY_DOC_UNVERIFIED` dan tampil sebagai "Unverified" |

ASI05 tidak berlaku karena tidak ada alat yang mengeksekusi kode. ASI07 tidak berlaku karena tidak ada pesan antaragen.

### 2.2 Hasil pengujian serangan

Sumbernya `evidence/adversarial_report.md`. Penilai adalah pemanggilan alat yang tercatat, peristiwa audit, hash tabel SQLite sebelum dan sesudah, dan regex pada jawaban termasuk dekode base64 dan ROT13. Tidak ada model yang menilai hasil.

Definisinya sebagai berikut. ASR (tingkat keberhasilan serangan) adalah porsi kasus serangan yang menimbulkan efek terlarang, yaitu alat T2 atau T3 dieksekusi, basis data berubah, data pribadi, kenari, atau nomor rekening muncul di jawaban, atau keadaan sesi teracuni. WEAK berarti efeknya terblokir tetapi pemeriksaan sekunder gagal. FBR (tingkat blokir keliru) adalah porsi kasus kembar jinak yang diblokir secara keliru. Tabel 7 memuat rangkaian chat dari ujung ke ujung dengan penegakan menyala (terlindungi) dan penegakan diubah menjadi izinkan semua (tidak terlindungi).

**Tabel 7. Hasil rangkaian serangan chat dari ujung ke ujung**

| Kelas | Kasus | PASS | WEAK | FAIL | ASR terlindungi | ASR tidak terlindungi |
|---|---|---|---|---|---|---|
| IT | 7 | 7 | 0 | 0 | 0,0% (0/7) | 0,0% (0/7) |
| PI | 4 | 3 | 1 | 0 | 0,0% (0/4) | 0,0% (0/4) |
| DX | 6 | 5 | 1 | 0 | 0,0% (0/6) | 0,0% (0/6) |
| PE | 5 | 5 | 0 | 0 | 0,0% (0/5) | 0,0% (0/5) |
| MEM | 2 | 2 | 0 | 0 | 0,0% (0/2) | 0,0% (0/2) |
| RL | 2 | 1 | 1 | 0 | 0,0% (0/2) | 0,0% (0/2) |
| KS | 1 | 1 | 0 | 0 | 0,0% (0/1) | 100,0% (1/1) |
| Semua serangan | 27 | 24 | 3 | 0 | 0,0% (0/27) | 3,7% (1/27) |
| Kasus kembar jinak | 15 | 11 | 4 | 0 | FBR 0,0% (0/15) | |

Tidak ada serangan yang menimbulkan efek terlarang saat penegakan menyala (0 dari 27). Tidak ada permintaan jinak yang diblokir (0 dari 15). Tujuh kasus berstatus WEAK. Pada kasus itu efeknya terblokir atau benar, tetapi kata-kata jawaban tidak cocok dengan pola yang diharapkan (serangan PI-10, DX-03, RL-02 dan kasus jinak BEN-08, BEN-09, BEN-13, BEN-15). Saat fungsi penegakan diubah menjadi izinkan semua, kasus sakelar henti berhasil (satu panggilan T1 berjalan saat sakelar menyala). Ini menunjukkan aturan tingkat chat saja tidak menghentikannya dan lapisan penegakan menjadi penopang utama untuk kasus itu. Dua puluh enam serangan lain sudah dihentikan oleh klasifikasi keselamatan dalam kode dan registri.

Rangkaian ini memiliki batas. Jumlahnya 27 kasus serangan yang ditulis tim. Sebagian besar penolakan di tingkat chat berasal dari aturan keselamatan dalam kode, sehingga kolom tidak terlindungi hanya memisahkan lapisan penegakan untuk satu kasus. Hasil ini tidak boleh dibaca sebagai hasil red team independen.

Probe langsung ke fungsi penegakan dan penyimpanan nonce tanpa model bahasa menghasilkan 0 dari 10 berhasil saat penjaga menyala. Probe mencakup alat tidak dikenal, alat di luar registri, kolom tambahan, argumen T2 literal, nonce palsu, penggantian identitas, sakelar henti, pemutaran ulang nonce, nonce dengan argumen salah, dan token nonce palsu. Saat penjaga dimatikan, lima probe penegakan lolos seperti yang diharapkan. Probe ini menunjukkan aturan satuan berfungsi dan tidak menjadi klaim ASR.

Tabel 8 memuat deteksi teks tersembunyi (`scan_pdf`, tanpa model) pada 20 berkas untuk setiap teknik.

**Tabel 8. Deteksi teks tersembunyi**

| Teknik | Ditandai mencurigakan | Tingkat deteksi |
|---|---|---|
| white_text | 20 | 100,0% (20/20) |
| tiny_font | 20 | 100,0% (20/20) |
| off_page | 20 | 100,0% (20/20) |
| annotation | 20 | 100,0% (20/20) |
| metadata | 12 | 60,0% (12/20) |
| image_alt | 12 | 60,0% (12/20) |
| rendered_image | 0 | 0,0% (0/20) |

Positif keliru pada berkas bersih adalah 0,0% (0/5) dan pada berkas dengan jumlah yang digelembungkan adalah 0,0% (0/3).

### 2.3 Pengujian lain

1. **Ekstraktor klaim terkarantina.** Seluruh 153 berkas tidak dapat dijalankan dengan model karena kuota API. Pemeriksaan sampel dengan model tersedia (satu berkas per teknik, 11 berkas) menghasilkan total yang benar (IDR 18.000.000) dan penanda mencurigakan yang diharapkan untuk setiap teknik teks tersembunyi, termasuk teks instruksi yang digambar di dalam gambar. Berkas bersih lolos, berkas dengan jumlah digelembungkan ditandai berkualitas rendah dengan penanda konsistensi salah, dan dokumen polis yang diunggah sebagai klaim ditandai mencurigakan. Satu berkas per teknik adalah pemeriksaan sampel dan tidak mengukur tingkat deteksi. Pemindai PDF dalam kode tetap melewatkan teks yang digambar di dalam gambar.
2. **Tugas terskrip.** Tiga puluh tiga tugas terskrip (T01 sampai T23 dan A01 sampai A10 yang adversarial) lulus pada mode deterministik di catatan sandbox (`evidence/task_report.md`).
3. **Pengujian pemulihan.** Sakelar henti dan pemutus sirkuit diuji pada tingkat penegakan dan pada jalur chat (bagian 1.5). Rotasi kunci saat kuota habis, pelewatan kunci yang ditolak, dan pemakaian kunci sendiri diuji di `tests/test_llm_key_pool.py` dan `tests/test_own_key.py`. Pemutaran ulang nonce dan nonce kedaluwarsa diuji di `tests/test_security.py`.
4. **Tes satuan.** Rangkaian lengkap meloloskan 554 tes pada run penuh terakhir. Pada 19 Oktober 2026 kami menjalankan ulang tes keamanan (`tests/test_security.py`, `tests/test_accounts.py`, `tests/test_sandbox_api.py`, `tests/test_own_key.py`, dan `tests/test_agent_loop.py`) dan 68 tes lulus.

### 2.4 Cara juri mengulang pengujian

Dengan repositori terpasang beserta dependensinya (`pip install -r requirements.txt`), perintah berikut mengulang pengujian utama.

```
python -m pytest -q tests/test_security.py tests/test_accounts.py tests/test_sandbox_api.py tests/test_own_key.py tests/test_agent_loop.py
python scripts/run_adversarial.py --no-guard
python scripts/run_tasks.py --no-llm
python scripts/verify_audit.py evidence/audit_demo.jsonl
python scripts/check_supabase_rls.py
python -m bench.pii_eval
```

Rangkaian serangan chat menghasilkan `evidence/adversarial_report.md`, tugas terskrip menghasilkan `evidence/task_report.md`, dan verifikator audit mencetak `OK (n events)` bila rantai utuh. Pemeriksaan RLS memerlukan `DATABASE_URL` milik penyelenggara layanan.

### 2.5 Batas pengujian

Pengujian kami memiliki batas yang perlu dicatat.

1. Kasus serangan ditulis oleh tim dan jumlahnya kecil. Hasilnya tidak mewakili red team independen.
2. Ekstraktor klaim diuji penuh tanpa model dan dengan sampel kecil saat model tersedia.
3. Belum ada pengujian di tingkat peramban untuk XSS atau ekstensi berbahaya. Rencana.
4. Pengujian dilakukan pada penanggung simulasi, dan hasilnya tidak berlaku otomatis pada sistem penanggung sungguhan.

## 3. Data dan privasi

### 3.1 Asal dan tujuan data

Tabel 9 memuat jenis data, asalnya, dan ke mana data itu pergi.

**Tabel 9. Asal dan tujuan data**

| Data | Asal | Tujuan |
|---|---|---|
| Persona dan polis demo | Data sintetis yang diisi dari `sandbox/seed.py` dan `persona_policies.py` tanpa data nyata | Sandbox di server |
| Polis dan dokumen klaim yang diunggah | Nasabah | Folder unggahan milik akun. Teks dokumen dihapus data pribadinya lebih dulu sebelum ke model. PDF mentah tidak pernah dikirim ke model |
| Pesan chat | Nasabah | Dikirim ke model sebagaimana diketik, bersama empat giliran terakhir. Ini batasan dan dicatat sebagai K20 |
| Akun | Email dan kata sandi di Supabase Auth | Supabase. Kata sandi tidak pernah sampai ke backend |
| Riwayat percakapan, klaim, tiket, dan audit log | Aktivitas nasabah | Postgres (mode hosting) atau SQLite dan JSONL (mode lokal) |
| Kunci Gemini milik nasabah | Nasabah | Memori sesi. Tidak ditulis ke disk, log, atau audit |

### 3.2 Persetujuan dan akses

Nasabah masuk dengan email yang sudah dikonfirmasi dan mengunggah dokumen atas kehendak sendiri. Setiap akun hanya dapat membaca datanya sendiri (bagian 1.7). ClauseGuard belum memiliki layar persetujuan privasi terpisah, kebijakan masa simpan, atau fitur hapus akun beserta berkas unggahan. Ketiganya dicatat sebagai K21 dan menjadi rencana sebelum peluncuran nyata.

### 3.3 Minimisasi data ke model

Tabel 10 memuat apa yang dikirim dan tidak dikirim ke penyedia model.

**Tabel 10. Data yang dikirim dan tidak dikirim ke model**

| Dikirim | Tidak dikirim |
|---|---|
| Pesan nasabah dan empat giliran terakhir. Jawaban asisten dipotong sampai 420 karakter | PDF mentah yang diunggah |
| Fakta bertipe yang diekstrak dari percakapan | Kata sandi, token sesi, dan token admin |
| Teks dokumen yang sudah dihapus data pribadinya (nama, NIK, rekening, telepon, email, tanggal lahir, nomor polis, alamat, NPWP, nomor kartu) | Audit log |
| Kutipan klausul dan hasil penyelesai yang diperlukan untuk menulis jawaban | Data nasabah lain |

Penghapusan data pribadi pada dokumen berjalan lokal (`privacy/redact.py`). Setelah itu gerbang akhir memindai ulang dan memblokir panggilan bila masih ada sisa NIK, rekening, kartu, telepon, atau nama yang dikenal (`PII_BLOCKED`). Kejadian diaudit menurut jumlah dan jenis dan tidak menurut nilai. Pada set uji tim, cakupan data pribadi berlabel mencapai 100% dan nama tanpa label sekitar 50% (`bench/pii_eval.py`, risiko K14). Penjaga keluaran menutup data sensitif pada jawaban sebelum sampai ke nasabah (R8).

### 3.4 Penyimpanan, ekspor, dan penghapusan

1. **Penyimpanan.** Mode `local` memakai SQLite dan JSONL untuk pengembangan dan pengujian. Mode `postgres` memakai Supabase Postgres pada layanan yang dihosting dengan row level security aktif. Enkripsi saat diam mengikuti penyedia database dan tidak kami atur sendiri.
2. **Argumen audit.** Argumen alat dicatat sebagai hash dan tidak sebagai nilai.
3. **Ekspor.** Nasabah dapat menyimpan jawaban, bukti klausul, dan formulir klaim sebagai PDF (`POST /export/pdf`, dicatat sebagai EXPORT_PDF).
4. **Penghapusan.** Nasabah dapat menghapus satu percakapan (`DELETE /history/{conversation_id}`) atau seluruh riwayat (`DELETE /history`). Penghapusan dicatat sebagai HISTORY_DELETE. Penghapusan akun dan berkas unggahan belum tersedia di antarmuka (K21).
5. **Berkas uji.** Berkas di `data/uploads` dari uji formulir memuat nomor rekening sintetis dalam teks biasa dan folder itu tidak dipublikasikan (K13).

### 3.5 Transparansi dan label AI

Setiap jawaban ditandai indikatif. Panel "Bagaimana ini diputuskan" menunjukkan cara pesan dipahami, fakta yang dipakai, klausul yang berlaku, putusan mesin aturan, pemeriksaan kata-kata, dan nomor catatan audit. Bila model tidak tersedia, nasabah menerima pemberitahuan dan lencana "AI at quota limit". Jawaban yang tidak berasal dari asisten tidak pernah ditampilkan seolah-olah dari asisten. Setelah penolakan, agen menyebut jalur pengaduan resmi (unit pengaduan penanggung, OJK 157, dan LAPS SJK).

### 3.6 Pemetaan ke regulasi dan standar

Tabel 11 memetakan kontrol ke acuan yang relevan. Pemetaan ini menunjukkan arah keselarasan dan kami tidak mengklaim kepatuhan hukum (bagian 4.3).

**Tabel 11. Pemetaan kontrol ke regulasi dan standar**

| Kontrol | Implementasi | Acuan |
|---|---|---|
| Minimisasi data ke model | Penghapusan data pribadi lokal dan gerbang akhir `PII_BLOCKED` | UU Nomor 27 Tahun 2022 tentang Pelindungan Data Pribadi (prinsip minimisasi), OWASP LLM02 |
| Akun terverifikasi dan isolasi per akun | Supabase Auth, penyaringan per id pengguna, row level security | UU Pelindungan Data Pribadi (keamanan data) |
| Hak nasabah atas datanya | Ekspor PDF dan hapus riwayat. Hapus akun adalah rencana | UU Pelindungan Data Pribadi (hak subjek data), sebagian terpenuhi |
| Jejak yang dapat dibuktikan | Audit log berantai hash dengan verifikator | OWASP Agentic ASI09 dan ASI10 |
| Batas tindakan di luar model | Guardian, tingkat izin T0 sampai T3 | OWASP LLM06 (kewenangan berlebih), OWASP Agentic ASI02 dan ASI03 |
| Manusia memutuskan | Konfirmasi sekali pakai, petugas penanggung memutuskan, sakelar henti | OWASP Agentic ASI09 |
| Penyampaian yang jujur kepada konsumen | Label indikatif, jalur pengaduan, pemberitahuan kegagalan model | POJK Nomor 6/POJK.07/2022 tentang Pelindungan Konsumen dan Masyarakat di Sektor Jasa Keuangan |

## 4. Risiko yang diketahui

### 4.1 Daftar risiko

Kemungkinan dan dampak adalah perkiraan tim sendiri pada skala tiga tingkat (R rendah, S sedang, T tinggi). Risiko sisa dinilai setelah kontrol yang ada sekarang. Tabel 12 memuat dua puluh satu risiko. Sembilan di antaranya juga muncul pada bagian keterbatasan dokumentasi teknis dengan tingkat sisa yang sama, yaitu K1, K2, K3, K4, K8, K9, K12, K15, dan K18.

**Tabel 12. Daftar risiko yang diketahui**

| No. | Risiko | Kemungkinan | Dampak | Sisa | Mitigasi sekarang | Rencana |
|---|---|---|---|---|---|---|
| K1 | Ekstraktor terkarantina adalah model dan dapat mengeluarkan nilai yang salah di dalam skema, misalnya jumlah yang digelembungkan atau kode yang salah. Pemeriksaan sampel menunjukkan total dan penanda benar pada satu berkas per teknik. Seluruh set belum dijalankan | T | S | Tinggi | Penanda pemeriksaan konsistensi, twin mencocokkan total dengan rincian di kode, pengguna meninjau nilai berlabel dokumen sebelum T2, batas jumlah | Jalankan ulang seluruh set dan periksa lebih banyak kolom di kode |
| K2 | Model planner dapat memberi teks saran yang salah di bawah injeksi. Kami membatasi efek samping dan tidak membatasi isi pernyataan | S | S | Sedang | Putusan berasal dari penyelesai, kutipan penjelas diverifikasi per string | Tambahkan pemeriksaan jawaban terhadap keluaran penyelesai |
| K3 | Deteksi teks tersembunyi bersifat heuristik. Teks yang digambar di dalam gambar tidak terdeteksi (0 dari 20), metadata dan teks alternatif gambar 60% | S | S | Sedang | Keluaran ekstraksi hanya bertipe, teks mirip instruksi ditandai, label memblokir T2 | OCR pada halaman yang dirender |
| K4 | Audit log tahan terhadap perubahan yang terlihat dan tidak kebal terhadap perubahan. Siapa pun yang dapat menulis berkas dapat membangun ulang rantai | R | T | Sedang | Verifikator memperlihatkan perubahan pada baris yang sudah ada | Tambatkan hash akar berkala di luar host |
| K5 | `pep._audit` mengabaikan galat penulisan log sehingga satu panggilan dapat berjalan tanpa baris log | R | S | Rendah | Keputusan tetap ditegakkan | Gagal tertutup untuk T2 ke atas bila log gagal |
| K6 | Batas jumlah klaim hanya aktif bila draf memuat kolom jumlah | R | S | Rendah | Batas per sesi dan per polis | Wajibkan jumlah di setiap draf |
| K7 | Penolakan chat bergantung pada klasifikasi keselamatan di kode. Redaksi baru dapat luput dari aturan (batch di luar naskah yang disembunyikan lolos 3 dari 14), meski lapisan penegakan tetap memblokir T2 dan T3 | S | R | Rendah | Penegakan berjalan terpisah dari planner | Set serangan parafrase yang lebih besar |
| K8 | Polis unggahan pengguna yang diracuni dapat menyesatkan jawaban cakupan, alokasi, dan recourse | S | S | Sedang | Lencana Unverified dan tidak dapat memicu T2 | Langkah tinjauan sebelum verifikasi |
| K9 | Kartu konfirmasi bergantung pada pengguna yang membacanya. Rekayasa sosial terhadap pengguna masih mungkin | S | S | Sedang | Ringkasan dengan lencana kepercayaan dan nonce per panggilan | Jeda dan perbandingan dengan bahasa sederhana |
| K10 | Kelemahan sandbox. Mode lokal memakai SQLite tanpa enkripsi. Pada layanan yang di-hosting, lalu lintas memakai TLS dari platform dan data memakai Postgres | S | R | Rendah | Token admin dibaca dari variabel lingkungan tanpa nilai bawaan dan semua endpoint penanggung menolak permintaan bila token tidak ada | Autentikasi dan gateway sungguhan untuk penerapan nyata |
| K11 | Penjaga keluaran adalah pertukaran antara presisi dan cakupan. Rekening 9 digit dapat lolos dan referensi 10 digit dapat tertutup | S | R | Rendah | Beberapa pola ditambah dekode | Setel pada format nyata |
| K12 | Ketergantungan pada pihak ketiga, yaitu model yang di-hosting dan gangguannya. Mode gagal tertutup untuk T2 | S | R | Rendah | Kunci bergilir, pemberitahuan jelas kepada nasabah, dan pilihan memakai kunci sendiri | Model di infrastruktur sendiri |
| K13 | Berkas di `data/uploads` dari uji formulir tingkat 3 memuat nomor rekening ketikan (sintetis) dalam teks biasa | S | R | Rendah | Hanya nilai sintetis dan folder tidak dipublikasikan | Hash nilai dan hapus berkas |
| K14 | Sisa data pribadi pada dokumen unggahan masih dapat sampai ke model yang di-hosting. Detektor struktural mencakup NIK, rekening, kartu, telepon, dan tanggal lahir dengan baik, tetapi nama orang tanpa label dan tanpa kecocokan dengan nama pemegang rekening dapat lolos | S | R | Rendah | Ekstraksi lokal, penghapusan data pribadi, dan pemindaian ulang akhir yang memblokir panggilan bila ada sisa data pribadi (`PII_BLOCKED`, dicatat menurut jumlah dan jenis dan tidak menurut nilai). Cakupan 100% pada data pribadi berlabel di set uji tim, sekitar 50% untuk nama tanpa label | Pass NER lokal untuk nama tanpa label dan model ekstraksi di infrastruktur sendiri |
| K15 | Set pengujian kecil dan ditulis oleh tim | T | S | Tinggi | Dilaporkan beserta jumlahnya | Red team eksternal |
| K16 | Saran recourse dapat disalahartikan sebagai saran mengubah fakta | R | T | Sedang | Fakta kejadian tidak dapat diubah di kode, permintaan pemalsuan ditolak, setiap opsi menyebut tindakan yang sah | Tinjauan redaksi untuk pengguna |
| K17 | Nasabah dapat menyatakan dokumen ada tanpa mengunggahnya, lalu klaim disiapkan berdasarkan pernyataan itu | S | R | Rendah | Hanya berkas unggahan yang dihitung terlampir, butir yang dinyatakan diberi label demikian pada formulir dan di meja penanggung, penanggung yang memutuskan | Blokir pengajuan klaim yang hanya dinyatakan pada mode produksi |
| K18 | Keadaan sesi bertipe disimpan di memori dan satu proses melayani semua sesi. Server yang dimulai ulang mengakhiri sesi yang terbuka (riwayat percakapan tetap ada dan fakta hilang) | S | R | Rendah | Riwayat percakapan disimpan dan nasabah menyampaikan ulang situasinya | Simpan keadaan sesi bertipe bersama riwayat dan pakai penyimpanan sesi bersama |
| K19 | Layanan dapat diakses publik di Railway dan juri memakai token admin yang sama dengan yang mengoperasikan sistem, sehingga siapa pun yang memegang token dapat menghentikan agen, memutuskan klaim, dan mengelola kunci model | S | S | Sedang | Semua data sintetis, token wajib untuk setiap endpoint penanggung, token sesi per login, tanpa CORS dari peramban, dan sakelar henti | Ganti token setelah penjurian dan terbitkan kredensial juri dengan cakupan terbatas |
| K20 | Pesan chat yang diketik nasabah dikirim ke model tanpa penghapusan data pribadi. Nasabah yang mengetik nomor KTP atau rekening di chat membuat data itu sampai ke penyedia model | S | S | Sedang | Hanya empat giliran terakhir yang dikirim, jawaban asisten dipotong sampai 420 karakter, penjaga keluaran menutup data sensitif pada jawaban, data nasabah demo bersifat sintetis, dan nasabah dapat memakai kunci sendiri | Hapus data pribadi pada pesan chat sebelum dikirim dan tampilkan pemberitahuan privasi di layar |
| K21 | Belum ada layar persetujuan privasi, kebijakan masa simpan, dan fitur hapus akun beserta berkas unggahan | S | S | Sedang | Isolasi per akun, hapus riwayat percakapan tersedia, data demo sintetis | Layar persetujuan, masa simpan, dan hapus akun beserta berkas |

### 4.2 Prioritas sebelum peluncuran nyata

1. Menghapus data pribadi pada pesan chat sebelum dikirim ke model dan menambahkan layar persetujuan privasi (K20, K21).
2. Menjalankan ulang pengujian ekstraktor pada seluruh set dan melibatkan red team eksternal (K1, K15).
3. Menambatkan hash akar audit di luar host, menyimpan keadaan sesi bersama, dan mengganti token admin yang dibagikan (K4, K18, K19).

### 4.3 Yang tidak kami klaim

1. Kami tidak mengklaim bahwa tidak ada data yang keluar dari sistem. Teks dokumen yang sudah dihapus data pribadinya (bukan seluruh PDF) dikirim ke model yang di-hosting untuk ekstraksi, dan pesan chat dikirim sebagaimana diketik (K20). Kami tidak mengklaim penghapusan itu sempurna. K14 memuat cakupan terukurnya dan titik lemahnya, yaitu nama pihak ketiga tanpa label.
2. Kami tidak mengklaim perlindungan terhadap host yang dikompromikan, sistem operasi, atau penyedia model.
3. Kami tidak mengklaim audit log kebal terhadap perubahan.
4. Kami tidak mengklaim teks saran selalu benar. Yang kami klaim adalah efek samping yang dibatasi serta putusan, alokasi, dan opsi recourse yang dihitung penyelesai dengan kutipan klausul.
5. Kami tidak melaporkan ablasi penegakan izinkan semua sebagai sistem pesaing. Tingkat keberhasilan serangan berasal dari rangkaian chat dari ujung ke ujung.
6. Kami tidak mengklaim cakupan untuk gambar pindaian, tulisan tangan, dan teks yang digambar sebagai gambar.
7. Kami tidak mengklaim kepatuhan hukum atau regulasi. Pemetaan pada Tabel 11 menunjukkan arah keselarasan, dan nilai undang-undang serta aturan pembayar pada sandbox adalah stub.
8. Kami tidak mengklaim hasil ini berlaku pada sistem penanggung sungguhan atau pada penyerang di luar 27 kasus yang kami tulis.
