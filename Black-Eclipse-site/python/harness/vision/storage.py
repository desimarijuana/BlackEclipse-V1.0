"""Content-addressed image storage.

Binary image bytes are written to the filesystem under the gitignored vision
artifacts tier; only METADATA is recorded in a `VisionAsset` table on the ONE
`agent-memory.db` connection (never jdds.db, never eclipse-memory.db). This keeps
large blobs out of the relational store while still making an asset addressable,
deduplicable and auditable.

The asset id is the SHA-256 of the raw bytes, so identical images dedupe and the
same asset can be re-analyzed without re-upload.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Optional

from .config import VisionConfig, vision_config
from .contracts import ImageAsset, now_iso
from .errors import VisionError, VisionErrorClass
from .image import DecodedImage, mime_for_path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS VisionAsset (
    assetId TEXT PRIMARY KEY,
    ownerId TEXT NOT NULL DEFAULT 'local',
    sha256 TEXT NOT NULL,
    mimeType TEXT NOT NULL,
    width INTEGER NOT NULL,
    height INTEGER NOT NULL,
    byteSize INTEGER NOT NULL,
    storageUri TEXT NOT NULL,
    sourceKind TEXT NOT NULL DEFAULT 'path',
    sourceRef TEXT,
    sessionId TEXT,
    runId TEXT,
    createdAt TEXT NOT NULL,
    expiresAt TEXT,
    metadataJson TEXT
);
CREATE INDEX IF NOT EXISTS idx_vision_asset_sha ON VisionAsset(sha256);
CREATE INDEX IF NOT EXISTS idx_vision_asset_run ON VisionAsset(runId);
CREATE INDEX IF NOT EXISTS idx_vision_asset_session ON VisionAsset(sessionId);
"""

_EXT_FOR_MIME = {
    "image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp",
    "image/gif": ".gif", "image/bmp": ".bmp", "image/tiff": ".tiff",
}


class VisionAssetStore:
    """File-backed, content-addressed image storage with metadata rows."""

    def __init__(self, store: Any, *, cfg: Optional[VisionConfig] = None, storage_dir: Optional[Path] = None) -> None:
        self._store = store
        self._cfg = cfg or vision_config()
        self._dir = Path(storage_dir or self._cfg.storage_dir)
        self._ensure_schema()

    @property
    def _db(self) -> Any:
        return self._store._db

    def _ensure_schema(self) -> None:
        self._db.executescript(_SCHEMA)
        columns = {row["name"] for row in self._db.execute("PRAGMA table_info(VisionAsset)")}
        if "ownerId" not in columns:
            self._db.execute(
                "ALTER TABLE VisionAsset ADD COLUMN ownerId TEXT NOT NULL DEFAULT 'local'"
            )
        if "metadataJson" not in columns:
            self._db.execute("ALTER TABLE VisionAsset ADD COLUMN metadataJson TEXT")
        # Create the owner index only AFTER the column exists; a legacy table
        # would otherwise fail the whole schema script.
        self._db.execute(
            "CREATE INDEX IF NOT EXISTS idx_vision_asset_owner ON VisionAsset(ownerId)"
        )
        self._db.commit()

    # ── write ────────────────────────────────────────────────────────────────
    def save(
        self,
        decoded: DecodedImage,
        *,
        run_id: Optional[str] = None,
        session_id: Optional[str] = None,
        source_kind: str = "path",
        source_ref: Optional[str] = None,
        expires_at: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
        owner: str = "local",
    ) -> ImageAsset:
        owner_id = str(owner or "local")[:120]
        # Keep the historical id for the local operator, and scope the id for any
        # other owner so one tenant cannot read another tenant's asset by id.
        # Bytes stay content-addressed on disk, so identical images still share
        # storage without sharing the addressable row.
        asset_id = decoded.asset_id
        if owner_id != "local":
            suffix = hashlib.sha256(owner_id.encode("utf-8")).hexdigest()[:12]
            asset_id = f"{decoded.asset_id}_{suffix}"
        metadata_json = None
        if metadata:
            try:
                metadata_json = json.dumps(metadata, ensure_ascii=False)[:8_000]
            except (TypeError, ValueError):
                metadata_json = None
        ext = _EXT_FOR_MIME.get(decoded.mime_type, ".png")
        relative = Path(decoded.sha256[:2]) / f"{decoded.sha256}{ext}"
        path = self._dir / relative
        if not path.exists():
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(decoded.data)
            except OSError as exc:
                raise VisionError(
                    VisionErrorClass.STORAGE_ERROR, f"the image could not be stored: {exc}", cause=exc
                ) from exc

        existing = self.get(asset_id)
        if existing is not None:
            # Content-addressed dedup: the row already exists; refresh provenance.
            # Preserve a descriptive source/name. Re-analyzing an uploaded image
            # passes raw bytes here; it must not turn "candle-option-A.png" into
            # a b'\\x89PNG...' source ref.
            self._db.execute(
                "UPDATE VisionAsset SET ownerId=?, runId=COALESCE(?, runId), "
                "sessionId=COALESCE(?, sessionId), "
                "sourceKind=CASE WHEN sourceRef IS NULL OR sourceRef='' THEN ? ELSE sourceKind END, "
                "sourceRef=CASE WHEN sourceRef IS NULL OR sourceRef='' THEN ? ELSE sourceRef END, "
                "metadataJson=COALESCE(?, metadataJson) WHERE assetId=?",
                (owner_id, run_id, session_id, source_kind, source_ref, metadata_json, asset_id),
            )
            self._db.commit()
            refreshed = self.get(asset_id)
            return refreshed if refreshed is not None else existing

        asset = ImageAsset(
            asset_id=asset_id, sha256=decoded.sha256, mime_type=decoded.mime_type,
            width=decoded.width, height=decoded.height, byte_size=decoded.byte_size,
            storage_uri=str(path), source_kind=source_kind, source_ref=source_ref,
            session_id=session_id, run_id=run_id, created_at=now_iso(), expires_at=expires_at,
            metadata=metadata or decoded.metadata, owner_id=owner_id,
        )
        self._db.execute(
            "INSERT OR REPLACE INTO VisionAsset (assetId, ownerId, sha256, mimeType, width, height, "
            "byteSize, storageUri, sourceKind, sourceRef, sessionId, runId, createdAt, expiresAt, "
            "metadataJson) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (asset.asset_id, asset.owner_id, asset.sha256, asset.mime_type, asset.width, asset.height,
             asset.byte_size, asset.storage_uri, asset.source_kind, asset.source_ref, asset.session_id,
             asset.run_id, asset.created_at, asset.expires_at, metadata_json),
        )
        self._db.commit()
        return asset

    # ── read ─────────────────────────────────────────────────────────────────
    def get(self, asset_id: str, *, owner: Optional[str] = None) -> Optional[ImageAsset]:
        sql = "SELECT * FROM VisionAsset WHERE assetId=?"
        params: list[Any] = [asset_id]
        if owner is not None:
            sql += " AND ownerId=?"
            params.append(str(owner or "local")[:120])
        row = self._db.execute(sql, params).fetchone()
        return self._row(row) if row else None

    def find_by_sha(self, sha256: str, *, owner: Optional[str] = None) -> Optional[ImageAsset]:
        sql = "SELECT * FROM VisionAsset WHERE sha256=?"
        params: list[Any] = [sha256]
        if owner is not None:
            sql += " AND ownerId=?"
            params.append(str(owner or "local")[:120])
        row = self._db.execute(sql + " LIMIT 1", params).fetchone()
        return self._row(row) if row else None

    def list_for_run(
        self, run_id: str, *, limit: int = 100, owner: Optional[str] = None,
    ) -> list[ImageAsset]:
        sql = "SELECT * FROM VisionAsset WHERE runId=?"
        params: list[Any] = [run_id]
        if owner is not None:
            sql += " AND ownerId=?"
            params.append(str(owner or "local")[:120])
        sql += " ORDER BY createdAt DESC LIMIT ?"
        params.append(limit)
        rows = self._db.execute(sql, params).fetchall()
        return [self._row(r) for r in rows]

    def open_bytes(self, asset_id: str, *, owner: Optional[str] = None) -> Optional[bytes]:
        asset = self.get(asset_id, owner=owner)
        if asset is None:
            return None
        try:
            return Path(asset.storage_uri).read_bytes()
        except OSError:
            return None

    def delete(self, asset_id: str, *, owner: Optional[str] = None) -> bool:
        asset = self.get(asset_id, owner=owner)
        if asset is None:
            return False
        self._db.execute("DELETE FROM VisionAsset WHERE assetId=?", (asset_id,))
        self._db.commit()
        try:
            Path(asset.storage_uri).unlink(missing_ok=True)
        except OSError:
            pass
        return True

    def sweep_expired(self, *, now: Optional[str] = None) -> int:
        """Delete assets past their expiry. Returns the count removed."""
        stamp = now or now_iso()
        rows = self._db.execute(
            "SELECT assetId FROM VisionAsset WHERE expiresAt IS NOT NULL AND expiresAt < ?", (stamp,)
        ).fetchall()
        removed = 0
        for row in rows:
            if self.delete(row["assetId"]):
                removed += 1
        return removed

    def count(self, *, owner: Optional[str] = None) -> int:
        if owner is None:
            row = self._db.execute("SELECT COUNT(*) AS n FROM VisionAsset").fetchone()
        else:
            row = self._db.execute(
                "SELECT COUNT(*) AS n FROM VisionAsset WHERE ownerId=?",
                (str(owner or "local")[:120],),
            ).fetchone()
        return int(row["n"]) if row else 0

    @staticmethod
    def _row(row: Any) -> ImageAsset:
        keys = set(row.keys())
        metadata: dict[str, Any] = {}
        if "metadataJson" in keys and row["metadataJson"]:
            try:
                parsed = json.loads(row["metadataJson"])
                if isinstance(parsed, dict):
                    metadata = parsed
            except (TypeError, ValueError):
                metadata = {}
        return ImageAsset(
            asset_id=row["assetId"], sha256=row["sha256"], mime_type=row["mimeType"],
            width=int(row["width"]), height=int(row["height"]), byte_size=int(row["byteSize"]),
            storage_uri=row["storageUri"], source_kind=row["sourceKind"] if "sourceKind" in keys else "path",
            source_ref=row["sourceRef"] if "sourceRef" in keys else None,
            session_id=row["sessionId"] if "sessionId" in keys else None,
            run_id=row["runId"] if "runId" in keys else None,
            created_at=row["createdAt"], expires_at=row["expiresAt"] if "expiresAt" in keys else None,
            owner_id=row["ownerId"] if "ownerId" in keys else "local",
            metadata=metadata,
        )


__all__ = ["VisionAssetStore"]
