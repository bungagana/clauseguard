"""Sample claim documents for the demo (synthetic hospital, synthetic patient Rizky Pratama).

Run: python data/demo/claim_docs/make_samples.py  -> writes four PDFs next to this file.
"""
from __future__ import annotations

from pathlib import Path

import pymupdf

HERE = Path(__file__).parent
HOSPITAL = "RS Sehat Sentosa, Jl. Merdeka 12, Surabaya"
PATIENT = "Patient: Rizky Pratama   DOB: 2002-03-14   MR No: 26-0931"
STAY = "Admission: 2026-09-25 (ER)   Discharge: 2026-09-28   Ward: Class 2   Diagnosis: A91 Dengue fever"

DOCS = {
    "01_invoice_receipt.pdf": [
        HOSPITAL, "INVOICE / KUITANSI No. INV-2026-0931   Date: 2026-09-28", PATIENT, STAY, "",
        "Room (3 nights x 500,000)              1,500,000",
        "Doctor visits (3 x 150,000)              450,000",
        "Laboratory (NS1, CBC x3)                 350,000",
        "Drugs and IV fluids                      250,000",
        "Administration                            50,000",
        "TOTAL                              IDR 2,600,000",
        "", "PAID IN FULL / LUNAS - 2026-09-28   Cashier: D. Pratiwi   (original receipt)",
    ],
    "02_medical_resume_inpatient.pdf": [
        HOSPITAL, "RESUME MEDIS RAWAT INAP / INPATIENT MEDICAL RESUME", PATIENT, STAY, "",
        "Chief complaint: fever 4 days, myalgia, petechiae.",
        "Findings: NS1 antigen positive, platelets 68,000/uL on day 2, haematocrit 46%.",
        "Treatment: IV crystalloids, paracetamol, platelet monitoring twice daily.",
        "Course: fever resolved day 3, platelets 142,000/uL at discharge.",
        "Discharge condition: improved. Follow-up: outpatient in 7 days.",
        "", "Attending physician: dr. A. Wijaya, Sp.PD   SIP 503/2021   Signed 2026-09-28",
    ],
    "03_prescription_copy.pdf": [
        HOSPITAL, "RESEP / PRESCRIPTION (copy)   Date: 2026-09-28", PATIENT, "",
        "R/ Paracetamol 500 mg tab No. XV    S 3 dd 1",
        "R/ Oral rehydration salts sachet No. X    S prn",
        "R/ Vitamin B complex tab No. X    S 1 dd 1",
        "", "dr. A. Wijaya, Sp.PD",
    ],
    "04_lab_results.pdf": [
        HOSPITAL, "LABORATORY REPORT / HASIL PEMERIKSAAN PENUNJANG", PATIENT, "",
        "2026-09-25  Dengue NS1 antigen: POSITIVE",
        "2026-09-25  Haemoglobin 14.8 g/dL   Haematocrit 46%   Platelets 95,000/uL   WBC 2,900/uL",
        "2026-09-26  Haematocrit 47%   Platelets 68,000/uL",
        "2026-09-28  Haematocrit 42%   Platelets 142,000/uL",
        "", "Validated by: dr. R. Santoso, Sp.PK",
    ],
}


def main() -> None:
    for name, lines in DOCS.items():
        doc = pymupdf.open()
        page = doc.new_page()
        y = 72
        for line in lines:
            page.insert_text((60, y), line, fontsize=10.5)
            y += 16
        doc.save(str(HERE / name))
        doc.close()
        print("wrote", name)


if __name__ == "__main__":
    main()
