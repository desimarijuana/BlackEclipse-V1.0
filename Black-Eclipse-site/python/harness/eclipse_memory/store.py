"""Eclipse-Memory store — the ONE persistence path for memory and skills.

`EclipseMemoryStore` holds both:
  * Memory domain (records, evidence, links, retrieval audit, mistakes,
    corrections), and
  * Skill domain (the Phase-3 tables, carried over unchanged).

The Phase-3 `harness.skills.store.SkillStore` is now a backward-compatible
alias for this class, so there is exactly one skill persistence implementation.
Nothing else may open `eclipse-memory.db` directly.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any, Optional

from .db import EclipseMemoryDb, new_id, now_iso

# Statuses a memory may carry. `proposed` is an automatic candidate awaiting
# review; `active` is usable; `archived`/`superseded`/`rejected`/`expired` are
# inert but retained for audit (never deleted).
MEMORY_STATUSES = frozenset(
    {"proposed", "active", "archived", "superseded", "rejected", "expired"}
)

MEMORY_TYPES = frozenset(
    {
        "episodic", "semantic", "procedural", "preference",
        "constraint", "correction", "observation", "summary",
    }
)


class EclipseMemoryStore:
    def __init__(self, path: Optional[str] = None, db: Optional[EclipseMemoryDb] = None) -> None:
        self.db = db or EclipseMemoryDb(path)
        self.path = self.db.path
        self._db = self.db.connection

    # ═══════════════════════════════════════════════════════════════════════
    # Memory
    # ═══════════════════════════════════════════════════════════════════════

    def save_memory(
        self,
        *,
        memory_type: str,
        scope: str,
        content: str,
        scope_id: Optional[str] = None,
        subject: Optional[str] = None,
        structured_data: Optional[dict[str, Any]] = None,
        source: Optional[str] = None,
        source_run_id: Optional[str] = None,
        confidence: float = 0.5,
        importance: float = 0.5,
        status: str = "active",
        verification: str = "unverified",
        created_by: Optional[str] = None,
        expires_at: Optional[str] = None,
        authority: str = "explicit",
        status_reason: Optional[str] = None,
    ) -> dict[str, Any]:
        memory_id = new_id("mem")
        now = now_iso()
        self._db.execute(
            """INSERT INTO MemoryRecord
               (id, memoryType, scope, scopeId, subject, content, structuredData, source,
                sourceRunId, confidence, importance, status, verification, createdBy,
                createdAt, updatedAt, accessCount, expiresAt, authority, statusReason)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?)""",
            (
                memory_id, memory_type, scope, scope_id, subject, content,
                json.dumps(structured_data) if structured_data is not None else None,
                source, source_run_id,
                max(0.0, min(float(confidence), 1.0)),
                max(0.0, min(float(importance), 1.0)),
                status, verification, created_by, now, now, expires_at,
                authority if authority in ("explicit", "automatic") else "explicit",
                status_reason,
            ),
        )
        self._db.commit()
        self.append_memory_event("memory.created", memory_id=memory_id, run_id=source_run_id,
                                 data={"memoryType": memory_type, "scope": scope, "status": status})
        return self.get_memory(memory_id)  # type: ignore[return-value]

    def get_memory(self, memory_id: str) -> Optional[dict[str, Any]]:
        row = self._db.execute("SELECT * FROM MemoryRecord WHERE id=?", (memory_id,)).fetchone()
        return _memory_row(row) if row else None

    def list_memories(
        self,
        *,
        memory_type: Optional[str] = None,
        scope: Optional[str] = None,
        scope_id: Optional[str] = None,
        status: Optional[str] = None,
        subject: Optional[str] = None,
        source: Optional[str] = None,
        limit: int = 100,
        include_inactive: bool = True,
    ) -> list[dict[str, Any]]:
        where: list[str] = []
        params: list[Any] = []
        if memory_type:
            where.append("memoryType = ?"); params.append(memory_type)
        if scope:
            where.append("scope = ?"); params.append(scope)
        if scope_id:
            where.append("scopeId = ?"); params.append(scope_id)
        if subject:
            where.append("subject = ?"); params.append(subject)
        if source:
            where.append("source = ?"); params.append(source)
        if status:
            where.append("status = ?"); params.append(status)
        elif not include_inactive:
            where.append("status = 'active'")
        clause = f"WHERE {' AND '.join(where)}" if where else ""
        limit = max(1, min(int(limit), 500))
        rows = self._db.execute(
            f"SELECT * FROM MemoryRecord {clause} ORDER BY updatedAt DESC LIMIT ?",
            [*params, limit],
        ).fetchall()
        return [_memory_row(r) for r in rows]

    def memory_lifecycle_counts(self) -> dict[str, Any]:
        """Counts for the Control Room lifecycle views (expired, superseded,
        never-used, frequently-recalled, conflicts). Never returns content."""
        def _count(sql: str, params: tuple[Any, ...] = ()) -> int:
            row = self._db.execute(sql, params).fetchone()
            return int(row[0]) if row else 0

        now = now_iso()
        return {
            "active": _count("SELECT COUNT(*) FROM MemoryRecord WHERE status='active'"),
            "expired": _count("SELECT COUNT(*) FROM MemoryRecord WHERE status='expired'"),
            "archived": _count("SELECT COUNT(*) FROM MemoryRecord WHERE status='archived'"),
            "superseded": _count("SELECT COUNT(*) FROM MemoryRecord WHERE status='superseded'"),
            "rejected": _count("SELECT COUNT(*) FROM MemoryRecord WHERE status='rejected'"),
            "proposed": _count("SELECT COUNT(*) FROM MemoryRecord WHERE status='proposed'"),
            "neverUsed": _count(
                "SELECT COUNT(*) FROM MemoryRecord WHERE status='active' AND lastUsedAt IS NULL"
            ),
            "frequentlyRecalled": _count(
                "SELECT COUNT(*) FROM MemoryRecord WHERE status='active' AND accessCount >= 3"
            ),
            "expiring": _count(
                "SELECT COUNT(*) FROM MemoryRecord WHERE status='active'"
                " AND expiresAt IS NOT NULL AND expiresAt <= ?",
                (now,),
            ),
            "automatic": _count("SELECT COUNT(*) FROM MemoryRecord WHERE authority='automatic'"),
            "explicit": _count("SELECT COUNT(*) FROM MemoryRecord WHERE authority='explicit'"),
        }

    def list_lifecycle_memories(
        self,
        view: str,
        *,
        scope_id: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Return memories for a named lifecycle view. Content is included (the
        Control Room needs to render it); this is a local operator surface."""
        limit = max(1, min(int(limit), 500))
        where: list[str] = []
        params: list[Any] = []
        if view == "active":
            where.append("status = 'active'")
        elif view == "expired":
            where.append("status = 'expired'")
        elif view == "superseded":
            where.append("status = 'superseded'")
        elif view == "rejected":
            where.append("status = 'rejected'")
        elif view == "archived":
            where.append("status = 'archived'")
        elif view == "never-used":
            where.append("status = 'active' AND lastUsedAt IS NULL")
        elif view == "frequently-recalled":
            where.append("status = 'active' AND accessCount >= 3")
        elif view == "automatic":
            where.append("authority = 'automatic'")
        elif view == "conflicts":
            where.append("status = 'superseded'")
        else:
            where.append("status = 'active'")
        if scope_id:
            where.append("(scopeId = ? OR scopeId IS NULL)")
            params.append(scope_id)
        clause = " AND ".join(where)
        rows = self._db.execute(
            f"SELECT * FROM MemoryRecord WHERE {clause} ORDER BY updatedAt DESC LIMIT ?",
            [*params, limit],
        ).fetchall()
        return [_memory_row(r) for r in rows]

    def update_memory(self, memory_id: str, **patch: Any) -> Optional[dict[str, Any]]:
        allowed = {
            "content", "structuredData", "confidence", "importance", "status",
            "verification", "reviewedAt", "reviewStatus", "expiresAt", "supersededBy",
            "lastAccessedAt", "subject", "lastConfirmedAt", "lastUsedAt",
            "lastReviewedAt", "authority", "statusReason", "scope", "scopeId",
        }
        sets, params = [], []
        for key, value in patch.items():
            if key not in allowed:
                continue
            sets.append(f"{key} = ?")
            params.append(json.dumps(value) if key == "structuredData" and value is not None else value)
        if not sets:
            return self.get_memory(memory_id)
        sets.append("updatedAt = ?"); params.append(now_iso())
        params.append(memory_id)
        self._db.execute(f"UPDATE MemoryRecord SET {', '.join(sets)} WHERE id=?", params)
        self._db.commit()
        return self.get_memory(memory_id)

    def archive_memory(
        self, memory_id: str, status: str = "archived", *, reason: Optional[str] = None
    ) -> Optional[dict[str, Any]]:
        updated = self.update_memory(
            memory_id, status=status,
            statusReason=reason or f"set to {status}", lastReviewedAt=now_iso(),
        )
        if updated:
            self.append_memory_event(f"memory.{status}", memory_id=memory_id,
                                     data={"reason": reason} if reason else None)
        return updated

    def restore_memory(self, memory_id: str) -> Optional[dict[str, Any]]:
        """Return an inert memory to active. History is retained; the restore is
        auditable. An explicit memory is restored directly; an automatic memory
        is restored as active (the caller re-confirms it)."""
        updated = self.update_memory(
            memory_id, status="active", statusReason="restored",
            lastConfirmedAt=now_iso(), lastReviewedAt=now_iso(), supersededBy=None,
        )
        if updated:
            self.append_memory_event("memory.restored", memory_id=memory_id)
        return updated

    def supersede_memory(self, old_id: str, new_id_value: str, *, reason: Optional[str] = None) -> None:
        """Mark `old_id` superseded by `new_id_value` and link them. The old
        record is retained (never deleted) for audit."""
        self.update_memory(
            old_id, status="superseded", supersededBy=new_id_value,
            statusReason=reason or f"superseded by {new_id_value}",
            lastReviewedAt=now_iso(),
        )
        self.add_link(old_id, new_id_value, "superseded", note=reason)
        self.append_memory_event("memory.superseded", memory_id=old_id,
                                 data={"supersededBy": new_id_value, "reason": reason})

    def confirm_memory(self, memory_id: str) -> Optional[dict[str, Any]]:
        """Record an explicit re-confirmation of an existing memory. Bumps
        `lastConfirmedAt` (the memory's freshness anchor) without changing
        content — used when the user restates the same durable fact."""
        updated = self.update_memory(memory_id, lastConfirmedAt=now_iso())
        if updated:
            self.append_memory_event("memory.confirmed", memory_id=memory_id)
        return updated

    def mark_reviewed(self, memory_id: str) -> Optional[dict[str, Any]]:
        return self.update_memory(memory_id, lastReviewedAt=now_iso())

    def record_access(self, memory_ids: list[str]) -> None:
        """Bump access counters AND last-used time for retrieved memories
        (best-effort). `lastUsedAt` is distinct from `lastAccessedAt`: the latter
        is a legacy column kept for compatibility; the former is the lifecycle
        signal used to find never-used / frequently-recalled memories."""
        now = now_iso()
        for memory_id in memory_ids:
            self._db.execute(
                "UPDATE MemoryRecord SET accessCount = accessCount + 1,"
                " lastAccessedAt = ?, lastUsedAt = ? WHERE id = ?",
                (now, now, memory_id),
            )
        self._db.commit()

    # ── Memory suggestions (inert, non-recalled proposals) ──────────────────

    def save_suggestion(self, suggestion: dict[str, Any]) -> str:
        suggestion_id = suggestion.get("id") or new_id("sugg")
        self._db.execute(
            """INSERT INTO MemorySuggestion
               (id, runId, scope, scopeId, subject, memoryType, content, reason, provenance,
                confidence, signature, status, candidateId, createdAt, decidedAt)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                suggestion_id, suggestion.get("runId"), suggestion.get("scope", "user"),
                suggestion.get("scopeId"), suggestion.get("subject"),
                suggestion.get("memoryType", "semantic"), suggestion["content"],
                suggestion.get("reason"), suggestion.get("provenance"),
                float(suggestion.get("confidence", 0.5)), suggestion["signature"],
                suggestion.get("status", "pending"), suggestion.get("candidateId"),
                suggestion.get("createdAt") or now_iso(), suggestion.get("decidedAt"),
            ),
        )
        self._db.commit()
        return suggestion_id

    def get_suggestion(self, suggestion_id: str) -> Optional[dict[str, Any]]:
        row = self._db.execute(
            "SELECT * FROM MemorySuggestion WHERE id=?", (suggestion_id,)
        ).fetchone()
        return dict(row) if row else None

    def list_suggestions(
        self, status: Optional[str] = None, *, scope_id: Optional[str] = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        where: list[str] = []
        params: list[Any] = []
        if status:
            where.append("status = ?"); params.append(status)
        if scope_id:
            where.append("scopeId = ?"); params.append(scope_id)
        clause = f"WHERE {' AND '.join(where)}" if where else ""
        limit = max(1, min(int(limit), 500))
        rows = self._db.execute(
            f"SELECT * FROM MemorySuggestion {clause} ORDER BY createdAt DESC LIMIT ?",
            [*params, limit],
        ).fetchall()
        return [dict(r) for r in rows]

    def find_suggestion_by_signature(
        self, signature: str, *, scope_id: Optional[str] = None
    ) -> Optional[dict[str, Any]]:
        """Most recent suggestion with this signature.

        When `scope_id` is given, only suggestions in that user scope (or
        unscoped ones) match — so one user's dismissal never suppresses another
        user's suggestion for identical content.
        """
        if scope_id is not None:
            row = self._db.execute(
                "SELECT * FROM MemorySuggestion WHERE signature=? AND (scopeId IS NULL OR scopeId=?)"
                " ORDER BY createdAt DESC LIMIT 1",
                (signature, scope_id),
            ).fetchone()
        else:
            row = self._db.execute(
                "SELECT * FROM MemorySuggestion WHERE signature=? ORDER BY createdAt DESC LIMIT 1",
                (signature,),
            ).fetchone()
        return dict(row) if row else None

    def set_suggestion_status(self, suggestion_id: str, status: str) -> Optional[dict[str, Any]]:
        self._db.execute(
            "UPDATE MemorySuggestion SET status=?, decidedAt=? WHERE id=?",
            (status, now_iso(), suggestion_id),
        )
        self._db.commit()
        return self.get_suggestion(suggestion_id)

    # ── Evidence ────────────────────────────────────────────────────────────

    def add_evidence(
        self,
        memory_id: str,
        *,
        source_type: str,
        source_ref: Optional[str] = None,
        source_url: Optional[str] = None,
        source_run_id: Optional[str] = None,
        evidence_text: Optional[str] = None,
        retrieved_at: Optional[str] = None,
        published_at: Optional[str] = None,
        verification_status: str = "unknown",
    ) -> dict[str, Any]:
        evidence_id = new_id("mev")
        self._db.execute(
            """INSERT INTO MemoryEvidence
               (id, memoryId, sourceType, sourceRef, sourceUrl, sourceRunId, evidenceText,
                retrievedAt, publishedAt, verificationStatus, createdAt)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (evidence_id, memory_id, source_type, source_ref, source_url, source_run_id,
             evidence_text, retrieved_at, published_at, verification_status, now_iso()),
        )
        self._db.commit()
        return self.get_evidence(evidence_id)  # type: ignore[return-value]

    def get_evidence(self, evidence_id: str) -> Optional[dict[str, Any]]:
        row = self._db.execute("SELECT * FROM MemoryEvidence WHERE id=?", (evidence_id,)).fetchone()
        return dict(row) if row else None

    def list_evidence(self, memory_id: str) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT * FROM MemoryEvidence WHERE memoryId=? ORDER BY createdAt", (memory_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Links ───────────────────────────────────────────────────────────────

    def add_link(self, from_id: str, to_id: str, relation: str, note: Optional[str] = None) -> dict[str, Any]:
        link_id = new_id("mlink")
        self._db.execute(
            "INSERT INTO MemoryLink (id, fromId, toId, relation, note, createdAt) VALUES (?, ?, ?, ?, ?, ?)",
            (link_id, from_id, to_id, relation, note, now_iso()),
        )
        self._db.commit()
        return {"id": link_id, "fromId": from_id, "toId": to_id, "relation": relation, "note": note}

    def list_links(self, memory_id: str) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT * FROM MemoryLink WHERE fromId=? OR toId=? ORDER BY createdAt",
            (memory_id, memory_id),
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Retrieval audit ─────────────────────────────────────────────────────

    def record_retrieval(self, event: dict[str, Any]) -> str:
        event_id = new_id("mret")
        self._db.execute(
            """INSERT INTO MemoryRetrievalEvent
               (id, runId, query, requestedTypes, candidates, selected, excluded,
                selectionReasons, budgetChars, usedChars, durationMs, ok, error, createdAt)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                event_id, event.get("runId"), event.get("query"),
                json.dumps(event.get("requestedTypes") or []),
                int(event.get("candidates", 0)), int(event.get("selected", 0)),
                json.dumps(event.get("excluded") or []),
                json.dumps(event.get("selectionReasons") or []),
                event.get("budgetChars"), int(event.get("usedChars", 0)),
                int(event.get("durationMs", 0)), 1 if event.get("ok", True) else 0,
                event.get("error"), now_iso(),
            ),
        )
        self._db.commit()
        return event_id

    def list_retrievals(self, limit: int = 50) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT * FROM MemoryRetrievalEvent ORDER BY createdAt DESC LIMIT ?", (max(1, limit),)
        ).fetchall()
        out = []
        for r in rows:
            record = dict(r)
            for key in ("requestedTypes", "excluded", "selectionReasons"):
                record[key] = json.loads(record[key]) if record.get(key) else []
            out.append(record)
        return out

    # ── Mistakes / corrections ──────────────────────────────────────────────

    def save_mistake(self, mistake: dict[str, Any]) -> str:
        mistake_id = mistake.get("id") or new_id("mistake")
        self._db.execute(
            """INSERT INTO MistakeRecord
               (id, category, severity, runId, skillId, skillVersion, toolName, expected,
                actual, evidence, correctiveAction, correctionWorked, reusable, candidateId, createdAt)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                mistake_id, mistake["category"], mistake.get("severity", "medium"),
                mistake.get("runId"), mistake.get("skillId"), mistake.get("skillVersion"),
                mistake.get("toolName"), mistake.get("expected"), mistake.get("actual"),
                json.dumps(mistake.get("evidence")) if mistake.get("evidence") is not None else None,
                mistake.get("correctiveAction"),
                None if mistake.get("correctionWorked") is None else (1 if mistake["correctionWorked"] else 0),
                1 if mistake.get("reusable") else 0,
                mistake.get("candidateId"), mistake.get("createdAt") or now_iso(),
            ),
        )
        self._db.commit()
        return mistake_id

    def list_mistakes(self, run_id: Optional[str] = None, limit: int = 100) -> list[dict[str, Any]]:
        if run_id:
            rows = self._db.execute(
                "SELECT * FROM MistakeRecord WHERE runId=? ORDER BY createdAt DESC LIMIT ?",
                (run_id, max(1, limit)),
            ).fetchall()
        else:
            rows = self._db.execute(
                "SELECT * FROM MistakeRecord ORDER BY createdAt DESC LIMIT ?", (max(1, limit),)
            ).fetchall()
        return [dict(r) for r in rows]

    def save_correction(self, correction: dict[str, Any]) -> str:
        correction_id = correction.get("id") or new_id("correction")
        self._db.execute(
            """INSERT INTO CorrectionRecord
               (id, runId, memoryId, subject, wrong, correction, providedBy, evidence, scope,
                generalizable, appliedToSkill, status, createdAt)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                correction_id, correction.get("runId"), correction.get("memoryId"),
                correction.get("subject"), correction["wrong"], correction["correction"],
                correction.get("providedBy", "user"),
                json.dumps(correction.get("evidence")) if correction.get("evidence") is not None else None,
                correction.get("scope", "user"),
                1 if correction.get("generalizable") else 0,
                correction.get("appliedToSkill"), correction.get("status", "recorded"),
                correction.get("createdAt") or now_iso(),
            ),
        )
        self._db.commit()
        return correction_id

    def list_corrections(self, limit: int = 100) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT * FROM CorrectionRecord ORDER BY createdAt DESC LIMIT ?", (max(1, limit),)
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Recurrence ledger (bounded, signature-only) ─────────────────────────

    def record_recurrence(self, signature: str) -> int:
        """Bump the seen-count for a normalized statement signature and return
        the new count. Only the digest is stored — never the raw text. Idempotent
        per call; prunes older rows so the table stays bounded."""
        if not signature:
            return 0
        now = now_iso()
        row = self._db.execute(
            "SELECT seenCount FROM MemoryRecurrence WHERE signature=?", (signature,)
        ).fetchone()
        if row:
            count = int(row["seenCount"]) + 1
            self._db.execute(
                "UPDATE MemoryRecurrence SET seenCount=?, lastSeenAt=? WHERE signature=?",
                (count, now, signature),
            )
        else:
            count = 1
            self._db.execute(
                "INSERT INTO MemoryRecurrence (signature, seenCount, firstSeenAt, lastSeenAt)"
                " VALUES (?, 1, ?, ?)",
                (signature, now, now),
            )
        self._db.commit()
        self._prune_recurrence()
        return count

    def recurrence_count(self, signature: str) -> int:
        """How many times this signature has been recorded (0 when unseen)."""
        if not signature:
            return 0
        row = self._db.execute(
            "SELECT seenCount FROM MemoryRecurrence WHERE signature=?", (signature,)
        ).fetchone()
        return int(row["seenCount"]) if row else 0

    def _prune_recurrence(self, keep: int = 2000) -> None:
        """Keep only the most recently seen signatures (bounded growth)."""
        try:
            self._db.execute(
                "DELETE FROM MemoryRecurrence WHERE signature IN ("
                "  SELECT signature FROM MemoryRecurrence ORDER BY lastSeenAt DESC LIMIT -1 OFFSET ?"
                ")",
                (max(1, int(keep)),),
            )
            self._db.commit()
        except Exception:  # noqa: BLE001 - pruning must never block a write
            pass

    # ── Memory events (audit) ───────────────────────────────────────────────

    def append_memory_event(
        self, event_type: str, *, memory_id: Optional[str] = None, run_id: Optional[str] = None,
        data: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        event = {
            "id": new_id("memevent"), "memoryId": memory_id, "runId": run_id,
            "type": event_type, "at": now_iso(), "data": data or {},
        }
        self._db.execute(
            "INSERT INTO MemoryEvent (id, memoryId, runId, type, at, data) VALUES (?, ?, ?, ?, ?, ?)",
            (event["id"], memory_id, run_id, event_type, event["at"], json.dumps(event["data"])),
        )
        self._db.commit()
        return event

    def list_memory_events(self, limit: int = 100) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT * FROM MemoryEvent ORDER BY at DESC LIMIT ?", (max(1, limit),)
        ).fetchall()
        out = []
        for r in rows:
            record = dict(r)
            record["data"] = json.loads(record["data"]) if record["data"] else {}
            out.append(record)
        return out

    # ═══════════════════════════════════════════════════════════════════════
    # Skills (Phase-3 API — unchanged behaviour, now in eclipse-memory.db)
    # ═══════════════════════════════════════════════════════════════════════

    def upsert_skill(
        self, *, skill_id: str, name: str, description: str, category: str,
        latest_version: str, status: str, tags: list[str],
    ) -> None:
        now = now_iso()
        existing = self._db.execute("SELECT id FROM Skill WHERE id = ?", (skill_id,)).fetchone()
        if existing:
            self._db.execute(
                """UPDATE Skill SET name=?, description=?, category=?, latestVersion=?,
                   status=?, tags=?, updatedAt=? WHERE id=?""",
                (name, description, category, latest_version, status, json.dumps(tags), now, skill_id),
            )
        else:
            self._db.execute(
                """INSERT INTO Skill (id, name, description, category, latestVersion, status, tags, createdAt, updatedAt)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (skill_id, name, description, category, latest_version, status, json.dumps(tags), now, now),
            )
        self._db.commit()

    def save_version(
        self,
        manifest: dict[str, Any],
        content_hash: str,
        *,
        instructions: Optional[str] = None,
        base_version: Optional[str] = None,
        patch_summary: Optional[str] = None,
        review_id: Optional[str] = None,
        patch_author: Optional[str] = None,
        canary_state: Optional[str] = None,
        patch: Optional[dict[str, Any]] = None,
    ) -> None:
        skill_id = manifest["id"]
        version = manifest["version"]
        existing = self._db.execute(
            "SELECT id FROM SkillVersion WHERE skillId=? AND version=?", (skill_id, version)
        ).fetchone()
        if existing:
            raise ValueError(
                f"skill {skill_id!r} version {version!r} already exists; versions are immutable"
            )
        now = now_iso()
        vid = new_id("skillver")
        self._db.execute(
            """INSERT INTO SkillVersion
               (id, skillId, version, manifest, contentHash, status, evaluationStatus, riskLevel,
                instructionsLocation, instructions, author, origin, sourceRunId, originCandidateId,
                limitations, createdAt, updatedAt,
                baseVersion, patchSummary, reviewId, patchAuthor, canaryState, patch)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                vid, skill_id, version, json.dumps(manifest), content_hash,
                manifest.get("status", "draft"), manifest.get("evaluationStatus", "not_evaluated"),
                manifest.get("riskLevel", "low"), manifest.get("instructions"),
                instructions, manifest.get("author"), manifest.get("origin", "builtin"),
                manifest.get("sourceRunId"), manifest.get("originCandidateId"),
                manifest.get("knownLimitations"), now, now,
                base_version, patch_summary, review_id, patch_author, canary_state,
                json.dumps(patch) if patch is not None else None,
            ),
        )
        for dep in manifest.get("requiredSkills", []) or []:
            self._db.execute(
                "INSERT INTO SkillDependency (id, skillId, version, dependsOn, constraint_, optional) VALUES (?, ?, ?, ?, ?, ?)",
                (new_id("dep"), skill_id, version, dep["skillId"], dep.get("version"), 1 if dep.get("optional") else 0),
            )
        for tool in manifest.get("requiredTools", []) or []:
            self._db.execute(
                "INSERT INTO SkillToolRequirement (id, skillId, version, toolName) VALUES (?, ?, ?, ?)",
                (new_id("toolreq"), skill_id, version, tool),
            )
        for perm in manifest.get("permissions", []) or []:
            self._db.execute(
                "INSERT INTO SkillPermissionRequirement (id, skillId, version, permission) VALUES (?, ?, ?, ?)",
                (new_id("permreq"), skill_id, version, perm),
            )
        self._db.commit()

    def list_skills(self, status: Optional[str] = None) -> list[dict[str, Any]]:
        if status:
            rows = self._db.execute("SELECT * FROM Skill WHERE status=? ORDER BY id", (status,)).fetchall()
        else:
            rows = self._db.execute("SELECT * FROM Skill ORDER BY id").fetchall()
        out = []
        for row in rows:
            record = dict(row)
            record["tags"] = json.loads(record["tags"]) if record["tags"] else []
            out.append(record)
        return out

    def get_skill(self, skill_id: str) -> Optional[dict[str, Any]]:
        row = self._db.execute("SELECT * FROM Skill WHERE id=?", (skill_id,)).fetchone()
        if not row:
            return None
        record = dict(row)
        record["tags"] = json.loads(record["tags"]) if record["tags"] else []
        return record

    def get_version(self, skill_id: str, version: str) -> Optional[dict[str, Any]]:
        row = self._db.execute(
            "SELECT * FROM SkillVersion WHERE skillId=? AND version=?", (skill_id, version)
        ).fetchone()
        return self._version_row(row) if row else None

    def get_version_by_hash(self, skill_id: str, content_hash: str) -> Optional[dict[str, Any]]:
        row = self._db.execute(
            "SELECT * FROM SkillVersion WHERE skillId=? AND contentHash=?", (skill_id, content_hash)
        ).fetchone()
        return self._version_row(row) if row else None

    def list_versions(self, skill_id: str) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT * FROM SkillVersion WHERE skillId=? ORDER BY createdAt ASC", (skill_id,)
        ).fetchall()
        return [self._version_row(r) for r in rows]

    def set_version_status(self, skill_id: str, version: str, status: str, evaluation_status: Optional[str] = None) -> None:
        sets = ["status = ?", "updatedAt = ?"]
        params: list[Any] = [status, now_iso()]
        if evaluation_status is not None:
            sets.append("evaluationStatus = ?"); params.append(evaluation_status)
        params.extend([skill_id, version])
        self._db.execute(f"UPDATE SkillVersion SET {', '.join(sets)} WHERE skillId=? AND version=?", params)
        self._db.execute("UPDATE Skill SET status=?, updatedAt=? WHERE id=?", (status, now_iso(), skill_id))
        self._db.commit()

    def set_latest_version(self, skill_id: str, version: str) -> None:
        self._db.execute("UPDATE Skill SET latestVersion=?, updatedAt=? WHERE id=?", (version, now_iso(), skill_id))
        self._db.commit()

    def set_version_activation(
        self, skill_id: str, version: str, *, activated: bool,
    ) -> None:
        """Stamp `activatedAt`/`rolledBackAt` on a version (Milestone 2)."""
        if activated:
            self._db.execute(
                "UPDATE SkillVersion SET activatedAt=?, rolledBackAt=NULL, canaryState=NULL WHERE skillId=? AND version=?",
                (now_iso(), skill_id, version),
            )
        else:
            self._db.execute(
                "UPDATE SkillVersion SET rolledBackAt=?, activatedAt=NULL WHERE skillId=? AND version=?",
                (now_iso(), skill_id, version),
            )
        self._db.commit()

    def set_canary_state(self, skill_id: str, version: str, canary_state: Optional[str]) -> None:
        self._db.execute(
            "UPDATE SkillVersion SET canaryState=?, updatedAt=? WHERE skillId=? AND version=?",
            (canary_state, now_iso(), skill_id, version),
        )
        self._db.commit()

    def create_execution(
        self, *, run_id: str, skill_id: str, version: str, manifest_hash: Optional[str],
        parent_run_id: Optional[str], execution_mode: str, actor: str, input_data: dict[str, Any],
    ) -> str:
        execution_id = new_id("skex")
        self._db.execute(
            """INSERT INTO SkillExecution
               (id, runId, skillId, version, manifestHash, parentRunId, executionMode, status,
                actor, input, durationMs, traceId, createdAt)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'running', ?, ?, 0, ?, ?)""",
            (execution_id, run_id, skill_id, version, manifest_hash, parent_run_id,
             execution_mode, actor, json.dumps(input_data), run_id, now_iso()),
        )
        self._db.commit()
        return execution_id

    def finish_execution(
        self, execution_id: str, *, status: str, output: Optional[str] = None,
        error: Optional[dict[str, Any]] = None, warnings: Optional[list[str]] = None,
        missing_data: Optional[list[str]] = None, limitations: Optional[list[str]] = None,
        evidence: Optional[list[Any]] = None, duration_ms: int = 0,
        output_validated: Optional[bool] = None, metrics: Optional[dict[str, Any]] = None,
    ) -> None:
        self._db.execute(
            """UPDATE SkillExecution SET status=?, output=?, error=?, warnings=?, missingData=?,
               limitations=?, evidence=?, durationMs=?, finishedAt=?,
               outputValidated=?, metrics=? WHERE id=?""",
            (status, output, json.dumps(error) if error else None, json.dumps(warnings or []),
             json.dumps(missing_data or []), json.dumps(limitations or []),
             json.dumps(evidence or []), int(duration_ms), now_iso(),
             None if output_validated is None else (1 if output_validated else 0),
             json.dumps(metrics) if metrics is not None else None, execution_id),
        )
        self._db.commit()

    def get_execution(self, run_id: str) -> Optional[dict[str, Any]]:
        row = self._db.execute("SELECT * FROM SkillExecution WHERE runId=?", (run_id,)).fetchone()
        return self._execution_row(row) if row else None

    def list_executions(self, skill_id: Optional[str] = None, limit: int = 50) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 500))
        if skill_id:
            rows = self._db.execute(
                "SELECT * FROM SkillExecution WHERE skillId=? ORDER BY createdAt DESC LIMIT ?",
                (skill_id, limit),
            ).fetchall()
        else:
            rows = self._db.execute("SELECT * FROM SkillExecution ORDER BY createdAt DESC LIMIT ?", (limit,)).fetchall()
        return [self._execution_row(r) for r in rows]

    def save_evaluation(
        self, *, skill_id: str, version: str, status: str, dimensions: list[dict[str, Any]],
        evaluator: str = "deterministic-v1", summary: Optional[str] = None,
        cases: Optional[list[dict[str, Any]]] = None,
    ) -> str:
        evaluation_id = new_id("eval")
        self._db.execute(
            """INSERT INTO SkillEvaluation (id, skillId, version, status, evaluator, dimensions, summary, createdAt)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (evaluation_id, skill_id, version, status, evaluator, json.dumps(dimensions), summary, now_iso()),
        )
        for case in cases or []:
            self._db.execute(
                """INSERT INTO SkillEvaluationCase
                   (id, evaluationId, skillId, version, caseId, name, kind, input, expected, createdAt)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (new_id("evalcase"), evaluation_id, skill_id, version, case["caseId"],
                 case.get("name", case["caseId"]), case.get("kind", "schema"),
                 json.dumps(case.get("input")) if case.get("input") is not None else None,
                 json.dumps(case.get("expected")) if case.get("expected") is not None else None,
                 now_iso()),
            )
        self._db.execute(
            "UPDATE SkillVersion SET evaluationStatus=?, updatedAt=? WHERE skillId=? AND version=?",
            (status, now_iso(), skill_id, version),
        )
        self._db.commit()
        return evaluation_id

    def get_evaluation(self, evaluation_id: str) -> Optional[dict[str, Any]]:
        row = self._db.execute("SELECT * FROM SkillEvaluation WHERE id=?", (evaluation_id,)).fetchone()
        if not row:
            return None
        record = dict(row)
        record["dimensions"] = json.loads(record["dimensions"]) if record["dimensions"] else []
        cases = self._db.execute(
            "SELECT * FROM SkillEvaluationCase WHERE evaluationId=? ORDER BY caseId", (evaluation_id,)
        ).fetchall()
        record["cases"] = [self._case_row(c) for c in cases]
        return record

    def list_evaluations(self, skill_id: Optional[str] = None, limit: int = 50) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 500))
        if skill_id:
            rows = self._db.execute(
                "SELECT * FROM SkillEvaluation WHERE skillId=? ORDER BY createdAt DESC LIMIT ?",
                (skill_id, limit),
            ).fetchall()
        else:
            rows = self._db.execute("SELECT * FROM SkillEvaluation ORDER BY createdAt DESC LIMIT ?", (limit,)).fetchall()
        out = []
        for row in rows:
            record = dict(row)
            record["dimensions"] = json.loads(record["dimensions"]) if record["dimensions"] else []
            out.append(record)
        return out

    def replace_evaluation_cases(self, skill_id: str, version: str, cases: list[dict[str, Any]]) -> None:
        self._db.execute(
            "DELETE FROM SkillEvaluationCase WHERE skillId=? AND version=? AND evaluationId IS NULL",
            (skill_id, version),
        )
        for case in cases:
            self._db.execute(
                """INSERT INTO SkillEvaluationCase
                   (id, evaluationId, skillId, version, caseId, name, kind, input, expected, createdAt)
                   VALUES (?, NULL, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (new_id("evalcase"), skill_id, version, case["caseId"], case.get("name", case["caseId"]),
                 case.get("kind", "schema"),
                 json.dumps(case.get("input")) if case.get("input") is not None else None,
                 json.dumps(case.get("expected")) if case.get("expected") is not None else None,
                 now_iso()),
            )
        self._db.commit()

    def list_evaluation_cases(self, skill_id: str, version: str) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT * FROM SkillEvaluationCase WHERE skillId=? AND version=? ORDER BY caseId",
            (skill_id, version),
        ).fetchall()
        return [self._case_row(r) for r in rows]

    def save_candidate(self, candidate: dict[str, Any]) -> str:
        candidate_id = candidate.get("id") or new_id("cand")
        self._db.execute(
            """INSERT INTO LearningCandidate
               (id, sourceRunId, candidateType, title, problem, observedBehavior, proposedLesson,
                proposedProcedure, evidenceReferences, confidence, generalizationNotes, knownLimitations,
                signature, duplicateGroup, status, createdAt, reviewedAt, resultingSkillId,
                resultingSkillVersion, draftManifest, diagnostics, scope)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (candidate_id, candidate.get("sourceRunId"), candidate["candidateType"], candidate["title"],
             candidate.get("problem"), candidate.get("observedBehavior"), candidate.get("proposedLesson"),
             json.dumps(candidate.get("proposedProcedure")) if candidate.get("proposedProcedure") is not None else None,
             json.dumps(candidate.get("evidenceReferences") or []),
             float(candidate.get("confidence", 0.5)),
             candidate.get("generalizationNotes"), candidate.get("knownLimitations"),
             candidate["signature"], candidate.get("duplicateGroup"),
             candidate.get("status", "detected"), candidate.get("createdAt") or now_iso(),
             candidate.get("reviewedAt"), candidate.get("resultingSkillId"),
             candidate.get("resultingSkillVersion"),
             json.dumps(candidate.get("draftManifest")) if candidate.get("draftManifest") is not None else None,
             json.dumps(candidate.get("diagnostics")) if candidate.get("diagnostics") is not None else None,
             json.dumps(candidate.get("scope")) if candidate.get("scope") is not None else None),
        )
        self._db.commit()
        return candidate_id

    def update_candidate(self, candidate_id: str, **patch: Any) -> None:
        allowed = {
            "status", "reviewedAt", "resultingSkillId", "resultingSkillVersion",
            "draftManifest", "confidence", "knownLimitations",
        }
        sets, params = [], []
        for key, value in patch.items():
            if key not in allowed:
                continue
            sets.append(f"{key} = ?")
            params.append(json.dumps(value) if key == "draftManifest" and value is not None else value)
        if not sets:
            return
        params.append(candidate_id)
        self._db.execute(f"UPDATE LearningCandidate SET {', '.join(sets)} WHERE id=?", params)
        self._db.commit()

    def get_candidate(self, candidate_id: str) -> Optional[dict[str, Any]]:
        row = self._db.execute("SELECT * FROM LearningCandidate WHERE id=?", (candidate_id,)).fetchone()
        return self._candidate_row(row) if row else None

    def list_candidates(self, status: Optional[str] = None, limit: int = 100) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 500))
        if status:
            rows = self._db.execute(
                "SELECT * FROM LearningCandidate WHERE status=? ORDER BY createdAt DESC LIMIT ?",
                (status, limit),
            ).fetchall()
        else:
            rows = self._db.execute("SELECT * FROM LearningCandidate ORDER BY createdAt DESC LIMIT ?", (limit,)).fetchall()
        return [self._candidate_row(r) for r in rows]

    def find_candidate_by_signature(self, signature: str) -> Optional[dict[str, Any]]:
        row = self._db.execute(
            "SELECT * FROM LearningCandidate WHERE signature=? ORDER BY createdAt DESC LIMIT 1", (signature,)
        ).fetchone()
        return self._candidate_row(row) if row else None

    def save_promotion_request(
        self, *, skill_id: str, version: str, requested_by: str, reason: str,
        evaluation_id: Optional[str], status: str = "pending",
    ) -> str:
        request_id = new_id("promo")
        self._db.execute(
            """INSERT INTO SkillPromotionRequest
               (id, skillId, version, requestedBy, status, reason, evaluationId, createdAt)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (request_id, skill_id, version, requested_by, status, reason, evaluation_id, now_iso()),
        )
        self._db.commit()
        return request_id

    def decide_promotion(self, request_id: str, status: str) -> None:
        self._db.execute(
            "UPDATE SkillPromotionRequest SET status=?, decidedAt=? WHERE id=?",
            (status, now_iso(), request_id),
        )
        self._db.commit()

    def list_promotion_requests(self, skill_id: Optional[str] = None, limit: int = 100) -> list[dict[str, Any]]:
        if skill_id:
            rows = self._db.execute(
                "SELECT * FROM SkillPromotionRequest WHERE skillId=? ORDER BY createdAt DESC LIMIT ?",
                (skill_id, limit),
            ).fetchall()
        else:
            rows = self._db.execute("SELECT * FROM SkillPromotionRequest ORDER BY createdAt DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    def save_review(self, *, skill_id: str, version: str, actor: str, decision: str, notes: str) -> str:
        review_id = new_id("review")
        self._db.execute(
            "INSERT INTO SkillReview (id, skillId, version, actor, decision, notes, createdAt) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (review_id, skill_id, version, actor, decision, notes, now_iso()),
        )
        self._db.commit()
        return review_id

    def list_reviews(self, skill_id: Optional[str] = None, limit: int = 100) -> list[dict[str, Any]]:
        if skill_id:
            rows = self._db.execute(
                "SELECT * FROM SkillReview WHERE skillId=? ORDER BY createdAt DESC LIMIT ?", (skill_id, limit)
            ).fetchall()
        else:
            rows = self._db.execute("SELECT * FROM SkillReview ORDER BY createdAt DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    def append_event(
        self, event_type: str, *, skill_id: Optional[str] = None, version: Optional[str] = None,
        run_id: Optional[str] = None, data: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        event = {
            "id": new_id("skillevent"), "skillId": skill_id, "version": version,
            "runId": run_id, "type": event_type, "at": now_iso(), "data": data or {},
        }
        self._db.execute(
            "INSERT INTO SkillEvent (id, skillId, version, runId, type, at, data) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (event["id"], skill_id, version, run_id, event_type, event["at"], json.dumps(event["data"])),
        )
        self._db.commit()
        return event

    def list_events(self, skill_id: Optional[str] = None, limit: int = 200) -> list[dict[str, Any]]:
        if skill_id:
            rows = self._db.execute(
                "SELECT * FROM SkillEvent WHERE skillId=? ORDER BY at DESC LIMIT ?", (skill_id, limit)
            ).fetchall()
        else:
            rows = self._db.execute("SELECT * FROM SkillEvent ORDER BY at DESC LIMIT ?", (limit,)).fetchall()
        out = []
        for row in rows:
            record = dict(row)
            record["data"] = json.loads(record["data"]) if record["data"] else {}
            out.append(record)
        return out

    # ── Row mappers ─────────────────────────────────────────────────────────

    def _version_row(self, row: sqlite3.Row) -> dict[str, Any]:
        record = dict(row)
        record["manifest"] = json.loads(record["manifest"])
        if record.get("patch"):
            try:
                record["patch"] = json.loads(record["patch"])
            except (TypeError, ValueError):
                record["patch"] = None
        return record

    @staticmethod
    def _execution_row(row: sqlite3.Row) -> dict[str, Any]:
        record = dict(row)
        for key in ("input", "error", "warnings", "missingData", "limitations", "evidence", "metrics"):
            if record.get(key):
                try:
                    record[key] = json.loads(record[key])
                except (TypeError, ValueError):
                    pass
        # SQLite stores the boolean as 0/1/NULL; expose a tri-state to the caller:
        # True / False / None ("not recorded", for pre-migration rows).
        raw_validated = record.get("outputValidated")
        record["outputValidated"] = None if raw_validated is None else bool(raw_validated)
        return record

    @staticmethod
    def _case_row(row: sqlite3.Row) -> dict[str, Any]:
        record = dict(row)
        for key in ("input", "expected"):
            if record.get(key):
                try:
                    record[key] = json.loads(record[key])
                except (TypeError, ValueError):
                    pass
        return record

    @staticmethod
    def _candidate_row(row: sqlite3.Row) -> dict[str, Any]:
        record = dict(row)
        for key in ("proposedProcedure", "evidenceReferences", "draftManifest", "diagnostics", "scope"):
            if record.get(key):
                try:
                    record[key] = json.loads(record[key])
                except (TypeError, ValueError):
                    pass
        return record

    # ── User-authored skills ────────────────────────────────────────────────

    def save_user_skill(self, skill: dict[str, Any]) -> dict[str, Any]:
        """Insert or update a user-authored skill. The `UserSkill` row is the
        authoritative source for a user skill (re-materialised into the Skill/
        SkillVersion tables on load)."""
        now = now_iso()
        existing = self._db.execute("SELECT id, createdAt FROM UserSkill WHERE id=?", (skill["id"],)).fetchone()
        created_at = existing["createdAt"] if existing else (skill.get("createdAt") or now)
        self._db.execute(
            """INSERT INTO UserSkill
               (id, name, description, category, tags, instructions, manifest, version, status, author, createdAt, updatedAt)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                 name=excluded.name, description=excluded.description, category=excluded.category,
                 tags=excluded.tags, instructions=excluded.instructions, manifest=excluded.manifest,
                 version=excluded.version, status=excluded.status, author=excluded.author,
                 updatedAt=excluded.updatedAt""",
            (
                skill["id"], skill["name"], skill["description"], skill["category"],
                json.dumps(skill.get("tags") or []), skill["instructions"],
                json.dumps(skill["manifest"]), skill["version"], skill.get("status", "draft"),
                skill.get("author"), created_at, now,
            ),
        )
        self._db.commit()
        return self.get_user_skill(skill["id"])  # type: ignore[return-value]

    def get_user_skill(self, skill_id: str) -> Optional[dict[str, Any]]:
        row = self._db.execute("SELECT * FROM UserSkill WHERE id=?", (skill_id,)).fetchone()
        return _user_skill_row(row) if row else None

    def list_user_skills(self) -> list[dict[str, Any]]:
        rows = self._db.execute("SELECT * FROM UserSkill ORDER BY updatedAt DESC").fetchall()
        return [_user_skill_row(r) for r in rows]

    def delete_user_skill(self, skill_id: str) -> bool:
        cursor = self._db.execute("DELETE FROM UserSkill WHERE id=?", (skill_id,))
        self._db.commit()
        return cursor.rowcount > 0

    def delete_skill_records(self, skill_id: str) -> None:
        """Remove a skill's materialised rows (Skill/SkillVersion/requirements).
        Execution/evaluation history is intentionally retained where it exists;
        this is only called for an unreferenced user skill."""
        for table in ("SkillDependency", "SkillToolRequirement", "SkillPermissionRequirement"):
            self._db.execute(f"DELETE FROM {table} WHERE skillId=?", (skill_id,))
        self._db.execute("DELETE FROM SkillVersion WHERE skillId=?", (skill_id,))
        self._db.execute("DELETE FROM Skill WHERE id=?", (skill_id,))
        self._db.commit()

    # ── Health / lifecycle ──────────────────────────────────────────────────

    def migration_status(self) -> dict[str, Any]:
        return self.db.migration_status()

    def health(self) -> dict[str, Any]:
        return self.db.health()

    # ── Maintenance state (observable retention sweeps) ─────────────────────

    def record_maintenance(
        self, operation: str, *, ok: bool, inspected: int = 0,
        expired: int = 0, skipped: int = 0, error: Optional[str] = None,
    ) -> None:
        """Persist the outcome of a maintenance operation (singleton per op).

        Best-effort: a bookkeeping failure must never break the operation it
        records.
        """
        try:
            self._db.execute(
                """INSERT INTO MemoryMaintenance
                   (id, operation, ranAt, ok, inspected, expired, skipped, error)
                   VALUES (1, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET
                     operation=excluded.operation, ranAt=excluded.ranAt, ok=excluded.ok,
                     inspected=excluded.inspected, expired=excluded.expired,
                     skipped=excluded.skipped, error=excluded.error""",
                (operation, now_iso(), 1 if ok else 0, int(inspected), int(expired),
                 int(skipped), error),
            )
            self._db.commit()
        except Exception:  # noqa: BLE001 - maintenance bookkeeping is best-effort
            pass

    def maintenance_status(self) -> Optional[dict[str, Any]]:
        """The last recorded maintenance outcome, or None when never run."""
        try:
            row = self._db.execute(
                "SELECT * FROM MemoryMaintenance WHERE id = 1"
            ).fetchone()
        except Exception:  # noqa: BLE001 - a pre-migration/closed db reads as unknown
            return None
        if not row:
            return None
        record = dict(row)
        record["ok"] = bool(record.get("ok"))
        return record

    # ── Profile snapshots (reproducible compact-profile metadata) ────────────

    def save_profile_snapshot(
        self,
        *,
        version: int,
        selected_ids: list[str],
        char_count: int = 0,
        token_estimate: int = 0,
        scope_id: Optional[str] = None,
        run_id: Optional[str] = None,
        excluded_count: int = 0,
        created_at: Optional[str] = None,
    ) -> str:
        """Persist the metadata of one materialized profile. Content is NOT
        copied — the selected ids remain the source of truth. Best-effort."""
        snapshot_id = new_id("prof")
        self._db.execute(
            """INSERT INTO MemoryProfileSnapshot
               (id, version, selectedIds, charCount, tokenEstimate, scopeId,
                runId, excludedCount, createdAt)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                snapshot_id, int(version), json.dumps(list(selected_ids)),
                int(char_count), int(token_estimate), scope_id, run_id,
                int(excluded_count), created_at or now_iso(),
            ),
        )
        self._db.commit()
        return snapshot_id

    def latest_profile_snapshot(self) -> Optional[dict[str, Any]]:
        try:
            row = self._db.execute(
                "SELECT * FROM MemoryProfileSnapshot ORDER BY createdAt DESC LIMIT 1"
            ).fetchone()
        except Exception:  # noqa: BLE001 - a pre-migration db reads as unknown
            return None
        return _profile_row(row) if row else None

    def list_profile_snapshots(self, limit: int = 20) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 200))
        try:
            rows = self._db.execute(
                "SELECT * FROM MemoryProfileSnapshot ORDER BY createdAt DESC LIMIT ?",
                (limit,),
            ).fetchall()
        except Exception:  # noqa: BLE001
            return []
        return [_profile_row(r) for r in rows]

    def close(self) -> None:
        self.db.close()


def _user_skill_row(row: sqlite3.Row) -> dict[str, Any]:
    record = dict(row)
    for key in ("tags", "manifest"):
        if record.get(key):
            try:
                record[key] = json.loads(record[key])
            except (TypeError, ValueError):
                pass
    return record


def _memory_row(row: sqlite3.Row) -> dict[str, Any]:
    record = dict(row)
    if record.get("structuredData"):
        try:
            record["structuredData"] = json.loads(record["structuredData"])
        except (TypeError, ValueError):
            pass
    return record


def _profile_row(row: sqlite3.Row) -> dict[str, Any]:
    record = dict(row)
    if record.get("selectedIds"):
        try:
            record["selectedIds"] = json.loads(record["selectedIds"])
        except (TypeError, ValueError):
            record["selectedIds"] = []
    return record


__all__ = ["EclipseMemoryStore", "MEMORY_STATUSES", "MEMORY_TYPES", "now_iso", "new_id"]
