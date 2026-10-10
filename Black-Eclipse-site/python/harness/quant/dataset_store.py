"""Immutable, versioned research datasets with reproducible manifests.

A research dataset is a named collection of instrument time-series frozen at a
point in time, together with a manifest that records exactly what produced it:
universe, interval, date range, adjustment basis, per-symbol row counts, the
data-quality report, source lineage, retrieval timestamps and a content hash.

Immutability is the contract:
  * a dataset version is INSERT-only; there is no update path,
  * building again with IDENTICAL content returns the SAME version (deterministic
    reproducibility), unless `force=True` is passed to deliberately fork a new one,
  * new data / changed adjustments / corrected normalization produces a NEW
    version (`vN+1`); the old version is never mutated.

Metadata lives in the ONE `agent-memory.db` connection (idempotent DDL, never
`jdds.db`/`eclipse-memory.db`); the rows are written as gzipped JSON artifacts
under `.black-eclipse/quant/datasets/` so a wide series never bloats a row.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import time
import uuid
from typing import Any, Optional

from .errors import QuantError


class DatasetNotFound(QuantError):
    """A requested dataset or version does not exist."""


def _iso_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()) + "Z"


def _artifact_root() -> str:
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    return os.path.join(root, ".black-eclipse", "quant", "datasets")


_SCHEMA = """
CREATE TABLE IF NOT EXISTS ResearchDataset (
  id          TEXT PRIMARY KEY,
  name        TEXT NOT NULL,
  description TEXT,
  createdAt   TEXT NOT NULL,
  updatedAt   TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ResearchDatasetVersion (
  datasetId   TEXT NOT NULL,
  version     TEXT NOT NULL,
  contentHash TEXT NOT NULL,
  manifestJson TEXT NOT NULL,
  createdBy   TEXT,
  artifactPath TEXT,
  createdAt   TEXT NOT NULL,
  PRIMARY KEY (datasetId, version)
);
CREATE INDEX IF NOT EXISTS idx_rdv_dataset ON ResearchDatasetVersion(datasetId);
CREATE INDEX IF NOT EXISTS idx_rdv_hash ON ResearchDatasetVersion(datasetId, contentHash);
"""


def _canonical_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "t": str(row.get("timestamp")),
        "o": row.get("open"), "h": row.get("high"),
        "l": row.get("low"), "c": row.get("close"),
        "v": row.get("volume"),
    }


def content_hash(series: dict[str, list[dict[str, Any]]]) -> str:
    """A stable sha256 over the canonicalized series (symbol order independent)."""
    canonical = {
        symbol: [_canonical_row(r) for r in rows]
        for symbol, rows in sorted(series.items())
    }
    blob = json.dumps(canonical, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


class DatasetStore:
    """The ONE research-dataset store. Additive DDL on the agent-memory connection."""

    def __init__(self, agent_memory_store: Any, *, artifact_root: Optional[str] = None) -> None:
        self._store = agent_memory_store
        self._root = artifact_root or _artifact_root()
        self._ensure_schema()
        os.makedirs(self._root, exist_ok=True)

    @property
    def _db(self):
        return self._store._db

    def _ensure_schema(self) -> None:
        self._db.executescript(_SCHEMA)
        self._db.commit()

    # ── Build ────────────────────────────────────────────────────────────────
    def build_version(
        self,
        *,
        series: dict[str, list[dict[str, Any]]],
        request: Optional[dict[str, Any]] = None,
        name: Optional[str] = None,
        dataset_id: Optional[str] = None,
        quality: Optional[dict[str, Any]] = None,
        lineage: Optional[dict[str, Any]] = None,
        created_by: Optional[str] = None,
        force: bool = False,
    ) -> dict[str, Any]:
        """Freeze a series into an immutable version and return its manifest.

        Identical content (same hash) for a dataset returns the existing version
        (reproducibility) unless `force=True`.
        """
        if not series:
            raise DatasetNotFound("cannot build a dataset version from an empty series")
        request = request or {}
        digest = content_hash(series)

        if dataset_id is None:
            dataset_id = f"ds_{uuid.uuid4().hex[:16]}"
            self._ensure_dataset(dataset_id, name or f"dataset {dataset_id[:8]}")

        existing_head = self._db.execute(
            "SELECT id FROM ResearchDataset WHERE id=?", (dataset_id,)
        ).fetchone()
        if existing_head is None:
            self._ensure_dataset(dataset_id, name or f"dataset {dataset_id[:8]}")

        if not force:
            prior = self._db.execute(
                "SELECT version, manifestJson FROM ResearchDatasetVersion "
                "WHERE datasetId=? AND contentHash=? ORDER BY version ASC LIMIT 1",
                (dataset_id, digest),
            ).fetchone()
            if prior is not None:
                manifest = json.loads(prior["manifestJson"])
                manifest["created"] = False
                manifest["note"] = "identical content — returned the existing immutable version"
                return manifest

        version = self._next_version(dataset_id)
        symbols = sorted(series.keys())
        counts = {s: len(rows) for s, rows in series.items()}
        all_ts = [r.get("timestamp") for rows in series.values() for r in rows if r.get("timestamp")]
        coverage = {
            "symbols": symbols,
            "symbolCount": len(symbols),
            "rowCount": sum(counts.values()),
            "perSymbolRows": counts,
            "start": min(all_ts) if all_ts else None,
            "end": max(all_ts) if all_ts else None,
        }
        created_at = _iso_now()
        artifact_path = os.path.join(self._root, f"{dataset_id}__{version}.json.gz")
        with gzip.open(artifact_path, "wt", encoding="utf-8") as fh:
            json.dump({"series": series}, fh, default=str)

        manifest: dict[str, Any] = {
            "datasetId": dataset_id,
            "version": version,
            "name": name or self._dataset_name(dataset_id),
            "contentHash": digest,
            "createdAt": created_at,
            "createdBy": created_by,
            "request": request,
            "coverage": coverage,
            "quality": quality or {},
            "lineage": lineage or {},
            "artifactPath": artifact_path,
            "immutable": True,
            "created": True,
        }
        self._db.execute(
            "INSERT INTO ResearchDatasetVersion "
            "(datasetId, version, contentHash, manifestJson, createdBy, artifactPath, createdAt) "
            "VALUES (?,?,?,?,?,?,?)",
            (dataset_id, version, digest, json.dumps(manifest), created_by, artifact_path, created_at),
        )
        self._db.execute(
            "UPDATE ResearchDataset SET updatedAt=? WHERE id=?", (_iso_now(), dataset_id)
        )
        self._db.commit()
        return manifest

    def _ensure_dataset(self, dataset_id: str, name: str, description: Optional[str] = None) -> None:
        now = _iso_now()
        self._db.execute(
            "INSERT INTO ResearchDataset (id,name,description,createdAt,updatedAt) "
            "VALUES (?,?,?,?,?) ON CONFLICT(id) DO NOTHING",
            (dataset_id, name, description, now, now),
        )
        self._db.commit()

    def _dataset_name(self, dataset_id: str) -> str:
        row = self._db.execute(
            "SELECT name FROM ResearchDataset WHERE id=?", (dataset_id,)
        ).fetchone()
        return row["name"] if row else dataset_id

    def _next_version(self, dataset_id: str) -> str:
        rows = self._db.execute(
            "SELECT version FROM ResearchDatasetVersion WHERE datasetId=?", (dataset_id,)
        ).fetchall()
        highest = 0
        for row in rows:
            try:
                highest = max(highest, int(str(row["version"]).lstrip("v")))
            except ValueError:
                continue
        return f"v{highest + 1}"

    # ── Read ─────────────────────────────────────────────────────────────────
    def get_version(self, dataset_id: str, version: Optional[str] = None) -> dict[str, Any]:
        if version:
            row = self._db.execute(
                "SELECT manifestJson FROM ResearchDatasetVersion WHERE datasetId=? AND version=?",
                (dataset_id, version),
            ).fetchone()
        else:
            row = self._db.execute(
                "SELECT manifestJson FROM ResearchDatasetVersion WHERE datasetId=? "
                "ORDER BY createdAt DESC LIMIT 1",
                (dataset_id,),
            ).fetchone()
        if row is None:
            raise DatasetNotFound(
                f"dataset {dataset_id!r} version {version or '(latest)'!r} not found",
                detail={"datasetId": dataset_id, "version": version},
            )
        return json.loads(row["manifestJson"])

    def list_versions(self, dataset_id: str) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT version, contentHash, createdBy, createdAt FROM ResearchDatasetVersion "
            "WHERE datasetId=? ORDER BY createdAt ASC",
            (dataset_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def list_datasets(self, limit: int = 100) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT d.id, d.name, d.description, d.createdAt, d.updatedAt, "
            "(SELECT COUNT(*) FROM ResearchDatasetVersion v WHERE v.datasetId=d.id) AS versions "
            "FROM ResearchDataset d ORDER BY d.updatedAt DESC LIMIT ?",
            (max(1, int(limit)),),
        ).fetchall()
        return [dict(r) for r in rows]

    def read_artifact(self, dataset_id: str, version: Optional[str] = None) -> dict[str, Any]:
        manifest = self.get_version(dataset_id, version)
        path = manifest.get("artifactPath")
        if not path or not os.path.exists(path):
            raise DatasetNotFound(
                f"artifact for dataset {dataset_id!r} {manifest.get('version')!r} is missing",
                detail={"datasetId": dataset_id, "path": path},
            )
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            return json.load(fh)

    def compare_versions(self, dataset_id: str, a: str, b: str) -> dict[str, Any]:
        """Compare two immutable versions: symbol/row/coverage/quality deltas."""
        ma = self.get_version(dataset_id, a)
        mb = self.get_version(dataset_id, b)
        ca, cb = ma.get("coverage", {}), mb.get("coverage", {})
        sa = set(ca.get("perSymbolRows", {}))
        sb = set(cb.get("perSymbolRows", {}))
        per_symbol = {}
        for symbol in sorted(sa | sb):
            ra = ca.get("perSymbolRows", {}).get(symbol)
            rb = cb.get("perSymbolRows", {}).get(symbol)
            per_symbol[symbol] = {"a": ra, "b": rb, "delta": (rb - ra) if (ra is not None and rb is not None) else None}
        return {
            "datasetId": dataset_id,
            "a": a, "b": b,
            "sameContent": ma.get("contentHash") == mb.get("contentHash"),
            "addedSymbols": sorted(sb - sa),
            "removedSymbols": sorted(sa - sb),
            "rowCountDelta": (cb.get("rowCount") or 0) - (ca.get("rowCount") or 0),
            "perSymbol": per_symbol,
            "startChanged": ca.get("start") != cb.get("start"),
            "endChanged": ca.get("end") != cb.get("end"),
            "qualityChanged": (ma.get("quality") or {}) != (mb.get("quality") or {}),
            "requestChanged": (ma.get("request") or {}) != (mb.get("request") or {}),
        }


__all__ = ["DatasetNotFound", "DatasetStore", "content_hash"]
