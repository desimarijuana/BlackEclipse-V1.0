"""Eclipse-Memory service â€” the controlled write/retrieve pipelines.

Nothing writes memory directly through the store; it goes through this service,
which implements the pipeline the brief requires:

    Candidate Observation
      â†’ Classify memory type
      â†’ Normalize/validate content
      â†’ Check scope
      â†’ Check duplication
      â†’ Attach evidence (optional)
      â†’ Determine confidence
      â†’ Apply retention (expiry)
      â†’ Persist
      â†’ Emit memory event

Memory is not saved just because a model produced a sentence. Callers must
state an explicit source (an explicit user request, a correction, a validated
execution lesson, a system decision), and the service rejects empty/duplicate
observations.

Retrieval is delegated to `retrieval.retrieve_memories`. This service is the
one object the harness runtime depends on.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from .policy import PolicyStore
from .retrieval import RetrievalResult, retrieve_memories
from .store import MEMORY_TYPES, EclipseMemoryStore

class MemoryWriteError(ValueError):
    """A memory write was rejected by the pipeline (never silently dropped)."""


class MemoryFullError(MemoryWriteError):
    """The active-memory storage budget is reached.

    A distinct, truthful failure: user memory is never auto-evicted to make
    room. The caller surfaces "memory is full" and the user reviews/archives.
    """

    def __init__(self, message: str, *, limit: int, active: int) -> None:
        super().__init__(message)
        self.limit = limit
        self.active = active


# Sources that justify persisting a memory. Anything else is refused, so the
# database cannot fill up with every conversational sentence.
VALID_SOURCES = frozenset(
    {
        "explicit_user",      # "remember that â€¦"
        "user_correction",    # the user corrected Eclipse
        "execution_lesson",   # a validated reusable lesson from a run
        "system_decision",    # an explicitly recorded architecture decision
        "verified_source",    # durable info from a verified source
        "skill_promotion",    # a validated skill produced a procedural memory
        "mistake",            # a captured mistake/recovery
        "manual",             # an operator wrote it through the UI/API
        "imported",           # restored from an operator export file
    }
)

MAX_CONTENT_CHARS = 4000

# Sources that mark a memory as EXPLICIT (a human stated or wrote it). Everything
# else is automatically learned and may become stale / require review. An explicit
# memory is never silently expired by retention policy.
EXPLICIT_SOURCES = frozenset({"explicit_user", "user_correction", "manual", "imported"})


def _derive_authority(source: str) -> str:
    return "explicit" if source in EXPLICIT_SOURCES else "automatic"


class EclipseMemoryService:
    def __init__(self, store: Optional[EclipseMemoryStore] = None) -> None:
        self.store = store or EclipseMemoryStore()
        self.policy = PolicyStore(self.store)
        # Named profiles (M4): a metadata registry + directory projection. It
        # owns no memory content; it only scopes which profile a query belongs to.
        from .profiles import ProfileRegistry  # noqa: PLC0415

        self.profiles = ProfileRegistry()
        try:
            self.profiles.ensure_default()
        except Exception:  # noqa: BLE001 - a projection failure must not block boot
            pass

    # â”€â”€ Write pipeline â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def write_memory(
        self,
        *,
        memory_type: str,
        content: str,
        source: str,
        scope: str = "general",
        scope_id: Optional[str] = None,
        subject: Optional[str] = None,
        structured_data: Optional[dict[str, Any]] = None,
        source_run_id: Optional[str] = None,
        confidence: float = 0.5,
        importance: float = 0.5,
        verification: str = "unverified",
        created_by: Optional[str] = None,
        expires_at: Optional[str] = None,
        evidence: Optional[dict[str, Any]] = None,
        allow_duplicate: bool = False,
    ) -> dict[str, Any]:
        # 1. Classify / validate type.
        if memory_type not in MEMORY_TYPES:
            raise MemoryWriteError(f"unknown memory type {memory_type!r}")
        # 1b. Local privacy controls (Phase 6). These can only REFUSE a write,
        # never authorize one, and never bypass scope/privacy rules below.
        try:
            settings = self.policy.get_all()
        except Exception:  # noqa: BLE001 - a policy read failure fails closed on the controls below
            settings = {}
        if settings.get("memory_enabled") is False:
            raise MemoryWriteError("memory is disabled by policy â€” no memory is stored")
        from .policy import category_policy  # noqa: PLC0415

        if source != "user_correction" and category_policy(settings, "capture_policy", memory_type) == "deny":
            raise MemoryWriteError(f"capture of {memory_type!r} memory is denied by policy")
        # 2. Validate content.
        text_value = (content or "").strip()
        if not text_value:
            raise MemoryWriteError("memory content must not be empty")
        if len(text_value) > MAX_CONTENT_CHARS:
            raise MemoryWriteError(f"memory content exceeds {MAX_CONTENT_CHARS} chars")
        # 2b. Defense in depth: a secret-shaped value is refused at the single
        # persistence path too, not only at the decision gate. The decision gate
        # is the primary guard; this ensures a non-gated caller (e.g. an import or
        # suggestion accept) cannot persist a credential.
        from .decision import looks_like_credential_value  # noqa: PLC0415

        if looks_like_credential_value(text_value):
            raise MemoryWriteError("content contains a credential value and was not stored")
        # 3. Validate source (prevents filling memory with arbitrary text).
        if source not in VALID_SOURCES:
            raise MemoryWriteError(f"source {source!r} is not a permitted memory source")
        # 4. Scope: a user preference must be user-scoped, never universal.
        if memory_type == "preference" and scope == "general":
            scope = "user"
            scope_id = scope_id or created_by
        # 5. Duplicate check (same scope + subject + normalized content).
        signature = _content_signature(memory_type, scope, scope_id, subject, text_value)
        if not allow_duplicate:
            existing = self._find_duplicate(signature)
            if existing:
                # Re-stating the same durable fact is a CONFIRMATION: refresh the
                # freshness anchor rather than creating a second record. This keeps
                # "last confirmed" meaningful and prevents a re-save from counting
                # against the storage budget. An automatic memory's retention is
                # refreshed too, so a re-affirmed fact does not expire on its old
                # clock. A non-active record is NEVER revived by a duplicate write â€”
                # unless the new statement carries explicit replacement intent
                # ("prefer X now"), which falls through so the user can deliberately
                # re-assert a reversed preference as a fresh active truth.
                if existing.get("status") == "active":
                    existing = self._confirm_existing(existing)
                    self.store.append_memory_event(
                        "memory.duplicate_skipped", memory_id=existing["id"],
                        run_id=source_run_id, data={"signature": signature},
                    )
                    return existing
                from .conflicts import is_replacement_intent  # noqa: PLC0415

                if not is_replacement_intent(text_value):
                    # An inert duplicate without replacement intent is returned
                    # unchanged â€” never revived, never duplicated.
                    self.store.append_memory_event(
                        "memory.duplicate_inert_skipped", memory_id=existing["id"],
                        run_id=source_run_id, data={"signature": signature},
                    )
                    return existing

        # 5b. Contradiction / replacement handling. Before a second active truth
        # is created, detect a conflict with an existing active memory in the same
        # scope. Explicit replacement supersedes the old record; an automatic
        # memory conflicting with an explicit one is stored inert; a conflicting
        # explicit statement supersedes the older one (latest explicit wins).
        # Nothing is ever merged, and the old record is always retained + linked.
        # 5b. Contradiction / replacement handling. Before a second active truth
        # is created, detect a conflict with an existing active memory in the same
        # scope + dimension. Authority decides: explicit replacement and explicit-
        # over-automatic supersede the old record (linked, retained); an automatic
        # conflict with explicit, or two ambiguous explicit statements, store the
        # new record inert (`proposed`) for review. Nothing is ever merged.
        superseded_ids: list[str] = []
        write_status = "active"
        write_reason: Optional[str] = None
        authority = _derive_authority(source)
        if not allow_duplicate and source != "user_correction" and memory_type != "correction":
            assessment = self._assess_conflict(
                memory_type=memory_type, scope=scope, scope_id=scope_id,
                subject=subject, content=text_value, new_authority=authority,
            )
            from .conflicts import DECISION_CONFIRM  # noqa: PLC0415

            if assessment.decision == DECISION_CONFIRM:
                # Same statement restated: confirm the existing record (refresh
                # freshness/expiry) instead of creating a second record.
                first = assessment.related[0]
                confirmed = self._confirm_existing(first)
                self.store.append_memory_event(
                    "memory.conflict_confirmed", memory_id=first["id"], run_id=source_run_id,
                    data={"reason": assessment.reason},
                )
                return confirmed
            if assessment.conflict:
                superseded_ids, write_status = self._resolve_conflict(
                    assessment, new_authority=authority,
                    subject=subject, run_id=source_run_id,
                )
                if write_status == "proposed":
                    write_reason = f"conflict: {assessment.reason}"

        # 5c. Storage budget. A duplicate return above does not consume budget;
        # a genuinely new record must fit. The budget is never enforced by
        # auto-deleting user memory â€” the write fails truthfully instead. A
        # correction is exempt: it supersedes an existing record right after, so
        # it does not grow the retained set, and blocking an explicit correction
        # would be worse than a temporarily over-full count.
        if source != "user_correction" and write_status != "proposed":
            self._check_budget()

        # Retention: only AUTOMATIC memories are eligible for a policy-derived
        # expiry. An explicit memory is never silently expired (the brief: do not
        # silently expire explicit memories). An explicit caller value always
        # wins over the policy-derived default.
        if expires_at is None and authority == "automatic":
            expires_at = self._retention_expiry()

        memory = self.store.save_memory(
            memory_type=memory_type, scope=scope, content=text_value,
            scope_id=scope_id, subject=subject, structured_data=structured_data,
            source=source, source_run_id=source_run_id, confidence=confidence,
            importance=importance, status=write_status, verification=verification,
            created_by=created_by, expires_at=expires_at,
            authority=authority, status_reason=write_reason,
        )
        memory = self.store.update_memory(memory["id"], structuredData=structured_data) or memory
        # Link any superseded records to the new one (history retained).
        for old_id in superseded_ids:
            self.store.supersede_memory(
                old_id, memory["id"], reason="superseded by a later conflicting memory",
            )
        if superseded_ids:
            memory = self.store.get_memory(memory["id"]) or memory
        # 6. Evidence.
        if evidence:
            self.store.add_evidence(
                memory["id"],
                source_type=evidence.get("sourceType", "unknown"),
                source_ref=evidence.get("sourceRef"),
                source_url=evidence.get("sourceUrl"),
                source_run_id=evidence.get("sourceRunId", source_run_id),
                evidence_text=evidence.get("text"),
                retrieved_at=evidence.get("retrievedAt"),
                published_at=evidence.get("publishedAt"),
                verification_status=evidence.get("verificationStatus", "unknown"),
            )
        # Announce the durable write on the Event System (canonical `memory.created`).
        # Best-effort: a publish failure must never fail a memory write.
        from ..event_system.emit import publish_event  # noqa: PLC0415

        publish_event("memory.created", {
            "memoryId": memory["id"], "memoryType": memory_type, "scope": scope,
            "status": memory.get("status"),
        }, source="memory")
        return memory

    def propose_memory(
        self,
        *,
        memory_type: str,
        content: str,
        source: str = "execution_lesson",
        **kwargs: Any,
    ) -> dict[str, Any]:
        """An automatic candidate â€” inert until reviewed. Uses status
        `proposed` so retrieval excludes it by default."""
        kwargs.setdefault("verification", "unverified")
        memory = self.write_memory(memory_type=memory_type, content=content, source=source, **kwargs)
        # A proposed memory is inert until reviewed: flip a freshly created row
        # to `proposed` so retrieval excludes it. (A duplicate return keeps its
        # existing status â€” never silently un-approve an active memory.)
        if memory.get("status") == "active":
            memory = self.store.update_memory(memory["id"], status="proposed") or memory
        return memory

    def review_memory(self, memory_id: str, *, approve: bool, reviewed_by: Optional[str] = None) -> Optional[dict[str, Any]]:
        status = "active" if approve else "rejected"
        now = _now()
        patch: dict[str, Any] = {
            "status": status,
            "reviewStatus": "approved" if approve else "rejected",
            "reviewedAt": now,
            "lastReviewedAt": now,
            "statusReason": "reviewed: approved" if approve else "reviewed: rejected",
        }
        if approve:
            patch["lastConfirmedAt"] = now
        updated = self.store.update_memory(memory_id, **patch)
        if updated:
            self.store.append_memory_event(
                f"memory.{status}", memory_id=memory_id, data={"reviewedBy": reviewed_by}
            )
            from ..event_system.emit import publish_event  # noqa: PLC0415

            publish_event("memory.updated", {
                "memoryId": memory_id, "status": status,
            }, source="memory")
        return updated

    def _find_duplicate(self, signature: str) -> Optional[dict[str, Any]]:
        """The existing memory with this signature, across ALL statuses.

        Searching inactive records too is what stops a duplicate write from
        silently re-asserting an expired/superseded/archived/rejected fact as a
        new active truth: the inert record is returned unchanged (never revived
        by duplicate handling â€” an explicit restore is the only way back).
        """
        for memory in self.store.list_memories(limit=500, include_inactive=True):
            if _content_signature(
                memory["memoryType"], memory["scope"], memory.get("scopeId"),
                memory.get("subject"), memory["content"],
            ) == signature:
                return memory
        return None

    def _confirm_existing(self, existing: dict[str, Any]) -> dict[str, Any]:
        """Confirm an active existing memory on a duplicate write.

        Refreshes `lastConfirmedAt`, and for an AUTOMATIC memory also extends
        `expiresAt` from the current retention policy (an explicit memory keeps
        no retention expiry). Never changes status, so an inert record can never
        be revived here.
        """
        now = _now()
        patch: dict[str, Any] = {"lastConfirmedAt": now}
        if (existing.get("authority") or "explicit") == "automatic":
            patch["expiresAt"] = self.renewal_expiry()
        updated = self.store.update_memory(existing["id"], **patch)
        if updated:
            self.store.append_memory_event("memory.confirmed", memory_id=existing["id"])
        return updated or existing

    # â”€â”€ Contradiction / replacement â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _assess_conflict(
        self, *, memory_type: str, scope: str, scope_id: Optional[str],
        subject: Optional[str], content: str, new_authority: str,
    ) -> Any:
        """Deterministically assess a conflict with an existing active memory."""
        from .conflicts import detect_conflict  # noqa: PLC0415

        try:
            existing = self.store.list_memories(
                memory_type=memory_type, scope=scope, scope_id=scope_id,
                limit=200, include_inactive=False,
            )
        except Exception:  # noqa: BLE001 - conflict detection must never block a write
            existing = []
        return detect_conflict(
            memory_type=memory_type, scope=scope, scope_id=scope_id,
            subject=subject, content=content, existing=existing,
            new_authority=new_authority,
        )

    def _resolve_conflict(
        self, assessment: Any, *, new_authority: str,
        subject: Optional[str], run_id: Optional[str],
    ) -> tuple[list[str], str]:
        """Decide the disposition of a detected conflict.

        Returns `(superseded_ids, new_status)`. Authority MATTERS here â€” it is
        what distinguishes "explicit overrides automatic" from "ambiguous".

          * ``supersede`` (explicit replacement, or explicit over automatic): the
            old record(s) are superseded (linked, retained) and the new one is
            active;
          * ``propose`` (automatic vs explicit, or two explicit statements): the
            new record is stored inert (`proposed`) so it is visible for review;
            no second active truth is created.
        """
        from .conflicts import DECISION_SUPERSEDE  # noqa: PLC0415

        if assessment.decision == DECISION_SUPERSEDE:
            superseded = [m["id"] for m in assessment.related]
            self.store.append_memory_event(
                "memory.conflict_superseded", run_id=run_id,
                data={"superseded": superseded, "replacement": assessment.replacement,
                      "authority": new_authority, "reason": assessment.reason},
            )
            return superseded, "active"
        self.store.append_memory_event(
            "memory.conflict_needs_review", run_id=run_id,
            data={"against": [m["id"] for m in assessment.related],
                  "authority": new_authority, "reason": assessment.reason},
        )
        return [], "proposed"

    def _active_memory_count(self) -> int:
        try:
            row = self.store._db.execute(
                "SELECT COUNT(*) FROM MemoryRecord WHERE status='active'"
            ).fetchone()
            return int(row[0]) if row else 0
        except Exception:  # noqa: BLE001 - a count failure must not block a write
            return 0

    def _check_budget(self) -> None:
        """Fail a genuinely new write truthfully when the storage budget is full.

        The budget counts ACTIVE memories; inert history (archived/superseded/
        proposed) does not consume it. User memory is never auto-deleted to make
        room â€” the caller must surface the honest full state.
        """
        try:
            limit = int(self.policy.get("max_memories") or 0)
        except Exception:  # noqa: BLE001
            limit = 0
        if limit <= 0:
            return
        active = self._active_memory_count()
        if active >= limit:
            self.store.append_memory_event(
                "memory.budget_full", data={"limit": limit, "active": active}
            )
            raise MemoryFullError(
                f"memory is full ({active}/{limit} active). Archive or review memories "
                "to free space â€” existing memory is never deleted automatically.",
                limit=limit, active=active,
            )

    def memory_budget(self) -> dict[str, Any]:
        """The current storage-budget state, for health/policy UI."""
        try:
            limit = int(self.policy.get("max_memories") or 0)
        except Exception:  # noqa: BLE001
            limit = 0
        active = self._active_memory_count()
        return {
            "limit": limit,
            "active": active,
            "unlimited": limit <= 0,
            "full": bool(limit > 0 and active >= limit),
            "remaining": None if limit <= 0 else max(0, limit - active),
        }

    # â”€â”€ Retention / lifecycle â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _retention_expiry(self) -> Optional[str]:
        """The `expiresAt` for a newly written AUTOMATIC memory, from
        `retention_days` (0 = never). Explicit memories never call this."""
        try:
            days = int(self.policy.get("retention_days") or 0)
        except Exception:  # noqa: BLE001
            days = 0
        if days <= 0:
            return None
        import datetime

        expiry = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=days)
        return expiry.strftime("%Y-%m-%dT%H:%M:%S") + ".000Z"

    def renewal_expiry(self, *, days: Optional[int] = None) -> Optional[str]:
        """The new `expiresAt` for an automatic memory when it is confirmed or
        renewed. `days` defaults to the current `retention_days` (0 = clear
        expiry). Explicit memories are never given an expiry by this path."""
        if days is None:
            try:
                days = int(self.policy.get("retention_days") or 0)
            except Exception:  # noqa: BLE001
                days = 0
        if days <= 0:
            return None
        import datetime

        expiry = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=days)
        return expiry.strftime("%Y-%m-%dT%H:%M:%S") + ".000Z"

    def expire_due_memories(self) -> dict[str, Any]:
        """Mark due AUTOMATIC memories `expired` (never delete). Idempotent.

        Retention is a review threshold, not deletion: a due record becomes inert
        and reviewable. EXPLICIT memories are exempt â€” retention never silently
        expires something the user stated.

        The result is observable (requirement: inspected/expired/skipped/reason)
        and is persisted so health/lifecycle diagnostics can report the last
        sweep. A sweep failure is reported honestly and never raised.
        """
        now = _now()
        inspected = 0
        expired: list[str] = []
        skipped = 0
        try:
            rows = self.store._db.execute(
                "SELECT id FROM MemoryRecord WHERE status='active'"
                " AND authority='automatic' AND expiresAt IS NOT NULL AND expiresAt <= ?",
                (now,),
            ).fetchall()
            inspected = len(rows)
            for row in rows:
                updated = self.store.archive_memory(
                    row["id"], status="expired",
                    reason="expiry: retention_period_elapsed (automatic memory)",
                )
                if updated:
                    expired.append(row["id"])
                else:
                    skipped += 1
        except Exception as exc:  # noqa: BLE001 - a sweep failure must never crash
            self.store.record_maintenance(
                "retention_sweep", ok=False, inspected=inspected,
                expired=len(expired), skipped=skipped, error=str(exc),
            )
            return {
                "ok": False, "inspected": inspected, "expired": len(expired),
                "skipped": skipped, "ids": expired, "error": str(exc),
                "ranAt": self.store.maintenance_status().get("ranAt")
                if self.store.maintenance_status() else None,
            }
        if expired:
            self.store.append_memory_event(
                "memory.retention_swept", data={"expired": len(expired)}
            )
        self.store.record_maintenance(
            "retention_sweep", ok=True, inspected=inspected,
            expired=len(expired), skipped=skipped,
        )
        status = self.store.maintenance_status() or {}
        return {
            "ok": True, "inspected": inspected, "expired": len(expired),
            "skipped": skipped, "ids": expired, "error": None,
            "ranAt": status.get("ranAt"),
        }

    def run_retention_maintenance(self) -> dict[str, Any]:
        """The boot/lifecycle entrypoint for retention.

        Safe to call on every start and idempotent. Always returns a result and
        NEVER raises, so a failure cannot stop the application from starting
        (requirement 5). The caller (the runtime lifespan) invokes this; there is
        no new daemon or thread.
        """
        try:
            return self.expire_due_memories()
        except Exception as exc:  # noqa: BLE001 - retention must never block boot
            try:
                self.store.record_maintenance(
                    "retention_sweep", ok=False, error=str(exc)
                )
            except Exception:  # noqa: BLE001
                pass
            return {"ok": False, "inspected": 0, "expired": 0, "skipped": 0,
                    "ids": [], "error": str(exc)}

    def preview_retention(self) -> dict[str, Any]:
        """Preview what a retention sweep would expire â€” WITHOUT sweeping.

        Returns the count + ids of due automatic memories so an operator can see
        the effect before it happens. Never writes. Explicit memories are exempt
        and listed separately as unaffected.
        """
        now = _now()
        try:
            rows = self.store._db.execute(
                "SELECT id FROM MemoryRecord WHERE status='active'"
                " AND authority='automatic' AND expiresAt IS NOT NULL AND expiresAt <= ?",
                (now,),
            ).fetchall()
            due_ids = [row["id"] for row in rows]
        except Exception as exc:  # noqa: BLE001 - a preview failure is reported honestly
            return {"ok": False, "due": 0, "ids": [], "error": str(exc)}
        return {
            "ok": True,
            "due": len(due_ids),
            "ids": due_ids,
            "action": "expire due automatic memories (status -> expired; never deleted)",
            "explicitExempt": True,
        }

    def retention_status(self) -> dict[str, Any]:
        """The retention policy state + the last sweep outcome (no content)."""
        try:
            retention_days = int(self.policy.get("retention_days") or 0)
        except Exception:  # noqa: BLE001
            retention_days = 0
        last = self.store.maintenance_status()
        review = self.preview_retention()
        # The next maintenance action: what a sweep would do now, stated plainly.
        if retention_days <= 0:
            next_action = "automatic retention is off â€” due automatic memories will not expire"
        elif review.get("due"):
            next_action = f"{review['due']} automatic memor(y/ies) are due to expire on the next sweep"
        else:
            next_action = "no automatic memory is due to expire"
        return {
            "retentionDays": retention_days,
            "automaticExpiryEnabled": retention_days > 0,
            "explicitMemoriesExempt": True,
            "lastSweep": last,
            "nextMaintenanceAction": next_action,
            "dueCount": review.get("due", 0),
        }

    def renew_memory(self, memory_id: str, *, days: Optional[int] = None) -> Optional[dict[str, Any]]:
        """Extend or clear an automatic memory's retention on explicit request.

        Confirming or renewing refreshes the lifecycle timestamps (requirement 8)
        and sets `expiresAt` from `days` (or the current policy when omitted).
        An explicit memory never receives an expiry from this path.
        """
        memory = self.store.get_memory(memory_id)
        if memory is None:
            return None
        expires: Optional[str]
        if (memory.get("authority") or "explicit") == "explicit" and days is None:
            # An explicit memory being (re)confirmed keeps no retention expiry.
            expires = None
        else:
            expires = self.renewal_expiry(days=days)
        now = _now()
        updated = self.store.update_memory(
            memory_id, expiresAt=expires, lastConfirmedAt=now, lastReviewedAt=now,
            statusReason="renewed/confirmed",
        )
        if updated:
            self.store.append_memory_event(
                "memory.renewed", memory_id=memory_id, data={"expiresAt": expires},
            )
        return updated

    # â”€â”€ Retrieval pipeline â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def retrieve(
        self,
        *,
        query: str,
        memory_types: Optional[list[str]] = None,
        scope: Optional[str] = None,
        scope_id: Optional[str] = None,
        subject: Optional[str] = None,
        actor_scope: Optional[str] = None,
        budget_chars: Optional[int] = None,
        limit: Optional[int] = None,
        run_id: Optional[str] = None,
        include_proposed: Optional[bool] = None,
        conversation_id: Optional[str] = None,
    ) -> RetrievalResult:
        # Policy supplies the defaults; an explicit caller value still wins.
        # A policy read failure must not crash retrieval â€” fall back to safe
        # defaults and let the retrieval path report its own diagnostics.
        try:
            settings = self.policy.get_all()
        except Exception:  # noqa: BLE001
            from .policy import DEFAULTS  # noqa: PLC0415

            settings = dict(DEFAULTS)
        denied: set[str] = set()
        recall_table = settings.get("recall_policy") or {}
        if isinstance(recall_table, dict):
            denied = {str(t) for t, v in recall_table.items() if str(v).lower() == "deny"}
        return retrieve_memories(
            self.store, query=query, memory_types=memory_types, scope=scope,
            scope_id=scope_id, subject=subject, actor_scope=actor_scope,
            budget_chars=budget_chars if budget_chars is not None else settings["context_budget_chars"],
            limit=limit if limit is not None else settings["retrieval_limit"],
            run_id=run_id,
            include_proposed=include_proposed if include_proposed is not None
            else settings["include_proposed_in_retrieval"],
            recall_denied_types=denied or None,
            conversation_id=conversation_id,
        )

    # â”€â”€ Compact prompt profile (materialized projection) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def build_profile(
        self,
        *,
        scope_id: Optional[str] = None,
        run_scope: Optional[str] = None,
        run_id: Optional[str] = None,
        persist: bool = False,
    ) -> Any:
        """Materialize the bounded compact profile over active memories.

        A projection, not a second store: nothing is written except optional
        reproducibility metadata. Never raises to the caller's run path.
        """
        from .profile import build_profile  # noqa: PLC0415

        try:
            settings = self.policy.get_all()
        except Exception:  # noqa: BLE001 - a policy failure uses safe defaults
            settings = {}
        return build_profile(
            self.store,
            scope_id=scope_id,
            run_scope=run_scope,
            policy=settings,
            persist=persist,
            run_id=run_id,
        )

    def profile_preview(
        self,
        *,
        scope_id: Optional[str] = None,
        run_scope: Optional[str] = None,
    ) -> dict[str, Any]:
        from .profile import preview_payload  # noqa: PLC0415

        snapshot = self.build_profile(scope_id=scope_id, run_scope=run_scope, persist=False)
        return preview_payload(snapshot)

    def profile_history(self, *, limit: int = 20) -> dict[str, Any]:
        return {
            "snapshots": self.store.list_profile_snapshots(limit=limit),
            "latest": self.store.latest_profile_snapshot(),
        }

    # â”€â”€ Corrections / mistakes â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def record_correction(
        self,
        *,
        wrong: str,
        correction: str,
        subject: Optional[str] = None,
        run_id: Optional[str] = None,
        provided_by: str = "user",
        scope: str = "user",
        generalizable: bool = False,
        evidence: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Record an explicit correction AND capture it as a correction memory.

        A correction is never automatically generalizable: it is recorded with
        its scope, and only a reviewed promotion can make it universal.
        """
        correction_id = self.store.save_correction({
            "wrong": wrong, "correction": correction, "subject": subject, "runId": run_id,
            "providedBy": provided_by, "scope": scope, "generalizable": generalizable,
            "evidence": evidence,
        })
        memory = self.write_memory(
            memory_type="correction",
            content=f"Correction â€” {subject or 'general'}: {wrong} â†’ {correction}",
            source="user_correction", scope=scope, subject=subject, source_run_id=run_id,
            confidence=0.9 if provided_by == "user" else 0.7,
            importance=0.8, verification="verified" if provided_by == "user" else "unverified",
            evidence=evidence,
        )
        self.store._db.execute(
            "UPDATE CorrectionRecord SET memoryId=?, status='captured' WHERE id=?",
            (memory["id"], correction_id),
        )
        self.store._db.commit()
        self.store.append_memory_event("memory.correction_recorded", memory_id=memory["id"], run_id=run_id,
                                       data={"correctionId": correction_id})
        return {"correctionId": correction_id, "memory": memory, "generalizable": generalizable}

    def record_mistake(self, mistake: dict[str, Any]) -> str:
        return self.store.save_mistake(mistake)

    # â”€â”€ Explicit user intent (deterministic post-run path) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def decide_turn(
        self,
        user_text: str,
        *,
        user_id: Optional[str] = None,
        recurring: bool = False,
        is_skill_run: bool = False,
        conversation_id: Optional[str] = None,
    ) -> Any:
        """Run the shared decision gate for one user turn.

        Reads policy + recent-dismissal state; never writes. Returns a
        `MemoryDecision`. Every write path must consult this gate.

        `recurring` is evidence that the same durable-sounding statement was seen
        in prior conversation history (computed by the caller from
        `RunRequest.input.history`). It is combined with a **persisted**,
        bounded recurrence ledger (signature-only; no raw text) so a convention
        repeated across sessions â€” beyond the bounded chat-history window â€” is
        still recognized.
        """
        from .decision import content_signature, decide_turn as _decide  # noqa: PLC0415

        settings = self.policy.get_all()
        signature = content_signature(user_text)
        recently_dismissed = False
        try:
            existing = self.store.find_suggestion_by_signature(signature, scope_id=user_id)
            recently_dismissed = bool(existing and existing.get("status") == "dismissed")
        except Exception:  # noqa: BLE001 - dismissal lookup must never block a run
            recently_dismissed = False
        prior = False
        try:
            prior = bool(self.store.list_memories(scope_id=user_id, limit=1, include_inactive=False))
        except Exception:  # noqa: BLE001
            prior = False
        # Persisted recurrence: prior occurrences of this exact statement.
        try:
            recurring = recurring or self.store.recurrence_count(signature) >= 1
        except Exception:  # noqa: BLE001 - recurrence lookup must never block a run
            pass
        decision = _decide(
            user_text, user_id=user_id, settings=settings,
            has_prior_memory=prior, recently_dismissed=recently_dismissed,
            recurring=recurring, is_skill_run=is_skill_run,
            conversation_id=conversation_id,
        )
        # Record this occurrence (after the decision) so the NEXT occurrence
        # counts as recurrence. Only durable-sounding turns are recorded, keeping
        # the ledger bounded and meaningful.
        try:
            if decision.action in ("save",) or decision.outcome in ("history_only", "suggest"):
                self.store.record_recurrence(signature)
        except Exception:  # noqa: BLE001
            pass
        return decision

    def create_suggestion(
        self,
        decision: Any,
        *,
        run_id: Optional[str] = None,
        scope_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Persist an INERT suggestion (never recalled, never a memory record).

        Deduplicated by signature; a previously dismissed suggestion is not
        re-created.
        """
        from .decision import content_signature  # noqa: PLC0415

        signature = content_signature(decision.content)
        existing = self.store.find_suggestion_by_signature(signature, scope_id=decision.scope_id or scope_id)
        if existing:
            status = existing.get("status")
            if status == "pending":
                return existing
            # A dismissed/decided suggestion is not silently re-offered.
            return {**existing, "alreadyDecided": True}
        suggestion_id = self.store.save_suggestion({
            "runId": run_id,
            "scope": decision.scope,
            "scopeId": decision.scope_id or scope_id,
            "subject": decision.subject,
            "memoryType": decision.memory_type,
            "content": decision.content,
            "reason": decision.reason,
            "provenance": decision.provenance,
            "confidence": decision.confidence,
            "signature": signature,
            "status": "pending",
        })
        self.store.append_memory_event(
            "memory.suggested", run_id=run_id,
            data={"suggestionId": suggestion_id, "reason": decision.reason},
        )
        return self.store.get_suggestion(suggestion_id) or {"id": suggestion_id}

    def accept_suggestion(self, suggestion_id: str, *, user_id: Optional[str] = None) -> dict[str, Any]:
        """Accept a suggestion â†’ write one scoped memory, mark it accepted.

        Cross-user isolation: a suggestion carrying a `scopeId` may only be
        accepted by that same user. When both the suggestion's owner and the
        acting `user_id` are present and differ, the request is refused rather
        than writing another user's preference into the wrong scope. (When
        `user_id` is omitted â€” the single-user/operator path â€” the suggestion's
        own scopeId is used and no mismatch can arise.)
        """
        from .decision import authorize_proposal  # noqa: PLC0415

        suggestion = self.store.get_suggestion(suggestion_id)
        if suggestion is None:
            return {"ok": False, "action": "not_found", "reason": "suggestion not found"}
        if suggestion["status"] != "pending":
            return {"ok": False, "action": suggestion["status"], "reason": "suggestion already decided"}
        owner = suggestion.get("scopeId")
        if owner and user_id and owner != user_id:
            self.store.append_memory_event(
                "memory.suggestion_scope_denied",
                data={"suggestionId": suggestion_id},
            )
            return {
                "ok": False, "action": "forbidden",
                "reason": "suggestion belongs to another user scope",
            }
        scope_id = owner or user_id
        decision = authorize_proposal(
            content=suggestion["content"], provenance="ui_save",
            user_id=user_id, memory_type=suggestion["memoryType"],
            scope=suggestion["scope"], scope_id=scope_id, subject=suggestion.get("subject"),
            confidence=suggestion.get("confidence") or 0.5,
            settings=self.policy.get_all(),
        )
        if decision.outcome != "save":
            self.store.set_suggestion_status(suggestion_id, "dismissed")
            return {"ok": False, "action": "refused", "reason": decision.reason}
        memory = self.write_memory(
            memory_type=decision.memory_type, content=decision.content,
            source="explicit_user", scope=decision.scope, scope_id=scope_id,
            subject=decision.subject, confidence=decision.confidence,
            importance=decision.importance, verification="unverified",
            created_by=user_id or "user",
        )
        self.store.set_suggestion_status(suggestion_id, "accepted")
        self.store.append_memory_event(
            "memory.suggestion_accepted", memory_id=memory["id"],
            data={"suggestionId": suggestion_id},
        )
        return {"ok": True, "action": "saved", "memory": memory}

    def dismiss_suggestion(self, suggestion_id: str, *, user_id: Optional[str] = None) -> dict[str, Any]:
        """Dismiss a suggestion. A suggestion owned by a different user scope may
        not be dismissed by another user (identifier guessing must not mutate
        another user's records)."""
        suggestion = self.store.get_suggestion(suggestion_id)
        if suggestion is None:
            return {"ok": False, "action": "not_found"}
        owner = suggestion.get("scopeId")
        if owner and user_id and owner != user_id:
            return {"ok": False, "action": "forbidden",
                    "reason": "suggestion belongs to another user scope"}
        suggestion = self.store.set_suggestion_status(suggestion_id, "dismissed")
        if suggestion is None:
            return {"ok": False, "action": "not_found"}
        self.store.append_memory_event(
            "memory.suggestion_dismissed", data={"suggestionId": suggestion_id}
        )
        return {"ok": True, "action": "dismissed", "suggestion": suggestion}

    def apply_explicit_intent(
        self,
        intent: Any,
        *,
        run_id: Optional[str] = None,
        user_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Persist (or act on) a detected explicit user intent.

        `intent` is a `MemoryIntent` (or its dict). Persistence always goes
        through `write_memory` (type/scope/dedupe/evidence/audit). A refused or
        confirmation-pending intent NEVER writes â€” it is returned as an honest
        outcome for the caller to surface.

        Outcomes:
          * save   â†’ `{action: "saved", memory: {...}, requiresConfirmation: False}`
          * correctâ†’ supersedes the prior memory (never hard-deletes) + writes a
                     correction memory
          * forget â†’ archives the matching memory(ies) (never hard-deletes)
          * refused/confirm â†’ `{action: "refused"|"needs_confirmation", ...}`
        """
        from .intent import MemoryIntent
        from .decision import resolve_owner_scope  # noqa: PLC0415

        if isinstance(intent, dict):
            intent = MemoryIntent(
                action=intent.get("action"),
                content=intent.get("content") or "",
                memory_type=intent.get("memoryType") or intent.get("memory_type") or "semantic",
                scope=intent.get("scope") or "general",
                scope_id=intent.get("scopeId") or intent.get("scope_id"),
                subject=intent.get("subject"),
                confidence=float(intent.get("confidence", 0.8)),
                requires_confirmation=bool(intent.get("requiresConfirmation")),
                refused=bool(intent.get("refused")),
                reason=intent.get("reason") or "",
                matched_phrase=intent.get("matchedPhrase") or "",
                generalizable=bool(intent.get("generalizable")),
                metadata=intent.get("metadata") or {},
            )

        if intent.refused:
            self.store.append_memory_event(
                "memory.intent_refused", run_id=run_id,
                data={"action": intent.action, "reason": intent.reason},
            )
            return {"ok": False, "action": "refused", "reason": intent.reason}

        if intent.requires_confirmation:
            self.store.append_memory_event(
                "memory.intent_needs_confirmation", run_id=run_id,
                data={"action": intent.action, "reason": intent.reason},
            )
            return {
                "ok": False, "action": "needs_confirmation",
                "reason": intent.reason, "intent": intent.to_dict(),
            }

        scope, scope_id = resolve_owner_scope(
            intent.scope, intent.scope_id, user_id=user_id, conversation_id=conversation_id,
        )

        if intent.action == "save":
            memory = self.write_memory(
                memory_type=intent.memory_type, content=intent.content,
                source="explicit_user", scope=scope, scope_id=scope_id,
                subject=intent.subject, source_run_id=run_id,
                confidence=intent.confidence,
                verification="unverified", created_by=user_id or "user",
            )
            if memory.get("status") == "proposed":
                # A contradiction with an existing active memory was stored inert
                # for review. NEVER claim it was saved as active truth.
                self.store.append_memory_event(
                    "memory.conflict_needs_review", memory_id=memory["id"], run_id=run_id,
                    data={"reason": memory.get("statusReason") or "conflicting memory requires review"},
                )
                return {
                    "ok": False, "action": "needs_review", "memory": memory,
                    "reason": (
                        "This conflicts with an existing memory and was NOT saved as "
                        "active truth â€” it needs review or clarification."
                    ),
                }
            self.store.append_memory_event(
                "memory.explicit_saved", memory_id=memory["id"], run_id=run_id,
                data={"matchedPhrase": intent.matched_phrase},
            )
            return {"ok": True, "action": "saved", "memory": memory}

        if intent.action == "correct":
            target, ambiguous = self._resolve_target(intent, scope_id, conversation_id=conversation_id)
            if ambiguous:
                return {
                    "ok": False, "action": "needs_clarification",
                    "reason": "more than one stored memory matches; specify which one to correct",
                    "candidates": [m["id"] for m in ambiguous],
                }
            result = self.record_correction(
                wrong=(intent.metadata.get("priorAssistantText") or "").strip()
                or (target["content"] if target else ""),
                correction=intent.content,
                subject=intent.subject, run_id=run_id,
                provided_by=user_id or "user", scope=scope,
                generalizable=intent.generalizable,
            )
            if target:
                # Never hard-delete: supersede + link, history retained.
                self.store.supersede_memory(target["id"], result["memory"]["id"])
            return {"ok": True, "action": "corrected", "memory": result["memory"],
                    "superseded": target["id"] if target else None}

        if intent.action == "forget":
            outcome = self._forget_matching(intent, scope_id, run_id=run_id, conversation_id=conversation_id)
            return outcome

        return {"ok": False, "action": "unsupported", "reason": f"unknown action {intent.action!r}"}

    def commit_decision(
        self,
        decision: Any,
        *,
        run_id: Optional[str] = None,
        user_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """The ONE write entry point for a `MemoryDecision`.

        Only a ``save`` decision with a memory action persists. A ``suggest``
        decision creates an inert suggestion (no durable memory). ``history_only``
        and ``ignore`` write nothing and return an honest outcome. Corrections
        and forgets preserve history (supersede/archive), never hard-delete.
        """
        # Resolve the owner: in a conversation-scoped run (a bot / group member
        # with no signed-in user) a personal fact belongs to that conversation's
        # private bucket, not an unattributable user row. This is the single
        # normalization point; both the deterministic-turn and model-proposal
        # paths pass through here.
        from dataclasses import replace  # noqa: PLC0415

        from .decision import resolve_owner_scope  # noqa: PLC0415

        if getattr(decision, "scope", None):
            owner_scope, owner_id = resolve_owner_scope(
                decision.scope, decision.scope_id,
                user_id=user_id, conversation_id=conversation_id,
            )
            if (owner_scope, owner_id) != (decision.scope, decision.scope_id):
                decision = replace(decision, scope=owner_scope, scope_id=owner_id)
        if decision.outcome == "ignore":
            if decision.refused:
                self.store.append_memory_event(
                    "memory.intent_refused", run_id=run_id,
                    data={"action": decision.action, "reason": decision.reason},
                )
            return {
                "ok": False, "action": "refused" if decision.refused else "ignored",
                "outcome": "ignore", "reason": decision.reason,
                "financial": decision.financial,
            }
        if decision.outcome in ("run_only", "history_only"):
            return {
                "ok": False, "action": "history_only",
                "outcome": decision.outcome, "reason": decision.reason,
            }
        if decision.outcome == "suggest":
            suggestion = self.create_suggestion(decision, run_id=run_id, scope_id=user_id)
            return {
                "ok": False, "action": "suggested", "outcome": "suggest",
                "reason": decision.reason, "suggestion": suggestion,
            }

        # outcome == "save"
        intent = _decision_to_intent(decision)
        try:
            return self.apply_explicit_intent(
                intent, run_id=run_id, user_id=user_id, conversation_id=conversation_id,
            )
        except MemoryFullError as exc:
            self.store.append_memory_event(
                "memory.budget_full", run_id=run_id,
                data={"limit": exc.limit, "active": exc.active},
            )
            return {
                "ok": False, "action": "memory_full", "outcome": "save",
                "reason": str(exc), "limit": exc.limit, "active": exc.active,
            }
        except MemoryWriteError as exc:
            # A policy floor (memory disabled, category denied, content refused)
            # or an invalid record is an HONEST outcome, never a crash. The model/
            # caller is told nothing was saved.
            self.store.append_memory_event(
                "memory.write_refused", run_id=run_id,
                data={"action": intent.action, "reason": str(exc)},
            )
            return {
                "ok": False, "action": "refused", "outcome": "save",
                "reason": str(exc),
            }

    def _resolve_target(
        self, intent: Any, scope_id: Optional[str], *, conversation_id: Optional[str] = None,
    ) -> tuple[Optional[dict[str, Any]], list[dict[str, Any]]]:
        """Resolve the single memory a correct/forget request targets.

        Returns `(target, ambiguous)`. When more than one eligible memory
        matches, `target` is None and `ambiguous` holds the candidates so the
        caller can ask rather than changing several records.
        """
        result = self.retrieve(
            query=intent.content, subject=intent.subject,
            scope_id=scope_id,
            actor_scope=None if conversation_id else ("user" if scope_id else None),
            conversation_id=conversation_id,
            limit=5, run_id=None,
        )
        if not result.memories:
            return None, []
        if len(result.memories) > 1:
            # An exact subject match narrows an otherwise-ambiguous set.
            if intent.subject:
                exact = [m for m in result.memories if (m.get("subject") or "").lower() == int(intent.subject)]
                if len(exact) == 1:
                    return exact[0], []
            return None, result.memories
        return result.memories[0], []

    def _forget_matching(
        self, intent: Any, scope_id: Optional[str], *, run_id: Optional[str],
        conversation_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Archive the single memory a forget request targets (never hard-delete).

        An ambiguous request (more than one eligible match) asks for
        clarification instead of archiving several records.
        """
        query = (intent.metadata.get("target") or intent.content or "").strip()
        if not query:
            return {"ok": False, "action": "needs_clarification",
                    "reason": "no memory target was specified"}
        target, ambiguous = self._resolve_target(intent, scope_id, conversation_id=conversation_id)
        if ambiguous:
            return {
                "ok": False, "action": "needs_clarification",
                "reason": "more than one stored memory matches; specify which one to forget",
                "candidates": [m["id"] for m in ambiguous],
            }
        if target is None:
            return {"ok": True, "action": "forgotten", "archived": []}
        self.store.archive_memory(target["id"], status="archived")
        self.store.append_memory_event(
            "memory.explicit_forgotten", memory_id=target["id"], run_id=run_id,
            data={"query": query[:200]},
        )
        return {"ok": True, "action": "forgotten", "archived": [target["id"]]}

    def forget_conversation(
        self, conversation_id: str, *, status: str = "archived", reason: Optional[str] = None,
    ) -> dict[str, Any]:
        """Archive every active memory owned by one conversation (never deletes).

        Used to purge a conversation's private memory (e.g. when its bot is
        deleted) and by the explicit "Forget this conversation" control. History
        is retained; the records simply become inert and unrecallable.
        """
        if not conversation_id:
            return {"ok": False, "reason": "a conversation id is required", "archived": []}
        rows = self.store.list_memories(
            scope="conversation", scope_id=conversation_id,
            limit=500, include_inactive=False,
        )
        archived: list[str] = []
        for row in rows:
            if self.store.archive_memory(row["id"], status=status, reason=reason) is not None:
                archived.append(row["id"])
        self.store.append_memory_event(
            "memory.conversation_forgotten",
            data={"conversationId": conversation_id, "archived": len(archived)},
        )
        return {"ok": True, "conversationId": conversation_id, "archived": archived}

    # â”€â”€ Post-run analysis (policy-gated, deterministic, never auto-enables) â”€â”€

    def analyze_run(
        self,
        run_id: str,
        run_store: Any,
        *,
        skill_store: Any = None,
    ) -> dict[str, Any]:
        """Analyze a finished run per the current policy.

        Under `skill_learning_mode != off`, learning candidates are created for
        qualifying experiences (still inert â€” promotion is separate). An
        eligible run is not, by itself, enough: implicit procedure candidates
        require recurrence evidence (enforced in `skills.learning.analyze_run`).
        Mistake detection always runs (it is cheap, deterministic and auditable).
        Never enables a skill, never claims improvement.
        """
        from ..skills.learning import analyze_run as learning_analyze, _signature  # type: ignore
        from .mistakes import capture_mistakes

        store = skill_store or self.store
        settings = self.policy.get_all()
        result: dict[str, Any] = {"runId": run_id, "candidatesCreated": 0, "candidatesSkipped": 0, "mistakesCreated": 0}

        # Mistake capture is always on (observation, not promotion).
        try:
            mistakes = capture_mistakes(run_id, run_store, store)
            result["mistakesCreated"] = len(mistakes)
            result["mistakes"] = [m["category"] for m in mistakes]
        except Exception as exc:  # noqa: BLE001 - analysis must never break a run
            result["mistakeError"] = str(exc)

        # Observation is always on: a review must be able to state what it saw,
        # even when candidate creation is policy-disabled. Only CREATION is gated.
        try:
            drafts = learning_analyze(run_id, run_store)
        except Exception as exc:  # noqa: BLE001
            result["candidateError"] = str(exc)
            drafts = []

        try:
            from ..self_improvement.lesson_contract import (  # noqa: PLC0415
                lesson_from_candidate,
            )

            lessons = []
            for draft in drafts:
                built = lesson_from_candidate(draft)
                if built is not None and not built.problems():
                    lessons.append({**built.to_dict(), "kind": draft.get("candidateType")})
            result["lessons"] = lessons[:8]
        except Exception:  # noqa: BLE001 - lesson shaping must never break analysis
            result["lessons"] = []

        mode = str(settings.get("skill_learning_mode") or "automatic_selective")
        if mode == "off":
            result["candidateDetection"] = "disabled by policy"
            return result

        from ..self_improvement.lesson_contract import candidate_problems  # noqa: PLC0415

        threshold = float(settings["candidate_confidence_threshold"])
        created = 0
        skipped = 0
        rejected: list[dict[str, Any]] = []
        for draft in drafts:
            problems = candidate_problems(draft)
            if problems:
                rejected.append({
                    "candidateType": draft.get("candidateType"),
                    "title": str(draft.get("title") or "")[:120],
                    "problems": problems,
                })
                skipped += 1
                continue
            if float(draft.get("confidence", 0)) < threshold:
                skipped += 1
                continue
            signature = _signature(draft["candidateType"], draft["problem"])
            if store.find_candidate_by_signature(signature):
                skipped += 1
                continue
            from ..persistence import now_iso as _now
            candidate_id = store.save_candidate({
                **draft, "id": None, "sourceRunId": run_id, "signature": signature,
                "status": "detected", "createdAt": _now(),
            })
            store.append_event("skill.learning_candidate_created", run_id=run_id,
                               data={"candidateId": candidate_id, "candidateType": draft["candidateType"],
                                     "automatic": True})
            created += 1
        result["candidatesCreated"] = created
        result["candidatesSkipped"] = skipped
        result["candidatesRejected"] = rejected
        return result

    # â”€â”€ One-time import from the legacy agent-memory.db skill tables â”€â”€â”€â”€â”€â”€â”€â”€

    def import_legacy_skills(self, legacy_path: str) -> dict[str, Any]:
        """Copy Phase-3 `Skill*`/`LearningCandidate` rows from the old
        `agent-memory.db` into eclipse-memory **if present and not already
        imported**. Idempotent and non-destructive: the source rows are left in
        place (rollback), and re-running is a no-op.

        Import is skipped silently when the legacy file/table does not exist
        (fresh installs never had one).
        """
        import os
        import sqlite3

        if not os.path.isfile(legacy_path):
            return {"imported": False, "reason": "legacy database not found"}
        try:
            src = sqlite3.connect(legacy_path)
            src.row_factory = sqlite3.Row
            tables = {r["name"] for r in src.execute(
                "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        except Exception as exc:  # noqa: BLE001
            return {"imported": False, "reason": f"cannot open legacy db: {exc}"}

        if "SkillVersion" not in tables:
            src.close()
            return {"imported": False, "reason": "legacy db has no skill tables"}

        # Already imported? (any local skill rows mean a previous import or a
        # fresh library load happened.)
        if self.store.list_skills():
            src.close()
            return {"imported": False, "reason": "eclipse-memory already has skills"}

        counts: dict[str, int] = {}
        try:
            for skill in src.execute("SELECT * FROM Skill").fetchall():
                self.store._db.execute(
                    """INSERT OR IGNORE INTO Skill
                       (id, name, description, category, latestVersion, status, tags, createdAt, updatedAt)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    tuple(skill[k] for k in
                          ("id", "name", "description", "category", "latestVersion", "status", "tags", "createdAt", "updatedAt")),
                )
                counts["Skill"] = counts.get("Skill", 0) + 1
            for table, columns in (
                ("SkillVersion", ("id", "skillId", "version", "manifest", "contentHash", "status",
                                  "evaluationStatus", "riskLevel", "instructionsLocation", "author",
                                  "origin", "sourceRunId", "createdAt", "updatedAt")),
                ("SkillDependency", ("id", "skillId", "version", "dependsOn", "constraint_", "optional")),
                ("SkillToolRequirement", ("id", "skillId", "version", "toolName")),
                ("SkillPermissionRequirement", ("id", "skillId", "version", "permission")),
                ("SkillExecution", ("id", "runId", "skillId", "version", "manifestHash", "parentRunId",
                                    "executionMode", "status", "actor", "input", "output", "error",
                                    "warnings", "missingData", "limitations", "evidence", "durationMs",
                                    "traceId", "createdAt", "finishedAt")),
                ("SkillEvaluation", ("id", "skillId", "version", "status", "evaluator", "dimensions",
                                     "summary", "createdAt")),
                ("SkillEvaluationCase", ("id", "evaluationId", "skillId", "version", "caseId", "name",
                                         "kind", "input", "expected", "createdAt")),
                ("LearningCandidate", ("id", "sourceRunId", "candidateType", "title", "problem",
                                       "observedBehavior", "proposedLesson", "proposedProcedure",
                                       "evidenceReferences", "confidence", "generalizationNotes",
                                       "knownLimitations", "signature", "status", "createdAt",
                                       "reviewedAt", "resultingSkillId", "resultingSkillVersion",
                                       "draftManifest")),
                ("SkillPromotionRequest", ("id", "skillId", "version", "requestedBy", "status", "reason",
                                           "evaluationId", "createdAt", "decidedAt")),
                ("SkillReview", ("id", "skillId", "version", "actor", "decision", "notes", "createdAt")),
                ("SkillEvent", ("id", "skillId", "version", "runId", "type", "at", "data")),
            ):
                if table not in tables:
                    continue
                placeholders = ", ".join("?" for _ in columns)
                for row in src.execute(f"SELECT * FROM {table}").fetchall():
                    try:
                        self.store._db.execute(
                            f"INSERT OR IGNORE INTO {table} ({', '.join(columns)}) VALUES ({placeholders})",
                            tuple(row[k] if k in row.keys() else None for k in columns),
                        )
                        counts[table] = counts.get(table, 0) + 1
                    except Exception:  # noqa: BLE001 - skip un-migratable rows, keep going
                        continue
            self.store._db.commit()
        finally:
            src.close()
        self.store.append_event("eclipse_memory.legacy_import", data={"counts": counts})
        return {"imported": True, "counts": counts}

    # â”€â”€ Lifecycle â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def health(self) -> dict[str, Any]:
        return {
            **self.store.health(),
            "memoryBudget": self.memory_budget(),
            "retention": self.retention_status(),
        }

    def migration_status(self) -> dict[str, Any]:
        return self.store.migration_status()

    def usage_report(self, *, window_days: int = 30) -> dict[str, Any]:
        """A bounded, READ-ONLY real-usage report (Milestone 7).

        Derived from actual persisted rows, content-free where possible. Counts
        durable-write outcomes, real conflict resolutions (and the implied false
        positive rate), and likely-missed conflicts for human review. Never
        writes; never raises. Complements the synthetic labeled evals, which can
        only prove the detector implements its rules.
        """
        from .usage_report import build_usage_report  # noqa: PLC0415

        try:
            return build_usage_report(self.store, window_days=window_days)
        except Exception as exc:  # noqa: BLE001 - a report must never raise
            return {
                "windowDays": window_days, "insufficientData": True,
                "error": str(exc), "readOnly": True,
            }

    # â”€â”€ Explainability â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def explain_memory(self, memory_id: str) -> Optional[dict[str, Any]]:
        """A concise, non-sensitive explanation of why a memory exists and its
        current lifecycle state. Never includes secrets â€” only the stored content
        the operator is already entitled to view locally."""
        memory = self.store.get_memory(memory_id)
        if memory is None:
            return None
        source = memory.get("source") or "unknown"
        authority = memory.get("authority") or "explicit"
        # Human reason for the original save, derived from provenance.
        save_reason = {
            "explicit_user": "saved because the user explicitly requested it",
            "user_correction": "saved because the user corrected an earlier answer",
            "manual": "saved by the operator through the UI",
            "execution_lesson": "learned automatically from a validated execution (incl. post-run analysis)",
            "system_decision": "saved because an architecture decision was recorded",
            "verified_source": "saved from a verified source",
            "skill_promotion": "saved from a validated promoted skill",
            "mistake": "saved from a captured mistake/recovery",
        }.get(source, f"saved from source '{source}'")

        # Current lifecycle disposition.
        status = memory.get("status") or "active"
        recall_reason: str
        if status == "active":
            if memory.get("expiresAt"):
                recall_reason = f"active; expires at {memory['expiresAt']}"
            else:
                recall_reason = "active and eligible for recall"
        elif status == "proposed":
            recall_reason = "inert suggestion/conflict â€” awaiting review; excluded from recall"
        elif status == "superseded":
            recall_reason = f"excluded from recall because it was superseded by {memory.get('supersededBy') or 'a later memory'}"
        elif status == "expired":
            recall_reason = "excluded from recall because it expired"
        elif status == "rejected":
            recall_reason = "excluded from recall because review rejected it"
        elif status == "archived":
            recall_reason = "excluded from recall because it was archived"
        else:
            recall_reason = f"excluded from recall (status={status})"

        timeline = {
            "createdAt": memory.get("createdAt"),
            "lastConfirmedAt": memory.get("lastConfirmedAt"),
            "lastUsedAt": memory.get("lastUsedAt"),
            "lastReviewedAt": memory.get("lastReviewedAt"),
            "expiresAt": memory.get("expiresAt"),
        }
        return {
            "memoryId": memory_id,
            "memoryType": memory.get("memoryType"),
            "scope": memory.get("scope"),
            "scopeId": memory.get("scopeId"),
            "authority": authority,
            "provenance": source,
            "saveReason": save_reason,
            "status": status,
            "statusReason": memory.get("statusReason"),
            "recallDisposition": recall_reason,
            "timeline": timeline,
            "supersededBy": memory.get("supersededBy"),
            "verification": memory.get("verification"),
            "confidence": memory.get("confidence"),
            "conflict": self._conflict_detail(memory_id, memory),
        }

    def conflict_review(self, memory_id: str) -> Optional[dict[str, Any]]:
        """A side-by-side competing-memory view for one memory id.

        Resolves the competing records from stored audit events AND link history
        (supersession/correction), then returns the FULL comparable fields for
        each record the operator needs to make a decision. Never includes
        secrets beyond what the local operator may already view; never decides
        anything (semantic similarity never auto-replaces).
        """
        memory = self.store.get_memory(memory_id)
        if memory is None:
            return None
        peer_ids: list[str] = []
        detail = self._conflict_detail(memory_id, memory) or {}
        for candidate in detail.get("candidateIds") or []:
            if candidate and candidate != memory_id and candidate not in peer_ids:
                peer_ids.append(candidate)
        for link in self.store.list_links(memory_id):
            other = link["toId"] if link["fromId"] == memory_id else link["fromId"]
            if other and other != memory_id and other not in peer_ids:
                peer_ids.append(other)
        peers: list[dict[str, Any]] = []
        for peer_id in peer_ids:
            record = self.store.get_memory(peer_id)
            if record is not None:
                peers.append(self._comparable(record))
        return {
            "memoryId": memory_id,
            "subject": memory.get("subject"),
            "scope": memory.get("scope"),
            "scopeId": memory.get("scopeId"),
            "self": self._comparable(memory),
            "peers": peers,
            "conflict": detail,
            "actions": [
                "keep", "supersede", "merge", "confirm_both", "dismiss", "defer",
            ],
            "recommendation": self._recommend_resolution(memory, peers, detail),
        }

    def _comparable(self, memory: dict[str, Any]) -> dict[str, Any]:
        """The fields a conflict-review view needs for one record."""
        return {
            "id": memory["id"],
            "content": memory.get("content"),
            "memoryType": memory.get("memoryType"),
            "scope": memory.get("scope"),
            "scopeId": memory.get("scopeId"),
            "subject": memory.get("subject"),
            "authority": memory.get("authority") or "explicit",
            "provenance": memory.get("source"),
            "confidence": memory.get("confidence"),
            "verification": memory.get("verification"),
            "status": memory.get("status"),
            "createdAt": memory.get("createdAt"),
            "lastConfirmedAt": memory.get("lastConfirmedAt"),
            "lastUsedAt": memory.get("lastUsedAt"),
            "expiresAt": memory.get("expiresAt"),
            "accessCount": memory.get("accessCount"),
            "supersededBy": memory.get("supersededBy"),
        }

    def _recommend_resolution(
        self, memory: dict[str, Any], peers: list[dict[str, Any]], detail: dict[str, Any],
    ) -> str:
        """A human recommendation. Never an automatic decision."""
        if not peers:
            return "No competing records were found to resolve."
        if memory.get("authority") == "explicit" and all(
            p.get("authority") != "explicit" for p in peers
        ):
            return (
                "This is an explicit memory; the competing record(s) are "
                "automatic. Review the newer statement and supersede the "
                "automatic record if it is now wrong."
            )
        if detail.get("reason"):
            return (
                "The detector flagged this as: "
                f"{detail['reason']}. Compare the two records and keep the one "
                "that is currently true; history is always retained."
            )
        return "Compare the records and keep the one that is currently true."

    def resolve_conflict(
        self, memory_id: str, action: str, *,
        target_id: Optional[str] = None, merged_content: Optional[str] = None,
        reason: Optional[str] = None, run_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Apply an operator conflict-resolution action. Every path is auditable
        and reversible (history is retained, never hard-deleted).

        Actions:
          * `keep` â€” mark reviewed; change nothing.
          * `supersede` â€” mark `target_id` superseded by `memory_id`.
          * `merge` â€” create a NEW explicit memory from `merged_content` (or the
            newer of the two) and supersede both; linked, reversible.
          * `confirm_both` â€” confirm both when contextually compatible.
          * `dismiss` â€” archive the competing target as rejected.
          * `defer` â€” mark reviewed, leave state unchanged.
        """
        memory = self.store.get_memory(memory_id)
        if memory is None:
            return {"ok": False, "error": "memory not found"}
        action = (action or "").strip().lower()
        allowed = {"keep", "supersede", "merge", "confirm_both", "dismiss", "defer"}
        if action not in allowed:
            return {"ok": False, "error": f"unknown action {action!r}"}
        target = self.store.get_memory(target_id) if target_id else None
        if action in {"supersede", "dismiss", "merge"} and target is None:
            return {"ok": False, "error": "target memory not found"}

        try:
            if action == "keep":
                self.store.mark_reviewed(memory_id)
                self.store.append_memory_event(
                    "memory.conflict_kept", memory_id=memory_id,
                    data={"reason": reason, "kept": memory_id},
                )
                return {"ok": True, "action": action, "kept": memory_id}

            if action == "defer":
                self.store.mark_reviewed(memory_id)
                self.store.append_memory_event(
                    "memory.conflict_deferred", memory_id=memory_id, data={"reason": reason},
                )
                return {"ok": True, "action": action}

            if action == "confirm_both":
                self.store.confirm_memory(memory_id)
                if target is not None:
                    self.store.confirm_memory(target_id)
                self.store.add_link(memory_id, target_id or "", "compatible", note=reason)
                self.store.append_memory_event(
                    "memory.conflict_confirmed_both", memory_id=memory_id,
                    data={"with": target_id, "reason": reason},
                )
                return {"ok": True, "action": action}

            if action == "dismiss":
                assert target is not None
                self.store.archive_memory(
                    target_id, status="rejected",
                    reason=reason or f"dismissed in conflict review against {memory_id}",
                )
                self.store.append_memory_event(
                    "memory.conflict_dismissed", memory_id=memory_id,
                    data={"dismissed": target_id, "reason": reason},
                )
                return {"ok": True, "action": action, "dismissed": target_id}

            if action == "supersede":
                assert target is not None
                self.store.supersede_memory(
                    target_id, memory_id,
                    reason=reason or f"superseded by {memory_id} during conflict review",
                )
                self.store.append_memory_event(
                    "memory.conflict_resolved", memory_id=memory_id,
                    data={"action": "supersede", "superseded": target_id, "reason": reason},
                )
                return {"ok": True, "action": action, "superseded": target_id}

            if action == "merge":
                assert target is not None
                content = (merged_content or "").strip()
                if not content:
                    # Deterministically pick the newer statement; never fabricate.
                    newer = memory if (memory.get("createdAt") or "") >= (target.get("createdAt") or "") else target
                    content = str(newer.get("content") or "").strip()
                if not content:
                    return {"ok": False, "error": "merge requires content"}
                merged = self.write_memory(
                    memory_type=memory.get("memoryType") or "semantic",
                    content=content,
                    source="manual",
                    scope=memory.get("scope") or "general",
                    scope_id=memory.get("scopeId"),
                    subject=memory.get("subject"),
                    confidence=max(
                        float(memory.get("confidence") or 0),
                        float(target.get("confidence") or 0),
                    ),
                    source_run_id=run_id,
                    # The merged record is the deliberate resolution of an
                    # explicit conflict â€” it must not itself be auto-proposed by
                    # the conflict pipeline. The operator chose this action.
                    allow_duplicate=True,
                )
                self.store.supersede_memory(memory_id, merged["id"], reason="merged into a new fact")
                self.store.supersede_memory(target_id, merged["id"], reason="merged into a new fact")
                self.store.add_link(merged["id"], memory_id, "merged_from")
                self.store.add_link(merged["id"], target_id, "merged_from")
                self.store.append_memory_event(
                    "memory.conflict_merged", memory_id=merged["id"],
                    data={"merged": [memory_id, target_id], "reason": reason},
                )
                return {"ok": True, "action": action, "mergedInto": merged["id"]}
        except MemoryWriteError as exc:
            return {"ok": False, "error": str(exc)}
        except Exception as exc:  # noqa: BLE001 - a resolution failure is structured
            return {"ok": False, "error": str(exc)}
        return {"ok": False, "error": "unreachable"}

    # ── Ground-truth conflict labels (Measurement honesty, Phase 2) ─────────

    def label_conflict(
        self, memory_id: str, label: str, *, reason: Optional[str] = None,
    ) -> dict[str, Any]:
        """Record the OPERATOR's ground-truth judgement of a raised conflict.

        `label` is `"true_conflict"` or `"false_positive"`. This is the honest
        signal the synthetic eval cannot provide. It is append-only (a bounded
        `MemoryEvent`), never mutates the memories, and is idempotent in effect
        (the most recent label for a memory wins when the usage report reads it).
        """
        normalized = (label or "").strip().lower()
        if normalized not in ("true_conflict", "false_positive"):
            return {"ok": False, "error": f"unknown label {label!r}"}
        memory = self.store.get_memory(memory_id)
        if memory is None:
            return {"ok": False, "error": "memory not found"}
        self.store.append_memory_event(
            "memory.conflict_labeled", memory_id=memory_id,
            data={"label": normalized, "reason": reason},
        )
        return {"ok": True, "memoryId": memory_id, "label": normalized}

    def _conflict_detail(self, memory_id: str, memory: dict[str, Any]) -> Optional[dict[str, Any]]:
        """The most recent conflict/candidate audit metadata for a memory.

        Built from stored audit events, so it reflects the ACTUAL decision. No raw
        embeddings are stored; only detector/score/ids/reason/authority.
        """
        try:
            events = [
                e for e in self.store.list_memory_events(limit=500)
                if e.get("memoryId") == memory_id
                and e.get("type") in (
                    "memory.conflict_needs_review", "memory.conflict_superseded",
                    "memory.conflict_confirmed",
                )
            ]
        except Exception:  # noqa: BLE001 - explanation must never fail
            return None
        if not events:
            return None
        event = events[0]
        data = event.get("data") or {}
        candidate_ids = data.get("candidateIds") or data.get("against") or data.get("superseded") or []
        return {
            "decision": data.get("decision") or event.get("type", "").replace("memory.", ""),
            "reason": data.get("reason") or memory.get("statusReason"),
            "detector": data.get("detector"),
            "similarity": data.get("similarity"),
            "candidateIds": list(candidate_ids),
            "authority": data.get("authority"),
            "requiresConfirmation": bool(
                data.get("requiresConfirmation")
                or event.get("type") == "memory.conflict_needs_review"
            ),
        }

    def detect_compaction(self, *, persist: bool = True, limit: int = 50) -> list[dict[str, Any]]:
        """Detect near-duplicate active memories and (optionally) persist INERT
        proposals. Never merges or deletes â€” acceptance is a separate gated step.
        """
        from .compaction import detect_proposals  # noqa: PLC0415

        try:
            memories = self.store.list_memories(limit=1000)
        except Exception:  # noqa: BLE001 - detection must never break a caller
            return []
        proposals = detect_proposals(memories, limit=limit)
        out: list[dict[str, Any]] = []
        for proposal in proposals:
            payload = proposal.to_dict()
            if persist:
                existing = [
                    p for p in self.store.list_compaction_proposals(status="proposed", limit=200)
                    if sorted(p.get("memberIds") or []) == sorted(payload["memberIds"])
                ]
                if existing:
                    payload["id"] = existing[0]["id"]
                else:
                    payload["id"] = self.store.save_compaction_proposal(payload)
                    self.store.append_memory_event(
                        "memory.compaction_proposed", data={"proposalId": payload["id"],
                                                            "members": payload["memberIds"]},
                    )
            out.append(payload)
        return out

    def accept_compaction(
        self, proposal_id: str, *, merged_content: Optional[str] = None,
    ) -> dict[str, Any]:
        """Accept a compaction proposal: create ONE merged memory and supersede
        the originals (linked + retained). Operator-gated at the API. Refuses a
        lossy merge that would drop member content."""
        proposal = self.store.get_compaction_proposal(proposal_id)
        if proposal is None:
            return {"ok": False, "error": "proposal not found"}
        if proposal.get("status") != "proposed":
            return {"ok": False, "error": f"proposal is {proposal.get('status')}"}
        member_ids = list(proposal.get("memberIds") or [])
        members = [m for m in (self.store.get_memory(mid) for mid in member_ids) if m]
        if len(members) < 2:
            return {"ok": False, "error": "not enough surviving members to compact"}
        # Scope safety: never compact across scopes.
        scopes = {(m.get("scope"), m.get("scopeId")) for m in members}
        if len(scopes) > 1:
            return {"ok": False, "error": "refusing to compact across scopes"}
        content = (merged_content or proposal.get("mergedContent") or "").strip()
        if not content:
            return {"ok": False, "error": "no merged content"}
        from .compaction import preservation_report  # noqa: PLC0415

        report = preservation_report(members, content)
        if not report["preserved"]:
            return {"ok": False, "error": "merge would lose content", "preservation": report}
        try:
            merged = self.write_memory(
                memory_type=members[0].get("memoryType") or "semantic",
                content=content,
                source="manual",
                scope=members[0].get("scope") or "general",
                scope_id=members[0].get("scopeId"),
                subject=members[0].get("subject"),
                confidence=max(float(m.get("confidence") or 0) for m in members),
                allow_duplicate=True,
            )
        except MemoryWriteError as exc:
            return {"ok": False, "error": str(exc)}
        for member in members:
            self.store.supersede_memory(
                member["id"], merged["id"],
                reason=f"compacted into {merged['id']}",
            )
            self.store.add_link(merged["id"], member["id"], "compacted_from")
        self.store.decide_compaction_proposal(
            proposal_id, status="accepted", resulting_memory_id=merged["id"],
        )
        self.store.append_memory_event(
            "memory.compaction_accepted",
            data={"proposalId": proposal_id, "members": member_ids, "mergedInto": merged["id"]},
        )
        return {"ok": True, "mergedInto": merged["id"], "superseded": member_ids,
                "preservation": report}

    def reject_compaction(self, proposal_id: str) -> dict[str, Any]:
        proposal = self.store.get_compaction_proposal(proposal_id)
        if proposal is None:
            return {"ok": False, "error": "proposal not found"}
        self.store.decide_compaction_proposal(proposal_id, status="rejected")
        self.store.append_memory_event(
            "memory.compaction_rejected", data={"proposalId": proposal_id},
        )
        return {"ok": True}

    def lifecycle_overview(self) -> dict[str, Any]:
        """Counts + views for the Control Room. Content is local operator data."""
        counts = self.store.memory_lifecycle_counts()
        views = {
            name: len(self.store.list_lifecycle_memories(name, limit=200))
            for name in (
                "active", "expired", "superseded", "rejected", "archived",
                "never-used", "frequently-recalled", "automatic", "stale", "conflicts",
            )
        }
        return {"counts": counts, "views": views, "budget": self.memory_budget()}

    def close(self) -> None:
        self.store.close()


def _decision_to_intent(decision: Any) -> Any:
    """Adapt an authorized `MemoryDecision` to the `MemoryIntent` shape that
    `apply_explicit_intent` consumes. The decision has already passed the gate,
    so this is a lossless structural mapping â€” never a second authorization."""
    from .intent import MemoryIntent

    return MemoryIntent(
        action=decision.action or "save",
        content=decision.content,
        memory_type=decision.memory_type,
        scope=decision.scope,
        scope_id=decision.scope_id,
        subject=decision.subject,
        confidence=decision.confidence,
        requires_confirmation=False,
        refused=False,
        reason=decision.reason,
        matched_phrase=decision.matched_phrase,
        generalizable=False,
        metadata=dict(decision.metadata),
    )


def _content_signature(
    memory_type: str, scope: str, scope_id: Optional[str], subject: Optional[str], content: str
) -> str:
    import hashlib

    normalized = re.sub(r"\s+", " ", (content or "").strip().lower())[:400]
    raw = f"{memory_type}|{scope}|{scope_id or ''}|{(subject or '').lower()}|{normalized}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _now() -> str:
    import time

    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()) + ".000Z"


__all__ = ["EclipseMemoryService", "MemoryFullError", "MemoryWriteError", "VALID_SOURCES"]
