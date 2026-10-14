"""Run the ClauseGuard demo: sandbox insurer API + the single-page UI on http://127.0.0.1:8000

    python scripts/serve.py              # serve on port 8000
    python scripts/serve.py --fresh      # re-seed the sandbox database first (clears demo tickets/claims)
    python scripts/serve.py --port 8080 --reload

The UI is served from ui/ at "/", the API under its usual routes (/login, /chat, /tools/{name}, ...) and the
UI read models (/policies, /portfolio, /entitlement/*). The entitlement modules are optional: when one is not
installed its card in the UI shows "not available" and the rest of the demo is unaffected.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--reload", action="store_true", help="uvicorn auto-reload (development)")
    ap.add_argument("--fresh", action="store_true", help="delete and re-seed data/sandbox.sqlite before starting")
    ap.add_argument("--release-kill-switch", action="store_true", help="remove a leftover AGENT_HALT flag before starting")
    a = ap.parse_args()

    from clauseguard import config

    if a.fresh:
        for suffix in ("", "-shm", "-wal"):
            p = Path(str(config.DB_PATH) + suffix)
            if p.exists():
                p.unlink()
        print(f"[serve] removed {config.DB_PATH}; it will be re-seeded on first request")
    if a.release_kill_switch:
        from clauseguard.security import kill_switch

        if kill_switch.is_active():
            kill_switch.deactivate(actor="serve.py")
            print("[serve] kill switch released")

    import uvicorn

    print(f"[serve] ClauseGuard demo UI: http://{a.host}:{a.port}/   (API docs: http://{a.host}:{a.port}/docs)")
    uvicorn.run("clauseguard.sandbox.api:app", host=a.host, port=a.port, reload=a.reload, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
