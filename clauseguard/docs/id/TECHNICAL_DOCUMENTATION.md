# ClauseGuard: Dokumentasi Teknis

*Jelas di setiap klausul, yakin di setiap klaim.*

FinTechathon 2026 · International Track · Topik D: AI Insurance Assistant
Tim: Bunga Laelatul Muna, Izra, Wan Sabrina · Institut Teknologi Sepuluh Nopember, Indonesia
Demo langsung: https://clauseguard.up.railway.app · Kode sumber: https://github.com/bungagana/clauseguard

## 1. Ringkasan

ClauseGuard adalah asisten asuransi berbasis AI untuk pemegang polis. Nasabah menceritakan apa yang terjadi dengan kata-katanya sendiri, dalam bahasa Indonesia atau Inggris, dan ClauseGuard menjawab tiga pertanyaan dari polis milik nasabah itu sendiri: apakah ditanggung, berapa yang dibayar, dan kapan batas pengajuan klaimnya. Setiap jawaban mengutip klausul yang menentukannya. Setelah itu ClauseGuard membaca dokumen rumah sakit nasabah, menyiapkan formulir klaim milik penanggung, mengajukan klaim setelah nasabah mengonfirmasi, dan menyampaikan keputusan penanggung kembali ke chat beserta langkah berikutnya.

Rancangannya bertumpu pada satu prinsip: **model bahasa memahami dan menjelaskan, kode memutuskan dan bertindak.** Putusan cakupan, jumlah, dan tenggat berasal dari mesin aturan deterministik yang bekerja atas redaksi polis yang telah dikompilasi menjadi aturan bertipe. Tindakan berjalan di dalam empat tingkat izin yang ditegakkan oleh kode. Perubahan yang menyangkut uang dan identitas tidak pernah dijalankan oleh asisten.

| Ukuran | Hasil |
|---|---|
| Serangan yang berhasil mengubah sesuatu, dari 27 (penegakan izin aktif) | 0 |
| Akurasi pada benchmark asuransi publik (390 label) | 84,6% |
| Penolakan yang dikarang padahal tidak ada klausul yang berlaku | 1,4% |
| Tugas klaim terskrip yang lulus | 33 dari 33 |
| Tes otomatis yang lulus | 554 |

## 2. Masalah

Banyak rumah tangga memegang beberapa polis sekaligus: jaminan kesehatan nasional, asuransi dari kantor, polis pribadi, rider, dan perlindungan kecelakaan. Aturan yang menentukan sebuah klaim (batas pengajuan, masa tunggu, dokumen wajib, siapa yang membayar lebih dulu) berada di dokumen yang jarang dibaca nasabah. Di Indonesia, OJK melaporkan bahwa lebih dari separuh pengaduan asuransi menyangkut kesulitan klaim. Di Amerika Serikat, penanggung di marketplace menolak sekitar satu dari lima klaim in-network pada 2023, dan kurang dari 1% yang diajukan banding (KFF, 2025). Di Tiongkok dan Hong Kong, sengketa yang dipublikasikan berpusat pada definisi penyakit kritis yang ketat dan ketidakterbukaan informasi.

Chatbot umum menjawab pertanyaan ini dari ingatan dan dapat menyatakan aturan yang salah dengan yakin. Lima kesalahan mahal terus berulang, dan masing-masing sebenarnya adalah hitungan atas dokumen nasabah sendiri: mengajukan setelah tenggat, mengklaim di dalam masa tunggu, mengklaim ke penanggung yang salah lebih dulu, membayar dua kali untuk perlindungan yang tumpang tindih atau melewatkan manfaat yang bisa ditumpuk, serta membiarkan polis lapse di masa tenggang.

## 3. Apa yang dilakukan ClauseGuard

### 3.1 Fitur utama

**ClauseLens: memahami perlindungan Anda.** Nasabah bertanya dengan bahasa sehari-hari ("dirawat tiga hari karena DBD, bisa klaim?"). ClauseLens membaca semua polis nasabah sekaligus dan menjawab per polis: ditanggung atau tidak, perkiraan jumlahnya, dan hari terakhir pengajuan, disertai kutipan klausul penentunya kata per kata. Bila satu fakta yang belum diketahui akan mengubah jawaban, hanya fakta itu yang ditanyakan. Bila beberapa polis berlaku, ClauseLens menghitung siapa yang membayar lebih dulu dan berapa bagian masing-masing.

**ClaimFlow: mengurus klaim Anda.** Nasabah mengirim dokumen rumah sakit (kuitansi, resume medis, resep, hasil laboratorium). ClaimFlow menampilkan apa yang dibaca dari setiap berkas, mencocokkannya dengan daftar dokumen wajib milik penanggung, dan mengisi formulir klaim penanggung tersebut. Nasabah dapat mengoreksi kolom mana pun sebelum mengirim. Klaim baru diajukan setelah nasabah menekan Konfirmasi. Saat penanggung memutuskan, keputusan dan catatan petugas muncul di chat, beserta apa yang dapat diperbaiki atau ada tidaknya dasar banding.

**TrustLock: Anda tetap memegang kendali.** Nasabah memilih seberapa jauh asisten boleh bertindak (Observe, Draft, atau Act). Mengirim apa pun memerlukan konfirmasi sekali pakai yang tidak dapat dibuat oleh model. Perubahan rekening pencairan atau ahli waris hanya dilakukan oleh petugas penanggung. Instruksi tersembunyi di dalam berkas yang diunggah dideteksi dan diabaikan. Setiap langkah dicatat dalam log yang tahan manipulasi.

### 3.2 Fitur pendukung

| Fitur | Manfaat bagi nasabah |
|---|---|
| Deadline Tracker | Peringatan sebelum batas pengajuan klaim atau masa tenggang premi habis |
| Claim Simulator | Jawaban pengandaian ("kalau saya dirawat lima hari") tanpa memengaruhi klaim sungguhan |
| Unggah polis sendiri | PDF polis apa pun dibaca langsung dan bisa ditanyakan saat itu juga; ditandai belum terverifikasi sampai ditinjau |
| Pembaca dokumen | Ringkasan per berkas: jumlah, tanggal, diagnosis, dan persyaratan yang dipenuhi berkas itu |
| Bantuan banding | Memeriksa apakah penolakan bertentangan dengan polis dan menyusun surat banding yang mengutip klausulnya |
| Ekspor PDF | Jawaban, bukti, dan formulir klaim dalam bentuk dokumen |
| Dua bahasa | Membalas dalam bahasa yang dipakai nasabah, Indonesia atau Inggris |
| Akun dan riwayat | Masuk dengan email; polis, klaim, dan chat setiap nasabah tersimpan di akunnya |

### 3.3 Satu klaim, dari awal sampai akhir

1. Rizky, seorang mahasiswa pascasarjana, menulis: "Saya dirawat karena DBD mulai 25 September selama tiga hari."
2. ClauseLens menjawab: polis santunan harian menanggungnya, Rp 1.500.000, ajukan paling lambat 27 November, dengan kutipan Pasal Manfaat 1. Untuk jaminan kesehatan nasional, ia menanyakan satu hal: apakah rumah sakitnya mitra BPJS?
3. Rizky mengirim empat berkas rumah sakit. ClaimFlow menampilkan isi setiap berkas dan menyatakan seluruh dokumen wajib sudah lengkap.
4. Rizky meminta asisten mengajukan klaim. ClaimFlow menampilkan formulir klaim penanggung yang sudah terisi; Rizky menekan Konfirmasi.
5. Petugas di meja klaim penanggung menyetujui klaim dengan catatan. Keputusan itu muncul di chat Rizky tanpa perlu ditanyakan.

Alur ini direkam terhadap penanggung sandbox lengkap dengan nomor urut audit (bukti eksekusi, butir "claims desk run").

## 4. Arsitektur

![Gambar 1. Arsitektur ClauseGuard: agen AI memahami dan menjelaskan; mesin aturan memutuskan; penjaga menegakkan izin; setiap langkah dicatat.](../img/architecture.png)

| Komponen | Jenis | Tanggung jawab |
|---|---|---|
| Conversation Agent | AI | Membaca hubungan pesan dengan percakapan: situasi baru, koreksi, jawaban atas pertanyaan asisten, pengandaian, atau pertanyaan umum |
| Fact Agent | AI | Mengubah teks bebas menjadi fakta bertipe (tanggal, hari rawat, tagihan, penyebab) |
| Document Reader Agent | AI, terisolasi | Menghapus data pribadi secara lokal, lalu mengubah redaksi polis dan dokumen klaim menjadi catatan bertipe; tidak punya alat dan tidak melihat riwayat percakapan |
| Mesin aturan | Kode | Memutuskan cakupan, jumlah, tenggat, urutan pembayar, dan kesiapan klaim dari aturan bertipe |
| Penjaga (Guardian) | Kode | Menegakkan empat tingkat izin pada setiap pemanggilan alat |
| Explainer Agent | AI | Menyusun kalimat jawaban; setiap jumlah, tanggal, dan nomor diperiksa terhadap hasil mesin sebelum ditampilkan |
| Watchdog Agent | AI dan kode | Memantau tenggat dan keputusan klaim, dan memberi tahu nasabah sebelum uang hilang |
| Log audit | Kode | Catatan berantai hash atas setiap langkah, hanya ditulis oleh kode |

Setiap pemanggilan model bahasa dibatasi skema: model mengisi struktur tertutup (maksud dari daftar tetap, pilihan di antara kandidat yang diberikan, fakta dari kosakata tetap), dan kode memvalidasi hasilnya sebelum dipakai. Keluaran model tidak pernah menjadi argumen untuk pengajuan, dan tidak ada model di dalam mesin aturan.

## 5. Metode inti

### 5.1 Polis sebagai aturan bertipe

Setiap polis dikompilasi menjadi kumpulan aturan klausul: *menanggung*, *mengecualikan*, *pengecualian atas pengecualian*, *bersyarat*, *periode* (masa tunggu, masa tenggang, batas pengajuan, masa bertahan hidup), *membayar*, *mewajibkan dokumen*, *berakhir jika*. Setiap aturan membawa kualifikasi bertipe (jumlah, batas per hari, deductible, co-payment, rentang waktu, syarat) dan teks klausul asli beserta nomor bagiannya. Teks klausul ditampilkan kepada nasabah tetapi tidak pernah dipakai untuk memutuskan. Ekstraksi berjalan dua tahap (kerangka dokumen, lalu aturan per bagian) dengan suhu nol dan skema tertutup.

### 5.2 Putusan

Untuk satu polis dan fakta nasabah, mesin mengevaluasi aturan dalam urutan tetap: mencari aturan penanggung untuk kejadian itu; bila tidak ada dan tidak ada aturan yang mengatur kejadian itu, jawabannya *tidak diatur oleh polis ini* (mesin tidak pernah mengarang penolakan); kemudian pengecualian, syarat dan periode yang belum terpenuhi, serta pengakhiran; selain itu *ditanggung*, dengan jumlah yang dihitung dari aturan manfaat dan batasnya. Setiap langkah mencatat aturan yang berlaku, sehingga setiap jawaban dapat mengutip klausulnya.

**Hanya menanyakan yang mengubah jawaban.** Bila satu fakta belum diketahui, mesin menjalankan ulang putusan untuk setiap kemungkinan nilai fakta itu. Bila putusannya tidak berubah, asisten tidak bertanya. Bila berubah, asisten menanyakan fakta itu saja dan menjelaskan klausul yang membuatnya penting.

### 5.3 Siapa yang membayar lebih dulu

Untuk satu tagihan dan beberapa polis yang memenuhi syarat, pembayar disusun berlapis menurut aturan koordinasi yurisdiksi (untuk Indonesia: Jasa Raharja untuk kecelakaan lalu lintas, lalu jaminan kesehatan nasional di fasilitas mitra, lalu asuransi kantor sebelum polis pribadi; santunan harian tetap dibayar sejajar). Polis *i* membayar *min(batas, jumlah yang diajukan dikurangi bagian biaya peserta)*, dan setiap pembayar hanya menerima sisa yang belum dibayar, sehingga totalnya tidak pernah melebihi tagihan. Di dalam satu lapisan, setiap urutan pengajuan dievaluasi secara tepat dan urutan dengan pemulihan terbesar dipilih.

### 5.4 Memperbaiki penolakan

Bila putusannya penolakan, mesin mencari himpunan terkecil perubahan *yang sah* yang membuatnya ditanggung (menunggu sampai tanggal tertentu, melengkapi dokumen, memakai polis lain dalam portofolio, memilih rumah sakit mitra untuk perawatan berikutnya) dan mengembalikan pilihan terbaik dari sisi waktu, biaya, dan usaha. Fakta yang menggambarkan kejadian (penyebab, tanggal, diagnosis, SIM, mabuk) tidak pernah boleh diubah, sehingga pencarian ini tidak dapat dipakai untuk mengajari misrepresentasi. Kembaran penilai klaim (adjudication twin) mendaftar setiap alasan yang mungkin diajukan petugas, bukan hanya yang pertama, dan memberi skor kesiapan sebelum klaim diajukan.

### 5.5 Menutup celah perlindungan sesuai anggaran

Untuk celah perlindungan, program bilangan bulat campuran memilih produk yang menutup celah berbobot terbesar dalam anggaran bulanan nasabah, tanpa membeli perlindungan indemnitas yang tumpang tindih.

### 5.6 Memahami percakapan

Sebelum fakta dipakai, Conversation Agent mengklasifikasikan pesan terhadap situasi yang sudah terbentuk, memakai beberapa pertukaran terakhir untuk memahami rujukan seperti "yang itu" atau "polis yang satunya?". Koreksi hanya mengubah fakta yang dikoreksi; pengandaian dijawab sebagai pengandaian; situasi baru menghapus situasi sebelumnya. Perencana juga membaca apa yang ingin diketahui nasabah (dokumen, tenggat, jumlah, kemajuan klaim yang sudah diajukan), dan jawaban deterministik atas pertanyaan itu ditempatkan paling depan. Bila lebih dari satu polis dapat menerima klaim, asisten bertanya polis mana yang diajukan, bukan memilih sendiri. Permintaan bertindak hanya diterima bila model membaca permintaan eksplisit atau penerimaan atas tawaran; sapaan tidak pernah dapat menyiapkan pengajuan.

### 5.7 Menyusun jawaban

Explainer Agent hanya menerima hasil mesin dan contoh-contoh jawaban. Ia menulis dua kandidat jawaban; pemeriksa memastikan setiap angka, tanggal, dan nomor pada kandidat terpilih muncul di hasil mesin, dan beralih ke kandidat lain, lalu ke teks tetap, bila tidak. Kutipan klausul harus sama persis dengan polis. Bila model bahasa tidak tersedia, nasabah diberi tahu dengan jelas dan dapat memakai kuncinya sendiri; tidak ada teks berbasis aturan yang disajikan sebagai jawaban asisten.

## 6. Keamanan

Empat tingkat izin ditegakkan oleh kode pada setiap pemanggilan alat:

| Tingkat | Yang diizinkan | Cara pengendaliannya |
|---|---|---|
| T0 | Membaca data milik nasabah sendiri | Isolasi akun pada setiap permintaan |
| T1 | Menghitung, menyusun draf, menyiapkan formulir | Berjalan otomatis, tanpa efek di luar sesi |
| T2 | Mengajukan klaim, melampirkan dokumen, mengajukan banding, menjadwalkan panggilan balik | Hanya setelah nasabah menekan Konfirmasi; token server sekali pakai yang terikat pada argumen yang persis sama |
| T3 | Uang dan identitas (rekening pencairan, ahli waris) | Tidak ada alat yang menjalankannya; asisten membuka tiket untuk petugas penanggung |

Pengendalian lain: teks dari dokumen, alat, dan model diberi label tidak tepercaya dan tidak pernah dapat menjadi argumen T2 atau T3; berkas yang diunggah dipindai untuk instruksi tersembunyi (teks putih, huruf sangat kecil, teks di luar halaman, anotasi); data pribadi dihapus secara lokal sebelum dokumen mana pun dikirim ke model yang di-hosting; pemutus sirkuit menghentikan sesi setelah penolakan berulang; penanggung memegang sakelar henti yang menghentikan semua tindakan asisten untuk semua nasabah; nasabah masuk dengan akun email terkonfirmasi, dan satu akun tidak pernah dapat membaca polis, klaim, berkas, atau chat akun lain. Model ancaman, pemetaan OWASP, hasil pengujian, dan daftar risiko terdapat di Penilaian Keamanan Mandiri.

## 7. Data

| Sumber | Penggunaan |
|---|---|
| Enam redaksi polis publik (Sompo, Astra, Chubb, Great Eastern) dan 30 ringkasan produk Indonesia (RIPLAY) | Ekstraksi; polis sandbox mengutip klausul-klausul ini secara harfiah |
| Benchmark asuransi publik: 10 kontrak, 58 skenario, 580 label yang ditelusuri ke klausul (Mridul, Kapa dan Seneviratne, 2026, CC-BY-4.0) | Evaluasi akurasi |
| Produk marketplace Amerika Serikat (CMS Public Use Files, 2026, 834 produk) | Eksperimen pemilihan produk dan urutan pembayar |
| Daftar kode ICD-10-CM (domain publik, 74.879 kode) | Pemetaan diagnosis ke aturan penyakit kritis |
| InsuranceQA dan putusan UK Financial Ombudsman | Bahan uji ketahanan dan replay sengketa |

Tiga nasabah demo, klaimnya, dan penanggung sandbox bersifat sintetis. Skema wajib negara (BPJS Kesehatan, Jasa Raharja) dimodelkan dari regulasi publik. Jumlah manfaat pada polis sandbox disetel agar sesuai dengan contoh-contoh pengerjaan. Tidak ada data nasabah sungguhan yang dipakai.

## 8. Evaluasi

Semua hasil dapat direproduksi dari skrip yang tercantum di Indeks Bukti Eksekusi; setiap angka di bawah menyebut laporannya.

| Evaluasi | Hasil | Laporan |
|---|---|---|
| Tugas klaim terskrip (fungsional, adversarial, rekomendasi produk) | 33 dari 33 lulus | task report |
| Serangan melalui chat penuh (prompt injection, eskalasi hak akses, eksfiltrasi data, misrepresentasi) | 0 dari 27 berhasil; 0 dari 15 permintaan wajar diblokir | adversarial report |
| Serangan yang sama dengan penegakan izin dimatikan | 1 dari 27 berhasil | adversarial report |
| Benchmark publik, aturan hasil ekstraksi ditambah mesin (n = 390) | akurasi 84,6% [77,8; 90,0]; 1,4% penolakan dikarang | benchmark report |
| Sama, dengan aturan emas milik benchmark (n = 342) | 91,8%; selisihnya berasal dari pembacaan dokumen | benchmark report |
| Klarifikasi (bertanya hanya bila jawaban akan berubah) | bertanya saat perlu 87%; diam saat tidak perlu 100% | clarification report |
| Konsistensi parafrase (tiga redaksi per pertanyaan) | 20 dari 20 putusan identik | paraphrase report |
| Urutan pembayar dibanding mengklaim sesuai urutan kepemilikan (500 rumah tangga, produk AS sungguhan) | urutan kepemilikan tidak optimal pada 47,2% rumah tangga, rata-rata selisih USD 988 | allocation report |
| Pemilihan produk dibanding produk termurah (100 rumah tangga) | menutup celah lebih besar pada 73 dari 100 | plan selection report |
| Deteksi teks tersembunyi (20 berkas per teknik) | 20 dari 20 untuk teks putih, sangat kecil, di luar halaman, dan anotasi; 0 dari 20 untuk teks yang digambar di dalam gambar | adversarial report |
| Pengodean diagnosis (76 baris berlabel) | 92,2% kategori benar; 3 dari 76 kode salah, tidak ada yang masuk rentang penyakit kritis | diagnosis report |
| Kualitas percakapan (47 giliran: bahasa gaul, salah ketik, koreksi, pengandaian, obrolan ringan, serangan) | 42 dari 47 lulus | conversation report |
| Biaya | rata-rata 0,98 pemanggilan model per giliran chat | cost report |
| Tes otomatis | 554 lulus | test suite |

**Mengapa setiap komponen diperlukan.** Pada benchmark, jawaban yang hanya mengandalkan model lebih sering mengarang penolakan ketika tidak ada klausul yang berlaku (3,1%) dibanding mesin (1,4%), dan tidak dapat menunjukkan klausul mana yang menentukan. Tanpa lapisan izin, satu serangan berhasil; dengan lapisan itu, tidak ada. Bertanya hanya untuk fakta yang mengubah putusan membuat asisten tetap diam pada seluruh 35 kekosongan yang tidak relevan. Pengoptimal urutan pembayar memulihkan lebih banyak dibanding mengklaim sesuai urutan kepemilikan polis setiap kali ada deductible, co-payment, atau batas.

## 9. Implementasi dan penyebaran

| Lapisan | Teknologi |
|---|---|
| Mesin aturan, agen, API penanggung sandbox | Python, FastAPI, Pydantic |
| Model bahasa | Google Gemini (keluaran JSON terbatas skema, suhu nol) |
| Aplikasi web dan meja penanggung | Next.js, TypeScript, Tailwind CSS |
| Akun dan penyimpanan | Supabase Auth dan Postgres (rantai audit, riwayat chat, klaim), dengan row-level security |
| Hosting | Railway: layanan web dan layanan API, region Asia Tenggara |

Penanggung sandbox adalah layanan terpisah dengan meja klaimnya sendiri. Klaim yang diajukan asisten masuk ke sana beserta formulir yang sudah terisi dan berkas lampirannya; petugas memindahkannya melalui status diterima, ditinjau, disetujui, ditolak, atau dibayar, dengan catatan yang dikembalikan kepada nasabah.

## 10. Keterbatasan

- Ekstraktor adalah model bahasa dan dapat salah membaca suatu nilai di dalam skema; pada benchmark, cakupan ekstraksi per kontrak berkisar 0,62 sampai 1,00, dan selisih antara aturan hasil ekstraksi dan aturan emas sebesar 7 poin.
- Mesin mencakup pertanyaan cakupan, pengecualian, periode, rider, dan pengakhiran; 24 dari 58 skenario benchmark (dividen, batas produk investasi, perencanaan warisan) berada di luar cakupannya.
- Benchmark publik hanya mencakup asuransi jiwa; produk Indonesia diuji pada polis sandbox yang diverifikasi manual dan tugas yang ditulis tim. Batch pertanyaan buta untuk mode tanpa model lulus 3 dari 14.
- Jumlah dan aturan pembayar skema wajib negara dimodelkan dan ditandai "verifikasi ke pembayar"; pengelompokan tarif INA-CBG belum diimplementasikan.
- Teks yang digambar di dalam gambar belum terdeteksi sebagai teks tersembunyi.
- Lapisan izin membatasi apa yang dapat dilakukan asisten; lapisan ini tidak menjamin teks sarannya benar, karena itu setiap jawaban ditandai indikatif.
- Ingatan kerja asisten atas suatu percakapan berakhir saat server dimulai ulang; nasabah diberi tahu dan diminta menyampaikan ulang situasinya. Chat tersimpan dan klaim yang sudah diajukan tetap ada.

## 11. Cara menjalankan

```bash
git clone https://github.com/bungagana/clauseguard.git && cd clauseguard
cd clauseguard && pip install -r requirements.txt && python scripts/serve.py --fresh
cd ../clauseguard-web && npm install && npm run dev
cd ../clauseguard && python -m pytest -q
```

Tanpa kunci model, setiap langkah memakai jalur deterministiknya. Daftar lengkap perintah evaluasi terdapat di Indeks Bukti Eksekusi.

## 12. Referensi

- Mridul, Kapa dan Seneviratne (2026). A benchmark for gap and overlap analysis of insurance contracts. arXiv:2604.10853.
- Debenedetti dkk. (2025). CaMeL: defeating prompt injections by design. arXiv:2503.18813.
- Wachter, Mittelstadt dan Russell (2017); Ustun, Spangher dan Liu (2019). Counterfactual explanations and algorithmic recourse.
- OWASP Top 10 for Agentic Applications (2026).
- KFF (2025). HealthCare.gov insurers denied nearly 1 in 5 in-network claims in 2023.
- OJK (2023). Kesulitan klaim menjadi pengaduan asuransi terbanyak.
