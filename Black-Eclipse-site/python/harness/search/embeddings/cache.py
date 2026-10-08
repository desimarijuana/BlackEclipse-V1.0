"""Content-addressed embedding cache.

Key = sha256(``provider|model|version|normalized_content``). Identical content
embedded with the same model+version is a cache hit and never re-sent to the
external API. Stored as float32 blobs in the search database.
"""

from __future__ import annotations

import array
import hashlib
import sqlite3
import unicodedata
from typing import Optional

_VECTOR = "VectorCache"  # table name constant used by the store schema too


def normalize_content(text: str) -> str:
    """Normalize text for hashing only (whitespace/case/unicode)."""
    folded = unicodedata.normalize("NFKC", text or "")
    return " ".join(folded.split()).strip().lower()


def cache_key(content: str, provider: str, model: str, version: str) -> str:
    material = f"{provider}|{model}|{version}|{normalize_content(content)}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def vector_to_blob(vector: list[float]) -> bytes:
    return array.array("f", vector).tobytes()


def blob_to_vector(blob: bytes) -> list[float]:
    if not blob:
        return []
    arr = array.array("f")
    arr.frombytes(blob)
    return list(arr)


class EmbeddingCache:
    """A bounded cache over the search database's shared connection."""

    def __init__(self, db: sqlite3.Connection, *, max_entries: int = 200_000) -> None:
        self._db = db
        self.max_entries = max_entries
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> Optional[list[float]]:
        row = self._db.execute(
            "SELECT vector, dims FROM EmbeddingCache WHERE cacheKey = ?", (key,)
        ).fetchone()
        if row is None:
            self.misses += 1
            return None
        self.hits += 1
        return blob_to_vector(row["vector"])

    def get_many(self, keys: list[str]) -> dict[str, list[float]]:
        if not keys:
            return {}
        found: dict[str, list[float]] = {}
        # Chunk to stay under SQLite's variable limit.
        for start in range(0, len(keys), 400):
            batch = keys[start : start + 400]
            placeholders = ",".join("?" for _ in batch)
            for row in self._db.execute(
                f"SELECT cacheKey, vector FROM EmbeddingCache WHERE cacheKey IN ({placeholders})",
                batch,
            ).fetchall():
                found[row["cacheKey"]] = blob_to_vector(row["vector"])
        self.hits += len(found)
        self.misses += len(keys) - len(found)
        return found

    def put(
        self,
        key: str,
        vector: list[float],
        *,
        provider: str,
        model: str,
        version: str,
        created_at: str,
    ) -> None:
        self._db.execute(
            "INSERT OR REPLACE INTO EmbeddingCache (cacheKey, provider, model, version, dims, vector, createdAt) "
            "VALUES (?,?,?,?,?,?,?)",
            (key, provider, model, version, len(vector), vector_to_blob(vector), created_at),
        )

    def put_many(self, entries: list[tuple[str, list[float]]], *, provider: str, model: str,
                 version: str, created_at: str) -> None:
        if not entries:
            return
        self._db.executemany(
            "INSERT OR REPLACE INTO EmbeddingCache (cacheKey, provider, model, version, dims, vector, createdAt) "
            "VALUES (?,?,?,?,?,?,?)",
            [
                (key, provider, model, version, len(vector), vector_to_blob(vector), created_at)
                for key, vector in entries
            ],
        )

    def prune(self) -> int:
        total = self._db.execute("SELECT COUNT(*) FROM EmbeddingCache").fetchone()[0]
        if total <= self.max_entries:
            return 0
        excess = total - self.max_entries
        self._db.execute(
            "DELETE FROM EmbeddingCache WHERE cacheKey IN "
            "(SELECT cacheKey FROM EmbeddingCache ORDER BY createdAt ASC LIMIT ?)",
            (excess,),
        )
        return excess

    def clear(self) -> int:
        count = self._db.execute("SELECT COUNT(*) FROM EmbeddingCache").fetchone()[0]
        self._db.execute("DELETE FROM EmbeddingCache")
        return count

    def commit(self) -> None:
        self._db.commit()

    def stats(self) -> dict[str, int]:
        total = self._db.execute("SELECT COUNT(*) FROM EmbeddingCache").fetchone()[0]
        return {"entries": total, "hits": self.hits, "misses": self.misses}


__all__ = [
    "EmbeddingCache",
    "blob_to_vector",
    "cache_key",
    "normalize_content",
    "vector_to_blob",
]
