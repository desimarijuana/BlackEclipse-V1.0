"""Thread-safe connection pooling for a single SQLite file.

`AgentMemoryStore` is shared across FastAPI worker threads and async tasks, so it
must not hand one `sqlite3.Connection` to several threads at once: concurrent
`execute`/`commit` on a shared connection can raise `SystemError: error return
without exception set` or interleave transactions, even with
`check_same_thread=False`.

`ThreadLocalConnections` gives each thread its **own** connection in autocommit
mode (`isolation_level=None`). SQLite WAL (set in the schema) lets many readers
run alongside one writer, and autocommit + `busy_timeout` make a second writer
wait for the write lock instead of failing on a deferred read-to-write upgrade
(the classic `database is locked`). Connections are tracked so `close()` can
release them at shutdown; per-connection pragmas (foreign keys, busy timeout) are
re-applied on every connection.
"""

from __future__ import annotations

import sqlite3
import threading

BUSY_TIMEOUT_MS = 5000


class ThreadLocalConnections:
    """A pool of one SQLite connection per thread for a single database file."""

    def __init__(self, path: str) -> None:
        self.path = path
        self._local = threading.local()
        self._connections: set[sqlite3.Connection] = set()
        self._lock = threading.Lock()

    def _connect(self) -> sqlite3.Connection:
        # `isolation_level=None` = autocommit; `timeout` is the busy timeout for
        # the connect-time write lock.
        db = sqlite3.connect(
            self.path, timeout=BUSY_TIMEOUT_MS / 1000.0,
            check_same_thread=False, isolation_level=None,
        )
        db.row_factory = sqlite3.Row
        # WAL/synchronous are persistent schema pragmas; these are per-connection.
        db.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
        db.execute("PRAGMA foreign_keys = ON")
        with self._lock:
            self._connections.add(db)
        return db

    @property
    def db(self) -> sqlite3.Connection:
        db = getattr(self._local, "db", None)
        if db is None:
            db = self._connect()
            self._local.db = db
        return db

    def close(self) -> None:
        """Close every tracked connection (idempotent; safe at shutdown)."""
        with self._lock:
            connections = list(self._connections)
            self._connections.clear()
        for db in connections:
            try:
                db.close()
            except Exception:  # noqa: BLE001 - best-effort cleanup
                pass
        self._local = threading.local()


__all__ = ["ThreadLocalConnections", "BUSY_TIMEOUT_MS"]
