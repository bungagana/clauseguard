"""Record one complete sandbox operation as execution evidence (evidence/claims_desk_run.md).

Against a running backend (default http://127.0.0.1:8000): log in as the Rizky persona, upload the four
sample claim documents, describe the stay, let the assistant prepare the insurer's claim form, confirm the
submission, approve the claim at the back-office desk with a note, and read the decision back from the
customer's digest. Needs CG_ADMIN_TOKEN in the environment (or .env) for the desk step.

Usage: python scripts/claims_desk_evidence.py [--base URL] [--persona rizky]
"""
from __future__ import annotations

import argparse
import glob
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "data" / "demo" / "claim_docs"
OUT = ROOT / "evidence" / "claims_desk_run.md"
MESSAGE = "I was admitted for dengue on 25 September 2026 at RS Sehat Sentosa, discharged 28 September. Here are my hospital documents."


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    ap.add_argument("--persona", default="rizky")
    args = ap.parse_args()
    base = args.base.rstrip("/")
    admin = os.getenv("CG_ADMIN_TOKEN", "")
    if not admin:
        try:
            from dotenv import load_dotenv

            load_dotenv(ROOT / ".env")
            admin = os.getenv("CG_ADMIN_TOKEN", "")
        except ImportError:
            pass
    if not admin:
        print("CG_ADMIN_TOKEN is not set; the desk step cannot run", file=sys.stderr)
        return 2

    lines: list[str] = ["# Claims desk run", "", f"Generated {datetime.now(timezone.utc).isoformat(timespec='seconds')} against `{base}`. "
                        "Every value below is copied from API responses; nothing is edited by hand.", ""]
    tok = requests.post(f"{base}/login", json={"persona": args.persona}, timeout=30).json()["session_token"]
    h = {"X-Session-Token": tok}

    ids = []
    lines += ["## 1. Uploads", ""]
    for p in sorted(glob.glob(str(DOCS / "*.pdf"))):
        with open(p, "rb") as fh:
            up = requests.post(f"{base}/upload", files={"file": (Path(p).name, fh, "application/pdf")}, headers=h, timeout=60).json()
        ids.append(up["doc_id"])
        lines.append(f"- `{Path(p).name}` -> `{up['doc_id']}` (label {up['label']})")

    lines += ["", "## 2. Conversation", ""]
    r = requests.post(f"{base}/chat", json={"text": MESSAGE, "uploads": ids}, headers=h, timeout=300).json()
    lines += [f"**Customer:** {MESSAGE}", "", f"**Assistant:** {r['text']}", ""]
    pending = [a for a in r.get("actions_pending", []) if a.get("tool") == "submit_claim"]
    if not pending:
        r = requests.post(f"{base}/chat", json={"text": "Submit the HCP claim for me.", "uploads": []}, headers=h, timeout=300).json()
        lines += ["**Customer:** Submit the HCP claim for me.", "", f"**Assistant:** {r['text']}", ""]
    pend = requests.get(f"{base}/chat/pending", headers=h, timeout=30).json()["pending"]
    sub = next((p for p in pend if p["tool"] == "submit_claim"), None)
    if sub is None:
        lines.append("No pending submission was prepared; run aborted.")
        OUT.write_text("\n".join(lines), encoding="utf-8")
        return 1
    draft = sub["args"]["draft_handle"]["value"]

    lines += ["## 3. Confirmation card and the insurer's form", "", f"Summary shown to the customer: {sub['summary']}", "",
              f"Form: **{draft.get('form_title')}** (layout source: {draft.get('form_layout_source')}; attachments: {len(draft.get('document_handles', []))})", ""]
    for sec in draft.get("form_sections", []):
        lines.append(f"**{sec['title']}**")
        for f in sec["fields"]:
            v = f["value"]
            if isinstance(v, list) and v and isinstance(v[0], dict):
                v = "; ".join(f"[{c.get('state', 'attached' if c.get('attached') else 'missing')}] {c['label']}" for c in v)
            txt = v if f["state"] == "filled" else f"({f['state'].replace('_', ' ')})"
            lines.append(f"- {f['label']}: {txt}")
        lines.append("")

    idx = pend.index(sub)
    c = requests.post(f"{base}/chat/confirm", json={"index": idx}, headers=h, timeout=300).json()
    claim_id = next((cl.get("claim_id") or cl.get("id") for cl in (c.get("open_claims") or []) if cl), None)
    if claim_id is None:
        import re

        m = re.search(r"CL-[A-Z0-9]{8}", c.get("text", ""))
        claim_id = m.group(0) if m else None
    lines += ["## 4. Submission", "", f"**Assistant after Confirm:** {c.get('text', '')}", "", f"Claim id: `{claim_id}`", ""]
    audit = requests.get(f"{base}/audit", headers=h, timeout=30).json()
    evs = [e for e in audit.get("events", []) if e.get("event_type") in ("CONFIRM_ISSUED", "CONFIRM_USED", "TOOL_ALLOW", "DOC_INGEST")]
    lines += [f"Audit chain verified: {audit.get('chain_ok')}; events for this session (selected): " +
              ", ".join(f"seq {e['seq']} {e['event_type']}{(' ' + e['tool']) if e.get('tool') else ''}" for e in evs[-8:]), ""]

    ah = {"X-Admin-Token": admin}
    desk = requests.get(f"{base}/backoffice/claims/{claim_id}", headers=ah, timeout=30).json()
    lines += ["## 5. Insurer's desk", "", f"Status on arrival: {desk.get('status')}; documents filed: " +
              ", ".join(f"{d['type']} ({d['taint_label']})" for d in desk.get("documents", [])), ""]
    note = "Approved at the policy limit; itemised bill and medical resume verified."
    requests.post(f"{base}/backoffice/claims/{claim_id}/decide", json={"decision": "under_review", "note": "Documents received."}, headers=ah, timeout=30)
    dec = requests.post(f"{base}/backoffice/claims/{claim_id}/decide", json={"decision": "approved", "note": note}, headers=ah, timeout=30).json()
    lines += [f"Decision recorded: {dec.get('status')} with note \"{note}\"", ""]

    dig = requests.get(f"{base}/entitlement/digest", headers=h, timeout=60).json()
    item = next((i for i in dig.get("items", []) if i.get("claim_id") == claim_id), None)
    lines += ["## 6. What the customer sees next", "", (item.get("message_en") if item else "(no digest item found)"), ""]
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print("wrote", OUT, "| claim", claim_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
