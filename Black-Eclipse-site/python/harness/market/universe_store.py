"""Point-in-time universe membership.

Survivorship bias enters a backtest when today's index members are used for
yesterday's decision. This store keeps **effective-dated** membership so a
research universe can be resolved `as_of` a past date from what was actually
recorded — joining on the effective interval, not silently assuming current
membership.

Membership is recorded, never invented: if nothing was recorded for a date, the
as-of resolution returns an explicit empty/unknown result rather than guessing.
Lives on the ONE `agent-memory.db` connection.
"""

from __future__ import annotations

from typing import Any, Optional

from ..persistence import now_iso

_SCHEMA = """
CREATE TABLE IF NOT EXISTS ResearchUniverse (
  universeId TEXT PRIMARY KEY,
  name       TEXT,
  createdAt  TEXT NOT NULL,
  updatedAt  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS UniverseMembership (
  universeId    TEXT NOT NULL,
  symbol        TEXT NOT NULL,
  effectiveFrom TEXT NOT NULL,
  effectiveTo   TEXT,
  metaJson      TEXT,
  recordedAt    TEXT NOT NULL,
  PRIMARY KEY (universeId, symbol, effectiveFrom)
);
CREATE INDEX IF NOT EXISTS idx_um_lookup ON UniverseMembership(universeId, effectiveFrom);
"""


class UniverseStore:
    def __init__(self, store: Any) -> None:
        self._store = store
        self._ensure_schema()

    @property
    def _db(self):
        return self._store._db

    def _ensure_schema(self) -> None:
        try:
            self._db.executescript(_SCHEMA)
            self._db.commit()
        except Exception:  # noqa: BLE001 - persistence best-effort
            pass

    def ensure_universe(self, universe_id: str, name: Optional[str] = None) -> None:
        now = now_iso()
        self._db.execute(
            "INSERT INTO ResearchUniverse (universeId,name,createdAt,updatedAt) VALUES (?,?,?,?) "
            "ON CONFLICT(universeId) DO UPDATE SET name=COALESCE(excluded.name, name), updatedAt=excluded.updatedAt",
            (universe_id, name, now, now),
        )
        self._db.commit()

    def record_membership(self, universe_id: str, members: list[dict[str, Any]],
                          name: Optional[str] = None) -> int:
        """Record effective-dated members. Each member: {symbol, effectiveFrom,
        effectiveTo?, meta?}. Rows are idempotent per (universe, symbol, from)."""
        import json

        if not universe_id or not members:
            return 0
        self.ensure_universe(universe_id, name)
        recorded = now_iso()
        rows = []
        for m in members:
            symbol = str(m.get("symbol") or "").upper().strip()
            eff_from = m.get("effectiveFrom") or m.get("effective_from")
            if not symbol or not eff_from:
                continue
            rows.append((
                universe_id, symbol, str(eff_from),
                str(m["effectiveTo"]) if m.get("effectiveTo") else None,
                json.dumps(m.get("meta")) if m.get("meta") is not None else None,
                recorded,
            ))
        if not rows:
            return 0
        # SCD-2 semantics: recording a member effective later CLOSES any earlier
        # open interval for that symbol, so a retirement is expressed as history
        # rather than leaving a stale open-ended row.
        for _uid, symbol, eff_from, _eff_to, _meta, _rec in rows:
            self._db.execute(
                "UPDATE UniverseMembership SET effectiveTo=? "
                "WHERE universeId=? AND symbol=? AND effectiveFrom<? "
                "AND (effectiveTo IS NULL OR effectiveTo>?)",
                (eff_from, universe_id, symbol, eff_from, eff_from),
            )
        self._db.executemany(
            "INSERT OR REPLACE INTO UniverseMembership "
            "(universeId,symbol,effectiveFrom,effectiveTo,metaJson,recordedAt) VALUES (?,?,?,?,?,?)",
            rows,
        )
        self._db.commit()
        return len(rows)

    def members_as_of(self, universe_id: str, as_of: str) -> list[dict[str, Any]]:
        import json

        rows = self._db.execute(
            "SELECT symbol, effectiveFrom, effectiveTo, metaJson FROM UniverseMembership "
            "WHERE universeId=? AND effectiveFrom<=? AND (effectiveTo IS NULL OR effectiveTo>?) "
            "ORDER BY symbol",
            (universe_id, str(as_of), str(as_of)),
        ).fetchall()
        return [
            {"symbol": r["symbol"], "effectiveFrom": r["effectiveFrom"],
             "effectiveTo": r["effectiveTo"],
             "meta": json.loads(r["metaJson"]) if r["metaJson"] else None}
            for r in rows
        ]

    def list_universes(self, limit: int = 200) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT u.universeId, u.name, u.createdAt, u.updatedAt, "
            "(SELECT COUNT(*) FROM UniverseMembership m WHERE m.universeId=u.universeId) AS members "
            "FROM ResearchUniverse u ORDER BY u.updatedAt DESC LIMIT ?",
            (max(1, int(limit)),),
        ).fetchall()
        return [dict(r) for r in rows]

    def has(self, universe_id: str) -> bool:
        row = self._db.execute(
            "SELECT 1 FROM ResearchUniverse WHERE universeId=?", (universe_id,)
        ).fetchone()
        return row is not None

    def delete(self, universe_id: str) -> None:
        self._db.execute("DELETE FROM UniverseMembership WHERE universeId=?", (universe_id,))
        self._db.execute("DELETE FROM ResearchUniverse WHERE universeId=?", (universe_id,))
        self._db.commit()


__all__ = ["UniverseStore"]
