"""Durable per-run event sequence (W6).

`RunEmitter._seq` used to be per instance, and `HarnessEvent` had only a
non-unique index on `(runId, seq)`. Two emitters for one run (a resume beside a
live path, the watchdog beside the owner) could allocate the same seq, and the
second INSERT was dropped by the primary key/constraint path.

This module owns the ONE allocator:

    BEGIN IMMEDIATE
      seq = COALESCE(MAX(seq), 0) + 1
      insert with id = evt_<run>_<seq>
    COMMIT

It also performs the one-time repair needed before the unique index can exist:
legacy duplicate seqs are renumbered deterministically (by `at`, then rowid),
preserving every row. The repair is idempotent and safe to run on every boot.

The module is deliberately small and owns no schema beyond the index it adds.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from typing import Any, Optional

from .persistence import now_iso

log = logging.getLogger("harness.event_sequence")

UNIQUE_INDEX = "idx_harness_event_run_seq_unique"


def _notify(event_type: str, data: dict[str, Any], *, run_id: str = "") -> None:
    """W8 telemetry for the allocator. Fail-open; never affects allocation."""
    try:
        from .observability.bridge import publish  # noqa: PLC0415

        publish(event_type, data, run_id=run_id)
    except Exception:  # noqa: BLE001 - telemetry must not break the allocator
        pass


class EventSequence:
    """Per-store event allocator over the ONE agent-memory connection."""

    def __init__(self, store: Any) -> None:
        self._store = store
        self._ready = False
        # The store exposes ONE sqlite connection per THREAD. Two threads cannot
        # both run BEGIN IMMEDIATE on the same connection; an in-process lock
        # serializes allocation, while the transaction serializes across
        # processes. The connection is resolved per call, never cached.
        self._lock = threading.RLock()

    @property
    def _db(self) -> Any:
        return getattr(self._store, "_db", None)

    def _ensure(self) -> None:
        if self._ready or self._db is None:
            return
        with self._lock:
            if self._ready:
                return
            self._ready = True
            try:
                self._db.execute("BEGIN IMMEDIATE")
                try:
                    self._repair_duplicates_locked()
                    self._db.execute(
                        f"CREATE UNIQUE INDEX IF NOT EXISTS {UNIQUE_INDEX} "
                        "ON HarnessEvent(runId, seq)"
                    )
                    self._db.execute("COMMIT")
                except Exception:
                    self._db.execute("ROLLBACK")
                    raise
            except Exception:  # noqa: BLE001 - the allocator degrades, never crashes boot
                log.warning("event sequence repair failed; collisions may still occur", exc_info=True)

    def _repair_duplicates_locked(self) -> None:
        """Renumber a run whose legacy rows share a seq.

        Every row is preserved; only `seq` changes. The order is `at`, then
        rowid — the same order a reader sees today, so no event changes place.
        """
        duplicates = self._db.execute(
            "SELECT runId FROM HarnessEvent GROUP BY runId, seq "
            "HAVING COUNT(*) > 1"
        ).fetchall()
        for row in duplicates:
            run_id = row["runId"]
            rows = self._db.execute(
                "SELECT id FROM HarnessEvent WHERE runId=? ORDER BY at ASC, rowid ASC",
                (run_id,),
            ).fetchall()
            for index, event in enumerate(rows):
                self._db.execute(
                    "UPDATE HarnessEvent SET seq=? WHERE id=?", (index + 1, event["id"])
                )

    def append(
        self, run_id: str, event_type: str, data: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Allocate+insert one durable event. Retries once on a forced collision."""
        if self._db is None:
            raise RuntimeError("event sequence needs a sqlite-backed store")
        self._ensure()
        with self._lock:
            return self._append_locked(run_id, event_type, data)

    def _append_locked(
        self, run_id: str, event_type: str, data: Optional[dict[str, Any]],
    ) -> dict[str, Any]:
        last_error: Optional[Exception] = None
        for _attempt in range(2):
            try:
                self._db.execute("BEGIN IMMEDIATE")
                try:
                    row = self._db.execute(
                        "SELECT COALESCE(MAX(seq), 0) AS m FROM HarnessEvent WHERE runId=?",
                        (run_id,),
                    ).fetchone()
                    seq = int(row["m"]) + 1
                    event = {
                        "id": f"evt_{run_id}_{seq}",
                        "runId": run_id,
                        "type": event_type,
                        "seq": seq,
                        "at": now_iso(),
                        "data": data or {},
                    }
                    self._db.execute(
                        "INSERT INTO HarnessEvent (id, runId, type, seq, at, data) "
                        "VALUES (?, ?, ?, ?, ?, ?)",
                        (event["id"], run_id, event_type, seq, event["at"],
                         json.dumps(event["data"])),
                    )
                    self._db.execute("COMMIT")
                    return event
                except Exception:
                    self._db.execute("ROLLBACK")
                    raise
            except sqlite3.IntegrityError as exc:
                last_error = exc
                _notify("event.seq_retry", {"attempt": _attempt + 1}, run_id=run_id)
                continue
        _notify("event.seq_collision", {"attempts": 2}, run_id=run_id)
        raise RuntimeError(f"could not allocate an event sequence for {run_id!r}") from last_error


_CACHE: dict[int, EventSequence] = {}


def get_event_sequence(store: Any) -> Optional[EventSequence]:
    """The allocator for a store, or None when it is not sqlite-backed."""
    if not hasattr(store, "_db"):
        return None
    key = id(store)
    sequence = _CACHE.get(key)
    if sequence is None or sequence._store is not store:  # noqa: SLF001 - cache identity
        sequence = EventSequence(store)
        _CACHE[key] = sequence
    return sequence


def append_durable(
    store: Any, run_id: str, event_type: str, data: Optional[dict[str, Any]] = None,
) -> Optional[dict[str, Any]]:
    """Append an event through the allocator, with a safe legacy fallback.

    Call sites that used a hard-coded seq (for example `0`) now go through here;
    the unique `(runId, seq)` index would otherwise reject a second such event.
    Never raises: an audit event must not break a run.
    """
    sequence = get_event_sequence(store)
    if sequence is not None:
        try:
            return sequence.append(run_id, event_type, data)
        except Exception:  # noqa: BLE001 - fall through to the legacy append
            pass
    try:
        next_seq = max((e.get("seq", 0) for e in store.list_events(run_id)), default=0) + 1
        return store.append_event(run_id, event_type, next_seq, data)
    except Exception:  # noqa: BLE001 - telemetry only
        return None


__all__ = [
    "EventSequence",
    "UNIQUE_INDEX",
    "append_durable",
    "get_event_sequence",
]
