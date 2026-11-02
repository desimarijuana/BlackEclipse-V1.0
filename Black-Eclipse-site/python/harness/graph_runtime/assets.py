"""Bounded local file assets for the graph runtime.

A Graph Studio workflow often starts with a file a person picked — a CSV export,
a broker statement, a JSON dump. This store keeps those bytes on the runtime's
OWN `agent-memory.db` connection (the same database the dataset store uses) and
returns a small, stable reference (`gas_<hash>`) that travels through the graph.

Deliberately a local asset store, not a market-data source and not a second
JDDS:

* Nothing is fabricated. A missing/expired ref is an explicit failure.
* Bytes are content-addressed per owner, so uploading the same file twice reuses
  the row and the disk.
* A file is capped (`MAX_ASSET_BYTES`) and the store is capped by count and total
  size, so a runaway upload cannot fill the disk.
* Image uploads do NOT belong here; they use the vision asset store, which
  already records dimensions and image provenance.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import sqlite3
from typing import Any, Optional

from ..persistence import now_iso

MAX_ASSET_BYTES = 25_000_000
MAX_ASSETS = 200
MAX_TOTAL_BYTES = 512_000_000

#: MIME values this store accepts. Anything else is refused by name rather than
#: silently stored and then failing at parse time.
ALLOWED_MIME_PREFIXES = ("text/", "application/json", "application/csv")
ALLOWED_MIME_EXACT = {
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/octet-stream",
    "application/x-ndjson",
    "application/xml",
}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS HarnessGraphAsset (
  id          TEXT PRIMARY KEY,
  ownerId     TEXT NOT NULL DEFAULT 'local',
  name        TEXT NOT NULL,
  mime        TEXT NOT NULL,
  bytes       INTEGER NOT NULL,
  sha256      TEXT NOT NULL,
  content     BLOB NOT NULL,
  createdAt   TEXT NOT NULL,
  expiresAt   TEXT
);
CREATE INDEX IF NOT EXISTS idx_graph_asset_owner ON HarnessGraphAsset(ownerId, createdAt);
CREATE INDEX IF NOT EXISTS idx_graph_asset_expiry ON HarnessGraphAsset(expiresAt);
"""


class AssetError(RuntimeError):
    """Base class for asset failures with a user-facing message."""


class AssetTooLarge(AssetError):
    pass


class AssetNotFound(AssetError):
    pass


class AssetExpired(AssetError):
    pass


class AssetUnsupportedType(AssetError):
    pass


class GraphAssetStore:
    """File bytes + refs on the ONE agent-memory connection."""

    def __init__(self, store: Any) -> None:
        self._store = store
        self._ensure_schema()

    @property
    def _db(self):
        return self._store._db

    def _ensure_schema(self) -> None:
        self._db.executescript(_SCHEMA)
        self._db.commit()

    @staticmethod
    def ref_of(asset_id: str) -> str:
        return f"gas:{asset_id}"

    @staticmethod
    def id_of(ref: str) -> str:
        value = (ref or "").strip()
        if value.startswith("gas:"):
            return value[4:]
        return value

    @staticmethod
    def _owner(owner: Optional[str]) -> str:
        return str(owner or "local")[:120]

    @classmethod
    def _check_mime(cls, mime: str) -> str:
        value = (mime or "application/octet-stream").strip().lower()[:120]
        if value in ALLOWED_MIME_EXACT or value.startswith(ALLOWED_MIME_PREFIXES):
            return value
        raise AssetUnsupportedType(
            f"file type {value!r} is not accepted here; use a text/CSV/JSON/Excel file"
        )

    def save(
        self,
        name: str,
        data: bytes,
        *,
        mime: str = "application/octet-stream",
        ttl_seconds: int = 0,
        owner: str = "local",
    ) -> dict[str, Any]:
        if not isinstance(data, (bytes, bytearray)):
            raise AssetError("file content must be bytes")
        blob = bytes(data)
        size = len(blob)
        if size == 0:
            raise AssetError("the file is empty")
        if size > MAX_ASSET_BYTES:
            raise AssetTooLarge(
                f"file is {size} bytes; the limit is {MAX_ASSET_BYTES}. "
                "Upload a smaller slice or pre-aggregate it."
            )
        if ttl_seconds < 0:
            raise AssetError("ttl_seconds cannot be negative")
        safe_mime = self._check_mime(mime)
        safe_owner = self._owner(owner)
        self.purge_expired()

        digest = hashlib.sha256(blob).hexdigest()
        asset_id = "gas_" + hashlib.sha256(
            f"{safe_owner}\0{digest}".encode("utf-8")
        ).hexdigest()[:32]

        existing = self._db.execute(
            "SELECT * FROM HarnessGraphAsset WHERE id=?", (asset_id,),
        ).fetchone()
        if existing is not None:
            return self._meta_row(existing)

        count = self._db.execute(
            "SELECT COUNT(*) AS n, COALESCE(SUM(bytes), 0) AS total "
            "FROM HarnessGraphAsset WHERE ownerId=?",
            (safe_owner,),
        ).fetchone()
        if int(count["n"]) >= MAX_ASSETS:
            raise AssetError(
                f"the asset store holds {count['n']} files (limit {MAX_ASSETS}); "
                "delete an old one first."
            )
        if int(count["total"]) + size > MAX_TOTAL_BYTES:
            raise AssetTooLarge(
                "the asset store is full; delete an old file or upload a smaller one."
            )

        created_at = now_iso()
        expires_at = None
        if ttl_seconds:
            expires = _dt.datetime.now(_dt.timezone.utc) + _dt.timedelta(seconds=ttl_seconds)
            expires_at = expires.strftime("%Y-%m-%dT%H:%M:%S") + ".000Z"

        self._db.execute(
            """INSERT INTO HarnessGraphAsset
               (id, ownerId, name, mime, bytes, sha256, content, createdAt, expiresAt)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (asset_id, safe_owner, (name or "file")[:200], safe_mime, size,
             digest, sqlite3.Binary(blob), created_at, expires_at),
        )
        self._db.commit()
        return {
            "assetId": asset_id,
            "ref": self.ref_of(asset_id),
            "name": (name or "file")[:200],
            "mime": safe_mime,
            "bytes": size,
            "sha256": digest,
            "createdAt": created_at,
            "expiresAt": expires_at,
        }

    def _row(self, asset_id: str, owner: str) -> Any:
        row = self._db.execute(
            "SELECT * FROM HarnessGraphAsset WHERE id=?", (asset_id,),
        ).fetchone()
        # A file from another owner is reported as missing, not "forbidden":
        # a reference holder must not learn whether it exists.
        if row is None or str(row["ownerId"] or "local") != self._owner(owner):
            raise AssetNotFound(
                f"file {asset_id!r} does not exist (it may have been deleted or "
                "uploaded in another runtime)."
            )
        expires_at = row["expiresAt"]
        if expires_at and expires_at <= now_iso():
            self._db.execute("DELETE FROM HarnessGraphAsset WHERE id=?", (asset_id,))
            self._db.commit()
            raise AssetExpired(f"file {asset_id!r} expired at {expires_at}.")
        return row

    def open_bytes(self, ref: str, *, owner: str = "local") -> bytes:
        asset_id = self.id_of(ref)
        if not asset_id:
            raise AssetNotFound("no file reference was supplied")
        row = self._row(asset_id, owner)
        return bytes(row["content"])

    def get(self, ref: str, *, owner: str = "local") -> dict[str, Any]:
        asset_id = self.id_of(ref)
        if not asset_id:
            raise AssetNotFound("no file reference was supplied")
        return self._meta_row(self._row(asset_id, owner))

    def list(self, limit: int = 50, *, owner: Optional[str] = None) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 200))
        if owner is None:
            rows = self._db.execute(
                "SELECT * FROM HarnessGraphAsset ORDER BY createdAt DESC LIMIT ?",
                (limit,),
            ).fetchall()
        else:
            rows = self._db.execute(
                "SELECT * FROM HarnessGraphAsset WHERE ownerId=? "
                "ORDER BY createdAt DESC LIMIT ?",
                (self._owner(owner), limit),
            ).fetchall()
        return [self._meta_row(row) for row in rows]

    def delete(self, ref: str, *, owner: Optional[str] = None) -> int:
        asset_id = self.id_of(ref)
        if owner is None:
            cursor = self._db.execute(
                "DELETE FROM HarnessGraphAsset WHERE id=?", (asset_id,),
            )
        else:
            cursor = self._db.execute(
                "DELETE FROM HarnessGraphAsset WHERE id=? AND ownerId=?",
                (asset_id, self._owner(owner)),
            )
        self._db.commit()
        return cursor.rowcount

    def purge_expired(self) -> int:
        cursor = self._db.execute(
            "DELETE FROM HarnessGraphAsset WHERE expiresAt IS NOT NULL AND expiresAt <= ?",
            (now_iso(),),
        )
        self._db.commit()
        return cursor.rowcount

    @staticmethod
    def _meta_row(row: Any) -> dict[str, Any]:
        return {
            "assetId": row["id"],
            "ref": GraphAssetStore.ref_of(row["id"]),
            "name": row["name"],
            "mime": row["mime"],
            "bytes": row["bytes"],
            "sha256": row["sha256"],
            "createdAt": row["createdAt"],
            "expiresAt": row["expiresAt"],
        }


_STORE: Optional[GraphAssetStore] = None


def set_asset_store(store: Optional[GraphAssetStore]) -> None:
    global _STORE
    _STORE = store


def get_asset_store() -> Optional[GraphAssetStore]:
    return _STORE


def require_asset_store() -> GraphAssetStore:
    if _STORE is None:
        raise AssetError("the graph asset store is not configured in this graph runtime")
    return _STORE


__all__ = [
    "ALLOWED_MIME_EXACT",
    "ALLOWED_MIME_PREFIXES",
    "AssetError",
    "AssetExpired",
    "AssetNotFound",
    "AssetTooLarge",
    "AssetUnsupportedType",
    "GraphAssetStore",
    "MAX_ASSETS",
    "MAX_ASSET_BYTES",
    "MAX_TOTAL_BYTES",
    "get_asset_store",
    "require_asset_store",
    "set_asset_store",
]
