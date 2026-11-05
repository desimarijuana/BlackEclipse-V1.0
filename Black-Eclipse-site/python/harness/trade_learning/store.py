"""Durable trade-learning state on the runtime's own database.

Three tables, all on `agent-memory.db` (never `jdds.db`, never
`eclipse-memory.db`):

* `TradeFinding` — one deterministic observation per (trade, category,
  detector version). A finding is never edited into a lesson.
* `TradePlaybook` — append-only versions of the envelope the risk gate can
  enforce. A version is a full snapshot, not a diff, so rollback is a pointer
  change rather than a replay.
* recurrence is **not** a table here: counts come from the ONE
  `LearningRecurrence` ledger, keyed by the trade id so re-reviewing a trade
  cannot inflate a pattern.

The DDL is idempotent and the store uses the shared connection, like
`projects/store.py`.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from ..persistence import new_id, now_iso
from .model import Finding, Playbook, _normalise_limit
from .playbook import PlaybookRefused, validate_limits

_DDL = """
CREATE TABLE IF NOT EXISTS TradeFinding (
  id              TEXT PRIMARY KEY,
  tradeId         TEXT NOT NULL,
  profileId       TEXT NOT NULL DEFAULT 'local',
  category        TEXT NOT NULL,
  severity        TEXT NOT NULL DEFAULT 'medium',
  detectorVersion TEXT NOT NULL DEFAULT '1',
  expected        TEXT,
  actual          TEXT,
  evidenceJson    TEXT,
  rMultiple       REAL,
  rAvailable      INTEGER NOT NULL DEFAULT 0,
  signature       TEXT NOT NULL,
  status          TEXT NOT NULL DEFAULT 'open',
  createdAt       TEXT NOT NULL,
  updatedAt       TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_trade_finding_unique
  ON TradeFinding(tradeId, category, detectorVersion);
CREATE INDEX IF NOT EXISTS idx_trade_finding_signature
  ON TradeFinding(signature, createdAt);
CREATE INDEX IF NOT EXISTS idx_trade_finding_profile
  ON TradeFinding(profileId, createdAt);
CREATE INDEX IF NOT EXISTS idx_trade_finding_status
  ON TradeFinding(status);

CREATE TABLE IF NOT EXISTS TradePlaybook (
  id            TEXT PRIMARY KEY,
  profileId     TEXT NOT NULL,
  version       INTEGER NOT NULL,
  hash          TEXT NOT NULL,
  limitsJson    TEXT NOT NULL,
  boundsJson    TEXT NOT NULL,
  reason        TEXT,
  mode          TEXT NOT NULL DEFAULT 'shadow',
  evidenceJson  TEXT,
  actionsJson   TEXT,
  status        TEXT NOT NULL DEFAULT 'active',
  revertsAt     TEXT,
  revertedAt    TEXT,
  approvedBy    TEXT,
  createdAt     TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_trade_playbook_version
  ON TradePlaybook(profileId, version);
CREATE INDEX IF NOT EXISTS idx_trade_playbook_status
  ON TradePlaybook(profileId, status);
"""


class TradeLearningStore:
    """Findings, playbook versions and the recurrence bridge."""

    def __init__(self, store: Any) -> None:
        self._store = store
        self._ensure_schema()

    @property
    def _db(self):
        return self._store._db  # noqa: SLF001 - the one shared connection

    def _ensure_schema(self) -> None:
        self._db.executescript(_DDL)
        self._db.commit()

    # ── findings ─────────────────────────────────────────────────────────────

    def record_findings(
        self,
        findings: list[dict[str, Any]] | list[Finding],
        *,
        profile_id: str = "local",
    ) -> int:
        """Persist findings idempotently. Returns how many rows were new."""
        inserted = 0
        now = now_iso()
        for raw in findings:
            finding = raw if isinstance(raw, Finding) else _finding(raw)
            if finding is None:
                continue
            cursor = self._db.execute(
                """INSERT OR IGNORE INTO TradeFinding
                   (id, tradeId, profileId, category, severity, detectorVersion,
                    expected, actual, evidenceJson, rMultiple, rAvailable,
                    signature, status, createdAt, updatedAt)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    new_id("tf"), finding.trade_id, profile_id[:120], finding.category,
                    finding.severity, finding.detector_version, finding.expected,
                    finding.actual, json.dumps(finding.evidence),
                    finding.r_multiple, 1 if finding.r_available else 0,
                    finding.signature, "open", now, now,
                ),
            )
            inserted += max(0, cursor.rowcount)
        self._db.commit()
        return inserted

    def list_findings(
        self,
        *,
        profile_id: str = "local",
        since: Optional[str] = None,
        status: Optional[str] = None,
        signature: Optional[str] = None,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        clauses = ["profileId=?"]
        args: list[Any] = [profile_id[:120]]
        if since:
            clauses.append("createdAt>=?")
            args.append(since)
        if status:
            clauses.append("status=?")
            args.append(status)
        if signature:
            clauses.append("signature=?")
            args.append(signature)
        args.append(max(1, min(int(limit), 5_000)))
        rows = self._db.execute(
            f"SELECT * FROM TradeFinding WHERE {' AND '.join(clauses)} "
            "ORDER BY createdAt DESC LIMIT ?",
            tuple(args),
        ).fetchall()
        return [_finding_row(row) for row in rows]

    def signature_stats(
        self,
        signature: str,
        *,
        profile_id: str = "local",
        since: Optional[str] = None,
    ) -> dict[str, Any]:
        """Occurrences, window and cost for one signature.

        The COUNT is still the ledger's; this query only supplies the fields the
        ledger does not carry (first/last seen, R cost, per-trade identity).
        """
        clauses = ["profileId=?", "signature=?"]
        args: list[Any] = [profile_id[:120], signature]
        if since:
            clauses.append("createdAt>=?")
            args.append(since)
        rows = self._db.execute(
            f"SELECT tradeId, rMultiple, rAvailable, createdAt FROM TradeFinding "
            f"WHERE {' AND '.join(clauses)}",
            tuple(args),
        ).fetchall()
        trade_ids = sorted({str(row["tradeId"]) for row in rows})
        with_r = [float(row["rMultiple"]) for row in rows if row["rAvailable"]]
        dates = sorted(str(row["createdAt"]) for row in rows)
        return {
            "signature": signature,
            "occurrences": len(trade_ids),
            "tradeIds": trade_ids[:200],
            "firstSeen": dates[0] if dates else None,
            "lastSeenAt": dates[-1] if dates else None,
            "costR": round(sum(abs(value) for value in with_r), 6) if with_r else None,
            "rAvailable": bool(with_r),
        }

    def record_recurrence(self, findings: list[dict[str, Any]] | list[Finding]) -> dict[str, int]:
        """Bump the ONE recurrence ledger, deduped by trade id."""
        counts: dict[str, int] = {}
        for raw in findings:
            finding = raw if isinstance(raw, Finding) else _finding(raw)
            if finding is None or not finding.signature:
                continue
            try:
                counts[finding.signature] = int(
                    self._store.record_learning_recurrence(
                        finding.signature, finding.trade_id,
                    )
                )
            except Exception:  # noqa: BLE001 - observation must never break a review
                continue
        return counts

    def ledger_count(self, signature: str) -> int:
        try:
            return int(self._store.learning_recurrence(signature))
        except Exception:  # noqa: BLE001 - a missing ledger is simply zero
            return 0

    # ── playbook versions ────────────────────────────────────────────────────

    def active_playbook(self, profile_id: str = "local") -> Optional[Playbook]:
        row = self._db.execute(
            "SELECT * FROM TradePlaybook WHERE profileId=? AND status='active' "
            "ORDER BY version DESC LIMIT 1",
            (profile_id[:120],),
        ).fetchone()
        return _playbook_row(row) if row else None

    def playbook_history(self, profile_id: str = "local", limit: int = 20) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT * FROM TradePlaybook WHERE profileId=? ORDER BY version DESC LIMIT ?",
            (profile_id[:120], max(1, min(int(limit), 100))),
        ).fetchall()
        return [_playbook_row(row).to_dict() | {"status": row["status"]} for row in rows]

    def save_playbook(
        self,
        limits: dict[str, Any],
        *,
        bounds: dict[str, Any],
        profile_id: str = "local",
        reason: str = "",
        mode: str = "shadow",
        evidence: Any = None,
        actions: Any = None,
        ttl_days: int = 14,
        approved_by: Optional[str] = None,
    ) -> dict[str, Any]:
        """Append the next version, enforcing bounds and tighten-only.

        Raises `PlaybookRefused` — the node then reports the refusal instead of
        silently changing behaviour.
        """
        active = self.active_playbook(profile_id)
        effective_bounds = (active.bounds if active is not None else bounds) or {}
        try:
            normalised = validate_limits(
                limits, bounds=effective_bounds, current=active,
                enforce_direction=active is not None,
            )
        except PlaybookRefused:
            raise
        candidate = Playbook(
            limits=normalised,
            bounds=effective_bounds,
            version=(active.version + 1) if active else 1,
            playbook_id=new_id("tpb"),
        )
        if active is not None and candidate.hash == active.hash:
            return {"playbook": active.to_dict(), "changed": False, "status": "unchanged"}
        now = now_iso()
        reverts_at = _plus_days(now, ttl_days)
        if active is not None:
            self._db.execute(
                "UPDATE TradePlaybook SET status='superseded' WHERE profileId=? AND status='active'",
                (profile_id[:120],),
            )
        self._db.execute(
            """INSERT INTO TradePlaybook
               (id, profileId, version, hash, limitsJson, boundsJson, reason, mode,
                evidenceJson, actionsJson, status, revertsAt, approvedBy, createdAt)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                candidate.playbook_id, profile_id[:120], candidate.version, candidate.hash,
                json.dumps(normalised, sort_keys=True),
                json.dumps(effective_bounds, sort_keys=True),
                reason[:1_000], mode[:20],
                json.dumps(evidence) if evidence is not None else None,
                json.dumps(actions) if actions is not None else None,
                "active", reverts_at, approved_by, now,
            ),
        )
        self._db.commit()
        return {
            "playbook": candidate.to_dict(),
            "changed": True,
            "status": "active",
            "revertsAt": reverts_at,
            "previousVersion": active.version if active else None,
        }

    def revert(self, profile_id: str = "local", *, reason: str = "manual") -> Optional[dict[str, Any]]:
        """Revert the active version to the previous one (a pointer change)."""
        active = self.active_playbook(profile_id)
        if active is None:
            return None
        previous = self._db.execute(
            "SELECT * FROM TradePlaybook WHERE profileId=? AND version<? "
            "ORDER BY version DESC LIMIT 1",
            (profile_id[:120], active.version),
        ).fetchone()
        now = now_iso()
        self._db.execute(
            "UPDATE TradePlaybook SET status='reverted', revertedAt=? WHERE id=?",
            (now, active.playbook_id),
        )
        if previous is not None:
            self._db.execute(
                "UPDATE TradePlaybook SET status='active' WHERE id=?",
                (previous["id"],),
            )
        self._db.commit()
        return {
            "reverted": active.to_dict(),
            "active": _playbook_row(previous).to_dict() if previous else None,
            "reason": reason,
        }

    def expire_due(self, profile_id: str = "local", now: Optional[str] = None) -> Optional[dict[str, Any]]:
        """Expire an active version whose TTL has passed (a canary action)."""
        active = self.active_playbook(profile_id)
        if active is None:
            return None
        row = self._db.execute(
            "SELECT revertsAt FROM TradePlaybook WHERE id=?",
            (active.playbook_id,),
        ).fetchone()
        due = (row["revertsAt"] if row else None)
        # Parse, never compare ISO strings: `now_iso()` ends in `Z` while a
        # version's `revertsAt` is written via `datetime.isoformat()` (+00:00).
        if not due or _parse_iso(str(due)) > _parse_iso(now or now_iso()):
            return None
        return self.revert(profile_id, reason="expired")


# ── row mapping ───────────────────────────────────────────────────────────────

def _finding(raw: Any) -> Optional[Finding]:
    from .model import finding_from_dict  # noqa: PLC0415 - avoid a cycle at import

    return finding_from_dict(raw) if isinstance(raw, dict) else None


def _finding_row(row: Any) -> dict[str, Any]:
    try:
        evidence = json.loads(row["evidenceJson"]) if row["evidenceJson"] else {}
    except (TypeError, ValueError):
        evidence = {}
    return {
        "id": row["id"],
        "tradeId": row["tradeId"],
        "category": row["category"],
        "severity": row["severity"],
        "detectorVersion": row["detectorVersion"],
        "expected": row["expected"],
        "actual": row["actual"],
        "evidence": evidence,
        "rMultiple": row["rMultiple"],
        "rAvailable": bool(row["rAvailable"]),
        "signature": row["signature"],
        "status": row["status"],
        "createdAt": row["createdAt"],
    }


def _playbook_row(row: Any) -> Playbook:
    try:
        limits = json.loads(row["limitsJson"]) if row["limitsJson"] else {}
    except (TypeError, ValueError):
        limits = {}
    try:
        bounds = json.loads(row["boundsJson"]) if row["boundsJson"] else {}
    except (TypeError, ValueError):
        bounds = {}
    # A stored snapshot may predate a newly added knob; fill the defaults so a
    # reader never has to guess what an absent key meant.
    from .model import DEFAULT_LIMITS  # noqa: PLC0415 - avoid a cycle at import

    merged = dict(DEFAULT_LIMITS)
    for name, value in (limits or {}).items():
        merged[name] = _normalise_limit(name, value)
    return Playbook(
        limits=merged,
        bounds=bounds if isinstance(bounds, dict) else {},
        version=int(row["version"]),
        playbook_id=row["id"],
    )


def _parse_iso(iso: str) -> Any:
    import datetime as _dt  # noqa: PLC0415

    try:
        parsed = _dt.datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except ValueError:
        return _dt.datetime.min.replace(tzinfo=_dt.timezone.utc)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_dt.timezone.utc)
    return parsed.astimezone(_dt.timezone.utc)


def _plus_days(iso: str, days: int) -> str:
    import datetime as _dt  # noqa: PLC0415

    try:
        moment = _dt.datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        moment = _dt.datetime.now(_dt.timezone.utc)
    return (moment + _dt.timedelta(days=max(1, min(int(days), 90)))).isoformat()


__all__ = ["TradeLearningStore"]
