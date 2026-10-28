"""Staged read-only widening proposals.

A tool that the contract shadow marks `eligible_shadow` can be staged as a
durable proposal. Staging is **not** a grant: it records the tool, its contract,
and the evidence still required (replay, deny path, conclusion stability). No
allowlist, agent preset, or runtime surface is changed.
"""

from __future__ import annotations

import json
import uuid
from typing import Any, Iterable, Optional

from ..persistence import now_iso
from .tool_shadow import shadow_report


class WideningProposalStore:
    _SCHEMA = """
    CREATE TABLE IF NOT EXISTS WideningProposal (
      id         TEXT PRIMARY KEY,
      toolName   TEXT NOT NULL,
      status     TEXT NOT NULL,
      evidence   TEXT NOT NULL,
      createdAt  TEXT NOT NULL,
      expiresAt  TEXT,
      stagedBy   TEXT
    );
    CREATE UNIQUE INDEX IF NOT EXISTS idx_widening_tool ON WideningProposal(toolName);
    """

    def __init__(self, store: Any) -> None:
        self._store = store
        self._db.executescript(self._SCHEMA)
        self._db.commit()

    @property
    def _db(self):
        return self._store._db

    def find(self, tool_name: str) -> Optional[dict[str, Any]]:
        row = self._db.execute(
            "SELECT * FROM WideningProposal WHERE toolName=?", (tool_name,),
        ).fetchone()
        return dict(row) if row else None

    def add(self, *, tool_name: str, evidence: dict[str, Any], expires_at: str, staged_by: str) -> dict[str, Any]:
        proposal_id = "wprop_" + uuid.uuid4().hex[:16]
        self._db.execute(
            "INSERT INTO WideningProposal "
            "(id, toolName, status, evidence, createdAt, expiresAt, stagedBy) "
            "VALUES (?, ?, 'needs_evidence', ?, ?, ?, ?)",
            (proposal_id, tool_name, json.dumps(evidence), now_iso(), expires_at, staged_by),
        )
        self._db.commit()
        return self.find(tool_name) or {"id": proposal_id, "toolName": tool_name}

    def withdraw(self, proposal_id: str) -> bool:
        cursor = self._db.execute(
            "UPDATE WideningProposal SET status='withdrawn' WHERE id=? AND status='needs_evidence'",
            (proposal_id,),
        )
        self._db.commit()
        return cursor.rowcount > 0

    def list(self, *, limit: int = 100) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT * FROM WideningProposal ORDER BY createdAt DESC LIMIT ?",
            (max(1, min(int(limit), 500)),),
        ).fetchall()
        return [dict(row) for row in rows]


def stage_proposals(
    store: Any,
    registry: Any,
    granted_tools: Iterable[str],
    *,
    limit: int = 5,
    staged_by: str = "operator",
    ttl_days: int = 14,
    blocked_tools: Iterable[str] = (),
) -> dict[str, Any]:
    """Stage eligible shadow tools. Never grants or activates."""
    import datetime as _dt

    report = shadow_report(registry, granted_tools, blocked_tools=blocked_tools)
    if not report.get("ok"):
        return {"ok": False, "error": report.get("error"), "staged": []}
    proposals = WideningProposalStore(store)
    expiry = (
        _dt.datetime.now(_dt.timezone.utc) + _dt.timedelta(days=max(1, int(ttl_days)))
    ).isoformat().replace("+00:00", "Z")
    staged: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for row in report.get("rows") or []:
        if len(staged) >= max(1, int(limit)):
            break
        if row.get("status") != "eligible_shadow":
            continue
        existing = proposals.find(str(row["name"]))
        if existing is not None and existing.get("status") != "withdrawn":
            skipped.append({"toolName": row["name"], "reason": "already_staged"})
            continue
        evidence = {
            "tool": row,
            "required": {
                "historicalReplay": False,
                "denyPath": False,
                "conclusionStability": False,
            },
            "note": "staging is not permission; a human ratifies after the evidence is complete",
        }
        staged.append(proposals.add(
            tool_name=str(row["name"]), evidence=evidence,
            expires_at=expiry, staged_by=staged_by,
        ))
    return {"ok": True, "counts": report.get("counts"), "staged": staged, "skipped": skipped}


__all__ = ["WideningProposalStore", "stage_proposals"]
