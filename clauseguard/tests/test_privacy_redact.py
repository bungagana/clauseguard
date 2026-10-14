import json
from pathlib import Path

import pytest

from clauseguard.privacy.redact import (
    final_gate, luhn_ok, nik_gender, redact, restore, valid_nik, valid_npwp,
)

SAMPLE = (
    "Nama: Budi Santoso NIK: 3578124509900001 Telp 0812-3456-7890 email budi@example.com\n"
    "Tgl Lahir: 05 September 1990. No. Polis: AB-123456. Pasal 4.2 limit Rp 5.000.000. K35.8\n"
    "Rekening BCA 1234567890\nAlamat: Jl. Mawar 5, Surabaya"
)


def test_nik_structure_and_female_offset():
    assert valid_nik("3578124509900001")
    assert nik_gender("3578124509900001") == "F"
    assert nik_gender("3171011503850002") == "M"
    assert valid_nik("7371052902960007")
    assert not valid_nik("3578123209900001")
    assert not valid_nik("3578127509900001")
    assert not valid_nik("9978124509900001")
    assert not valid_nik("3578124513900001")
    assert not valid_nik("3578124509900000")
    assert not valid_nik("357812450990000")


def test_luhn_and_npwp():
    assert luhn_ok("4111111111111111")
    assert not luhn_ok("4111111111111112")
    assert valid_npwp("09.254.294.3-407.000")
    assert valid_npwp("092542943407000")
    assert not valid_npwp("12.34")


def test_round_trip_and_placeholders():
    r = redact(SAMPLE, ["Budi Santoso"])
    for tok in ("[NAMA_1]", "[NIK_1]", "[TELP_1]", "[EMAIL_1]", "[TGL_LAHIR_1]", "[NO_POLIS_1]", "[REKENING_1]", "[ALAMAT_1]"):
        assert tok in r.text_clean
    assert restore(r.text_clean, r.mapping) == SAMPLE
    assert "Budi" not in r.text_clean


def test_same_value_same_token():
    r = redact("Nama: Budi Santoso\nPasien Budi Santoso, NIK 3578124509900001 dan 3578124509900001", ["Budi Santoso"])
    assert r.text_clean.count("[NAMA_1]") == 2
    assert r.text_clean.count("[NIK_1]") == 2
    assert "[NAMA_2]" not in r.text_clean


def test_repr_does_not_leak_mapping():
    r = redact(SAMPLE, ["Budi Santoso"])
    assert "3578124509900001" not in repr(r)
    assert "Santoso" not in repr(r)


@pytest.mark.parametrize("text", [
    "Berdasarkan Pasal 4.2 manfaat Rp 1.500.000 per hari selama 30 hari.",
    "Limit tahunan Rp 1.000.000.000 diagnosa K35.8 dan A09.",
    "Pasien masuk 12 Maret 2025 di RS Siloam Lippo Village, produk Prime Care Plus.",
    "Nama Produk: Prime Care Plus\nNama Rumah Sakit: RS Premier Bintaro",
    "Policy limit USD 500,000 per year under Section 3.1 and Article 7 in 2025.",
    "Periode polis 01/01/2025 sampai 31/12/2025, kejadian 03/11/2025.",
])
def test_must_survive_untouched(text):
    r = redact(text)
    assert r.text_clean == text
    assert final_gate(text) == []


def test_must_survive_dataset():
    path = Path(__file__).resolve().parents[1] / "data" / "benchmark" / "pii_eval.jsonl"
    rows = [json.loads(l) for l in path.read_text(encoding="utf8").splitlines() if l.strip()]
    keeps = [r for r in rows if r["kind"] == "survive"]
    assert len(keeps) >= 25
    for r in keeps:
        assert redact(r["text"]).findings == [], r["id"]
    assert sum(r["kind"] == "pii" for r in rows) >= 60


def test_gate_blocks_residual_and_passes_clean():
    assert final_gate("NIK 3578124509900001")
    assert final_gate("NIK 3 5 7 8 1 2 4 5 0 9 9 0 0 0 0 1")
    assert final_gate("NIK 3578.1245.0990.0001")
    assert final_gate("NIK 35781245O9900001")
    assert final_gate("hubungi 081234567890")
    assert final_gate("a@b.com")
    assert final_gate("kartu 4111 1111 1111 1111")
    assert final_gate("budi\nsantoso mengajukan", ["Budi Santoso"])
    assert final_gate("BUDI SANTOSO", ["Budi Santoso"])
    clean = redact(SAMPLE, ["Budi Santoso"]).text_clean
    assert final_gate(clean, ["Budi Santoso"]) == []
    assert final_gate("Total Rp 3.578.124.509.900 pasal 4.2", ["Budi Santoso"]) == []


def test_gate_violations_do_not_echo_values():
    v = final_gate("NIK 3578124509900001 budi@example.com", ["Budi Santoso"])
    assert v and all("3578" not in x and "@example" not in x for x in v)


def test_known_name_redacted_in_free_text():
    r = redact("Surat dari Rina Wijaya, dan rina wijaya lagi.", ["Rina Wijaya"])
    assert "Rina" not in r.text_clean and "rina" not in r.text_clean
    assert restore(r.text_clean, r.mapping) == "Surat dari Rina Wijaya, dan rina wijaya lagi."


def test_card_phone_npwp_account():
    r = redact("Kartu 4111 1111 1111 1111; WA +62 812 3456 7891; NPWP 09.254.294.3-407.000; Rek 1234567890", [])
    assert "[KARTU_1]" in r.text_clean and "[TELP_1]" in r.text_clean and "[NPWP_1]" in r.text_clean
    assert "[REKENING_1]" in r.text_clean
