# ClauseGuard — presentasi dek

Delapan salindia, di bawah sepuluh menit. Satu gagasan per salindia, satu kalimat teks, satu gambar. Angka-angka berasal dari `evidence/`; gambar-gambar berasal dari produk yang berjalan. `docs/deck/build_deck.py` membaca berkas ini dan menulis `docs/deck/ClauseGuard_deck.pptx`.

Format: `## Slide N: judul`, lalu `Line:` (satu kalimat ditampilkan berukuran besar), opsional `Image:` / `Image2:` (jalur relatif terhadap akar repositori), opsional `Chart: benchmark`, hingga tiga butir `- `, dan `Notes:` (diucapkan, paling banyak 60 kata).
## Slide 1: ClauseGuard
Line: Jelas di setiap klausul, yakin di setiap klaim.
Image: clauseguard-web/public/brand/logo-wordmark.png
- Bunga Laelatul Muna · Izra · Wan Sabrina — Institut Teknologi Sepuluh Nopember, Indonesia
- FinTechathon 2026 · International Track · Topic D
Notes: ClauseGuard adalah asisten asuransi yang membaca polis Anda sendiri, menyiapkan klaim dari dokumen Anda, mengirimkannya hanya setelah Anda mengonfirmasi, dan mengembalikan keputusan penanggung kepada Anda. Setiap jawaban merujuk pada kalimat polis yang menentukannya.

## Slide 2: Masalah
Line: Klaim gagal karena urusan administratif dan tenggat, bukan karena pertanggungan.
- Sebuah rumah tangga memegang tiga hingga empat polis, masing-masing berupa redaksional setebal 40 halaman dengan daftar dokumen dan batas waktu pengajuannya sendiri
- Orang-orang tidak tahu polis mana yang cair lebih dulu, berapa besarannya, atau apa yang harus dikirim dan kapan
- Chatbot menjawab dengan lancar — dan mengarang penolakan yang tidak ada di dalam polis
Notes: Kebanyakan orang tidak pernah membaca polis mereka. Ketika sesuatu terjadi, mereka menghadapi beberapa redaksional, beberapa daftar periksa dokumen, dan tenggat pengajuan. Asisten chat generik menjawab dengan percaya diri tetapi mengarang pengecualian. Masalahnya bukan memahami asuransi secara umum; melainkan bertindak secara benar pada polis Anda sendiri.

## Slide 3: Empat dokumen, satu kalimat, siap klaim
Line: Unggah dokumen rumah sakit Anda ke dalam chat; formulir klaim resmi penanggung akan muncul kembali dalam keadaan terisi.
Image: clauseguard/docs/deck/img/form_crop.png
Notes: Rizky melampirkan empat dokumen rumah sakit dan satu kalimat. Agen membacanya, mencocokkannya dengan daftar dokumen Sompo, mengambil tagihan dari faktur, dan menyusun formulir klaim resmi Sompo dari redaksional Sompo. Setiap kolom diisi dari fakta yang diketik; pelanggan melihat formulir sebelum ada yang dikirimkan.

## Slide 4: Setiap jawaban mengutip klausul
Line: Ditanggung, untuk besaran berapa, selambat-lambatnya kapan — beserta kalimat persis yang menentukannya.
Image: clauseguard-web/public/screens/focus-verdict.png
- Mesin aturan yang memutuskan; model hanya membaca, mengikat fakta, dan merumuskan balasan
- Satu pertanyaan hanya diajukan ketika satu fakta yang hilang dapat mengubah hasil
Notes: Keputusan bukanlah teks hasil bangkitan. Polis dikompilasi menjadi aturan bertipe, dan mesin deterministik menerapkannya. Balasan menunjukkan jumlah, tenggat pengajuan, dan klausul yang dikutip. Jika satu fakta yang hilang dapat membalikkan hasil, agen akan meminta fakta tersebut dan tidak yang lain.

## Slide 5: Ia bertindak, dan keputusan kembali
Line: Setelah satu kali ketukan, klaim tiba di meja penanggung; keputusan penyesuaian klaim kembali ke chat.
Image: clauseguard-web/public/screens/focus-insurer.png
Image2: clauseguard/docs/deck/img/decision_crop.png
Notes: Pengiriman memerlukan ketukan Konfirmasi yang terikat pada token server satu kali pakai. Klaim, formulir, dan lampiran mendarat di meja penanggung, sebuah sandbox dalam entri ini. Seseorang meninjau, memutuskan dengan catatan, dan keputusan muncul di chat pelanggan. Agen menyiapkan dan melaporkan; ia tidak pernah memutuskan klaim.

## Slide 6: Tidak dapat menyentuh dana Anda
Line: Izin ditegakkan dalam kode: baca, hitung, kirim setelah Konfirmasi — uang dan identitas, tidak pernah.
Image: clauseguard-web/public/screens/focus-refusal.png
- Sakelar Observasi / Draf / Aksi, sakelar henti di sisi penanggung, log audit berantai hash
- Dokumen yang diunggah adalah data: instruksi tersembunyi dideteksi dan diabaikan
Notes: Empat tingkat izin berada dalam kode, bukan dalam prompt. Mengubah akun pembayaran tidak memiliki alat sama sekali; agen membuka tiket untuk manusia. Penanggung dapat menghentikan agen untuk setiap pelanggan. Setiap langkah ditulis ke log yang tahan terhadap perusakan. Dalam rangkaian serangan kami, tidak satu pun dari 27 serangan yang berdampak.

## Slide 7: Terukur, dengan batasan
Line: Lebih sedikit penolakan rekaan dibandingkan model chat umum, diukur pada benchmark publik.
Chart: benchmark
- Akurasi 84,6 % pada 390 label benchmark; 1,4 % penolakan rekaan (model umum: 2,4 % hingga 26,6 %)
- 33 dari 33 klaim berskrip, 0 dari 27 serangan berhasil, 0 dari 15 permintaan jinak diblokir
Notes: Pada benchmark kontrak asuransi publik, ClauseGuard mencapai akurasi 84,6 persen dan merekayasa penolakan pada 1,4 persen kasus. Kami tidak mengklaim mengalahkan model frontier dalam hal akurasi; perbedaannya adalah jawaban dilacak ke klausul dan penolakan tidak direkayasa. Klaim berskrip dan rangkaian serangan lolos sepenuhnya.

## Slide 8: Apa yang nyata, apa selanjutnya
Line: Aplikasi web langsung, penanggung sandbox, data publik — dan daftar jujur mengenai apa yang belum dibangun.
- Nyata: enam redaksional penanggung, 30 ringkasan produk Indonesia, 834 paket CMS, pertanyaan konsumen, keputusan ombudsman
- Sandbox: meja penanggung dan tiga persona; tidak ada penanggung nyata yang menerima klaim
- Berikutnya: API penanggung nyata, status sesi yang bertahan setelah dimulai ulang, tim red team eksternal
- github.com/bungagana/clauseguard · clauseguard-red.vercel.app
Notes: Yang nyata adalah data publik dan produk yang berfungsi. Yang disimulasikan adalah penanggung: meja kami adalah sandbox, sehingga tidak ada klaim nyata yang diajukan. Langkah selanjutnya adalah API penanggung, sesi persisten, dan red team eksternal. Kode, pengujian, bukti, dan keterbatasan semuanya ada di dalam repositori. Terima kasih.
