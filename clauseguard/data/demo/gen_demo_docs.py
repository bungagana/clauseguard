"""Demo claim documents for the critical-illness (ICD-10) scene.

Two hospital discharge summaries ("Resume Medis") for the Rizky persona, written the way
Indonesian hospitals actually write them: the diagnosis is a name, not a code. The system
must resolve the name through the diagnosis coder (clauseguard/icd10_coder.py; the curated
dictionary in clauseguard/icd10_lookup.py is only the offline fallback):

  resume_medis_rizky_ca_mammae.pdf  -> "Carcinoma mammae" -> C50, inside CI-CHUBB-05's covered range
  resume_medis_rizky_dbd.pdf        -> "Demam Berdarah Dengue" -> A91, not a covered critical illness

Deterministic output (fixed text, no timestamps). Run:  python data/demo/gen_demo_docs.py
"""
from __future__ import annotations

from pathlib import Path

import pymupdf as fitz

OUT = Path(__file__).resolve().parent

CASES = {
    "resume_medis_rizky_ca_mammae.pdf": {
        "admit": "2 Oktober 2026",
        "discharge": "9 Oktober 2026",
        "ward": "Onkologi",
        "diagnosis": "Carcinoma mammae dextra (kanker payudara), stadium IIA",
        "secondary": "-",
        "procedure": "Biopsi eksisi payudara kanan; pemeriksaan histopatologi",
        "findings": "Histopatologi (PA No. 2026/PA/4471): invasive ductal carcinoma, grade 2, "
                    "reseptor estrogen positif. Konfirmasi diagnosis oleh dokter spesialis bedah onkologi.",
        "plan": "Rujuk ke tim onkologi untuk kemoterapi adjuvan; kontrol poliklinik 14 hari.",
        "doctor": "dr. Andini Mahardika, Sp.B(K)Onk",
    },
    "resume_medis_rizky_dbd.pdf": {
        "admit": "25 September 2026",
        "discharge": "28 September 2026",
        "ward": "Penyakit Dalam",
        "diagnosis": "Demam Berdarah Dengue (DBD) derajat II",
        "secondary": "Trombositopenia",
        "procedure": "Rawat inap, terapi cairan intravena, pemantauan trombosit harian",
        "findings": "NS1 antigen positif; trombosit terendah 48.000/uL pada hari ke-2, membaik ke 132.000/uL saat pulang.",
        "plan": "Kontrol poliklinik 5 hari; kembali segera bila perdarahan atau demam berulang.",
        "doctor": "dr. Bagus Wicaksono, Sp.PD",
    },
}


def _build(name: str, c: dict[str, str]) -> None:
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    y = 60

    def line(text: str, size: int = 10, bold: bool = False, gap: int = 16) -> None:
        nonlocal y
        page.insert_text((56, y), text, fontsize=size, fontname="hebo" if bold else "helv")
        y += gap

    line("RS MOCK SILOAM SURABAYA", 14, True, 20)
    line("Jl. Raya Gubeng No. 70, Surabaya  -  Telp (031) 555-0100", 9, False, 24)
    line("RESUME MEDIS PASIEN RAWAT INAP", 12, True, 26)
    line(f"Nama pasien       : Rizky Pratama")
    line(f"Tanggal lahir     : 12 April 2002")
    line(f"No. rekam medis   : RM-26-091842")
    line(f"Ruang / bangsal   : {c['ward']}")
    line(f"Tanggal masuk     : {c['admit']}")
    line(f"Tanggal keluar    : {c['discharge']}", gap=24)
    line("Diagnosis utama", 10, True)
    line(f"  {c['diagnosis']}", gap=20)
    line("Diagnosis sekunder", 10, True)
    line(f"  {c['secondary']}", gap=20)
    line("Tindakan / prosedur", 10, True)
    line(f"  {c['procedure']}", gap=20)
    line("Hasil pemeriksaan penunjang", 10, True)
    for chunk in _wrap(c["findings"], 92):
        line(f"  {chunk}")
    y += 6
    line("Rencana tindak lanjut", 10, True)
    for chunk in _wrap(c["plan"], 92):
        line(f"  {chunk}")
    y += 30
    line(f"Dokter penanggung jawab: {c['doctor']}")
    line("Tanda tangan dan stempel rumah sakit", 9, False, 40)
    line("Dokumen ini dikeluarkan atas permintaan pasien untuk keperluan klaim asuransi.", 8)

    doc.save(OUT / name, deflate=True)
    doc.close()


def _wrap(text: str, width: int) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 > width:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        lines.append(cur)
    return lines


if __name__ == "__main__":
    for name, case in CASES.items():
        _build(name, case)
        print("wrote", OUT / name)
