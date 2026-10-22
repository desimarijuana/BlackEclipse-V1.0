"""The gallery — a local catalogue of PUBLISHED strategies.

QuantPad has a community: you publish a strategy, other people clone it and
like it. A local-first, single-operator runtime cannot have a community of
strangers, and pretending to would be dishonest. What it CAN have is the part
that matters: a **catalogue of frozen, graded strategies** - each published
record carries the strategy spec, the grade its evidence earned, and the report
it came from - that you can browse, favourite and clone back into your own
store.

The semantics are the same, the scope is honest:

- **publish** freezes a strategy (and optionally the Edge Report that graded
  it) into an immutable record. The record is a snapshot: the live strategy
  may move on, the published record does not.
- **clone** copies a published spec into the quant store as a NEW strategy. The
  original is untouched.
- **favourite** counts interest locally.

Nothing here is a substitute for a shared marketplace, and it does not pretend
to be one.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class PublishedStrategy:
    """One frozen, published strategy."""

    id: str
    name: str
    description: str = ""
    author: str = "local"
    strategy_id: str = ""
    strategy_version: str = ""
    spec: dict[str, Any] = field(default_factory=dict)
    grade: Optional[str] = None
    score: Optional[float] = None
    summary: str = ""
    report: str = ""
    symbols: list[str] = field(default_factory=list)
    favourites: int = 0
    clones: int = 0
    created_at: str = ""

    def to_dict(self, *, include_spec: bool = False) -> dict[str, Any]:
        data = {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "author": self.author,
            "strategyId": self.strategy_id,
            "strategyVersion": self.strategy_version,
            "grade": self.grade,
            "score": self.score,
            "summary": self.summary,
            "symbols": list(self.symbols),
            "favourites": self.favourites,
            "clones": self.clones,
            "createdAt": self.created_at,
            "hasReport": bool(self.report),
        }
        if include_spec:
            data["spec"] = dict(self.spec)
            data["report"] = self.report
        return data


_DDL = """
CREATE TABLE IF NOT EXISTS PublishedStrategy (
  id              TEXT PRIMARY KEY,
  name            TEXT NOT NULL,
  description     TEXT NOT NULL DEFAULT '',
  author          TEXT NOT NULL DEFAULT 'local',
  strategyId      TEXT NOT NULL DEFAULT '',
  strategyVersion TEXT NOT NULL DEFAULT '',
  specJson        TEXT NOT NULL DEFAULT '{}',
  grade           TEXT,
  score           REAL,
  summary         TEXT NOT NULL DEFAULT '',
  reportMarkdown  TEXT NOT NULL DEFAULT '',
  symbolsJson     TEXT NOT NULL DEFAULT '[]',
  favourites      INTEGER NOT NULL DEFAULT 0,
  clones          INTEGER NOT NULL DEFAULT 0,
  createdAt       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_published_created
  ON PublishedStrategy(createdAt DESC);
"""


class GalleryStore:
    """The published catalogue, on the ONE agent-memory connection."""

    def __init__(self, store: Any) -> None:
        self._store = store
        self._ensure_schema()

    @property
    def _db(self):
        return self._store._db

    def _ensure_schema(self) -> None:
        try:
            self._db.executescript(_DDL)
            self._db.commit()
        except Exception:  # noqa: BLE001 - persistence is best-effort
            pass

    # ── publishing ───────────────────────────────────────────────────────────

    def publish(
        self,
        *,
        name: str,
        spec: dict[str, Any],
        strategy_id: str = "",
        strategy_version: str = "",
        description: str = "",
        author: str = "local",
        grade: Optional[str] = None,
        score: Optional[float] = None,
        summary: str = "",
        report: str = "",
        symbols: Optional[list[str]] = None,
    ) -> PublishedStrategy:
        """Freeze a strategy into an immutable published record."""
        from ..persistence import now_iso

        entry = PublishedStrategy(
            id=f"pub_{uuid.uuid4().hex[:12]}",
            name=str(name)[:200],
            description=str(description)[:2_000],
            author=str(author)[:120],
            strategy_id=str(strategy_id)[:200],
            strategy_version=str(strategy_version)[:40],
            spec=dict(spec or {}),
            grade=(str(grade) if grade else None),
            score=(float(score) if score is not None else None),
            summary=str(summary)[:1_000],
            report=str(report),
            symbols=[str(s) for s in (symbols
                                     or (spec.get("universe") or {}).get("symbols")
                                     or [])][:64],
            created_at=now_iso(),
        )
        self._db.execute(
            "INSERT INTO PublishedStrategy (id,name,description,author,strategyId,"
            "strategyVersion,specJson,grade,score,summary,reportMarkdown,symbolsJson,"
            "favourites,clones,createdAt) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (entry.id, entry.name, entry.description, entry.author, entry.strategy_id,
             entry.strategy_version, json.dumps(entry.spec), entry.grade, entry.score,
             entry.summary, entry.report, json.dumps(entry.symbols),
             entry.favourites, entry.clones, entry.created_at),
        )
        self._db.commit()
        return entry

    # ── reading ──────────────────────────────────────────────────────────────

    def get(self, published_id: str) -> Optional[PublishedStrategy]:
        row = self._db.execute(
            "SELECT * FROM PublishedStrategy WHERE id=?", (str(published_id),)).fetchone()
        return self._row_to_entry(row) if row else None

    def list(self, *, limit: int = 100) -> list[PublishedStrategy]:
        rows = self._db.execute(
            "SELECT * FROM PublishedStrategy ORDER BY createdAt DESC, rowid DESC "
            "LIMIT ?",
            (max(1, min(int(limit), 500)),)).fetchall()
        return [self._row_to_entry(row) for row in rows]

    def remove(self, published_id: str) -> bool:
        row = self._db.execute(
            "SELECT id FROM PublishedStrategy WHERE id=?", (str(published_id),)).fetchone()
        if row is None:
            return False
        self._db.execute("DELETE FROM PublishedStrategy WHERE id=?", (row["id"],))
        self._db.commit()
        return True

    # ── interest ─────────────────────────────────────────────────────────────

    def favourite(self, published_id: str) -> Optional[PublishedStrategy]:
        entry = self.get(published_id)
        if entry is None:
            return None
        entry.favourites += 1
        self._db.execute(
            "UPDATE PublishedStrategy SET favourites=? WHERE id=?",
            (entry.favourites, entry.id))
        self._db.commit()
        return entry

    def count_clone(self, published_id: str) -> Optional[PublishedStrategy]:
        entry = self.get(published_id)
        if entry is None:
            return None
        entry.clones += 1
        self._db.execute(
            "UPDATE PublishedStrategy SET clones=? WHERE id=?",
            (entry.clones, entry.id))
        self._db.commit()
        return entry

    def _row_to_entry(self, row: Any) -> PublishedStrategy:
        try:
            spec = json.loads(row["specJson"] or "{}")
        except (TypeError, ValueError):
            spec = {}
        try:
            symbols = json.loads(row["symbolsJson"] or "[]")
        except (TypeError, ValueError):
            symbols = []
        return PublishedStrategy(
            id=row["id"], name=row["name"], description=row["description"] or "",
            author=row["author"] or "local", strategy_id=row["strategyId"] or "",
            strategy_version=row["strategyVersion"] or "",
            spec=spec if isinstance(spec, dict) else {},
            grade=row["grade"], score=row["score"], summary=row["summary"] or "",
            report=row["reportMarkdown"] or "",
            symbols=symbols if isinstance(symbols, list) else [],
            favourites=int(row["favourites"] or 0), clones=int(row["clones"] or 0),
            created_at=row["createdAt"] or "",
        )


__all__ = ["GalleryStore", "PublishedStrategy"]
