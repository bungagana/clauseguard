"""Readable names of the typed document codes, in English and Indonesian."""
from __future__ import annotations

DOC_LABELS = {
    "CLAIM_FORM": "original claim form", "DOCTOR_STATEMENT": "doctor's statement / medical resume (original)",
    "ITEMISED_BILL": "itemised bill and receipts (original)", "ITEMISED_BILL_COPY_LEGALISED": "legalised copy of the itemised bill (copies accepted; the original stays with BPJS or the hospital)",
    "ITEMISED_BILL_ORIGINAL_OR_LEGALISED": "original itemised bill or a legalised copy", "DISCHARGE_SUMMARY": "discharge summary",
    "ID_CARD": "identity card (KTP) of the insured and claimant", "POLICY_NUMBER": "policy number", "BANK_ACCOUNT": "bank account details",
    "POLICE_REPORT": "police report (BAP)", "ACCIDENT_CHRONOLOGY": "written chronology of the accident", "JASA_RAHARJA_FORM": "Jasa Raharja claim form",
    "EMPLOYER_REPORT": "employer's accident report", "JKK_FORM": "BPJS Ketenagakerjaan JKK form", "DEATH_CERT": "death certificate (civil registry)",
    "BENEFICIARY_ID": "beneficiary's identity card", "RELATIONSHIP_PROOF": "proof of relationship to the insured", "PATHOLOGY_REPORT": "pathology / imaging reports",
    "SPECIALIST_CONFIRMATION": "specialist's confirmation of diagnosis", "LEGALISED_BILL_COPY": "legalised copy of the itemised bill (the original went to the first payer)",
    "COB_LETTER": "settlement / coordination-of-benefits letter from the first payer", "BPJS_CARD": "BPJS card", "REFERRAL_LETTER": "referral letter (or emergency note)",
    "EMPLOYEE_ID": "employee ID", "DRIVING_LICENCE_COPY": "copy of the driving licence", "APP_CLAIM": "claim submitted in the platform app", "TRIP_ID": "trip / order ID",
}

DOC_LABELS_ID = {
    "CLAIM_FORM": "formulir klaim asli", "CLAIM_FORM_INPATIENT": "formulir klaim rawat inap", "CLAIM_FORM_DEATH": "formulir klaim meninggal dunia",
    "DOCTOR_STATEMENT": "surat keterangan dokter / resume medis (asli)", "DOCTOR_STATEMENT_INPATIENT": "surat keterangan dokter rawat inap",
    "ITEMISED_BILL": "rincian tagihan dan kuitansi (asli)", "ITEMISED_BILL_ORIGINAL": "rincian tagihan asli",
    "ITEMISED_BILL_ORIGINAL_OR_LEGALISED": "rincian tagihan asli atau salinan yang dilegalisir", "RECEIPT_ORIGINAL_OR_LEGALISED": "kuitansi asli atau salinan yang dilegalisir",
    "RECEIPT_DETAILS": "rincian kuitansi", "MEDICAL_RESUME_INPATIENT": "resume medis rawat inap", "PRESCRIPTION_COPY": "salinan resep",
    "DIAGNOSTIC_RESULTS": "hasil pemeriksaan penunjang (lab/radiologi)", "MEDICAL_RESULTS_COPY": "salinan hasil pemeriksaan medis",
    "DISCHARGE_SUMMARY": "ringkasan pulang", "ID_CARD": "KTP tertanggung dan pengaju klaim", "ID_COPY": "salinan KTP", "EMPLOYEE_ID": "kartu karyawan",
    "BANK_ACCOUNT": "data rekening bank", "BANK_BOOK_COPY": "salinan buku tabungan", "POLICE_REPORT": "laporan polisi (BAP)",
    "ACCIDENT_CHRONOLOGY": "kronologi kecelakaan tertulis", "JASA_RAHARJA_FORM": "formulir klaim Jasa Raharja", "JASA_RAHARJA_CLAIM_FORM": "formulir klaim Jasa Raharja",
    "MEDICAL_BILL_ORIGINAL": "kuitansi biaya perawatan asli", "MEDICAL_REPORT": "laporan medis", "DRIVING_LICENSE_COPY": "salinan SIM",
    "BPJS_CARD_OR_JKN_APP": "kartu BPJS atau aplikasi Mobile JKN", "REFERRAL_LETTER_OR_ER_NOTE": "surat rujukan (atau keterangan IGD)", "SEP": "Surat Eligibilitas Peserta (SEP)",
    "COB_LETTER": "surat penyelesaian / koordinasi manfaat (COB) dari penanggung pertama", "COB_LETTER_FIRST_INSURER": "surat COB dari penanggung pertama",
    "LEGALISED_BILL_COPY": "salinan rincian tagihan yang dilegalisir (aslinya ke penanggung pertama)", "APP_CLAIM_FORM": "formulir klaim di aplikasi",
    "TRIP_LOG_SCREENSHOT": "tangkapan layar riwayat perjalanan", "PATHOLOGY_REPORT": "laporan patologi / pencitraan", "SPECIALIST_CONFIRMATION": "konfirmasi diagnosis dokter spesialis",
    "DEATH_CERT_ORIGINAL_OR_LEGALISED": "akta kematian asli atau yang dilegalisir", "POLICE_REPORT_IF_UNNATURAL": "laporan polisi (jika meninggal tidak wajar)",
}


def doc_label(code: str, lang: str = "en") -> str:
    if lang == "id" and code in DOC_LABELS_ID:
        return DOC_LABELS_ID[code]
    return DOC_LABELS.get(code, code.replace("_", " ").lower())
