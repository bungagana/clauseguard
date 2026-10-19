# ClauseGuard: Dokumentasi Teknis

*Jelas di setiap klausul, yakin di setiap klaim.*

FinTechathon 2026 · International Track · Topik D: AI Insurance Assistant
Tim: Bunga Laelatul Muna, Izra, Wan Sabrina · Institut Teknologi Sepuluh Nopember, Indonesia
Demo langsung: https://clauseguard.up.railway.app · Kode sumber: https://github.com/bungagana/clauseguard

## 1. Problem & scope

### 1.1 Topik dan masalah

ClauseGuard menjawab Topik D, asisten asuransi berbasis AI. Banyak rumah tangga memegang beberapa polis sekaligus, misalnya BPJS Kesehatan, asuransi dari kantor, polis pribadi, dan perlindungan kecelakaan. Aturan yang menentukan sebuah klaim ada di dokumen polis yang panjang dan jarang dibaca. Aturan itu mencakup batas waktu pengajuan, masa tunggu, dokumen wajib, dan urutan pembayar. OJK melaporkan bahwa lebih dari separuh pengaduan asuransi di Indonesia menyangkut kesulitan klaim. Di Amerika Serikat, sekitar satu dari lima klaim in-network ditolak pada 2023 dan kurang dari 1% yang diajukan banding (KFF, 2025).

Lima kesalahan mahal terus berulang. Klaim diajukan setelah tenggat. Klaim diajukan di dalam masa tunggu. Klaim diajukan ke pembayar yang salah lebih dulu. Nasabah membayar dua kali untuk perlindungan yang tumpang tindih atau melewatkan manfaat yang bisa ditumpuk. Polis dibiarkan lapse di masa tenggang. Kelima kesalahan ini sebenarnya dapat dihitung dari dokumen milik nasabah sendiri.

### 1.2 Persona pengguna

| Persona | Profil | Polis yang dimiliki |
|---|---|---|
| Rizky, 24 tahun | Mahasiswa pascasarjana, sedang mengurus klaim rawat inap DBD | Santunan harian rumah sakit (Sompo), asuransi jiwa berjangka (premi menunggak), penyakit kritis, BPJS Kesehatan kelas 2 |
| Keluarga Santoso | Keluarga empat orang, kepala keluarga karyawan swasta | Asuransi kesehatan dan jiwa kelompok dari kantor, rider santunan harian keluarga, polis kesehatan pribadi istri, BPJS Kesehatan kelas 1 |
| Dewi, 29 tahun | Kurir ojek daring | Asuransi kecelakaan diri, perlindungan kecelakaan dari platform saat bertugas, BPJS Kesehatan kelas 3 (menunggak tiga bulan), Jasa Raharja |

Ketiga persona dan polisnya bersifat sintetis. Redaksi polisnya dimodelkan dari dokumen publik penanggung. Nasabah sungguhan juga dapat mendaftar, mengunggah PDF polisnya sendiri, dan langsung bertanya.

### 1.3 Task keuangan yang diselesaikan agent

1. **Memeriksa cakupan.** Untuk setiap polis, agent menentukan apakah kejadian ditanggung, berapa perkiraan manfaatnya, dan kapan batas pengajuannya, disertai kutipan klausul.
2. **Menentukan urutan pembayar.** Untuk satu tagihan rumah sakit, agent menghitung polis mana yang membayar lebih dulu dan berapa bagian masing-masing.
3. **Menyiapkan dan mengajukan klaim.** Agent membaca dokumen rumah sakit, mencocokkannya dengan daftar dokumen wajib, mengisi formulir klaim milik penanggung, lalu mengajukannya setelah nasabah menekan Konfirmasi.
4. **Menindaklanjuti keputusan.** Agent menyampaikan keputusan penanggung, menjelaskan apa yang perlu diperbaiki, dan memeriksa apakah penolakan punya dasar banding.
5. **Memantau tenggat dan status polis.** Agent mengingatkan batas pengajuan dan masa tenggang premi sebelum terlewat.
6. **Menutup celah perlindungan.** Agent merekomendasikan produk yang menutup celah terbesar sesuai anggaran bulanan.

### 1.4 Metrik keberhasilan

| Metrik | Definisi | Hasil |
|---|---|---|
| Penyelesaian tugas terskrip | Persentase tugas klaim yang lulus pemeriksaan otomatis atas putusan, jumlah, tenggat, kode penolakan, dan tindakan | 33 dari 33 (100%) |
| Akurasi cakupan | Putusan yang benar pada benchmark asuransi publik | 84,6% (n = 390) |
| Penolakan yang dikarang | Putusan ditolak padahal tidak ada klausul yang berlaku | 1,4% |
| Ketepatan klarifikasi | Bertanya saat jawaban akan berubah, diam saat tidak | 87% dan 100% |
| Klaim ujung ke ujung | Dokumen, formulir, konfirmasi, keputusan meja penanggung, dan kabar kembali ke chat | Berhasil, terekam beserta nomor audit |
| Kualitas percakapan | Giliran yang lulus dari 47 giliran bahasa gaul, salah ketik, koreksi, dan pengandaian | 42 dari 47 (89%) |
| Keamanan tindakan | Serangan yang berhasil menimbulkan efek | 0 dari 27 |

## 2. System architecture

### 2.1 Diagram komponen

![Gambar 1. Arsitektur ClauseGuard. Agen AI memahami dan menjelaskan, mesin aturan memutuskan, penjaga menegakkan izin, dan setiap langkah dicatat.](../img/architecture.png)

| Komponen | Peran |
|---|---|
| UI dan dialog | Aplikasi web untuk nasabah (chat, kartu putusan, formulir klaim, unggah dokumen) dan meja klaim untuk petugas penanggung |
| Orchestrator | Loop agent yang mengatur urutan perencanaan, pemeriksaan izin, pemanggilan alat, pengikatan fakta, mesin aturan, dan penyusunan jawaban untuk setiap giliran |
| LLM | Google Gemini, dipakai untuk memahami pesan, membaca dokumen, dan menyusun kalimat jawaban |
| Agen AI | Conversation Agent, Fact Agent, Document Reader Agent, Explainer Agent, dan Watchdog Agent |
| Tools dan API | 19 alat bertingkat izin (membaca polis, memeriksa cakupan, menyusun draf, mengajukan klaim, melampirkan dokumen, mengajukan banding, dan lainnya) yang memanggil API penanggung sandbox |
| Mesin aturan | Kode deterministik yang memutuskan cakupan, jumlah, tenggat, urutan pembayar, dan kesiapan klaim |
| Penjaga (Guardian) | Titik penegakan izin di dalam kode yang memeriksa setiap pemanggilan alat |
| Penyimpanan data | Postgres di Supabase untuk rantai audit, riwayat chat, klaim, dan tiket. Basis data sandbox untuk polis dan nasabah |
| Sandbox insurer | Layanan penanggung simulasi lengkap dengan meja klaim, tempat petugas memutuskan klaim yang diajukan agent |

### 2.2 Alur data

1. Nasabah mengirim pesan atau berkas melalui aplikasi web.
2. Berkas melewati pemindai teks tersembunyi. Data pribadi seperti NIK, nomor rekening, dan nomor telepon dihapus secara lokal.
3. Document Reader Agent mengubah isi berkas menjadi catatan bertipe, misalnya jenis dokumen, tanggal, total tagihan, dan diagnosis.
4. Polis nasabah tersedia sebagai kumpulan aturan bertipe yang setiap aturannya terhubung ke kalimat aslinya di polis.
5. Hasil mesin aturan dan jawaban disimpan di sesi nasabah. Riwayat chat, klaim, dan log audit disimpan di Postgres per akun.

### 2.3 Alur keputusan

1. Conversation Agent menentukan hubungan pesan dengan percakapan, yaitu situasi baru, koreksi, jawaban atas pertanyaan, pengandaian, atau pertanyaan umum.
2. Perencana menentukan maksud pesan dan alat yang diperlukan. Aturan keamanan diputuskan lebih dulu oleh kode.
3. Penjaga memeriksa setiap alat terhadap tingkat izin dan mode otonomi pilihan nasabah.
4. Fact Agent mengubah kalimat menjadi fakta bertipe. Mesin aturan menghitung putusan untuk setiap polis.
5. Bila satu fakta yang belum diketahui akan mengubah putusan, agent menanyakan fakta itu saja.
6. Explainer Agent menyusun jawaban. Setiap angka, tanggal, dan nomor diperiksa terhadap hasil mesin sebelum ditampilkan.
7. Tindakan yang mengirim sesuatu ke penanggung menunggu konfirmasi nasabah. Petugas penanggung memutuskan klaim, dan keputusannya kembali ke chat.

### 2.4 Stack teknologi, deployment, dan alasannya

| Lapisan | Teknologi | Alasan |
|---|---|---|
| Mesin aturan dan agent | Python, FastAPI, Pydantic | Skema bertipe yang ketat untuk aturan polis, fakta, dan keluaran model. Pydantic menolak keluaran model yang tidak sesuai skema |
| LLM | Google Gemini Flash Lite | Mendukung keluaran JSON terbatas skema, cepat, biaya rendah, dan memahami bahasa Indonesia sehari-hari |
| Optimasi | SciPy (MILP, HiGHS) | Pemilihan produk penutup celah sebagai program bilangan bulat yang hasilnya optimal dan dapat diperiksa |
| Aplikasi web | Next.js, TypeScript, Tailwind CSS | Antarmuka chat dengan kartu interaktif, satu basis kode untuk nasabah dan meja penanggung |
| Akun dan penyimpanan | Supabase Auth dan Postgres | Login email dengan konfirmasi, row-level security, dan rantai audit yang bertahan saat server dimulai ulang |
| Hosting | Railway, region Asia Tenggara | Web dan API sebagai dua layanan terpisah yang dekat dengan basis data, dengan penyebaran otomatis dari repositori |

## 3. Core algorithm description

### 3.1 Planning

Perencana bekerja dua lapis. Lapis pertama adalah aturan kode untuk klasifikasi yang menyangkut keamanan, seperti permintaan misrepresentasi, akses ke data nasabah lain, perubahan rekening, dan permintaan membuka isi sistem. Model tidak dapat mengubah klasifikasi ini. Lapis kedua adalah model yang membaca pesan dalam konteks percakapan. Model menentukan maksud, alat baca yang diperlukan, dan topik pertanyaan, misalnya dokumen, tenggat, jumlah, atau kemajuan klaim. Permintaan untuk bertindak hanya diterima bila model membaca permintaan yang jelas atau persetujuan atas tawaran agent.

### 3.2 Tool-calling

Setiap alat terdaftar dengan tingkat izin, tipe argumen, dan tipe hasil. Hasil alat disimpan sebagai handle bertipe dengan label kepercayaan. Alat tingkat 2 hanya menerima handle, sehingga teks bebas dari dokumen atau model tidak dapat menjadi argumen pengajuan. Bila beberapa polis dapat menerima klaim, agent bertanya polis mana yang diajukan lebih dulu, dengan satu tombol untuk setiap polis.

### 3.3 Memory

Agent memakai tiga jenis ingatan. Ingatan kerja sesi menyimpan fakta bertipe, tanggal, dokumen yang dibaca, dan formulir yang menunggu konfirmasi. Ingatan percakapan menyimpan empat pertukaran terakhir sebagai data untuk memahami rujukan seperti "yang itu" atau "polis yang satunya". Riwayat chat disimpan per akun di Postgres, sehingga dapat dibuka dari perangkat lain.

### 3.4 Retrieval

Pengambilan informasi polis memakai penyimpanan klausul bertipe. Setiap polis telah dikompilasi menjadi aturan seperti menanggung, mengecualikan, masa tunggu, batas pengajuan, membayar, dan dokumen wajib. Mesin aturan mengambil aturan yang relevan berdasarkan kejadian, penyebab, dan orang yang ditanggung. Cara ini dipilih karena putusan asuransi membutuhkan aturan yang tepat beserta angka dan rentang waktunya. Setiap aturan yang dipakai dapat ditunjukkan kalimat aslinya. Untuk diagnosis, agent memakai retrieval BM25 atas 74.879 deskripsi kode ICD-10, lalu model memilih satu kode dari daftar kandidat dan kode memverifikasi pilihan itu.

### 3.5 Model alokasi klaim

Untuk satu tagihan *B* dan beberapa polis, pembayar disusun berlapis menurut aturan koordinasi Indonesia. Jasa Raharja membayar lebih dulu untuk kecelakaan lalu lintas dengan dua kendaraan atau lebih. BPJS Kesehatan membayar bila rumah sakit adalah mitra dan kepesertaan aktif. Asuransi kantor membayar sebelum polis pribadi. Santunan harian dibayar sejajar karena dapat ditumpuk.

Polis *i* membayar *min(A_i, s_i − m_i)*. Di sini *s_i* adalah jumlah yang diajukan, *m_i* adalah bagian biaya peserta (deductible dan co-payment), dan *A_i* adalah batas pembayaran polis. Setiap pembayar hanya menerima sisa yang belum dibayar, sehingga total pembayaran tidak pernah melebihi tagihan. Di dalam satu lapisan, semua urutan pengajuan dievaluasi dan urutan dengan pemulihan terbesar dipilih.

### 3.6 Penilaian risiko klaim

Kembaran penilai klaim (adjudication twin) memeriksa setiap klausul yang dapat menolak klaim secara terpisah, lalu mendaftar semua alasan penolakan yang mungkin diajukan petugas. Dokumen diperiksa silang, misalnya tanggal terhadap jumlah hari rawat, kode diagnosis terhadap penyebab, dan total kuitansi terhadap rinciannya. Hasilnya adalah skor kesiapan klaim beserta alasan yang dapat diperbaiki. Bila klaim ditolak, mesin mencari perubahan sah terkecil yang membuat klaim ditanggung, misalnya menunggu tanggal tertentu, melengkapi dokumen, atau memakai polis lain. Fakta kejadian seperti penyebab, tanggal, dan diagnosis dikunci di kode sehingga tidak pernah diubah.

### 3.7 Prompt design

Setiap pemanggilan model memakai skema keluaran tertutup dengan suhu nol. Model mengisi pilihan dari daftar tetap, misalnya maksud pesan, hubungan pesan, atau satu polis dari daftar kandidat. Kode memvalidasi setiap keluaran sebelum dipakai. Isi pesan nasabah dan isi dokumen ditandai sebagai data dalam prompt, dan model diinstruksikan untuk mengabaikan perintah di dalamnya. Prompt perencana dan penilai hubungan pesan berisi contoh-contoh nyata (few-shot) dalam bahasa Indonesia dan Inggris. Penyusun jawaban menerima hasil mesin dan enam contoh jawaban. Model menulis catatan penalaran singkat, menyusun dua kandidat jawaban, lalu memilih yang terbaik.

### 3.8 Guardrail dan explainability

Pemeriksa jawaban memastikan setiap angka, tanggal, persentase, dan nomor polis dalam jawaban berasal dari hasil mesin. Bila kandidat pertama gagal, kandidat kedua diperiksa, lalu teks tetap dipakai. Kutipan klausul harus sama persis dengan teks polis. Setiap jawaban memiliki panel "How was this decided" yang menampilkan cara pesan dipahami, fakta yang dipakai, klausul yang berlaku, putusan mesin, hasil pemeriksaan kalimat, dan nomor catatan audit. Bila model tidak tersedia, nasabah diberi tahu dengan jelas dan dapat memakai kunci API miliknya sendiri.

### 3.9 Evaluasi

| Evaluasi | Dataset atau skenario | Baseline | Hasil |
|---|---|---|---|
| Tugas klaim | 33 tugas terskrip (20 fungsional, 10 adversarial, 3 rekomendasi) | Tidak ada | 33 dari 33 lulus |
| Akurasi cakupan | Benchmark publik asuransi jiwa, 10 kontrak, 580 label (CC-BY-4.0) | Model membaca seluruh kontrak (b0, b0cw) | 84,6% dengan 1,4% penolakan dikarang. Baseline b0cw 87,5% dengan 3,1% penolakan dikarang pada subset 112 item |
| Klarifikasi | 18 pesan, satu fakta dihapus per uji, dinilai oracle | Bertanya untuk setiap fakta yang hilang | Bertanya saat perlu 87%, diam saat tidak perlu 100% |
| Konsistensi parafrase | 20 skenario dengan tiga redaksi | Tidak ada | 20 dari 20 putusan identik |
| Urutan pembayar | 500 rumah tangga dengan 200 produk marketplace AS sungguhan | Klaim sesuai urutan kepemilikan, satu polis saja | Urutan kepemilikan tidak optimal pada 47,2% rumah tangga, selisih rata-rata USD 988 |
| Pemilihan produk | 100 rumah tangga, katalog campuran | Produk termurah, produk termahal | Menutup celah lebih besar pada 73 dan 79 dari 100 |
| Pengodean diagnosis | 76 baris diagnosis berlabel | Kamus alias | 92,2% kategori benar. Kamus alias 17,2% |
| Percakapan | 47 giliran naratif, gaul, salah ketik, koreksi, pengandaian | Versi prompt sebelumnya | 42 dari 47, naik dari 40 dari 47 |
| Biaya | 90 giliran tugas terskrip | Model membaca seluruh dokumen | 0,98 pemanggilan model per giliran, 17% token dibanding baseline |

**Ablation.**

| Komponen yang dilepas | Akibat |
|---|---|
| Penegakan izin di kode | Serangan yang berhasil naik dari 0 menjadi 1 dari 27 |
| Aturan hasil ekstraksi diganti aturan emas benchmark | Akurasi naik dari 84,6% menjadi 91,8%, sehingga selisih yang tersisa berasal dari pembacaan dokumen |
| Mesin aturan diganti jawaban model saja | Penolakan yang dikarang naik dari 1,4% menjadi 3,1% dan klausul penentu tidak dapat ditunjukkan |
| Klarifikasi berbasis sensitivitas putusan | Tanpanya agent menanyakan semua fakta yang hilang. Dengannya, 35 dari 35 kekosongan yang tidak relevan tidak ditanyakan |

## 4. Security design

### 4.1 Permission tier

| Tingkat | Jenis | Contoh aksi | Aturan |
|---|---|---|---|
| T0 | Otomatis | Membaca polis, status klaim, status premi, dan pengingat tenggat milik nasabah sendiri | Selalu dibatasi pada akun yang sedang masuk |
| T1 | Otomatis | Memeriksa cakupan, menghitung urutan pembayar, menyusun draf klaim, menyiapkan formulir, menyusun draf banding | Tanpa efek di luar sesi |
| T2 | Butuh konfirmasi | Mengajukan klaim, melampirkan dokumen ke klaim, mengajukan banding, menjadwalkan panggilan balik | Berjalan setelah nasabah menekan Konfirmasi. Server menerbitkan token sekali pakai yang terikat pada sesi, alat, dan argumen yang sama persis |
| T3 | Dilarang untuk agent | Mengubah rekening pencairan, mengubah ahli waris, memindahkan uang | Tidak ada alat yang menjalankannya. Agent membuka tiket untuk petugas penanggung, yang memverifikasi identitas melalui jalur terpisah |

Nasabah juga memilih mode otonomi. Mode Observe hanya menjawab. Mode Draft menyiapkan tanpa mengirim. Mode Act mengirim setelah konfirmasi.

### 4.2 Threat model

| Ancaman | Contoh | Kontrol | Hasil uji |
|---|---|---|---|
| Prompt injection | Instruksi tersembunyi di kuitansi rumah sakit, misalnya teks putih yang meminta persetujuan klaim | Pemindai teks tersembunyi, ekstraktor terisolasi tanpa alat, label tidak tepercaya pada teks dokumen, argumen T2 hanya berupa handle | 0 dari 27 serangan berhasil. Teks putih, huruf kecil, di luar halaman, dan anotasi terdeteksi 20 dari 20 |
| Data leakage | Meminta polis atau klaim nasabah lain, atau meminta isi sistem | Isolasi akun pada setiap rute, row-level security di basis data, penyaringan keluaran untuk nomor rekening dan identitas, penghapusan data pribadi sebelum dokumen dikirim ke model | Akun kedua mendapat penolakan atau daftar kosong untuk unggahan, chat, dan klaim akun pertama. Setiap percobaan dicatat di log audit |
| Unauthorized transaction | Mengajukan klaim tanpa konfirmasi, mengubah rekening dengan alasan darurat | Token konfirmasi sekali pakai, tidak ada alat T3, batas jumlah aksi per sesi, pemutus sirkuit, sakelar henti di meja penanggung | Serangan tanpa konfirmasi dan permintaan ubah rekening tidak menimbulkan efek |
| Hallucinated advice | Menyebut jumlah, tanggal, atau penolakan yang tidak ada di polis | Putusan dari mesin aturan, pemeriksa angka dan tanggal pada jawaban, kutipan klausul harus sama persis, label indikatif | 1,4% penolakan dikarang pada benchmark. Jawaban yang menyebut nilai di luar hasil mesin ditolak sebelum tampil |

### 4.3 Kontrol risiko

**Limit transaksi.** Batas jumlah klaim Rp 100.000.000 per pengajuan. Paling banyak tiga aksi T2 dan 60 pemanggilan alat per sesi. Satu tiket T3 per 24 jam. Sesi dihentikan otomatis setelah tiga penolakan izin berturut-turut.

**Audit log.** Setiap pesan, rencana, pemanggilan alat, putusan izin, dan jawaban dicatat dalam rantai hash. Setiap catatan memuat hash catatan sebelumnya, sehingga perubahan pada satu catatan terdeteksi saat verifikasi.

**Human in the loop.** Nasabah mengonfirmasi setiap pengajuan. Petugas penanggung memutuskan setiap klaim di meja klaim. Penanggung memegang sakelar henti yang menghentikan semua aksi agent untuk semua nasabah.

**Privasi data.** NIK, nomor rekening, nomor kartu, nomor telepon, tanggal lahir, dan nama orang dihapus secara lokal sebelum dokumen dikirim ke model. Bila masih ada sisa data pribadi, pemanggilan model diblokir. Nasabah masuk dengan email terkonfirmasi, dan data setiap akun terisolasi.

**Kepatuhan regulasi.** Setiap jawaban ditandai indikatif dan menyatakan bahwa ketentuan polis yang berlaku tetap menentukan. Setelah penolakan, agent menyampaikan jalur pengaduan resmi (unit pengaduan penanggung, Kontak OJK 157, dan LAPS SJK). Verifikasi identitas (KYC) untuk perubahan data sensitif dilakukan oleh penanggung melalui jalur terpisah. Agent tidak memindahkan dana, sehingga pemeriksaan AML berada di sisi penanggung.

Topik ini tidak menggunakan blockchain, sehingga key management, signing policy, dan transaction simulation untuk Topik F tidak berlaku.

## 5. Innovation & interaction

### 5.1 Perbedaan dengan solusi yang ada

| Kemampuan | Chatbot penanggung | Chatbot AI umum | Situs perbandingan polis | ClauseGuard |
|---|---|---|---|---|
| Membaca semua polis nasabah dari penanggung berbeda sekaligus | Hanya produk sendiri | Bila diunggah, tanpa aturan tetap | Tidak | Ya |
| Putusan cakupan dengan kutipan klausul penentu | Jawaban umum | Dari ingatan model | Tidak | Ya, dihitung mesin aturan |
| Urutan pembayar antar polis termasuk BPJS dan Jasa Raharja | Tidak | Tidak konsisten | Tidak | Ya |
| Mengisi formulir klaim milik penanggung dari dokumen | Formulir sendiri | Tidak | Tidak | Ya |
| Mengajukan klaim dengan konfirmasi dan menerima keputusan di chat | Sebagian | Tidak | Tidak | Ya |
| Memeriksa dasar banding atas penolakan | Tidak | Tidak terverifikasi | Tidak | Ya, dengan klausul |
| Batas tindakan yang ditegakkan kode | Tidak relevan | Tidak ada | Tidak relevan | Empat tingkat izin |

Inti pembaruannya adalah memperlakukan polis asuransi sebagai program aturan. Model bahasa memahami percakapan dan dokumen. Mesin aturan menghitung hak nasabah. Setiap jawaban dapat dibuktikan dengan klausul.

### 5.2 Desain interaksi

1. **Bahasa sehari-hari.** Nasabah menulis dalam bahasa Indonesia, Inggris, atau campuran, termasuk singkatan dan salah ketik. Agent membalas dalam bahasa yang sama.
2. **Satu pertanyaan saja.** Agent hanya bertanya bila jawabannya akan berubah, dengan tombol jawaban cepat.
3. **Kartu bukti.** Putusan per polis, kutipan klausul, urutan pembayar, kesiapan klaim, dan isi setiap dokumen tampil sebagai kartu. Untuk pertanyaan lanjutan, kartu dilipat agar percakapan tetap ringkas.
4. **Formulir yang dapat dikoreksi.** Formulir klaim tampil sebelum dikirim. Nasabah dapat mengubah kolom seperti nama rumah sakit atau tanggal, dan formulir dibangun ulang.
5. **Kartu konfirmasi.** Pengajuan memerlukan satu ketukan Konfirmasi yang menampilkan dokumen terlampir dan yang belum ada.
6. **Kabar proaktif.** Keputusan penanggung muncul di chat tanpa diminta, lengkap dengan penjelasan dan langkah berikutnya.
7. **Mode otonomi.** Sakelar Observe, Draft, dan Act selalu terlihat di bagian atas layar.

## 6. Limitations & known risks

Daftar ini konsisten dengan daftar risiko di Penilaian Keamanan Mandiri. Nomor K merujuk ke dokumen tersebut.

| No. | Keterbatasan atau risiko | Tingkat sisa | Penanganan saat ini |
|---|---|---|---|
| K1 | Ekstraktor adalah model dan dapat salah membaca nilai di dalam skema. Pada benchmark, selisih aturan hasil ekstraksi dengan aturan emas sebesar 7 poin | Tinggi | Pemeriksaan silang total dan rincian, label belum terverifikasi, nasabah meninjau nilai dari dokumen sebelum mengirim |
| K2 | Teks saran dapat keliru. Lapisan izin membatasi tindakan dan tidak memeriksa kebenaran saran | Sedang | Putusan dari mesin aturan, pemeriksa angka pada jawaban, label indikatif |
| K3 | Teks yang digambar di dalam gambar belum terdeteksi sebagai teks tersembunyi (0 dari 20) | Sedang | Keluaran ekstraktor bertipe, label tidak tepercaya memblokir T2 |
| K4 | Log audit dapat dibangun ulang oleh pihak yang memiliki akses tulis ke penyimpanannya | Sedang | Verifikasi rantai menunjukkan perubahan pada catatan yang ada |
| K8 | Polis yang diunggah nasabah dapat menyesatkan putusan bila isinya dimanipulasi | Sedang | Label belum terverifikasi, tidak dapat memicu T2 |
| K9 | Konfirmasi bergantung pada nasabah membaca kartunya | Sedang | Ringkasan dengan label kepercayaan dan token per pemanggilan |
| K12 | Ketergantungan pada layanan model yang di-hosting dan batas kuotanya | Rendah | Rotasi kunci, pemberitahuan yang jelas kepada nasabah, opsi kunci milik nasabah |
| K15 | Set uji kecil dan ditulis tim. Batch pertanyaan buta untuk mode tanpa model lulus 3 dari 14 | Tinggi | Setiap hasil dilaporkan beserta jumlah sampel |
| K18 | Ingatan kerja sesi berakhir saat server dimulai ulang | Rendah | Riwayat chat tersimpan, nasabah diberi tahu dan diminta menyampaikan ulang situasinya |

Keterbatasan cakupan lainnya:

- Benchmark publik hanya mencakup asuransi jiwa. Produk Indonesia diuji pada polis sandbox yang diverifikasi manual.
- Mesin aturan mencakup cakupan, pengecualian, periode, rider, dan pengakhiran. Sebanyak 24 dari 58 skenario benchmark (dividen, batas produk investasi, perencanaan warisan) berada di luar cakupan.
- Jumlah dan aturan pembayar BPJS Kesehatan dan Jasa Raharja dimodelkan dari regulasi publik dan ditandai untuk diverifikasi ke pembayar. Pengelompokan tarif INA-CBG belum diimplementasikan.
- Klaim yang sudah diajukan tidak dapat diubah langsung. Penolakan yang dapat diperbaiki ditindaklanjuti dengan pengajuan baru setelah konfirmasi nasabah.

## Referensi

- Mridul, Kapa, dan Seneviratne (2026). A benchmark for gap and overlap analysis of insurance contracts. arXiv:2604.10853.
- Debenedetti dkk. (2025). CaMeL: defeating prompt injections by design. arXiv:2503.18813.
- Wachter, Mittelstadt, dan Russell (2017). Ustun, Spangher, dan Liu (2019). Counterfactual explanations and algorithmic recourse.
- OWASP Top 10 for Agentic Applications (2026).
- KFF (2025). HealthCare.gov insurers denied nearly 1 in 5 in-network claims in 2023.
- OJK (2023). Kesulitan klaim menjadi pengaduan asuransi terbanyak.
