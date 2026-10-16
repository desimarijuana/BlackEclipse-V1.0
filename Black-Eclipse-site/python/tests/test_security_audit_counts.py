"""`/health` must never 500 on the security audit summary.

`SecurityStore.audit_counts` feeds `GET /health`. The front door treats a 500
there as "runtime down" and restarts — orphaning in-flight runs — so a single
malformed/NULL aggregate row must degrade to "skipped", never raise.
"""

from __future__ import annotations

import os
import tempfile

import pytest

from harness.persistence import AgentMemoryStore, DB_FILENAME
from harness.security.store import SecurityStore, _as_int


@pytest.fixture()
def security_store():
    directory = tempfile.mkdtemp(prefix="be-sec-counts-")
    memory = AgentMemoryStore(os.path.join(directory, DB_FILENAME))
    yield memory, SecurityStore(memory)
    memory.close()


def test_as_int_coerces_and_is_null_safe():
    assert _as_int(3) == 3
    assert _as_int("4") == 4
    assert _as_int(None) is None
    assert _as_int("not-a-number") is None


def test_audit_counts_reports_real_groups(security_store):
    memory, security = security_store
    for category, decision in (("authorization", "allow"), ("authorization", "deny"), ("isolation", "allow")):
        memory._db.execute(
            "INSERT INTO SecurityAuditEvent (id, timestamp, category, type, decision, hash) "
            "VALUES (?, ?, ?, 'test', ?, 'h')",
            (f"a-{category}-{decision}", 1.0, category, decision),
        )
    counts = security.audit_counts()
    assert counts["total"] == 3
    assert counts["byCategory"] == {"authorization": 2, "isolation": 1}
    assert counts["byDecision"] == {"allow": 2, "deny": 1}


def test_audit_counts_skips_null_count_rows(security_store):
    # Simulate the malformed aggregate row that produced a real `/health` 500:
    # a NULL `c`. The summary must skip it, not raise. `_db` is swapped for a
    # fake connection because a built-in sqlite3.Connection cannot be patched.
    _memory, security = security_store

    class _Cursor:
        def __init__(self, rows):
            self._rows = rows

        def fetchall(self):
            return self._rows

        def fetchone(self):
            return self._rows[0] if self._rows else None

    class _FakeConn:
        def execute(self, sql, *args):
            if "GROUP BY category" in sql:
                return _Cursor([{"category": "authorization", "c": None}])
            if "GROUP BY decision" in sql:
                return _Cursor([{"decision": None, "c": None}])
            return _Cursor([{"c": 1}])

    class _FakeStore:
        _db = _FakeConn()

    security._store = _FakeStore()  # noqa: SLF001 - swap the SQL edge for a fake

    counts = security.audit_counts()
    assert counts["byCategory"] == {}
    assert counts["byDecision"] == {}
    assert counts["total"] == 1
