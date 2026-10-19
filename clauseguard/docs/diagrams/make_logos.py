"""Figure of the products ClauseGuard is compared with (HTML rendered to PNG with Playwright).

python docs/diagrams/make_logos.py  ->  docs/img/competitors_{id,en}.png
Logos are the owners' marks, used only to identify the products compared (docs/img/logos).
"""
from __future__ import annotations

import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "img"
LOGOS = OUT / "logos"
WEB = HERE.parents[2] / "clauseguard-web"

CSS = """
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Segoe UI',Inter,Arial,sans-serif;background:#fff;color:#141A29}
.wrap{padding:28px 32px;width:1180px}
h1{font-size:20px;font-weight:700;margin-bottom:18px}
.grid{display:grid;grid-template-columns:1.4fr 1fr 1.2fr;gap:18px}
.grp{border:2px solid #E1E4EA;border-radius:14px;padding:14px 16px}
.grp h2{font-size:13px;font-weight:700;color:#1C58E3;letter-spacing:.3px;margin-bottom:12px;text-transform:uppercase}
.items{display:flex;flex-wrap:wrap;gap:10px}
.item{display:flex;align-items:center;gap:8px;border:1.5px solid #E1E4EA;border-radius:10px;padding:8px 12px;font-size:14px;font-weight:600;background:#FBFCFD}
.item img{width:30px;height:30px;border-radius:6px;object-fit:contain}
.item small{display:block;font-size:11px;font-weight:400;color:#677083}
.note{font-size:11px;color:#677083;margin-top:14px}
"""

T = {
    "id": {
        "title": "Produk dan layanan yang menjadi pembanding",
        "groups": [
            ("Asisten virtual asuransi Indonesia", [("Garxia", "Astra"), ("Vania", "Aswata"), ("Hummi", "Cakrawala Proteksi"), ("Asisten Tripa", "Tripa"), ("WE+", "WINA")]),
            ("Asuransi digital dengan klaim berbasis AI", [("Lemonade", "Maya dan AI Jim", "lemonade.png")]),
            ("Marketplace dan perbandingan produk", [("Lifepal", "", "lifepal.png"), ("Qoala", "", "qoala.png"), ("PasarPolis", "")]),
        ],
        "note": "Logo adalah milik pemiliknya masing-masing dan hanya dipakai untuk menandai produk yang dibandingkan.",
    },
    "en": {
        "title": "Products and services used for comparison",
        "groups": [
            ("Indonesian insurer virtual assistants", [("Garxia", "Astra"), ("Vania", "Aswata"), ("Hummi", "Cakrawala Proteksi"), ("Tripa assistant", "Tripa"), ("WE+", "WINA")]),
            ("Digital insurer with AI claims", [("Lemonade", "Maya dan AI Jim", "lemonade.png")]),
            ("Marketplaces and product comparison", [("Lifepal", "", "lifepal.png"), ("Qoala", "", "qoala.png"), ("PasarPolis", "")]),
        ],
        "note": "Logos belong to their owners and are used only to identify the products compared.",
    },
}


def item(spec) -> str:
    name, sub, *logo = spec
    img = f'<img src="file:///{(LOGOS / logo[0]).as_posix()}">' if logo else ""
    small = f"<small>{sub}</small>" if sub else ""
    return f'<div class="item">{img}<div>{name}{small}</div></div>'


def page(t) -> str:
    groups = "".join(f'<div class="grp"><h2>{h}</h2><div class="items">{"".join(item(i) for i in items)}</div></div>' for h, items in t["groups"])
    return f'<div class="wrap"><h1>{t["title"]}</h1><div class="grid">{groups}</div><div class="note">{t["note"]}</div></div>'


def main():
    pages = []
    for lang, t in T.items():
        html = HERE / f"_logos_{lang}.html"
        html.write_text(f"<!doctype html><html><head><meta charset='utf-8'><style>{CSS}</style></head><body>{page(t)}</body></html>", encoding="utf-8")
        pages.append((html, OUT / f"competitors_{lang}.png"))
    js = "const {chromium}=require('@playwright/test');(async()=>{const b=await chromium.launch();const p=await b.newPage({deviceScaleFactor:2});"
    for html, png in pages:
        js += f"await p.goto('file:///{html.as_posix()}');await (await p.$('.wrap')).screenshot({{path:'{png.as_posix()}'}});"
    js += "await b.close();})();"
    script = WEB / "_logos.cjs"
    script.write_text(js, encoding="utf-8")
    subprocess.run(["node", str(script)], cwd=WEB, check=True)
    script.unlink()
    for html, _ in pages:
        html.unlink()
    print("wrote", [p.name for _, p in pages])


if __name__ == "__main__":
    main()
