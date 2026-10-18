"""The Postgres audit store chains events in memory and stores them behind the request, without ever forking."""
from __future__ import annotations

from clauseguard.security import audit
from clauseguard.storage.audit_backend import PgAuditStore, verify_events


class _FakeDb(PgAuditStore):
    """The store with its two database hooks replaced by a list, so no Postgres is needed."""

    def __init__(self, stored=None):
        super().__init__(pool=object())  # type: ignore[arg-type]
        self.rows: list[dict] = list(stored or [])
        self.calls = 0

    def _read_head(self):
        return (self.rows[-1]["seq"], self.rows[-1]["hash"]) if self.rows else (0, audit.GENESIS)

    def _write_batch(self, batch):
        self.calls += 1
        head = self._read_head()
        if (batch[0]["seq"] - 1, batch[0]["prev_hash"]) != head:
            return False
        self.rows.extend(dict(e) for e in batch)
        return True


def _event(i):
    return {"event_type": "USER_MSG", "session_id": "S-1", "user_id": "U-1", "reason": f"m{i}"}


def test_events_are_chained_immediately_and_stored_in_order():
    st = _FakeDb()
    evs = [st.append_chained(_event(i)) for i in range(25)]
    assert [e["seq"] for e in evs] == list(range(1, 26))  # ids known to the caller before anything is stored
    assert st.flush(10)
    assert verify_events(st.rows, (25, st.rows[-1]["hash"]))["ok"]
    assert st.calls < 25  # batched, not one round trip per event


def test_a_second_writer_never_forks_the_chain():
    st = _FakeDb()
    st.append_chained(_event(0))
    assert st.flush(10)
    # another process appends to the stored chain behind this one's back
    other = PgAuditStore.__mro__[0]
    prev = st.rows[-1]
    from clauseguard.storage.audit_backend import _stamp

    st.rows.append(_stamp(_event("other"), prev["seq"] + 1, prev["hash"]))
    mine = [st.append_chained(_event(i)) for i in range(1, 6)]
    assert st.flush(10)
    assert other is PgAuditStore
    assert verify_events(st.rows, (len(st.rows), st.rows[-1]["hash"]))["ok"]
    assert len(st.rows) == 7
    assert [e["seq"] for e in mine] == [e["seq"] for e in st.rows[2:]]  # the callers' event objects were re-chained in place
