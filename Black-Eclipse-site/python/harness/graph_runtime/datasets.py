"""Bounded local datasets for the graph runtime.

A graph should not have to move a 50 MB series through JSON config or a run
record. This store keeps a JSON payload on the runtime's OWN `agent-memory.db`
connection and returns a small, stable reference (`gds_<uuid>`) that can travel
between nodes and runs.

Deliberately local scratch, not a market-data source and not a second JDDS:

* Nothing is fabricated. A missing/expired ref is an explicit failure.
* A payload is capped (`MAX_DATASET_BYTES`) and the store is capped
  (`MAX_DATASETS`), so a runaway graph cannot fill the disk.
* Values must be JSON-serializable and finite; a numpy array is not silently
  stringified.
* Every dataset is owned by this table; no other subsystem reads it.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
from typing import Any, Optional

from ..persistence import new_id, now_iso

MAX_DATASET_BYTES = 8_000_000
MAX_DATASETS = 200

_SCHEMA = """
CREATE TABLE IF NOT EXISTS HarnessGraphDataset (
  id          TEXT PRIMARY KEY,
  ownerId     TEXT NOT NULL DEFAULT 'local',
  name        TEXT NOT NULL,
  valueType   TEXT NOT NULL,
  bytes       INTEGER NOT NULL,
  rows        INTEGER,
  contentHash TEXT NOT NULL,
  payload     TEXT NOT NULL,
  createdAt   TEXT NOT NULL,
  expiresAt   TEXT
);
CREATE INDEX IF NOT EXISTS idx_graph_dataset_created ON HarnessGraphDataset(createdAt);
CREATE INDEX IF NOT EXISTS idx_graph_dataset_expiry  ON HarnessGraphDataset(expiresAt);
"""


class DatasetError(RuntimeError):
    """Base class for dataset failures with a user-facing message."""


class DatasetTooLarge(DatasetError):
    pass


class DatasetSerializationError(DatasetError):
    pass


class DatasetNotFound(DatasetError):
    pass


class DatasetExpired(DatasetError):
    pass


class GraphDatasetStore:
    """JSON payloads + refs on the ONE agent-memory connection."""

    def __init__(self, store: Any) -> None:
        self._store = store
        self._ensure_schema()

    @property
    def _db(self):
        return self._store._db

    def _ensure_schema(self) -> None:
        self._db.executescript(_SCHEMA)
        columns = {
            row["name"] for row in self._db.execute("PRAGMA table_info(HarnessGraphDataset)")
        }
        if "ownerId" not in columns:
            self._db.execute(
                "ALTER TABLE HarnessGraphDataset ADD COLUMN ownerId TEXT NOT NULL DEFAULT 'local'"
            )
        self._db.commit()

    @staticmethod
    def ref_of(dataset_id: str) -> str:
        return f"gds:{dataset_id}"

    @staticmethod
    def id_of(ref: str) -> str:
        value = (ref or "").strip()
        if value.startswith("gds:"):
            return value[4:]
        return value

    @staticmethod
    def _serialize(value: Any) -> tuple[str, str, int, Optional[int]]:
        try:
            text = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise DatasetSerializationError(
                f"dataset value must be finite JSON, not {type(value).__name__}: {exc}"
            ) from exc
        encoded = text.encode("utf-8")
        value_type = "array" if isinstance(value, list) else "object" if isinstance(value, dict) else type(value).__name__
        rows = len(value) if isinstance(value, list) else None
        return text, value_type, len(encoded), rows

    def save(self, name: str, value: Any, *, ttl_seconds: int = 0,
             owner: str = "local") -> dict[str, Any]:
        text, value_type, size, rows = self._serialize(value)
        if size > MAX_DATASET_BYTES:
            raise DatasetTooLarge(
                f"dataset is {size} bytes; the limit is {MAX_DATASET_BYTES}. Save a smaller slice or use a dataset tool."
            )
        if ttl_seconds < 0:
            raise DatasetError("ttl_seconds cannot be negative")
        self.purge_expired()
        count = self._db.execute("SELECT COUNT(*) AS n FROM HarnessGraphDataset").fetchone()["n"]
        if count >= MAX_DATASETS:
            raise DatasetError(
                f"dataset store holds {count} datasets (limit {MAX_DATASETS}); delete an old one first."
            )

        dataset_id = new_id("gds")
        created_at = now_iso()
        expires_at = None
        if ttl_seconds:
            expires = _dt.datetime.now(_dt.timezone.utc) + _dt.timedelta(seconds=ttl_seconds)
            expires_at = expires.strftime("%Y-%m-%dT%H:%M:%S") + ".000Z"
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()

        self._db.execute(
            """INSERT INTO HarnessGraphDataset
               (id, ownerId, name, valueType, bytes, rows, contentHash, payload, createdAt, expiresAt)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (dataset_id, str(owner or "local")[:120], (name or "dataset")[:200],
             value_type, size, rows, digest, text, created_at, expires_at),
        )
        self._db.commit()
        return {
            "ref": self.ref_of(dataset_id),
            "name": (name or "dataset")[:200],
            "valueType": value_type,
            "bytes": size,
            "rows": rows,
            "contentHash": digest,
            "createdAt": created_at,
            "expiresAt": expires_at,
        }

    def load(self, ref: str, *, owner: str = "local") -> Any:
        dataset_id = self.id_of(ref)
        if not dataset_id:
            raise DatasetNotFound("no dataset reference was supplied")
        row = self._db.execute(
            "SELECT payload, expiresAt, ownerId FROM HarnessGraphDataset WHERE id=?",
            (dataset_id,),
        ).fetchone()
        # A dataset from another owner is reported as missing, not "forbidden":
        # a reference holder must not learn whether it exists.
        if row is None or str(row["ownerId"] or "local") != str(owner or "local")[:120]:
            raise DatasetNotFound(
                f"dataset {ref!r} does not exist (it may have been deleted or created in another runtime)."
            )
        expires_at = row["expiresAt"]
        if expires_at and expires_at <= now_iso():
            self.delete(ref)
            raise DatasetExpired(f"dataset {ref!r} expired at {expires_at}.")
        try:
            return json.loads(row["payload"])
        except json.JSONDecodeError as exc:  # pragma: no cover - our own writes are JSON
            raise DatasetSerializationError(f"dataset {ref!r} is unreadable: {exc}") from exc

    def meta(self, ref: str, *, owner: str = "local") -> dict[str, Any]:
        dataset_id = self.id_of(ref)
        row = self._db.execute(
            "SELECT * FROM HarnessGraphDataset WHERE id=?", (dataset_id,),
        ).fetchone()
        if row is None or str(row["ownerId"] or "local") != str(owner or "local")[:120]:
            raise DatasetNotFound(f"dataset {ref!r} does not exist.")
        return {
            "ref": self.ref_of(row["id"]),
            "name": row["name"],
            "valueType": row["valueType"],
            "bytes": row["bytes"],
            "rows": row["rows"],
            "contentHash": row["contentHash"],
            "createdAt": row["createdAt"],
            "expiresAt": row["expiresAt"],
        }

    def delete(self, ref: str, *, owner: Optional[str] = None) -> int:
        dataset_id = self.id_of(ref)
        if owner is None:
            cursor = self._db.execute(
                "DELETE FROM HarnessGraphDataset WHERE id=?", (dataset_id,),
            )
        else:
            cursor = self._db.execute(
                "DELETE FROM HarnessGraphDataset WHERE id=? AND ownerId=?",
                (dataset_id, str(owner or "local")[:120]),
            )
        self._db.commit()
        return cursor.rowcount

    def list(self, limit: int = 50, *, owner: Optional[str] = None) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 200))
        if owner is None:
            rows = self._db.execute(
                "SELECT * FROM HarnessGraphDataset ORDER BY createdAt DESC LIMIT ?", (limit,),
            ).fetchall()
        else:
            rows = self._db.execute(
                "SELECT * FROM HarnessGraphDataset WHERE ownerId=? ORDER BY createdAt DESC LIMIT ?",
                (str(owner or "local")[:120], limit),
            ).fetchall()
        return [
            {
                "ref": self.ref_of(row["id"]),
                "name": row["name"],
                "valueType": row["valueType"],
                "bytes": row["bytes"],
                "rows": row["rows"],
                "contentHash": row["contentHash"],
                "createdAt": row["createdAt"],
                "expiresAt": row["expiresAt"],
            }
            for row in rows
        ]

    def purge_expired(self) -> int:
        cursor = self._db.execute(
            "DELETE FROM HarnessGraphDataset WHERE expiresAt IS NOT NULL AND expiresAt <= ?",
            (now_iso(),),
        )
        self._db.commit()
        return cursor.rowcount


_store: Optional[GraphDatasetStore] = None


def set_dataset_store(store: Optional[GraphDatasetStore]) -> None:
    global _store
    _store = store


def get_dataset_store() -> Optional[GraphDatasetStore]:
    return _store


def require_dataset_store() -> GraphDatasetStore:
    if _store is None:
        raise DatasetError(
            "no dataset store is configured in this runtime; datasets are available once the graph layer boots."
        )
    return _store


__all__ = [
    "MAX_DATASET_BYTES",
    "MAX_DATASETS",
    "DatasetError",
    "DatasetTooLarge",
    "DatasetSerializationError",
    "DatasetNotFound",
    "DatasetExpired",
    "GraphDatasetStore",
    "set_dataset_store",
    "get_dataset_store",
    "require_dataset_store",
]
