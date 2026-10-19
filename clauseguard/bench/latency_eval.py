"""Chat turn latency through the FastAPI sandbox, measured in process (no network hop).

  offline   CG_OFFLINE=1, no model call: the rules engine and planner only (20 turns)
  live      the configured Gemini keys answer (5 turns, each tagged unique so the response cache is skipped).
            Includes key rotation when a quota runs out

Usage: python -m bench.latency_eval offline|live
Writes evidence/latency_report.md. Numbers depend on the machine and on the model service.
"""
from __future__ import annotations

import os
import statistics
import sys
import tempfile
import time
import uuid
from pathlib import Path

MODE = sys.argv[1] if len(sys.argv) > 1 else "offline"
if MODE not in {"offline", "live"}:
    raise SystemExit("usage: python -m bench.latency_eval offline|live")

os.environ["CG_DB_PATH"] = os.path.join(tempfile.mkdtemp(), "s.sqlite")
os.environ["CG_AUDIT_PATH"] = os.path.join(tempfile.mkdtemp(), "a.jsonl")
os.environ["CG_STORAGE"] = "local"
os.environ["CG_AUTH"] = ""
os.environ["DATABASE_URL"] = ""
if MODE == "offline":
    os.environ["CG_OFFLINE"] = "1"

from fastapi.testclient import TestClient  # noqa: E402

from clauseguard.sandbox import api  # noqa: E402

QUESTIONS = [
    "Aku dirawat 3 hari karena DBD, apakah ditanggung?",
    "Berapa batas waktu klaim untuk rawat inap?",
    "Polis mana yang harus ditagih lebih dulu?",
    "Kalau dirawat 5 hari, berapa yang saya dapat?",
    "Apa yang harus kusiapkan untuk klaim?",
]


def main() -> None:
    questions = QUESTIONS * 4 if MODE == "offline" else [f"{q} (ref {uuid.uuid4().hex[:6]})" for q in QUESTIONS]  # a unique tag keeps the model cache from answering
    times: list[float] = []
    with TestClient(api.app) as c:
        headers = {"X-Session-Token": c.post("/login", json={"persona": "rizky"}).json()["session_token"]}
        for q in questions:
            t0 = time.perf_counter()
            r = c.post("/chat", json={"text": q}, headers=headers)
            times.append(time.perf_counter() - t0)
            r.raise_for_status()
    times.sort()
    line = (f"| {MODE} | {len(times)} | {statistics.median(times):.2f} s | {times[max(0, int(0.9 * len(times)) - 1)]:.2f} s | {times[-1]:.2f} s |")
    print(line)
    out = Path(__file__).resolve().parents[1] / "evidence" / "latency_report.md"
    head = "# Chat turn latency\n\nMeasured in process through the FastAPI sandbox on one developer machine. `live` includes key rotation when a quota ran out.\n\n| mode | turns | median | p90 | max |\n|---|---|---|---|---|\n"
    rows = [ln for ln in (out.read_text(encoding="utf-8").splitlines() if out.exists() else []) if ln.startswith("| ") and not ln.startswith("| mode") and not ln.startswith(f"| {MODE} ")]
    out.write_text(head + "\n".join(rows + [line]) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
