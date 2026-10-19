"""Flowcharts for the technical documentation (HTML rendered to PNG with Playwright).

python docs/diagrams/make_flows.py   ->  docs/img/flow_*_{id,en}.png
"""
from __future__ import annotations

import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "img"
WEB = HERE.parents[2] / "clauseguard-web"

CSS = """
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Segoe UI',Inter,Arial,sans-serif;background:#fff;color:#141B2E}
.wrap{padding:36px 40px;display:inline-block}
h1{font-size:22px;font-weight:700;margin-bottom:22px}
.col{display:flex;flex-direction:column;align-items:center;gap:0}
.row{display:flex;align-items:stretch;gap:0}
.box{border-radius:14px;padding:12px 16px;border:2px solid;min-width:250px;max-width:300px;text-align:center}
.box b{display:block;font-size:15px;margin-bottom:4px}
.box span{font-size:12.5px;color:#4A5370;line-height:1.35}
.tag{display:inline-block;font-size:10.5px;font-weight:700;letter-spacing:.6px;text-transform:uppercase;padding:2px 8px;border-radius:999px;margin-bottom:6px}
.user{border-color:#1C58E3;background:#EEF3FD}.user .tag{background:#1C58E3;color:#fff}
.ai{border-color:#7A5AF8;background:#F3F0FE}.ai .tag{background:#7A5AF8;color:#fff}
.code{border-color:#248968;background:#EAF6F1}.code .tag{background:#248968;color:#fff}
.human{border-color:#E9890C;background:#FDF3E3}.human .tag{background:#E9890C;color:#fff}
.stop{border-color:#D6293F;background:#FCEBED}.stop .tag{background:#D6293F;color:#fff}
.dec{border-color:#141B2E;background:#fff;border-style:dashed}
.down{width:2px;height:26px;background:#9AA3B8;position:relative;margin:0 auto}
.down:after{content:'';position:absolute;bottom:-1px;left:-5px;border:6px solid transparent;border-top:8px solid #9AA3B8}
.right{height:2px;width:34px;background:#9AA3B8;position:relative;align-self:center}
.right:after{content:'';position:absolute;right:-2px;top:-5px;border:6px solid transparent;border-left:8px solid #9AA3B8}
.lbl{font-size:11.5px;color:#4A5370;font-weight:600;padding:4px 0}
.legend{display:flex;gap:16px;margin-top:22px;font-size:12px;color:#4A5370}
.legend i{display:inline-block;width:12px;height:12px;border-radius:3px;margin-right:6px;vertical-align:-1px}
.branch{display:flex;gap:28px;align-items:flex-start}
"""

T = {
    "id": {
        "legend": [("user", "#1C58E3", "Nasabah"), ("ai", "#7A5AF8", "Agen AI"), ("code", "#248968", "Kode deterministik"), ("human", "#E9890C", "Petugas penanggung")],
        "claim_title": "Alur klaim dari pertanyaan sampai keputusan",
        "claim": [
            ("user", "Nasabah", "Bercerita dengan bahasa sehari-hari", "\"Dirawat 3 hari karena DBD, bisa klaim?\""),
            ("code", "ClauseLens", "Memeriksa semua polis", "Ditanggung atau tidak, jumlah, tenggat, kutipan klausul"),
            ("user", "Nasabah", "Mengirim dokumen rumah sakit", "Kuitansi, resume medis, resep, hasil lab"),
            ("ai", "ClaimFlow", "Membaca dan mencocokkan dokumen", "Isi setiap berkas dan dokumen wajib yang terpenuhi"),
            ("code", "ClaimFlow", "Mengisi formulir klaim penanggung", "Tata letak dari redaksi polis, nilai dari dokumen"),
            ("user", "Nasabah", "Memeriksa dan menekan Konfirmasi", "Kolom dapat dikoreksi sebelum dikirim"),
            ("human", "Meja penanggung", "Petugas memutuskan klaim", "Disetujui, ditolak, atau dibayar, dengan catatan"),
            ("ai", "Watchdog", "Menyampaikan keputusan ke chat", "Arti keputusan dan langkah berikutnya"),
        ],
        "turn_title": "Alur keputusan dalam satu giliran percakapan",
        "turn": [
            ("user", "Pesan nasabah", "Teks bebas atau berkas", ""),
            ("ai", "Conversation Agent", "Hubungan pesan dengan percakapan", "Situasi baru, koreksi, jawaban, pengandaian, umum"),
            ("code", "Aturan keamanan", "Diputuskan kode lebih dulu", "Misrepresentasi, data orang lain, ubah rekening"),
            ("ai", "Planner Agent", "Maksud, topik, dan alat", "Dokumen, tenggat, jumlah, kemajuan klaim"),
            ("code", "Guardian", "Memeriksa izin setiap alat", "Tingkat T0 sampai T3 dan mode otonomi"),
            ("ai", "Fact Agent", "Kalimat menjadi fakta bertipe", "Tanggal, hari rawat, tagihan, penyebab"),
            ("code", "Mesin aturan", "Menghitung putusan per polis", "Cakupan, jumlah, tenggat, urutan pembayar"),
        ],
        "turn_dec": "Ada satu fakta yang akan mengubah putusan?",
        "turn_yes": ("ai", "Tanya satu hal", "Hanya fakta itu, dengan tombol jawaban", ""),
        "turn_no": ("ai", "Explainer Agent", "Menulis dua kandidat jawaban", "Pemeriksa mencocokkan angka dan tanggal dengan mesin"),
        "turn_end": ("code", "Jawaban dan audit", "Kartu bukti, kutipan klausul, catatan audit", ""),
        "yes": "Ya", "no": "Tidak",
        "tier_title": "Alur izin untuk setiap tindakan agent",
        "tier_start": ("ai", "Agent ingin bertindak", "Setiap pemanggilan alat lewat Guardian", ""),
        "tiers": [
            ("code", "T0 dan T1", "Membaca dan menghitung", "Berjalan otomatis untuk akun sendiri", [("code", "Jawaban langsung", "Tanpa efek di luar sesi", "")]),
            ("user", "T2", "Mengajukan klaim, melampirkan, banding", "Butuh konfirmasi nasabah", [("user", "Kartu konfirmasi", "Nasabah menekan Konfirmasi", ""), ("code", "Token sekali pakai", "Terikat pada argumen yang sama", ""), ("human", "Masuk meja penanggung", "Petugas memutuskan", "")]),
            ("stop", "T3", "Uang dan identitas", "Tidak ada alat yang menjalankan", [("human", "Tiket ke petugas", "Verifikasi identitas lewat jalur terpisah", "")]),
        ],
    },
    "en": {
        "legend": [("user", "#1C58E3", "Customer"), ("ai", "#7A5AF8", "AI agent"), ("code", "#248968", "Deterministic code"), ("human", "#E9890C", "Insurer staff")],
        "claim_title": "Claim flow from question to decision",
        "claim": [
            ("user", "Customer", "Describes it in everyday words", "\"Three days in hospital with dengue, can I claim?\""),
            ("code", "ClauseLens", "Checks every policy", "Covered or not, amount, deadline, clause quoted"),
            ("user", "Customer", "Sends hospital documents", "Receipt, medical resume, prescription, lab results"),
            ("ai", "ClaimFlow", "Reads and matches the documents", "What each file says and which requirements it meets"),
            ("code", "ClaimFlow", "Fills in the insurer's claim form", "Layout from the policy wording, values from the files"),
            ("user", "Customer", "Reviews and taps Confirm", "Any field can be corrected before sending"),
            ("human", "Insurer desk", "A person decides the claim", "Approved, rejected or paid, with a note"),
            ("ai", "Watchdog", "Brings the decision to the chat", "What it means and the next step"),
        ],
        "turn_title": "Decision flow in one conversation turn",
        "turn": [
            ("user", "Customer message", "Free text or a file", ""),
            ("ai", "Conversation Agent", "How the message relates to the chat", "New situation, correction, answer, what-if, general"),
            ("code", "Safety rules", "Decided by code first", "Misrepresentation, other people's data, account changes"),
            ("ai", "Planner Agent", "Intent, topic and tools", "Documents, deadline, amount, claim progress"),
            ("code", "Guardian", "Checks every tool's permission", "Tiers T0 to T3 and the autonomy mode"),
            ("ai", "Fact Agent", "Sentences into typed facts", "Dates, days in hospital, bill, cause"),
            ("code", "Rules engine", "Computes the verdict per policy", "Coverage, amount, deadline, payer order"),
        ],
        "turn_dec": "Would one missing fact change the verdict?",
        "turn_yes": ("ai", "Ask one question", "That fact only, with answer buttons", ""),
        "turn_no": ("ai", "Explainer Agent", "Writes two candidate replies", "A verifier matches numbers and dates to the engine"),
        "turn_end": ("code", "Answer and audit", "Evidence cards, clause quotes, audit record", ""),
        "yes": "Yes", "no": "No",
        "tier_title": "Permission flow for every agent action",
        "tier_start": ("ai", "The agent wants to act", "Every tool call passes the Guardian", ""),
        "tiers": [
            ("code", "T0 and T1", "Read and compute", "Run automatically on the customer's own account", [("code", "Answer right away", "No effect outside the session", "")]),
            ("user", "T2", "File a claim, attach, appeal", "Needs the customer's confirmation", [("user", "Confirmation card", "The customer taps Confirm", ""), ("code", "Single-use token", "Bound to the exact arguments", ""), ("human", "Lands at the insurer desk", "A person decides", "")]),
            ("stop", "T3", "Money and identity", "No tool can execute it", [("human", "Ticket for staff", "Identity verified through a separate channel", "")]),
        ],
    },
}


def box(kind, tag, title, sub):
    s = f'<span>{sub}</span>' if sub else ""
    return f'<div class="box {kind}"><div class="tag">{tag}</div><b>{title}</b>{s}</div>'


def legend(t):
    return '<div class="legend">' + "".join(f'<div><i style="background:{c}"></i>{n}</div>' for _, c, n in t["legend"]) + "</div>"


def claim_html(t):
    items = "".join((('<div class="down"></div>' if i else "") + box(*b)) for i, b in enumerate(t["claim"]))
    return f'<div class="wrap"><h1>{t["claim_title"]}</h1><div class="col">{items}</div>{legend(t)}</div>'


def turn_html(t):
    items = "".join((('<div class="down"></div>' if i else "") + box(*b)) for i, b in enumerate(t["turn"]))
    dec = f'<div class="down"></div><div class="box dec"><b>{t["turn_dec"]}</b></div>'
    yes = f'<div class="col"><div class="lbl">{t["yes"]}</div>{box(*t["turn_yes"])}</div>'
    no = f'<div class="col"><div class="lbl">{t["no"]}</div>{box(*t["turn_no"])}<div class="down"></div>{box(*t["turn_end"])}</div>'
    return f'<div class="wrap"><h1>{t["turn_title"]}</h1><div class="col">{items}{dec}<div class="down"></div><div class="branch">{yes}{no}</div></div>{legend(t)}</div>'


def tier_html(t):
    cols = []
    for kind, tag, title, sub, chain in t["tiers"]:
        inner = box(kind, tag, title, sub) + "".join('<div class="down"></div>' + box(*c) for c in chain)
        cols.append(f'<div class="col">{inner}</div>')
    head = box(*t["tier_start"])
    return f'<div class="wrap"><h1>{t["tier_title"]}</h1><div class="col">{head}<div class="down"></div><div class="branch">{"".join(cols)}</div></div>{legend(t)}</div>'


def main():
    OUT.mkdir(exist_ok=True)
    pages = []
    for lang, t in T.items():
        for name, fn in (("claim", claim_html), ("turn", turn_html), ("tier", tier_html)):
            html = HERE / f"_flow_{name}_{lang}.html"
            html.write_text(f"<!doctype html><html><head><meta charset='utf-8'><style>{CSS}</style></head><body>{fn(t)}</body></html>", encoding="utf-8")
            pages.append((html, OUT / f"flow_{name}_{lang}.png"))
    js = "const {chromium}=require('@playwright/test');(async()=>{const b=await chromium.launch();const p=await b.newPage({deviceScaleFactor:2});"
    for html, png in pages:
        js += f"await p.goto('file:///{html.as_posix()}');await (await p.$('.wrap')).screenshot({{path:'{png.as_posix()}'}});"
    js += "await b.close();})();"
    script = WEB / "_flows.cjs"
    script.write_text(js, encoding="utf-8")
    subprocess.run(["node", str(script)], cwd=WEB, check=True)
    script.unlink()
    for html, _ in pages:
        html.unlink()
    print("wrote", [p.name for _, p in pages])


if __name__ == "__main__":
    main()
