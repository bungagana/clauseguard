"""Re-walk the hash-chained audit log and report the first broken sequence number.

Usage: python scripts/verify_audit.py [path]   (default: config.AUDIT_PATH)
       python scripts/verify_audit.py --postgres [--schema NAME]   (chain in DATABASE_URL)
Prints "OK (<n> events)" and exits 0, or "BROKEN at seq <n>" and exits 1.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from clauseguard import config  # noqa: E402
from clauseguard.security import audit  # noqa: E402


def verify_postgres(argv: list[str]) -> int:
    from clauseguard.storage.audit_backend import ChainedAuditLog, PgAuditStore
    from clauseguard.storage.postgres import Pool, StorageError

    schema = argv[argv.index("--schema") + 1] if "--schema" in argv else None
    try:
        rep = ChainedAuditLog(PgAuditStore(Pool(schema=schema))).verify_report()
    except StorageError as e:
        print(f"UNREACHABLE {e}")
        return 2
    for g in rep["gaps"]:
        print(f"GAP at seq {g['seq']}: {g['detail']}")
    if rep["ok"]:
        print(f"OK ({rep['events']} events, {len(rep['gaps'])} declared gaps) postgres")
        return 0
    print(f"BROKEN at seq {rep['first_bad_seq']} postgres (head_matches={rep['head_matches']})")
    return 1


def main(argv: list[str]) -> int:
    if "--postgres" in argv:
        return verify_postgres(argv)
    path = Path(argv[1]) if len(argv) > 1 else Path(config.AUDIT_PATH)
    ok, bad = audit.verify(path)
    if ok:
        n = sum(1 for line in path.open("r", encoding="utf-8") if line.strip()) if path.exists() else 0
        print(f"OK ({n} events) {path}")
        return 0
    print(f"BROKEN at seq {bad} {path}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
