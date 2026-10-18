"""Record the complete claim flow from a real backend run as a replay scene for the web client.

Runs: upload four hospital documents, describe the stay, let the assistant prepare the insurer's form,
confirm the submission, approve it at the back-office desk, read the decision from the digest. The
responses are written to clauseguard-web/lib/fixtures.claimflow.ts so the site can replay the run when
the backend is not reachable. The scene is labelled as a recording in the UI; nothing here is invented.

Usage: python scripts/record_replay_scene.py [--base http://127.0.0.1:8000] [--persona rizky]
Needs CG_ADMIN_TOKEN (environment or .env) for the desk step.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "data" / "demo" / "claim_docs"
OUT = ROOT.parent / "clauseguard-web" / "lib" / "fixtures.claimflow.ts"
MESSAGE = "I was admitted for dengue on 25 September 2026 at RS Sehat Sentosa, discharged 28 September. Here are my hospital documents."
NOTE = "Approved at the policy limit; itemised bill and medical resume verified."


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    ap.add_argument("--persona", default="rizky")
    args = ap.parse_args()
    base = args.base.rstrip("/")
    admin = os.getenv("CG_ADMIN_TOKEN", "")
    if not admin:
        from dotenv import load_dotenv

        load_dotenv(ROOT / ".env")
        admin = os.getenv("CG_ADMIN_TOKEN", "")
    if not admin:
        print("CG_ADMIN_TOKEN is not set", file=sys.stderr)
        return 2

    login = requests.post(f"{base}/login", json={"persona": args.persona}, timeout=30).json()
    tok = login["session_token"]
    h = {"X-Session-Token": tok}

    docs, ids = [], []
    for p in sorted(glob.glob(str(DOCS / "*.pdf"))):
        with open(p, "rb") as fh:
            up = requests.post(f"{base}/upload", files={"file": (Path(p).name, fh, "application/pdf")}, headers=h, timeout=60).json()
        ids.append(up["doc_id"])
        docs.append({"doc_id": up["doc_id"], "filename": Path(p).name})

    reply = requests.post(f"{base}/chat", json={"text": MESSAGE, "uploads": ids}, headers=h, timeout=400).json()
    pend = requests.get(f"{base}/chat/pending", headers=h, timeout=30).json()["pending"]
    sub = next((p for p in pend if p["tool"] == "submit_claim"), None)
    if sub is None:
        print("no pending submission was prepared; nothing recorded", file=sys.stderr)
        return 1
    draft = sub["args"]["draft_handle"]["value"]
    confirm = requests.post(f"{base}/chat/confirm", json={"index": pend.index(sub)}, headers=h, timeout=400).json()
    claim_id = (re.search(r"CL-[A-Z0-9]{8}", json.dumps(confirm)) or [None])[0]
    if claim_id is None:
        print("no claim id in the confirm response", file=sys.stderr)
        return 1

    ah = {"X-Admin-Token": admin}
    requests.post(f"{base}/backoffice/claims/{claim_id}/decide", json={"decision": "under_review", "note": "Documents received."}, headers=ah, timeout=30)
    requests.post(f"{base}/backoffice/claims/{claim_id}/decide", json={"decision": "approved", "note": NOTE}, headers=ah, timeout=30)
    dig = requests.get(f"{base}/entitlement/digest", headers=h, timeout=60).json()
    item = next((i for i in dig.get("items", []) if i.get("claim_id") == claim_id), None)
    news = item["message_en"] if item else None
    audit = requests.get(f"{base}/audit", headers=h, timeout=30).json()
    seqs = [e["seq"] for e in audit.get("events", []) if isinstance(e.get("seq"), int)]

    scene = {
        "id": "scene4",
        "personaKey": args.persona,
        "title": "From documents to the insurer's decision",
        "summary": "Four hospital documents uploaded together, the insurer's own claim form prepared, confirmed, approved at the claims desk, and the decision returned to the chat.",
        "recorded": {
            "recordedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "claimId": claim_id,
            "auditSeqFrom": min(seqs) if seqs else 0,
            "auditSeqTo": max(seqs) if seqs else 0,
            "backend": "sandbox insurer API, Gemini Flash models",
        },
        "steps": [{"kind": "chat", "userText": MESSAGE, "docs": docs, "reply": reply, "confirmReply": confirm, "claimDraft": draft, "followUpText": news}],
    }
    body = json.dumps(scene, ensure_ascii=False)
    # a recording must never carry credentials
    for secret in (tok, admin, os.getenv("DATABASE_URL", "x" * 40)):
        if secret and secret in body:
            print("a credential appeared in the recording; aborted", file=sys.stderr)
            return 3
    OUT.write_text(
        "// RECORDED from a real run of the ClauseGuard sandbox backend (scripts/record_replay_scene.py).\n"
        "// Replayed in the browser when this scene is opened; no server or model is involved at replay time.\n"
        "// Do not hand edit; record again instead. To remove the scene, delete this file and its import in lib/fixtures.ts.\n"
        'import type { Scene } from "./fixtures";\n\n'
        f"export const CLAIM_FLOW_SCENE: Scene = {body};\n",
        encoding="utf-8",
    )
    print("wrote", OUT, "| claim", claim_id, "| audit seq", scene["recorded"]["auditSeqFrom"], "-", scene["recorded"]["auditSeqTo"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
