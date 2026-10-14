from __future__ import annotations

import logging
import threading
from collections import Counter

log = logging.getLogger("clauseguard.storage")
_lock = threading.Lock()
_counts: Counter = Counter()


def degraded(component: str, err: BaseException | str) -> None:
    with _lock:
        _counts["storage_degraded"] += 1
        _counts[f"storage_degraded.{component}"] += 1
    log.warning("storage degraded component=%s error=%s", component, err if isinstance(err, str) else type(err).__name__)


def counters() -> dict[str, int]:
    with _lock:
        return dict(_counts)
