"""Hand-authored, human-verified PolicyRecords for the three sandbox personas.

Every tuple is `POLICY_DOC_VERIFIED`. Where a product is modelled on a real public document
(Sompo/Roojai HCP, Astra HCP rider, Astra Flexi Life, Chubb MY Essential Plus PA) the
`evidence.text` is the verbatim clause from the public PDF in `data/policies/real/` and
`evidence.section` names the article. Group/individual mock products (Nusantara, Sehat
Mandiri, platform cover, BPJS, Jasa Raharja) carry wording written for the sandbox and are
marked `doc_id = "<id>-wording(mock)"`. Persona numbers are fixed sandbox values.

As of the 2026-10-11 pass over `data/real/riplay/` (30 downloaded Indonesian RIPLAY PDFs, see
`data/real/riplay/PROVENANCE.md`): GH-NUSA-GRP and HI-INDIV-S had their qualitative clauses
(exclusions, waiting period, COB, filing deadline, claim documents) replaced with verbatim
quotes from a real individual-hospitalisation RIPLAY used as a documented stand-in for the
group/individual product (no Indonesian insurer publishes a group-health or an individual
Sehat-Mandiri-style RIPLAY), while the benefit *amounts* that drive the deterministic
walkthrough scenario (room/day limit, per-case limit, annual cap, pre-existing window,
specified-disease sub-limit) remain sandbox-chosen and keep the `-wording(mock)` doc id on
those specific tuples -- see the per-function comments. HCP-SOMPO-01 and HCP-RIDER-B were
checked against their cited PDFs (`data/policies/real/roojai_hcp_en.pdf`,
`data/policies/real/astra_hcp.pdf`) and found already verbatim-real; no change was needed.
PLATFORM-ACC stays fully illustrative (see its own comment). BPJS-KES and JASA-RAHARJA stay
modelled on public regulatory sources, since RIPLAY is a private-insurer disclosure
requirement that does not apply to statutory schemes.

Modelling conventions (so the deterministic solver behaves as the wording intends):
- Pre-existing-condition exclusions are attached to the covered *event* with
  `applies_if diagnosis_before_effective IS_TRUE` (+ window where the wording has one).
- Accident/emergency exemptions to waiting periods are handled by the solver's WAITING rule;
  exemptions to exclusions are explicit EXCEPTS tuples.
- Licence / occupation requirements of PA policies are CONDITIONED_ON tuples so they apply
  to every benefit of that policy.
- `other_insurance`: STACKABLE for hospital-cash / PA income benefits, EXCESS for indemnity.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional

from ..schema import (
    Basis,
    ClauseTuple,
    Condition,
    Evidence,
    Op,
    PeriodKind,
    PolicyRecord,
    Qualifiers,
    Relation,
    Slot,
    SourceTier,
    TimeUnit,
    WindowFrom,
)

V = SourceTier.POLICY_DOC_VERIFIED
IDR = Decimal


def _t(pid: str, tid: str, rel: Relation, obj: str, q: Qualifiers, doc: str, section: str, text: str, lang: str = "en", head: Optional[str] = None) -> ClauseTuple:
    return ClauseTuple(
        id=tid, policy_id=pid, head=head or pid, relation=rel, object=obj, qualifiers=q,
        evidence=Evidence(doc_id=doc, section=section, text=text[:1200]), source_tier=V,
        extractor_version="hand-verified-1.0", language=lang,
    )


def _preexisting(pid: str, events: list[str], doc: str, section: str, text: str, lang: str = "en", window_months: Optional[int] = None) -> list[ClauseTuple]:
    q = Qualifiers(applies_if=[Condition(slot=Slot.DIAGNOSIS_BEFORE_EFFECTIVE, op=Op.IS_TRUE, note="pre-existing condition")])
    if window_months:
        q.window_len, q.window_unit, q.window_from = window_months, TimeUnit.MONTHS, WindowFrom.EFFECTIVE
    return [_t(pid, f"x_preexisting_{e.lower()}", Relation.EXCLUDES, e, q, doc, section, text, lang) for e in events]


# --------------------------------------------------------------------------- Rizky
def hcp_sompo_01() -> PolicyRecord:
    pid, doc = "HCP-SOMPO-01", "roojai_hcp_en"
    T = []
    T.append(_t(pid, "c_hosp_daily", Relation.COVERS, "HOSPITALIZATION",
                Qualifiers(per_day_limit=IDR(500000), currency="IDR", max_days_per_year=90, deductible_days=0, basis=Basis.FIXED_BENEFIT, other_insurance="STACKABLE",
                           formula="IDR 500,000 x days hospitalised (min 1x24h), max 90 days and 2 hospitalisations per policy year"),
                doc, "Benefits, Art. 1",
                "This Policy provide daily cash compensation to Participants as stated in the Policy Summary if during the Insurance period, the Participant is affected by an illness or has an accident and requires Hospitalization in the Hospital. For this benefit, it is valid for maximum 2 (two) events of Hospitalization and a maximum of 90 (Ninety) days of treatment during the policy period or the period listed in the Policy Summary. Participants are entitled to inpatient compensation benefits if they have received treatment for at least 1x24 (one time twenty-four) hours at the hospital."))
    T.append(_t(pid, "c_icu_daily", Relation.COVERS, "ICU",
                Qualifiers(per_day_limit=IDR(1000000), currency="IDR", max_days_per_year=20, basis=Basis.FIXED_BENEFIT, other_insurance="STACKABLE"),
                doc, "Benefits, Art. 3",
                "This Policy provide daily cash compensation to Participants as stated in the Policy Summary if during the Insurance period, the Participant is exposed to an illness or experiences a critical incident as a result of an Accident and requires treatment in the Intensive Care Unit (ICU / ICCU / HCU / PICU / NICU) room. For this benefit, the maximum 2 (two) two Hospitalizations are valid and a maximum of 20 (twenty) days of treatment during the policy period or the period listed in the Policy Summary."))
    T.append(_t(pid, "c_surgical", Relation.COVERS, "SURGERY",
                Qualifiers(amount=IDR(2500000), currency="IDR", multiplier_of_daily=5.0, basis=Basis.FIXED_BENEFIT, other_insurance="STACKABLE", formula="5 x daily benefit, once per policy year, inpatient surgery only"),
                doc, "Benefits, Art. 2",
                "This Policy provide cash compensation to Participants as stated in the Policy Summary if during the Insurance period, the Participant is exposed to a critical illness or injury due to an Accident and requires surgery or Hospital Operation. For this benefit, it is valid only for 1 (one) time during the policy period. This Surgical Fee compensation benefit applies if the Participant has undergone Inpatient treatment."))
    T.append(_t(pid, "p_waiting_30", Relation.HAS_PERIOD, "WAITING",
                Qualifiers(period_kind=PeriodKind.WAITING, waiting_days=30, window_from=WindowFrom.EFFECTIVE),
                doc, "Terms and Conditions, c",
                "This Policy applies a waiting period of 30 (thirty) calendar days from the beginning of the Insurance period. This waiting period provision does not apply if the Participant experiences an emergency that requires Hospitalization or Surgery."))
    T.append(_t(pid, "p_waiting_specified_12m", Relation.HAS_PERIOD, "WAITING_SPECIFIED",
                Qualifiers(period_kind=PeriodKind.WAITING_SPECIFIED, window_len=12, window_unit=TimeUnit.MONTHS, window_from=WindowFrom.EFFECTIVE,
                           diseases=["HERNIA", "CATARACT", "TONSILS", "HAEMORRHOIDS", "SINUSITIS", "KIDNEY_STONE", "GALLSTONE", "UTERINE_FIBROID", "THYROID"]),
                doc, "Policy Summary (specified diseases, 12 months)",
                "Treatment or Treatment related to Specific Diseases or existing Diseases related to Congenital Disorders found and or known after birth and or Hereditary Diseases, for example: Hernia, VSD, ASD, Debilitation, Embicil, Mongoloid, Cretinism, Thalassemia, Haemophillia, Epilepsy / Apoplexy, Hydrocele and others"))
    T.append(_t(pid, "p_filing_60d", Relation.HAS_PERIOD, "FILING_DEADLINE",
                Qualifiers(period_kind=PeriodKind.FILING_DEADLINE, deadline_days=60, from_event=WindowFrom.TREATMENT_END, late_effect="REJECT"),
                doc, "Claim Submission Procedure, c",
                "The submission claimed by the Participant is made in writing and must be received by the Insurer within 60 (sixty) days from the completion of treatment by completing the claim that has been provided by the Insurer. Claims submitted beyond that time period will be rejected by the Insurer;"))
    T.append(_t(pid, "p_freelook_14d", Relation.HAS_PERIOD, "FREE_LOOK",
                Qualifiers(period_kind=PeriodKind.FREE_LOOK, window_len=14, window_unit=TimeUnit.DAYS, window_from=WindowFrom.ISSUE),
                doc, "Terms and Conditions, k",
                "The Insured may terminate the Membership by submitting a written application to the Insurer, within 14 (fourteen) calendar days during the policy study period (Free Look Period)."))
    T.append(_t(pid, "d_other_insurance_stackable", Relation.DEFINES, "OTHER_INSURANCE",
                Qualifiers(other_insurance="STACKABLE"), doc, "Terms and Conditions, i",
                "The insured still gets reimbursed or receives this benefit, even though he already has other insurance."))
    T.append(_t(pid, "k_premium_paid", Relation.CONDITIONED_ON, "PREMIUM_PAID",
                Qualifiers(applies_if=[Condition(slot=Slot.PREMIUM_STATUS, op=Op.EQ, value="PAID", note="premium must be paid in full")]),
                doc, "Terms and Conditions, f",
                "The guarantee for benefits under this Policy applies if the Premium on the Policy and Membership has been paid in full."))
    T.extend(_preexisting(pid, ["HOSPITALIZATION", "ICU", "SURGERY"], doc, "Exclusions 1",
                          "Pre-existing Conditions and/or Diseases and/or Injuries (Pre-Existing Conditions) including Critical Ilness Pre-Exsiting Condition."))
    T.append(_t(pid, "x_war", Relation.EXCLUDES, "WAR", Qualifiers(), doc, "Exclusions 2",
                "Wounded and or sick due to war or active duty in the military or armed forces of a country or international agency, strikes, riots, riots (direct and indirect), rebellion and the like."))
    T.append(_t(pid, "x_aviation", Relation.EXCLUDES, "AVIATION", Qualifiers(applies_if=[Condition(slot=Slot.PILOT_ROLE, op=Op.NE, value="PASSENGER", note="scheduled commercial passenger exempt")]), doc, "Exclusions 3",
                "Boarding, disembarking from, being in or flying with an engine or non-engine means of air transportation, flying with chartered aircraft / military / police / helicopters, except when using commercial aircraft with scheduled flights. and a fixed flight path."))
    T.append(_t(pid, "x_suicide", Relation.EXCLUDES, "SUICIDE", Qualifiers(), doc, "Exclusions 6",
                "Suicide, self-injury, attempted suicide, whether sane or insane, intentionally involving oneself in a situation that endangers oneself"))
    T.append(_t(pid, "x_criminal", Relation.EXCLUDES, "CRIMINAL_ACT", Qualifiers(), doc, "Exclusions 7",
                "Performing an attempted unlawful, criminal, against lawful detention and being attacked for his provocation"))
    T.append(_t(pid, "x_intoxication", Relation.EXCLUDES, "INTOXICATION", Qualifiers(), doc, "Exclusions 8",
                "Treatment and or treatment of Diseases and or Injuries as a result of drug abuse, drug addiction, use and or consumption of alcohol, narcotics, anesthetics and other psychotropic drugs."))
    T.append(_t(pid, "x_hazardous", Relation.EXCLUDES, "HAZARDOUS_ACTIVITY", Qualifiers(), doc, "Exclusions 9",
                "Certain dangerous sports such as but not limited to Rock Climbing, Bungy Jumping, Hang Gliding, Car / Motorcycle / Bike / Speed Race with other motorized or non-motorized vehicles, Parachute / Parachuting, Boxing / Martial arts or physical contact sports others, Acrobatics, Diving, Hanging, Kite Flying / Hanging Kite, Rafting and all kinds of other risky sports."))
    T.append(_t(pid, "x_congenital", Relation.EXCLUDES, "CONGENITAL", Qualifiers(), doc, "Exclusions 13",
                "Treatment or Treatment related to Specific Diseases or existing Diseases related to Congenital Disorders found and or known after birth and or Hereditary Diseases, for example: Hernia, VSD, ASD, Debilitation, Embicil, Mongoloid, Cretinism, Thalassemia, Haemophillia, Epilepsy / Apoplexy, Hydrocele and others"))
    T.append(_t(pid, "r_docs_hosp", Relation.REQUIRES_DOCUMENT, "HOSPITALIZATION",
                Qualifiers(document_codes=["CLAIM_FORM", "RECEIPT_ORIGINAL_OR_LEGALISED", "RECEIPT_DETAILS", "MEDICAL_RESUME_INPATIENT", "PRESCRIPTION_COPY", "DIAGNOSTIC_RESULTS"]),
                doc, "Claim Document",
                "To file a claim, fill out the claim report form provided by the Insurer and submit it to the Insurer by attaching supporting documents for the claim, including: 1. Original or Legalized Receipt 2. Receipt details during treatment 3. Medical Resume from the Hospital filled in by the treating Doctor (Inpatient). 4. Copies of prescription medicine. 5. The results of reading diagnostic tests (Lab, X-ray, USG, and others)."))
    T.append(_t(pid, "d_sla", Relation.DEFINES, "INSURER_SLA",
                Qualifiers(formula="decision within 15 calendar days of complete documents; payment within 14 working days of written agreement"),
                doc, "Procedure for Settlement and Payment of Claims",
                "The Insurer is obliged to provide a written answer to the Insured regarding approval or rejection of the claim for benefits in this Policy within 15 (fifteen) calendar days from the receipt of complete support claims documents as long as no further medical verification is required. The insurer is then required to complete the payment of compensation and/or cash benefits within 14 (fourteen) working days from the date of written agreement and certainty regarding the amount of benefits to be paid."))
    return PolicyRecord(id=pid, doc_id=doc, insurer="PT Sompo Insurance Indonesia (via Roojai)", product_name="Sompo Health Insurance Hospital Care Plan (Hospital Cash Plan)",
                        product_type="hospital_cash", basis=Basis.FIXED_BENEFIT, effective_date=date(2026, 8, 20), issue_date=date(2026, 8, 20), expiry_date=date(2027, 8, 19),
                        status="active", grace_days=None, sum_assured=IDR(500000), currency="IDR", tuples=T, verified=True, extraction_coverage=1.0)


def tl_astra_07() -> PolicyRecord:
    pid, doc = "TL-ASTRA-07", "astra_flexi_life"
    T = []
    T.append(_t(pid, "c_death", Relation.COVERS, "DEATH",
                Qualifiers(pct_of_sum_assured=100.0, currency="IDR", basis=Basis.FIXED_BENEFIT, other_insurance="STACKABLE"),
                doc, "Manfaat Produk 1", "Manfaat Meninggal Dunia sebesar 100% Uang Pertanggungan akan dibayarkan apabila Tertanggung meninggal dunia.", "id"))
    T.append(_t(pid, "p_suicide_24m", Relation.HAS_PERIOD, "SUICIDE",
                Qualifiers(period_kind=PeriodKind.SUICIDE, window_len=24, window_unit=TimeUnit.MONTHS, window_from=WindowFrom.EFFECTIVE, resets_on_reinstatement=True, benefit_type="NONE"),
                doc, "Pengecualian 2",
                "Bunuh diri atau percobaan bunuh diri baik dalam keadaan sadar maupun tidak dalam waktu 2 tahun terhitung sejak Tanggal Berlakunya Polis atau Tanggal Pemulihan Polis (mana yang terjadi paling akhir).", "id"))
    T.append(_t(pid, "x_criminal", Relation.EXCLUDES, "CRIMINAL_ACT", Qualifiers(), doc, "Pengecualian 1",
                "Adanya suatu tindakan melanggar hukum atau tindakan kejahatan atau percobaan melakukan tindakan kejahatan yang secara langsung atau tidak langsung dilakukan oleh Pemegang Polis, Tertanggung dan/atau Penerima Manfaat", "id"))
    T.append(_t(pid, "p_grace_30d", Relation.HAS_PERIOD, "GRACE",
                Qualifiers(period_kind=PeriodKind.GRACE, window_len=30, window_unit=TimeUnit.DAYS, window_from=WindowFrom.PREMIUM_DUE),
                doc, "Risiko Produk 2 (masa leluasa 30 hari per polis)",
                "Risiko Polis Tidak Aktif (Lapse): Risiko yang berkaitan dengan kondisi dimana Polis menjadi tidak aktif (lapse) karena Pemegang Polis gagal membayar Premi tepat waktu sehingga Polis menjadi berakhir, oleh karena itu Penanggung dibebaskan dari kewajiban untuk membayarkan manfaat asuransi", "id"))
    T.append(_t(pid, "t_lapse", Relation.TERMINATES_IF, "LAPSE",
                Qualifiers(applies_if=[Condition(slot=Slot.PREMIUM_STATUS, op=Op.EQ, value="LAPSED")]),
                doc, "Risiko Produk 2",
                "Polis menjadi tidak aktif (lapse) karena Pemegang Polis gagal membayar Premi tepat waktu sehingga Polis menjadi berakhir, oleh karena itu Penanggung dibebaskan dari kewajiban untuk membayarkan manfaat asuransi dan Premi yang sudah dibayarkan (jika ada) tidak dapat", "id"))
    T.append(_t(pid, "p_filing_90d", Relation.HAS_PERIOD, "FILING_DEADLINE",
                Qualifiers(period_kind=PeriodKind.FILING_DEADLINE, deadline_days=90, from_event=WindowFrom.DEATH, late_effect="DISCRETIONARY"),
                doc, "Dokumen Pengajuan Klaim Wajib",
                "Penerima Manfaat wajib menyampaikan dokumen-dokumen klaim kepada Kami, selambat-lambatnya 90 hari sejak tanggal Tertanggung meninggal dunia. Kami berhak untuk menolak pengajuan klaim yang diajukan setelah lewatnya batas waktu tersebut.", "id"))
    T.append(_t(pid, "r_docs_death", Relation.REQUIRES_DOCUMENT, "DEATH",
                Qualifiers(document_codes=["CLAIM_FORM_DEATH", "DOCTOR_STATEMENT_DEATH", "ID_AND_RELATIONSHIP_PROOF", "DEATH_CERT_ORIGINAL_OR_LEGALISED", "BENEFICIARY_BANK_BOOK_COPY", "DISCLAIMER_DEATH_BENEFIT", "POLICE_REPORT_IF_UNNATURAL"]),
                doc, "Dokumen Pengajuan Klaim Wajib",
                "1. Asli formulir klaim meninggal dunia (Bagian 1 formulir klaim) yang telah diisi dengan jujur, benar dan lengkap dan telah ditandatangani oleh Penerima Manfaat; 2. Asli Surat Keterangan Dokter klaim meninggal dunia (Bagian 2 formulir klaim) yang telah diisi oleh Dokter yang memeriksa; 3. Fotokopi identitas dan dokumen pendukung hubungan antara Pemegang Polis, Tertanggung dan/atau Penerima Manfaat yang masih berlaku; 4. Asli atau legalisir Surat Kematian yang dikeluarkan oleh pihak yang berwenang; 5. Fotokopi halaman depan buku tabungan yang mencantumkan nomor rekening Penerima Manfaat; 6. Asli Surat Pernyataan Pembebasan Tuntutan Pembayaran Klaim Meninggal Dunia (Disclaimer Death Benefit); 7. Asli Berita Acara dari kepolisian atau legalisirnya yang dikeluarkan oleh instansi yang berwenang apabila meninggal karena Kecelakaan", "id"))
    T.append(_t(pid, "d_beneficiary", Relation.DEFINES, "BENEFICIARY", Qualifiers(formula="nominated beneficiary: Siti Rahayu (mother), 100%"),
                "TL-ASTRA-07-nomination(mock)", "Beneficiary nomination on file (sandbox record)",
                "Beneficiary on file: Siti Rahayu (mother), 100%. The nomination can only be changed through the insurer's verified change process, not in chat."))
    T.append(_t(pid, "d_payment_sla", Relation.DEFINES, "INSURER_SLA", Qualifiers(formula="payment within 30 calendar days of claim approval"),
                doc, "Cara Pengajuan Klaim 4", "Astra Life akan membayarkan Manfaat Asuransi selambat-lambatnya 30 hari kalender sejak klaim disetujui.", "id"))
    return PolicyRecord(id=pid, doc_id=doc, insurer="PT Asuransi Jiwa Astra", product_name="Flexi Life Protection (term life, yearly renewable to age 85)", product_type="term_life",
                        basis=Basis.FIXED_BENEFIT, effective_date=date(2025, 2, 1), issue_date=date(2025, 2, 1), expiry_date=date(2027, 1, 31), status="grace", grace_days=30,
                        sum_assured=IDR(500000000), currency="IDR", tuples=T, verified=True)


def bpjs_kes() -> PolicyRecord:
    pid, doc = "BPJS-KES", "BPJS-KES-wording(mock)"
    T = []
    T.append(_t(pid, "c_inpatient_partner", Relation.COVERS, "HOSPITALIZATION",
                Qualifiers(basis=Basis.INDEMNITY, other_insurance="EXCESS", formula="INA-CBG package tariff for the member's class at a partner facility (cashless; no reimbursement)",
                           applies_if=[Condition(slot=Slot.FACILITY_BPJS_PARTNER, op=Op.IS_TRUE, note="partner facility")]),
                doc, "Manfaat 1 (modelled)",
                "Inpatient care is guaranteed at a BPJS Kesehatan partner facility (FKRTL) according to the INA-CBG package tariff for the participant's class, on referral from the first-level facility or through the emergency unit. Services at non-partner facilities are not reimbursed except in an emergency."))
    T.append(_t(pid, "c_inpatient_emergency", Relation.COVERS, "HOSPITALIZATION",
                Qualifiers(basis=Basis.INDEMNITY, other_insurance="EXCESS", formula="emergency at any facility until stable, then transfer to partner facility",
                           applies_if=[Condition(slot=Slot.IS_EMERGENCY, op=Op.IS_TRUE, note="emergency exception")]),
                doc, "Manfaat 1 (modelled)",
                "In an emergency the participant may be treated at any facility, including a non-partner facility, until the condition is stable; the facility bills BPJS Kesehatan directly."))
    T.append(_t(pid, "c_outpatient_partner", Relation.COVERS, "OUTPATIENT",
                Qualifiers(basis=Basis.INDEMNITY, other_insurance="EXCESS", applies_if=[Condition(slot=Slot.FACILITY_BPJS_PARTNER, op=Op.IS_TRUE)]),
                doc, "Manfaat 2 (modelled)", "Outpatient care at the registered first-level facility (FKTP) and referred specialist care at partner facilities."))
    T.append(_t(pid, "k_premium_active", Relation.CONDITIONED_ON, "PREMIUM_STATUS",
                Qualifiers(applies_if=[Condition(slot=Slot.PREMIUM_STATUS, op=Op.EQ, value="PAID", note="membership inactive while contributions are in arrears")]),
                doc, "Kepesertaan (modelled)",
                "Membership status becomes inactive from the 1st of the month following a missed contribution. Benefits are suspended until all arrears are paid; after reactivation, inpatient care within 45 days is subject to a service fee."))
    T.append(_t(pid, "x_cosmetic", Relation.EXCLUDES, "COSMETIC", Qualifiers(), doc, "Pelayanan yang tidak dijamin (modelled)",
                "Cosmetic and aesthetic services, infertility treatment, orthodontics, and services that are not medically necessary are not guaranteed."))
    T.append(_t(pid, "d_cob_statutory", Relation.DEFINES, "OTHER_INSURANCE",
                Qualifiers(other_insurance="EXCESS", formula="traffic accidents: Jasa Raharja pays first up to its limit; work accidents: BPJS Ketenagakerjaan JKK for members"),
                doc, "Koordinasi Manfaat (modelled)",
                "For traffic accidents the Jasa Raharja guarantee is the first payer up to its limit and BPJS Kesehatan guarantees the excess. Work-related accidents of BPJS Ketenagakerjaan members are guaranteed by the JKK programme, not by BPJS Kesehatan."))
    T.append(_t(pid, "r_docs_inpatient", Relation.REQUIRES_DOCUMENT, "HOSPITALIZATION",
                Qualifiers(document_codes=["BPJS_CARD_OR_JKN_APP", "ID_COPY", "REFERRAL_LETTER_OR_ER_NOTE", "SEP"]),
                doc, "Prosedur (modelled)", "Show the JKN card or Mobile JKN, identity card and the referral letter (or emergency note) at admission; the facility issues the SEP (Surat Eligibilitas Peserta)."))
    return PolicyRecord(id=pid, doc_id=doc, insurer="BPJS Kesehatan (statutory, modelled)", product_name="Jaminan Kesehatan Nasional (JKN)", product_type="social_bpjs_kes",
                        basis=Basis.INDEMNITY, status="active", currency="IDR", tuples=T, verified=True)


# --------------------------------------------------------------------------- Santoso
def gh_nusa_grp() -> PolicyRecord:
    pid, doc = "GH-NUSA-GRP", "GH-NUSA-GRP-wording(mock)"
    # No Indonesian insurer publishes a RIPLAY for employer *group* health (RIPLAY is a retail
    # disclosure requirement); the closest available real document is Chubb's individual
    # hospitalisation RIPLAY (data/real/riplay/chubb_medical_pro.pdf). Wording for the
    # product-generic clauses below (exclusions, dental exception, filing deadline, claim
    # documents) is quoted verbatim from that PDF as a stand-in for the group wording. The
    # benefit *amounts* (room/day, per-case, annual cap) and the no-waiting-period-for-new-joiners
    # feature are sandbox-engineered to drive the walkthrough scenario and are not literally the
    # Chubb retail schedule, so those tuples keep the original "-wording(mock)" doc id.
    real_doc = "data/real/riplay/chubb_medical_pro.pdf"
    T = []
    T.append(_t(pid, "c_room", Relation.COVERS, "HOSPITALIZATION",
                Qualifiers(per_day_limit=IDR(1500000), currency="IDR", max_days_per_year=60, annual_cap=IDR(150000000), basis=Basis.INDEMNITY, other_insurance="EXCESS",
                           formula="room and board up to IDR 1,500,000/day, 60 days/year; other inpatient charges per PAYS clause; annual limit IDR 150,000,000 per insured person"),
                doc, "Schedule of Benefits, 1",
                "Room and board: actual charges up to IDR 1,500,000 per day, maximum 60 days per policy year per insured person. Other inpatient charges (drugs, laboratory, doctor visits): actual charges up to IDR 7,700,000 per case. Annual limit IDR 150,000,000 per insured person. Benefits are provided cashless at network N1 hospitals."))
    # a COVERS clause (not PAYS) so the COB inner-limit logic sees the per-case ceiling for non-room charges
    T.append(_t(pid, "pays_other_inpatient", Relation.COVERS, "HOSPITALIZATION",
                Qualifiers(per_case_limit=IDR(7700000), currency="IDR", basis=Basis.INDEMNITY, other_insurance="EXCESS", formula="other inpatient charges (drugs, laboratory, doctor visits) up to IDR 7,700,000 per case"),
                doc, "Schedule of Benefits, 1",
                "Other inpatient charges (drugs, laboratory, doctor visits): actual charges up to IDR 7,700,000 per case."))
    T.append(_t(pid, "c_surgery", Relation.COVERS, "SURGERY",
                Qualifiers(per_case_limit=IDR(25000000), currency="IDR", annual_cap=IDR(150000000), basis=Basis.INDEMNITY, other_insurance="EXCESS"),
                doc, "Schedule of Benefits, 2", "Surgical charges (surgeon, anaesthetist, operating theatre): actual charges up to IDR 25,000,000 per case."))
    T.append(_t(pid, "c_icu", Relation.COVERS, "ICU",
                Qualifiers(per_day_limit=IDR(3000000), currency="IDR", max_days_per_year=15, basis=Basis.INDEMNITY, other_insurance="EXCESS"),
                doc, "Schedule of Benefits, 3", "Intensive care unit: actual charges up to IDR 3,000,000 per day, maximum 15 days per policy year."))
    T.append(_t(pid, "d_no_waiting", Relation.DEFINES, "WAITING",
                Qualifiers(waiting_days=0, formula="no waiting period; pre-existing conditions covered for members enrolled within 30 days of eligibility"),
                doc, "General Conditions, 4",
                "No waiting period applies and pre-existing conditions are covered for employees and dependants enrolled within 30 days of becoming eligible."))
    T.append(_t(pid, "t_employment", Relation.TERMINATES_IF, "GROUP_TERMINATION",
                Qualifiers(applies_if=[Condition(slot=Slot.EMPLOYMENT_ACTIVE, op=Op.IS_FALSE, note="cover ends on exit from employment")]),
                doc, "General Conditions, 9",
                "Cover for an insured employee and his or her dependants terminates on the date the employee ceases to be employed by the Policyholder, or on the date the master policy terminates, whichever is earlier."))
    T.append(_t(pid, "d_other_insurance_excess", Relation.DEFINES, "OTHER_INSURANCE",
                Qualifiers(other_insurance="EXCESS"), doc, "General Conditions, 12",
                "If the insured person is entitled to indemnity under any other insurance or statutory scheme, this policy pays only the excess of the amount recoverable from that other source. The Company may require a settlement letter from the other insurer and legalised copies of the bills."))
    T.append(_t(pid, "x_cosmetic", Relation.EXCLUDES, "COSMETIC", Qualifiers(), real_doc, "Pengecualian B.m (Chubb Medical Pro)",
                "Perawatan yang berkaitan dengan kosmetik dan/atau estetika;", "id"))
    T.append(_t(pid, "x_dental", Relation.EXCLUDES, "DENTAL", Qualifiers(), doc, "Exclusions 5",
                "Dental treatment except treatment of sound natural teeth required as a result of an accident."))
    T.append(_t(pid, "e_dental_accident", Relation.EXCEPTS, "x_dental", Qualifiers(applies_if=[Condition(slot=Slot.IS_ACCIDENT, op=Op.IS_TRUE)]),
                doc, "Exclusions 5", "except treatment of sound natural teeth required as a result of an accident."))
    T.append(_t(pid, "x_suicide", Relation.EXCLUDES, "SUICIDE", Qualifiers(), real_doc, "Pengecualian A.1.b (Chubb Medical Pro)",
                "Upaya bunuh diri atau upaya apapun sejenisnya baik dalam keadaan sadar atau tidak sadar, kesepakatan untuk melakukan tindakan bunuh diri;", "id"))
    T.append(_t(pid, "p_filing_30d", Relation.HAS_PERIOD, "FILING_DEADLINE",
                Qualifiers(period_kind=PeriodKind.FILING_DEADLINE, deadline_days=30, from_event=WindowFrom.DISCHARGE, late_effect="DISCRETIONARY"),
                real_doc, "Prosedur Pengajuan Klaim Reimbursement I (Chubb Medical Pro)",
                "Batas waktu pengajuan klaim oleh Pemegang Polis kepada Penanggung adalah selambat-lambatnya 30 (tiga puluh) hari kalender sejak tanggal terjadinya Rawat Inap, Rawat Jalan, Rawat Gigi, Persalinan dan Penyakit kritis. Penanggung berhak menolak permintaan pembayaran Manfaat Asuransi apabila klaim diajukan di luar jangka waktu tersebut.", "id"))
    T.append(_t(pid, "r_docs_hosp", Relation.REQUIRES_DOCUMENT, "HOSPITALIZATION",
                Qualifiers(document_codes=["CLAIM_FORM", "ITEMISED_BILL_ORIGINAL", "MEDICAL_RESUME_INPATIENT", "EMPLOYEE_ID", "ID_COPY"]),
                real_doc, "Prosedur Pengajuan Klaim Reimbursement II (Chubb Medical Pro)",
                "Formulir Klaim Asuransi Kesehatan yang telah diisi dengan lengkap; Perincian biaya Perawatan di Rumah Sakit; Kuitansi asli/legalisir dari Rumah Sakit; Fotokopi seluruh hasil pemeriksaan medis yang telah dilakukan seperti hasil pemeriksaan laboratorium, radiologi, dan patologi; Fotokopi kartu identitas (KTP/SIM/Paspor) yang masih berlaku; Fotokopi Kartu Keluarga.", "id"))
    return PolicyRecord(id=pid, doc_id=real_doc, insurer="PT Asuransi Nusantara (mock; clauses from Chubb Medical Pro RIPLAY)", product_name="Nusantara Group Health (employer plan, cashless network N1)", product_type="group_health",
                        basis=Basis.INDEMNITY, effective_date=date(2026, 1, 1), issue_date=date(2026, 1, 1), expiry_date=date(2026, 12, 31), status="active", currency="IDR", tuples=T, verified=True)


def gl_nusa_grp() -> PolicyRecord:
    pid, doc = "GL-NUSA-GRP", "GL-NUSA-GRP-wording(mock)"
    T = []
    T.append(_t(pid, "c_death", Relation.COVERS, "DEATH",
                Qualifiers(amount=IDR(288000000), currency="IDR", basis=Basis.FIXED_BENEFIT, other_insurance="STACKABLE", formula="24 x monthly basic salary (IDR 12,000,000) = IDR 288,000,000"),
                doc, "Schedule, 1", "Death benefit: 24 times the insured employee's monthly basic salary, payable to the nominated beneficiary; in the absence of a nomination, to the employee's legal heirs (estate)."))
    T.append(_t(pid, "d_beneficiary_default", Relation.DEFINES, "BENEFICIARY",
                Qualifiers(formula="no nomination on file -> estate / legal heirs (probate delay)"),
                doc, "Schedule, 1", "in the absence of a nomination, to the employee's legal heirs (estate)."))
    T.append(_t(pid, "p_suicide_12m", Relation.HAS_PERIOD, "SUICIDE",
                Qualifiers(period_kind=PeriodKind.SUICIDE, window_len=12, window_unit=TimeUnit.MONTHS, window_from=WindowFrom.EFFECTIVE, benefit_type="NONE"),
                doc, "Exclusions 1", "Death by suicide within 12 months of the date the employee's cover commenced is excluded."))
    T.append(_t(pid, "t_employment", Relation.TERMINATES_IF, "GROUP_TERMINATION",
                Qualifiers(applies_if=[Condition(slot=Slot.EMPLOYMENT_ACTIVE, op=Op.IS_FALSE)]),
                doc, "General Conditions, 6", "Cover terminates on the date the employee ceases employment with the Policyholder. No conversion option applies."))
    T.append(_t(pid, "p_filing_90d", Relation.HAS_PERIOD, "FILING_DEADLINE",
                Qualifiers(period_kind=PeriodKind.FILING_DEADLINE, deadline_days=90, from_event=WindowFrom.DEATH, late_effect="DISCRETIONARY"),
                doc, "Claims", "Written notice of death with supporting documents must reach the Company within 90 days of the date of death; late claims may be rejected."))
    T.append(_t(pid, "r_docs_death", Relation.REQUIRES_DOCUMENT, "DEATH",
                Qualifiers(document_codes=["CLAIM_FORM_DEATH", "DEATH_CERT_ORIGINAL_OR_LEGALISED", "EMPLOYER_CONFIRMATION", "HEIR_ID_AND_RELATIONSHIP_PROOF", "POLICE_REPORT_IF_UNNATURAL"]),
                doc, "Claims", "Claim form countersigned by the employer, civil-registry death certificate, employer's confirmation of employment on the date of death, identity and relationship proof of the claimant, police report where death is unnatural."))
    return PolicyRecord(id=pid, doc_id=doc, insurer="PT Asuransi Nusantara (mock)", product_name="Nusantara Group Term Life (24 x salary)", product_type="group_life",
                        basis=Basis.FIXED_BENEFIT, effective_date=date(2026, 1, 1), issue_date=date(2026, 1, 1), expiry_date=date(2026, 12, 31), status="active",
                        sum_assured=IDR(288000000), currency="IDR", tuples=T, verified=True)


def hcp_rider_b() -> PolicyRecord:
    pid, doc = "HCP-RIDER-B", "astra_hcp"
    T = []
    T.append(_t(pid, "c_hosp_daily", Relation.COVERS, "HOSPITALIZATION",
                Qualifiers(per_day_limit=IDR(300000), currency="IDR", max_days_per_year=365, basis=Basis.FIXED_BENEFIT, other_insurance="STACKABLE",
                           formula="1 x daily cash (IDR 300,000) per day hospitalised for illness; 2 x for accident (see pays_hosp_accident)"),
                doc, "Manfaat 1.a / 1.d",
                "Kami akan membayar manfaat Asuransi Tambahan sebesar 1 kali Santunan Tunai Harian apabila Tertanggung menjalani Rawat Inap akibat Penyakit. Maksimum jumlah hari Rawat Inap yang ditanggung oleh Kami akibat Penyakit dan Kecelakaan atas Polis ini adalah 365 hari dalam 1 tahun Polis per Tertanggung.", "id"))
    T.append(_t(pid, "pays_hosp_accident", Relation.PAYS, "HOSPITALIZATION",
                Qualifiers(per_day_limit=IDR(600000), currency="IDR", multiplier_of_daily=2.0, applies_if=[Condition(slot=Slot.IS_ACCIDENT, op=Op.IS_TRUE)]),
                doc, "Manfaat 1.b", "Kami akan membayar manfaat Asuransi Tambahan sebesar 2 kali Santunan Tunai Harian apabila Tertanggung menjalani Rawat Inap akibat Kecelakaan.", "id"))
    T.append(_t(pid, "c_icu_daily", Relation.COVERS, "ICU",
                Qualifiers(per_day_limit=IDR(600000), currency="IDR", max_days_per_year=15, multiplier_of_daily=2.0, basis=Basis.FIXED_BENEFIT, other_insurance="STACKABLE"),
                doc, "Manfaat 2.a / 2.c",
                "Kami akan membayar manfaat Asuransi Tambahan sebesar 2 kali Santunan Tunai Harian apabila Tertanggung menjalani Rawat Inap ICU. Maksimum jumlah hari Rawat Inap ICU yang ditanggung oleh Kami akibat Penyakit dan Kecelakaan atas Polis ini adalah 15 hari dalam 1 tahun Polis per Tertanggung", "id"))
    T.append(_t(pid, "c_surgery", Relation.COVERS, "SURGERY",
                Qualifiers(amount=IDR(3000000), currency="IDR", multiplier_of_daily=10.0, basis=Basis.FIXED_BENEFIT, other_insurance="STACKABLE", formula="10 x daily cash for illness, 20 x for accident"),
                doc, "Manfaat 3.a / 3.b",
                "Kami akan membayar manfaat Asuransi Tambahan sebesar 10 kali Santunan Tunai Harian apabila Tertanggung menjalani Pembedahan akibat Penyakit. Kami akan membayar manfaat Asuransi Tambahan sebesar 20 kali Santunan Tunai Harian apabila Tertanggung menjalani Pembedahan akibat Kecelakaan.", "id"))
    T.append(_t(pid, "p_waiting_30", Relation.HAS_PERIOD, "WAITING",
                Qualifiers(period_kind=PeriodKind.WAITING, waiting_days=30, window_from=WindowFrom.EFFECTIVE),
                doc, "Pengecualian 3", "Jika Rawat Inap terjadi selama Masa Tunggu kecuali akibat Kecelakaan;", "id"))
    T.append(_t(pid, "p_specified_2y_5days", Relation.HAS_PERIOD, "WAITING_SPECIFIED",
                Qualifiers(period_kind=PeriodKind.WAITING_SPECIFIED, window_len=24, window_unit=TimeUnit.MONTHS, window_from=WindowFrom.EFFECTIVE, max_days_per_year=5, resets_on_reinstatement=True,
                           diseases=["DENGUE", "DHF", "TYPHOID", "HEPATITIS_A", "DIARRHOEA", "DYSPEPSIA", "GASTRITIS", "VIRAL_INFECTION", "URTI", "COMMON_COLD", "FEBRIS", "GERD", "IBS", "DEHYDRATION", "HEAD_TRAUMA"],
                           formula="listed diseases: max 5 days/year in the first 2 policy years (reduced benefit, not exclusion)"),
                doc, "Manfaat 1.e",
                "Khusus untuk Penyakit-penyakit yang disebutkan di bawah ini, manfaat Santunan Rawat Inap yang dibayarkan Penanggung adalah hanya maksimum 5 hari per tahun Polis per Tertanggung dalam 2 tahun pertama Polis sejak Tanggal Berlakunya Polis atau Tanggal Pemulihan Polis, manapun terjadi yang lebih akhir, yaitu: a. Dengue Fever b. Dengue Hemorrhagic Fever c. Typhoid Fever d. Hepatitis A e. Diare f. Dispepsia g. Gastritis h. Viral Infection i. URTI/ISPA j. Common Cold k. Febris l. GERD m. IBS (Irritable Bowel syndrome) n. Dehidrasi Ringan atau Sedang o. Cedera Kepala/Trauma Kapitis", "id"))
    T.extend(_preexisting(pid, ["HOSPITALIZATION", "ICU", "SURGERY"], doc, "Pengecualian 1",
                          "Kondisi Kesehatan Yang Sudah Ada Sebelumnya dalam 12 bulan pertama sejak Tanggal Berlakunya Asuransi Tambahan atau Tanggal Pemulihan Polis, manapun yang terjadi lebih akhir;", "id", window_months=12))
    T.append(_t(pid, "x_cosmetic", Relation.EXCLUDES, "COSMETIC", Qualifiers(), doc, "Pengecualian 4",
                "Perawatan atau bedah kosmetik, termasuk (namun tidak terbatas) pada kelopak mata ganda, jerawat, keloid, bekas luka, tanda lahir, kerontokan pada rambut, dan segala komplikasinya kecuali akibat Kecelakaan dalam jangka waktu 6 bulan terhitung sejak tanggal perawatan pertama", "id"))
    T.append(_t(pid, "x_intoxication", Relation.EXCLUDES, "INTOXICATION", Qualifiers(), doc, "Pengecualian 6",
                "Penggunaan obat-obatan, narkotika, dan/atau bahan-bahan terlarang lainnya, minuman beralkohol dan/atau minuman keras lainnya, keracunan nikotin termasuk untuk tujuan rehabilitasi;", "id"))
    T.append(_t(pid, "x_hazardous", Relation.EXCLUDES, "HAZARDOUS_ACTIVITY", Qualifiers(), doc, "Pengecualian 7",
                "Ikut serta dalam olahraga atau aktivitas berisiko tinggi, termasuk namun tidak terbatas pada seni bela diri, skydiving, menyelam, mendaki, panjat tebing (buatan atau natural), arung jeram, bungee jumping, balap (dengan atau tanpa motor), sepeda, berkuda, berlayar (dengan atau tanpa layar), terbang layang, gantole dan/atau olahraga lainnya di udara;", "id"))
    T.append(_t(pid, "x_pregnancy", Relation.EXCLUDES, "PREGNANCY", Qualifiers(), doc, "Pengecualian 9",
                "Segala hal yang berhubungan dengan kehamilan, melahirkan, keguguran, ketidaksuburan dan sterilisasi/kontrasepsi;", "id"))
    T.append(_t(pid, "x_congenital", Relation.EXCLUDES, "CONGENITAL", Qualifiers(), doc, "Pengecualian 10", "Kelainan bawaan dari lahir (kongenital) baik diketahui maupun tidak diketahui;", "id"))
    T.append(_t(pid, "x_war", Relation.EXCLUDES, "WAR", Qualifiers(), doc, "Pengecualian 11",
                "Penyakit atau cedera yang diakibatkan secara langsung maupun tidak langsung oleh perang, bahaya perang, atau keadaan darurat perang baik dinyatakan atau tidak, pemogokan, kerusuhan, huru-hara, pemberontakan, perang saudara, pengambilalihan kekuasaan pemerintahan/kudeta;", "id"))
    T.append(_t(pid, "x_suicide", Relation.EXCLUDES, "SUICIDE", Qualifiers(), doc, "Pengecualian 12",
                "Bunuh diri atau percobaan bunuh diri baik dalam keadaan sadar maupun tidak, hukuman mati oleh pengadilan, karena adanya suatu tindakan melanggar hukum atau tindakan kejahatan atau percobaan melakukan tindakan kejahatan dilakukan oleh Tertanggung", "id"))
    T.append(_t(pid, "x_criminal", Relation.EXCLUDES, "CRIMINAL_ACT", Qualifiers(), doc, "Pengecualian 12",
                "karena adanya suatu tindakan melanggar hukum atau tindakan kejahatan atau percobaan melakukan tindakan kejahatan dilakukan oleh Tertanggung dan/atau pihak lainnya yang memiliki kepentingan untuk mendapatkan manfaat Asuransi Tambahan;", "id"))
    T.append(_t(pid, "x_dental", Relation.EXCLUDES, "DENTAL", Qualifiers(), doc, "Pengecualian 17",
                "Segala hal yang berhubungan dengan pemeriksaan dan perawatan gigi (termasuk namun tidak terbatas pada keluhan-keluhan karena sakit gigi, operasi gigi, kista gigi, gusi, bedah mulut, jaringan penunjang gigi, kawat gigi, gigi palsu) kecuali disebabkan oleh Kecelakaan;", "id"))
    T.append(_t(pid, "e_dental_accident", Relation.EXCEPTS, "x_dental", Qualifiers(applies_if=[Condition(slot=Slot.IS_ACCIDENT, op=Op.IS_TRUE)]),
                doc, "Pengecualian 17", "kecuali disebabkan oleh Kecelakaan;", "id"))
    T.append(_t(pid, "p_filing_90d", Relation.HAS_PERIOD, "FILING_DEADLINE",
                Qualifiers(period_kind=PeriodKind.FILING_DEADLINE, deadline_days=90, from_event=WindowFrom.DISCHARGE, late_effect="DISCRETIONARY"),
                doc, "Cara Pengajuan Klaim 3", "Serahkan/kirimkan Formulir Klaim beserta dokumen-dokumen yang diperlukan selambat-lambatnya 90 hari kalender sejak Tertanggung keluar dari Rumah Sakit.", "id"))
    T.append(_t(pid, "r_docs_hosp", Relation.REQUIRES_DOCUMENT, "HOSPITALIZATION",
                Qualifiers(document_codes=["CLAIM_FORM_INPATIENT", "DOCTOR_STATEMENT_INPATIENT", "ID_COPY", "MEDICAL_RESULTS_COPY", "ITEMISED_BILL_ORIGINAL_OR_LEGALISED", "BANK_BOOK_COPY"]),
                doc, "Dokumen Pengajuan Klaim Wajib",
                "a. Asli formulir klaim rawat inap yang telah diisi dengan jujur, benar dan lengkap dan telah ditandatangani oleh Anda atau Penerima Manfaat; b. Asli Surat Keterangan Dokter klaim rawat inap (Bagian 2 formulir klaim); c. Fotokopi identitas Anda, Tertanggung dan/atau Penerima Manfaat yang masih berlaku; d. Fotokopi semua hasil Pemeriksaan Medis (termasuk namun tidak terbatas laboratorium, radiologi, obat); e. Asli atau fotokopi legalisir semua kuitansi dan rincian tagihan biaya Rumah Sakit; f. Fotokopi halaman depan Tabungan yang mencantumkan nomor rekening Anda atau Penerima Manfaat", "id"))
    T.append(_t(pid, "d_payment_sla", Relation.DEFINES, "INSURER_SLA", Qualifiers(formula="payment within 30 calendar days of approval"),
                doc, "Cara Pengajuan Klaim 4", "Astra Life akan membayarkan Manfaat Asuransi Tambahan selambat-lambatnya 30 hari kalender sejak klaim disetujui.", "id"))
    return PolicyRecord(id=pid, doc_id=doc, insurer="PT Asuransi Jiwa Astra (rider on Budi's unit-link, modelled)", product_name="Hospital Cash Plan rider (family, IDR 300,000/day)", product_type="hospital_cash",
                        basis=Basis.FIXED_BENEFIT, effective_date=date(2024, 5, 1), issue_date=date(2024, 5, 1), status="active", grace_days=30, sum_assured=IDR(300000), currency="IDR", tuples=T, verified=True)


def hi_indiv_s() -> PolicyRecord:
    pid, doc = "HI-INDIV-S", "HI-INDIV-S-wording(mock)"
    # Real stand-in: PT Asuransi Jiwa Astra's "Perawatan Medis & Bedah" individual
    # hospitalisation rider RIPLAY (data/real/riplay/astra_medis_dan_bedah.pdf). The qualitative
    # clauses below (30-day waiting period, exclusions, COB, filing deadline, claim documents)
    # are quoted verbatim from that PDF. The benefit amounts, the 24-month pre-existing window
    # and the specified-illness sub-limits are sandbox-chosen to drive the walkthrough scenario
    # (Astra's rider states a shorter, undated "Kondisi Yang Sudah Ada Sebelumnya" exclusion with
    # no RIPLAY-stated window), so those tuples keep the "-wording(mock)" doc id.
    real_doc = "data/real/riplay/astra_medis_dan_bedah.pdf"
    T = []
    T.append(_t(pid, "c_room", Relation.COVERS, "HOSPITALIZATION",
                Qualifiers(per_day_limit=IDR(800000), currency="IDR", annual_cap=IDR(100000000), copay_pct=5.0, copay_cap=IDR(3000000), basis=Basis.INDEMNITY, other_insurance="EXCESS",
                           formula="room up to IDR 800,000/day; eligible expenses less 5% co-payment (max IDR 3,000,000 per admission); annual limit IDR 100,000,000"),
                doc, "Schedule of Benefits, 1",
                "Room and board: actual charges up to IDR 800,000 per day. Eligible inpatient expenses are reimbursed after a co-payment of 5% borne by the Policyholder, capped at IDR 3,000,000 per admission. Annual limit IDR 100,000,000 per insured person. Benefits are paid by reimbursement only."))
    T.append(_t(pid, "c_surgery", Relation.COVERS, "SURGERY",
                Qualifiers(per_case_limit=IDR(20000000), currency="IDR", copay_pct=5.0, copay_cap=IDR(3000000), basis=Basis.INDEMNITY, other_insurance="EXCESS"),
                doc, "Schedule of Benefits, 2", "Surgical charges: actual charges up to IDR 20,000,000 per case, subject to the co-payment."))
    T.append(_t(pid, "p_waiting_30", Relation.HAS_PERIOD, "WAITING", Qualifiers(period_kind=PeriodKind.WAITING, waiting_days=30, window_from=WindowFrom.EFFECTIVE),
                real_doc, "Pengecualian 2 (Astra Perawatan Medis & Bedah)",
                "Semua biaya perawatan atas manfaat Asuransi Tambahan yang terjadi dalam Masa Tunggu;", "id"))
    T.append(_t(pid, "p_specified_12m", Relation.HAS_PERIOD, "WAITING_SPECIFIED",
                Qualifiers(period_kind=PeriodKind.WAITING_SPECIFIED, window_len=12, window_unit=TimeUnit.MONTHS, window_from=WindowFrom.EFFECTIVE,
                           diseases=["HERNIA", "CATARACT", "TONSILLITIS", "HAEMORRHOIDS", "SINUSITIS", "KIDNEY_STONE", "GALLSTONE", "UTERINE_FIBROID", "THYROID", "HYPERTENSION", "DIABETES"]),
                doc, "General Conditions, 4", "Treatment of the following specified illnesses is not covered within the first 12 months of the effective date: hernia, cataract, tonsillitis, haemorrhoids, sinusitis, kidney and gall stones, uterine fibroids, thyroid disorders, hypertension and diabetes."))
    T.extend(_preexisting(pid, ["HOSPITALIZATION", "SURGERY"], real_doc, "Pengecualian 1 (Astra Perawatan Medis & Bedah)",
                          "Kondisi Yang Sudah Ada Sebelumnya;", "id", window_months=24))
    T.append(_t(pid, "x_dental", Relation.EXCLUDES, "DENTAL", Qualifiers(), doc, "Exclusions 4 (sandbox: no standalone dental benefit)", "Dental treatment of any kind, except treatment of sound natural teeth necessitated by an accident."))
    T.append(_t(pid, "e_dental_accident", Relation.EXCEPTS, "x_dental", Qualifiers(applies_if=[Condition(slot=Slot.IS_ACCIDENT, op=Op.IS_TRUE)]), doc, "Exclusions 4", "except treatment of sound natural teeth necessitated by an accident."))
    T.append(_t(pid, "x_pregnancy", Relation.EXCLUDES, "PREGNANCY", Qualifiers(), real_doc, "Daftar Manfaat, Komplikasi Kehamilan (Astra Medis & Bedah)",
                "Komplikasi Kehamilan Maks per tahun", "id"))
    T.append(_t(pid, "x_cosmetic", Relation.EXCLUDES, "COSMETIC", Qualifiers(), real_doc, "Pengecualian 26-27 (Astra Perawatan Medis & Bedah)",
                "Perawatan dan pembedahan untuk mengubah jenis kelamin;", "id"))
    T.append(_t(pid, "x_suicide", Relation.EXCLUDES, "SUICIDE", Qualifiers(), real_doc, "Pengecualian (Astra Perawatan Medis & Bedah)",
                "Bunuh diri atau percobaan bunuh diri baik dalam keadaan sadar maupun tidak", "id"))
    T.append(_t(pid, "x_intoxication", Relation.EXCLUDES, "INTOXICATION", Qualifiers(), doc, "Exclusions 9", "Illness or injury arising from the influence of alcohol or drugs not prescribed by a physician."))
    T.append(_t(pid, "x_hazardous", Relation.EXCLUDES, "HAZARDOUS_ACTIVITY", Qualifiers(), real_doc, "Pengecualian 20 (Astra Perawatan Medis & Bedah)",
                "Ikut serta dalam olahraga atau aktivitas berisiko tinggi, termasuk namun tidak terbatas pada seni bela diri, skydiving, menyelam, mendaki, panjat tebing, arung jeram, bungee jumping, balap (dengan atau tanpa motor), sepeda, berkuda, berlayar (dengan atau tanpa layar), terbang layang, gantole dan/atau olahraga di udara;", "id"))
    T.append(_t(pid, "d_other_insurance_excess", Relation.DEFINES, "OTHER_INSURANCE",
                Qualifiers(other_insurance="EXCESS", document_codes=["COB_LETTER_FIRST_INSURER", "RECEIPT_ORIGINAL_OR_LEGALISED"]),
                real_doc, "Pengecualian 29 (Astra Perawatan Medis & Bedah)",
                "Sebagian dan/atau seluruh biaya-biaya atas manfaat Asuransi Tambahan ini yang telah ditanggung oleh hukum, program kesehatan, atau polis asuransi lain yang diterbitkan oleh pemerintah, perusahaan asuransi lain, atau pihak lainnya.", "id"))
    T.append(_t(pid, "p_filing_30d", Relation.HAS_PERIOD, "FILING_DEADLINE",
                Qualifiers(period_kind=PeriodKind.FILING_DEADLINE, deadline_days=30, from_event=WindowFrom.DISCHARGE, late_effect="DISCRETIONARY"),
                doc, "Claims, 1 (sandbox: no numeric filing deadline in Astra RIPLAY)",
                "Claim documents must be received by the Company within 30 days of discharge. The Company may reject claims submitted after this period."))
    T.append(_t(pid, "r_docs_hosp", Relation.REQUIRES_DOCUMENT, "HOSPITALIZATION",
                Qualifiers(document_codes=["CLAIM_FORM", "RECEIPT_ORIGINAL_OR_LEGALISED", "ITEMISED_BILL", "MEDICAL_RESUME_INPATIENT", "ID_COPY", "COB_LETTER_FIRST_INSURER", "BANK_BOOK_COPY"]),
                doc, "Claims, 2", "Completed claim form, original receipt or legalised copy, itemised bill, medical resume signed by the treating doctor, identity card of the insured person, settlement letter from any other insurer, and a copy of the bank book of the Policyholder."))
    T.append(_t(pid, "d_dependants", Relation.DEFINES, "INSURED_PERSONS", Qualifiers(formula="policyholder Sari and children Aditya, Nadia"),
                doc, "Schedule", "Insured persons: the Policyholder and the dependent children named in the Schedule."))
    return PolicyRecord(id=pid, doc_id=real_doc, insurer="PT Asuransi Sehat Mandiri (mock; clauses from Astra Medis & Bedah RIPLAY)", product_name="Sehat Mandiri Individual Health (reimbursement)", product_type="health_indemnity",
                        basis=Basis.INDEMNITY, effective_date=date(2025, 11, 1), issue_date=date(2025, 11, 1), expiry_date=date(2026, 10, 31), status="active", grace_days=30, currency="IDR", tuples=T, verified=True)


# --------------------------------------------------------------------------- Dewi
def pa_chubb_03() -> PolicyRecord:
    pid, doc = "PA-CHUBB-03", "chubb_my_pa"
    acc = Condition(slot=Slot.IS_ACCIDENT, op=Op.IS_TRUE, note="bodily injury by accident")
    T = []
    T.append(_t(pid, "c_accidental_death", Relation.COVERS, "ACCIDENTAL_DEATH",
                Qualifiers(amount=IDR(100000000), currency="IDR", basis=Basis.FIXED_BENEFIT, other_insurance="STACKABLE", applies_if=[acc]),
                doc, "Part A - Accidental Death and Permanent Disablement, 1",
                "Compensation under this Benefit shall be payable in the event of Accidental Death and/or disability due to Bodily Injury. 1. Accidental Death 100%"))
    T.append(_t(pid, "c_tpd", Relation.COVERS, "TPD",
                Qualifiers(amount=IDR(100000000), currency="IDR", basis=Basis.FIXED_BENEFIT, other_insurance="STACKABLE", applies_if=[acc]),
                doc, "Part A - Accidental Death and Permanent Disablement", "Compensation under this Benefit shall be payable in the event of Accidental Death and/or disability due to Bodily Injury."))
    T.append(_t(pid, "c_weekly_ttd", Relation.COVERS, "TEMPORARY_DISABILITY",
                Qualifiers(per_week_amount=IDR(500000), max_weeks=52, currency="IDR", basis=Basis.FIXED_BENEFIT, other_insurance="STACKABLE", applies_if=[acc],
                           formula="IDR 500,000 per week of certified temporary total disablement, up to 52 weeks"),
                doc, "Weekly Benefits, 1 Temporary Total Disablement",
                "If during the Period of Insurance, from the date of Temporary Total Disablement and whilst the Temporary Total Disablement persists, We will pay the Insured Person the Sum Insured as specified in the Schedule of Benefits under this Benefit, up to a maximum of fifty-two (52) weeks. The above Benefit is not applicable to food and drink poisoning and Sickness, Disease Or Illness."))
    T.append(_t(pid, "c_accident_medical", Relation.COVERS, "ACCIDENT_MEDICAL",
                Qualifiers(per_case_limit=IDR(10000000), annual_cap=IDR(10000000), currency="IDR", basis=Basis.INDEMNITY, other_insurance="EXCESS", applies_if=[acc]),
                doc, "Part B - Medical Expenses",
                "We will reimburse the Insured Person for actual Medical Expenses incurred as a result of a Bodily Injury or if the actual Medical Expenses are incurred by the Insured Person as a result of having contracted dengue fever, malaria or Japanese encephalitis (JE), provided that Our maximum liability arising out of any one (1) Accident shall not exceed the Sum Insured specified in the Schedule of Benefits under Part B, current at the time of the Accident causing the Bodily Injury."))
    T.append(_t(pid, "k_valid_license", Relation.CONDITIONED_ON, "NO_VALID_LICENSE",
                Qualifiers(applies_if=[Condition(slot=Slot.LICENSE_VALID, op=Op.IS_TRUE, note="exclusion (d): driving/riding without a valid license")]),
                doc, "General Exclusions (d)", "driving/riding without a valid license; or"))
    T.append(_t(pid, "k_occupation_declared", Relation.CONDITIONED_ON, "COMMERCIAL_MOTORCYCLING",
                Qualifiers(applies_if=[Condition(slot=Slot.OCCUPATION_CLASS, op=Op.IN, value=[1, 2], note="schedule: declared occupation class 1 (administrative staff); commercial riding is class 3 and must be declared/loaded")]),
                doc, "Schedule - Occupation (modelled) / Extension 6 Motorcycling",
                "It is hereby declared and understood that this Policy shall be extended to cover the Insured Person whilst motor-cycling (whether as a passenger or as a pillion rider) provided always that this extension shall not apply whilst the Insured Person is engaged in racing, pace-making or participating in any contest reliability or other trial or speed testing."))
    T.append(_t(pid, "x_commercial_motorcycling", Relation.EXCLUDES, "COMMERCIAL_MOTORCYCLING", Qualifiers(),
                doc, "Schedule - Occupation (modelled)",
                "Occupation declared: administrative staff (Class 1). Cover does not extend to Bodily Injury sustained whilst riding a motorcycle for hire or reward (commercial motorcycling) unless such occupation has been declared to and accepted by Us and the appropriate additional premium paid."))
    T.append(_t(pid, "x_suicide", Relation.EXCLUDES, "SUICIDE", Qualifiers(), doc, "General Exclusions (a)", "insanity, deliberate self-inflicted injury or any attempt thereat, suicide or any attempt thereat; or"))
    T.append(_t(pid, "x_criminal", Relation.EXCLUDES, "CRIMINAL_ACT", Qualifiers(), doc, "General Exclusions (b)",
                "committing or attempting to commit any criminal or illegal act, malicious or deliberate act, including resistance to arrest and road traffic offences; or"))
    T.append(_t(pid, "x_intoxication", Relation.EXCLUDES, "INTOXICATION", Qualifiers(), doc, "General Exclusions (c)",
                "intoxicating by alcohol or drugs, including having a blood alcohol content over the prescribed legal limit whilst driving, or being under the influence of any other drug unless it was prescribed by a Physician and taken in accordance with the Physician's advice; or"))
    T.append(_t(pid, "e_intoxication_within_limit", Relation.EXCEPTS, "x_intoxication",
                Qualifiers(applies_if=[Condition(slot=Slot.INTOXICATED, op=Op.IS_FALSE, note="blood alcohol within the legal limit")]),
                doc, "Extensions 1. Intoxication",
                "It is hereby declared and agreed that this Policy is extended to cover Bodily Injury sustained by the Insured Person due to intoxication by alcohol but not exceeding the limit set by the law in the country where the Accident happened and/or drugs prescribed by a qualified Physician."))
    T.append(_t(pid, "x_no_valid_license", Relation.EXCLUDES, "NO_VALID_LICENSE", Qualifiers(), doc, "General Exclusions (d)", "driving/riding without a valid license; or"))
    T.append(_t(pid, "x_motor_sports", Relation.EXCLUDES, "HAZARDOUS_ACTIVITY", Qualifiers(), doc, "General Exclusions (e)(f)",
                "the Insured Person engaging in any professional sport, meaning his/her livelihood is substantially dependent on income received as a result of him/her playing sport; or engaging in any motor sports as a rider, driver and/or a passenger; or"))
    T.append(_t(pid, "x_war", Relation.EXCLUDES, "WAR", Qualifiers(), doc, "General Exclusions (g)",
                "war, invasion, act of foreign enemy, hostilities or warlike operations (whether declared or not), civil war, rebellion, revolution, insurrection, mutiny or usurped power, strike, riot or civil commotion, military or popular uprising; or"))
    T.append(_t(pid, "x_aviation", Relation.EXCLUDES, "AVIATION", Qualifiers(applies_if=[Condition(slot=Slot.PILOT_ROLE, op=Op.NE, value="PASSENGER")]), doc, "General Exclusions (i)",
                "travelling in an aircraft as a pilot or crew member (on active duty) of any aircraft, or engaging in any aerial activity, including parachuting and hang-gliding, except as a passenger in any properly licensed aircraft; or"))
    T.append(_t(pid, "x_preexisting", Relation.EXCLUDES, "PRE_EXISTING_CONDITION", Qualifiers(), doc, "General Exclusions (j)", "Pre-Existing Medical Conditions; or"))
    T.append(_t(pid, "p_waiting_30_sickness", Relation.HAS_PERIOD, "WAITING",
                Qualifiers(period_kind=PeriodKind.WAITING, waiting_days=30, window_from=WindowFrom.EFFECTIVE, applies_if=[Condition(slot=Slot.IS_ACCIDENT, op=Op.IS_FALSE, note="dengue/malaria/JE medical expenses only")]),
                doc, "Definitions - Waiting Period", "Waiting Period means the first thirty (30) days from the date the Insured Person is included into the Policy"))
    T.append(_t(pid, "p_notice_30d", Relation.HAS_PERIOD, "NOTICE_DEADLINE",
                Qualifiers(period_kind=PeriodKind.NOTICE_DEADLINE, deadline_days=30, from_event=WindowFrom.ACCIDENT, late_effect="DISCRETIONARY"),
                doc, "General Conditions - Claims notification",
                "Provided always that all notification is given as soon as possible and in any event within thirty (30) days of the occurrence of any event which may give rise to a claim under this Policy."))
    T.append(_t(pid, "p_filing_30d", Relation.HAS_PERIOD, "FILING_DEADLINE",
                Qualifiers(period_kind=PeriodKind.FILING_DEADLINE, deadline_days=30, from_event=WindowFrom.ACCIDENT, late_effect="DISCRETIONARY"),
                doc, "General Conditions - Claims notification",
                "Provided always that all notification is given as soon as possible and in any event within thirty (30) days of the occurrence of any event which may give rise to a claim under this Policy."))
    T.append(_t(pid, "r_docs_medical", Relation.REQUIRES_DOCUMENT, "ACCIDENT_MEDICAL",
                Qualifiers(document_codes=["CLAIM_FORM", "POLICE_REPORT", "MEDICAL_REPORT", "ITEMISED_BILL_ORIGINAL", "ID_COPY", "DRIVING_LICENSE_COPY"]),
                doc, "Claims procedure (modelled on Part B)", "Compensation under this Benefit shall be payable only if such medical or surgical or traditional treatment is provided to the Insured Person by a qualified Physician"))
    T.append(_t(pid, "r_docs_ttd", Relation.REQUIRES_DOCUMENT, "TEMPORARY_DISABILITY",
                Qualifiers(document_codes=["CLAIM_FORM", "PHYSICIAN_CERTIFICATE_TTD", "MEDICAL_REPORT", "ID_COPY"]),
                doc, "Definitions - Temporary Total Disablement", "Temporary Total Disablement means where, certified by a Physician, the Insured Person is temporarily unable to engage in his or her usual occupation."))
    T.append(_t(pid, "r_docs_death", Relation.REQUIRES_DOCUMENT, "ACCIDENTAL_DEATH",
                Qualifiers(document_codes=["CLAIM_FORM_DEATH", "DEATH_CERT_ORIGINAL_OR_LEGALISED", "POLICE_REPORT", "POST_MORTEM_IF_AVAILABLE", "BENEFICIARY_ID_AND_RELATIONSHIP_PROOF"]),
                doc, "Part A (modelled)", "Accidental Death means death occurring as a result of a Bodily Injury."))
    return PolicyRecord(id=pid, doc_id=doc, insurer="Chubb (modelled on Chubb Malaysia Essential Plus PA wording)", product_name="Essential Plus Personal Accident", product_type="pa",
                        basis=Basis.FIXED_BENEFIT, effective_date=date(2026, 3, 15), issue_date=date(2026, 3, 15), expiry_date=date(2027, 3, 14), status="active",
                        sum_assured=IDR(100000000), currency="IDR", tuples=T, verified=True)


def platform_acc() -> PolicyRecord:
    # Genuinely synthetic: no Indonesian ride-hailing platform publishes a RIPLAY (a RIPLAY is
    # issued by a licensed insurer for a named retail product; platform driver-partner accident
    # cover is typically a group policy whose terms are not published to the public, let alone as
    # a RIPLAY). A real personal-accident RIPLAY (e.g. Chubb's or Sompo's PA RIPLAY in
    # data/real/riplay/) could stand in for the *generic* PA clause shapes, but every clause in
    # this record is already the platform-specific "on trip" condition the sandbox scenario turns
    # on (app-logged trip window, 7-day app-only filing), which has no counterpart in a retail PA
    # policy, so substituting real wording here would misrepresent, not clarify, the product.
    # This record stays illustrative/mock by design; see data/real/riplay/PROVENANCE.md.
    pid, doc = "PLATFORM-ACC", "PLATFORM-ACC-wording(mock)"
    on_trip = Condition(slot=Slot.WORK_RELATED, op=Op.IS_TRUE, note="only while an order is active (on trip)")
    acc = Condition(slot=Slot.IS_ACCIDENT, op=Op.IS_TRUE)
    T = []
    T.append(_t(pid, "c_death_on_trip", Relation.COVERS, "ACCIDENTAL_DEATH",
                Qualifiers(amount=IDR(50000000), currency="IDR", basis=Basis.FIXED_BENEFIT, other_insurance="STACKABLE", applies_if=[acc, on_trip]),
                doc, "Benefits, 1", "Accidental death while the driver-partner is on an active order (from order acceptance to completion as recorded by the app): IDR 50,000,000 paid to the registered heir."))
    T.append(_t(pid, "c_medical_on_trip", Relation.COVERS, "ACCIDENT_MEDICAL",
                Qualifiers(per_case_limit=IDR(5000000), annual_cap=IDR(5000000), currency="IDR", basis=Basis.INDEMNITY, other_insurance="EXCESS", applies_if=[acc, on_trip]),
                doc, "Benefits, 2", "Medical expenses from an accident while on an active order: actual expenses up to IDR 5,000,000 per accident, in excess of any amount recoverable from Jasa Raharja or other insurance."))
    T.append(_t(pid, "d_on_trip", Relation.DEFINES, "ON_TRIP", Qualifiers(formula="work_related = order active in the app log"),
                doc, "Definitions", "\"On trip\" means the period between the driver-partner's acceptance of an order and its completion or cancellation as recorded in the platform's trip log."))
    T.append(_t(pid, "p_filing_7d", Relation.HAS_PERIOD, "FILING_DEADLINE",
                Qualifiers(period_kind=PeriodKind.FILING_DEADLINE, deadline_days=7, from_event=WindowFrom.ACCIDENT, late_effect="REJECT"),
                doc, "Claims, 1", "Claims must be submitted through the driver app within 7 days of the accident. Claims submitted after 7 days are not accepted."))
    T.append(_t(pid, "r_docs", Relation.REQUIRES_DOCUMENT, "ACCIDENT_MEDICAL",
                Qualifiers(document_codes=["APP_CLAIM_FORM", "TRIP_LOG_SCREENSHOT", "MEDICAL_REPORT", "ITEMISED_BILL", "ID_COPY"]),
                doc, "Claims, 2", "Attach the trip record, hospital bill and receipts, doctor's letter and identity card in the app claim form."))
    T.append(_t(pid, "x_intoxication", Relation.EXCLUDES, "INTOXICATION", Qualifiers(), doc, "Exclusions 1", "Accidents while under the influence of alcohol or drugs."))
    T.append(_t(pid, "x_criminal", Relation.EXCLUDES, "CRIMINAL_ACT", Qualifiers(), doc, "Exclusions 2", "Accidents arising from a criminal act by the driver-partner."))
    return PolicyRecord(id=pid, doc_id=doc, insurer="Ride-hailing platform group accident cover (mock)", product_name="Driver-partner on-trip accident protection", product_type="platform_accident",
                        basis=Basis.FIXED_BENEFIT, effective_date=date(2026, 1, 1), issue_date=date(2026, 1, 1), status="active", sum_assured=IDR(50000000), currency="IDR", tuples=T, verified=True)


def jasa_raharja() -> PolicyRecord:
    pid, doc = "JASA-RAHARJA", "JASA-RAHARJA-wording(mock, PMK 15-16/2017)"
    multi = Condition(slot=Slot.VEHICLES_INVOLVED, op=Op.GE, value=2, note="collision between two or more vehicles")
    T = []
    T.append(_t(pid, "c_medical", Relation.COVERS, "ACCIDENT_MEDICAL",
                Qualifiers(per_case_limit=IDR(20000000), currency="IDR", basis=Basis.INDEMNITY, other_insurance="NONE", applies_if=[multi], formula="first payer; medical costs up to IDR 20,000,000 per victim"),
                doc, "Santunan (modelled on PMK 15/16 2017)", "Victims of a traffic accident involving two or more motor vehicles are entitled to compensation for medical treatment costs up to IDR 20,000,000, paid directly to the hospital or reimbursed."))
    T.append(_t(pid, "c_death", Relation.COVERS, "ACCIDENTAL_DEATH",
                Qualifiers(amount=IDR(50000000), currency="IDR", basis=Basis.FIXED_BENEFIT, other_insurance="STACKABLE", applies_if=[multi]),
                doc, "Santunan (modelled on PMK 15/16 2017)", "Death compensation of IDR 50,000,000 is paid to the legal heirs of a victim who dies as a result of a traffic accident involving two or more motor vehicles."))
    T.append(_t(pid, "x_single_vehicle_medical", Relation.EXCLUDES, "ACCIDENT_MEDICAL",
                Qualifiers(applies_if=[Condition(slot=Slot.VEHICLES_INVOLVED, op=Op.LT, value=2, note="single-vehicle accident")]),
                doc, "Pengecualian (modelled)", "Single-vehicle accidents (the victim is the driver and no other vehicle is involved) are not covered by the road-traffic accident guarantee."))
    T.append(_t(pid, "x_single_vehicle_death", Relation.EXCLUDES, "ACCIDENTAL_DEATH",
                Qualifiers(applies_if=[Condition(slot=Slot.VEHICLES_INVOLVED, op=Op.LT, value=2)]),
                doc, "Pengecualian (modelled)", "Single-vehicle accidents (the victim is the driver and no other vehicle is involved) are not covered by the road-traffic accident guarantee."))
    T.append(_t(pid, "p_filing_180d", Relation.HAS_PERIOD, "FILING_DEADLINE",
                Qualifiers(period_kind=PeriodKind.FILING_DEADLINE, deadline_days=180, from_event=WindowFrom.ACCIDENT, late_effect="REJECT"),
                doc, "Kadaluarsa (modelled on UU 33/34 1964)", "The right to compensation lapses if the claim is not submitted within 6 months of the accident."))
    T.append(_t(pid, "r_docs", Relation.REQUIRES_DOCUMENT, "ACCIDENT_MEDICAL",
                Qualifiers(document_codes=["POLICE_REPORT", "JASA_RAHARJA_CLAIM_FORM", "ID_COPY", "MEDICAL_BILL_ORIGINAL", "DOCTOR_STATEMENT"]),
                doc, "Prosedur (modelled)", "Police accident report (Laporan Polisi) from the traffic unit, Jasa Raharja claim form, identity card, original hospital bills and doctor's statement."))
    return PolicyRecord(id=pid, doc_id=doc, insurer="PT Jasa Raharja (statutory, modelled)", product_name="Road traffic accident compensation (UU 33/34 1964)", product_type="jasa_raharja",
                        basis=Basis.INDEMNITY, status="active", currency="IDR", tuples=T, verified=True)


def ci_chubb_05() -> PolicyRecord:
    """Critical-illness plan modelled on Chubb Essential Critical Care (90-day waiting, 30-day survival)."""
    pid, doc = "CI-CHUBB-05", "CI-CHUBB-05-wording(mock)"
    T = []
    # icd10_codes: WHO ICD-10 chapter/category identifiers (public domain, not a licensed dataset) for
    # the illnesses this rider typically covers: malignant neoplasms, acute MI, stroke, kidney failure.
    T.append(_t(pid, "ci_cover", Relation.COVERS, "CRITICAL_ILLNESS",
                Qualifiers(amount=IDR(100000000), currency="IDR", basis=Basis.FIXED_BENEFIT, other_insurance="STACKABLE",
                           icd10_codes=["C00-C97", "I21", "I60-I69", "N18.5", "N18.6"]),
                doc, "Benefits",
                "Critical Illness Benefit: a lump sum of IDR 100,000,000 is paid on first diagnosis of a covered critical illness, subject to the waiting period and the survival period."))
    T.append(_t(pid, "ci_wait", Relation.HAS_PERIOD, "WAITING", Qualifiers(period_kind=PeriodKind.WAITING, waiting_days=90),
                doc, "Waiting Period",
                "No benefit is payable for a critical illness whose signs or symptoms first appeared within 90 days from the Policy effective date."))
    T.append(_t(pid, "ci_survival", Relation.HAS_PERIOD, "SURVIVAL",
                Qualifiers(period_kind=PeriodKind.SURVIVAL, window_len=30, window_unit=TimeUnit.DAYS, window_from=WindowFrom.DIAGNOSIS),
                doc, "Survival Period",
                "The Insured must survive for at least 30 days after the date of diagnosis of the critical illness; no benefit is payable if the Insured dies within this survival period."))
    T.append(_t(pid, "ci_filing", Relation.HAS_PERIOD, "FILING_DEADLINE",
                Qualifiers(period_kind=PeriodKind.FILING_DEADLINE, deadline_days=90, from_event=WindowFrom.DIAGNOSIS, late_effect="REJECT"),
                doc, "Claims",
                "Claims must be submitted within 90 days of diagnosis together with the pathology or imaging reports and the specialist's confirmation."))
    T.append(_t(pid, "ci_complaint", Relation.DEFINES, "COMPLAINT_ROUTE", Qualifiers(), doc, "Complaints",
                "Complaints may be submitted to the Insurer's complaint unit, which responds within 10 working days; unresolved disputes may be referred to the OJK consumer complaint channel or to LAPS SJK."))
    T.append(_t(pid, "ci_docs", Relation.REQUIRES_DOCUMENT, "CLAIM_FORM",
                Qualifiers(document_codes=["CLAIM_FORM", "DOCTOR_STATEMENT", "PATHOLOGY_REPORT", "SPECIALIST_CONFIRMATION", "ID_CARD", "BANK_ACCOUNT"]),
                doc, "Claims", "Claim form, attending doctor's statement, pathology or imaging reports, specialist confirmation, identity card and bank account."))
    return PolicyRecord(id=pid, doc_id=doc, insurer="Chubb Life Indonesia (modelled)", product_name="Essential Critical Care (critical illness, modelled)", product_type="ci",
                        basis=Basis.FIXED_BENEFIT, effective_date=date(2025, 6, 1), issue_date=date(2025, 6, 1), status="active", grace_days=30,
                        sum_assured=IDR(100000000), currency="IDR", tuples=T, verified=True)


BUILDERS = {
    "HCP-SOMPO-01": hcp_sompo_01,
    "TL-ASTRA-07": tl_astra_07,
    "CI-CHUBB-05": ci_chubb_05,
    "GH-NUSA-GRP": gh_nusa_grp,
    "GL-NUSA-GRP": gl_nusa_grp,
    "HCP-RIDER-B": hcp_rider_b,
    "HI-INDIV-S": hi_indiv_s,
    "PA-CHUBB-03": pa_chubb_03,
    "PLATFORM-ACC": platform_acc,
    "BPJS-KES": bpjs_kes,
    "JASA-RAHARJA": jasa_raharja,
}


def build_policy_records() -> dict[str, PolicyRecord]:
    return {k: f() for k, f in BUILDERS.items()}


# --------------------------------------------------------------------------- persona holdings and meta
# (policy row id, record id, status). The sandbox `policies` table (seed.POLICIES) must agree with
# this table; tests/test_persona_policies.py cross-checks it. The same table feeds the agent loop
# whether it reads the sandbox DB or runs without one, so there is a single source of truth.
PERSONA_HOLDINGS: dict[str, list[tuple[str, str, str]]] = {
    "rizky": [("HCP-SOMPO-01", "HCP-SOMPO-01", "active"), ("TL-ASTRA-07", "TL-ASTRA-07", "grace"), ("CI-CHUBB-05", "CI-CHUBB-05", "active"),
              ("BPJS-KES-RIZKY", "BPJS-KES", "active"), ("JASA-RAHARJA", "JASA-RAHARJA", "active")],
    "santoso": [("GH-NUSA-GRP", "GH-NUSA-GRP", "active"), ("GL-NUSA-GRP", "GL-NUSA-GRP", "active"), ("HCP-RIDER-B", "HCP-RIDER-B", "active"),
                ("HI-INDIV-S", "HI-INDIV-S", "active"), ("BPJS-KES-SANTOSO", "BPJS-KES", "active"), ("JASA-RAHARJA", "JASA-RAHARJA", "active")],
    "dewi": [("PA-CHUBB-03", "PA-CHUBB-03", "active"), ("PLATFORM-ACC", "PLATFORM-ACC", "active"), ("BPJS-KES-DEWI", "BPJS-KES", "lapsed"),
             ("JASA-RAHARJA", "JASA-RAHARJA", "active")],
}

PERSONA_META: dict[str, dict] = {
    "rizky": {
        "user_id": "rizky", "name": "Rizky Pratama", "persons": {"rizky": "Rizky Pratama"},
        "insured": {"HCP-SOMPO-01": ["rizky"], "TL-ASTRA-07": ["rizky"], "CI-CHUBB-05": ["rizky"], "BPJS-KES-RIZKY": ["rizky"], "JASA-RAHARJA": ["rizky"]},
        "payments": {"TL-ASTRA-07": {"due_date": "2026-09-01", "paid_date": None, "last_paid": "2026-08-01"},
                     "HCP-SOMPO-01": {"due_date": "2026-08-20", "paid_date": "2026-08-20"}},
        "bpjs": {"policy_id": "BPJS-KES-RIZKY", "status": "active", "arrears_months": 0, "class": 2},
        "employment_active": True, "liabilities": None, "dependants": 0, "conditions": {},
        "claims": [{"id": "CLM-A-001", "policy_id": "HCP-SOMPO-01", "event": "HOSPITALIZATION", "diagnosis": "DENGUE",
                    "admission": "2026-10-03", "discharge": "2026-10-07", "facility_bpjs_partner": True, "billed": 9200000, "status": "draft"}],
    },
    "santoso": {
        "user_id": "santoso", "name": "Budi Santoso",
        "persons": {"budi": "Budi Santoso", "sari": "Sari Santoso", "aditya": "Aditya Santoso", "nadia": "Nadia Santoso"},
        "insured": {"GH-NUSA-GRP": ["budi", "sari", "aditya", "nadia"], "GL-NUSA-GRP": ["budi"],
                    "HCP-RIDER-B": ["budi", "sari", "aditya", "nadia"], "HI-INDIV-S": ["sari", "aditya", "nadia"],
                    "BPJS-KES-SANTOSO": ["budi", "sari", "aditya", "nadia"], "JASA-RAHARJA": ["budi", "sari", "aditya", "nadia"]},
        "payments": {}, "bpjs": {"policy_id": "BPJS-KES-SANTOSO", "status": "active", "arrears_months": 0, "class": 1},
        "employment_active": True, "liabilities": 600000000, "dependants": 2,
        "conditions": {"aditya": {"ASTHMA": "2024-05-01"}},
        "claims": [{"id": "CLM-B-001", "policy_id": "GH-NUSA-GRP", "person": "aditya", "event": "HOSPITALIZATION", "diagnosis": "ASTHMA",
                    "admission": "2026-10-07", "discharge": "2026-10-10", "facility_bpjs_partner": False, "billed": 18000000,
                    "breakdown": {"room": 8000000, "drugs": 7000000, "doctor": 3000000}, "status": "draft"}],
    },
    "dewi": {
        "user_id": "dewi", "name": "Dewi Lestari", "persons": {"dewi": "Dewi Lestari"},
        "insured": {"PA-CHUBB-03": ["dewi"], "PLATFORM-ACC": ["dewi"], "BPJS-KES-DEWI": ["dewi"], "JASA-RAHARJA": ["dewi"]},
        "payments": {}, "bpjs": {"policy_id": "BPJS-KES-DEWI", "status": "inactive", "arrears_months": 3, "class": 3},
        "bpjs_tk_member": False, "employment_active": True, "liabilities": None, "dependants": 0,
        "occupation_declared": "administrative staff (class 1)", "occupation_actual": "motorcycle courier (class 3)",
        "license_expiry": "2026-09-30", "conditions": {},
        "claims": [{"id": "CLM-C-001", "policy_id": "PA-CHUBB-03", "event": "HOSPITALIZATION", "cause": "ACCIDENT_TRAFFIC",
                    "accident": "2026-10-05", "admission": "2026-10-05", "discharge": "2026-10-11", "facility_bpjs_partner": True,
                    "billed": 22000000, "status": "draft"}],
    },
}

PERSONA_BY_USER = {"rizky": "rizky", "santoso": "santoso", "budi": "santoso", "sari": "santoso", "dewi": "dewi",
                   "C-RIZKY": "rizky", "C-BUDI": "santoso", "C-SARI": "santoso", "C-ADITYA": "santoso", "C-NADIA": "santoso", "C-DEWI": "dewi"}


def holding_record(rec: PolicyRecord, policy_id: str, status: str) -> PolicyRecord:
    """The record of one policy row. Shared wording (BPJS-KES) is instantiated per member so the
    id and status are the member's own; tuple ids stay unchanged."""
    if rec.id == policy_id and rec.status == status:
        return rec
    tuples = [t.model_copy(update={"policy_id": policy_id, "head": policy_id if t.head == rec.id else t.head}) for t in rec.tuples]
    return rec.model_copy(update={"id": policy_id, "status": status, "tuples": tuples})


def policies_for_persona(persona: str, records: Optional[dict[str, PolicyRecord]] = None) -> list[PolicyRecord]:
    recs = records or build_policy_records()
    if persona not in PERSONA_HOLDINGS:
        raise KeyError(persona)
    return [holding_record(recs[rid], pid, st) for pid, rid, st in PERSONA_HOLDINGS[persona]]
