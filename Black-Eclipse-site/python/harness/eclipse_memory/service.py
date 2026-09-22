"""Eclipse-Memory service — the controlled write/retrieve pipelines.

Nothing writes memory directly through the store; it goes through this service,
which implements the pipeline the brief requires:

    Candidate Observation
      → Classify memory type
      → Normalize/validate content
      → Check scope
      → Check duplication
      → Attach evidence (optional)
      → Determine confidence
      → Apply retention (expiry)
      → Persist
      → Emit memory event

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


# Sources that justify persisting a memory. Anything else is refused, so the
# database cannot fill up with every conversational sentence.
VALID_SOURCES = frozenset(
    {
        "explicit_user",      # "remember that …"
        "user_correction",    # the user corrected Eclipse
        "execution_lesson",   # a validated reusable lesson from a run
        "system_decision",    # an explicitly recorded architecture decision
        "verified_source",    # durable info from a verified source
        "skill_promotion",    # a validated skill produced a procedural memory
        "mistake",            # a captured mistake/recovery
        "manual",             # an operator wrote it through the UI/API
    }
)

MAX_CONTENT_CHARS = 4000


class EclipseMemoryService:
    def __init__(self, store: Optional[EclipseMemoryStore] = None) -> None:
        self.store = store or EclipseMemoryStore()
        self.policy = PolicyStore(self.store)

    # ── Write pipeline ──────────────────────────────────────────────────────

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
        # 2. Validate content.
        text_value = (content or "").strip()
        if not text_value:
            raise MemoryWriteError("memory content must not be empty")
        if len(text_value) > MAX_CONTENT_CHARS:
            raise MemoryWriteError(f"memory content exceeds {MAX_CONTENT_CHARS} chars")
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
                self.store.append_memory_event(
                    "memory.duplicate_skipped", memory_id=existing["id"], run_id=source_run_id,
                    data={"signature": signature},
                )
                return existing

        memory = self.store.save_memory(
            memory_type=memory_type, scope=scope, content=text_value,
            scope_id=scope_id, subject=subject, structured_data=structured_data,
            source=source, source_run_id=source_run_id, confidence=confidence,
            importance=importance, status="active", verification=verification,
            created_by=created_by, expires_at=expires_at,
        )
        memory = self.store.update_memory(memory["id"], structuredData=structured_data) or memory
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
        return memory

    def propose_memory(
        self,
        *,
        memory_type: str,
        content: str,
        source: str = "execution_lesson",
        **kwargs: Any,
    ) -> dict[str, Any]:
        """An automatic candidate — inert until reviewed. Uses status
        `proposed` so retrieval excludes it by default."""
        kwargs.setdefault("verification", "unverified")
        memory = self.write_memory(memory_type=memory_type, content=content, source=source, **kwargs)
        # A proposed memory is inert until reviewed: flip a freshly created row
        # to `proposed` so retrieval excludes it. (A duplicate return keeps its
        # existing status — never silently un-approve an active memory.)
        if memory.get("status") == "active":
            memory = self.store.update_memory(memory["id"], status="proposed") or memory
        return memory

    def review_memory(self, memory_id: str, *, approve: bool, reviewed_by: Optional[str] = None) -> Optional[dict[str, Any]]:
        status = "active" if approve else "rejected"
        updated = self.store.update_memory(
            memory_id, status=status, reviewStatus="approved" if approve else "rejected",
            reviewedAt=_now(),
        )
        if updated:
            self.store.append_memory_event(
                f"memory.{status}", memory_id=memory_id, data={"reviewedBy": reviewed_by}
            )
        return updated

    def _find_duplicate(self, signature: str) -> Optional[dict[str, Any]]:
        for memory in self.store.list_memories(limit=500, include_inactive=False):
            if _content_signature(
                memory["memoryType"], memory["scope"], memory.get("scopeId"),
                memory.get("subject"), memory["content"],
            ) == signature:
                return memory
        return None

    # ── Retrieval pipeline ──────────────────────────────────────────────────

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
    ) -> RetrievalResult:
        # Policy supplies the defaults; an explicit caller value still wins.
        settings = self.policy.get_all()
        return retrieve_memories(
            self.store, query=query, memory_types=memory_types, scope=scope,
            scope_id=scope_id, subject=subject, actor_scope=actor_scope,
            budget_chars=budget_chars if budget_chars is not None else settings["context_budget_chars"],
            limit=limit if limit is not None else settings["retrieval_limit"],
            run_id=run_id,
            include_proposed=include_proposed if include_proposed is not None
            else settings["include_proposed_in_retrieval"],
        )

    # ── Corrections / mistakes ──────────────────────────────────────────────

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
            content=f"Correction — {subject or 'general'}: {wrong} → {correction}",
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

    # ── Post-run analysis (policy-gated, deterministic, never auto-enables) ──

    def analyze_run(
        self,
        run_id: str,
        run_store: Any,
        *,
        skill_store: Any = None,
    ) -> dict[str, Any]:
        """Analyze a finished run per the current policy.

        When `auto_candidate_detection` is enabled, learning candidates are
        created for qualifying experiences (still inert — promotion is separate).
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

        if not settings["auto_candidate_detection"]:
            result["candidateDetection"] = "disabled by policy"
            return result

        threshold = float(settings["candidate_confidence_threshold"])
        try:
            drafts = learning_analyze(run_id, run_store)
        except Exception as exc:  # noqa: BLE001
            result["candidateError"] = str(exc)
            return result

        created = 0
        skipped = 0
        for draft in drafts:
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
        return result

    # ── One-time import from the legacy agent-memory.db skill tables ────────

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

    # ── Lifecycle ───────────────────────────────────────────────────────────

    def health(self) -> dict[str, Any]:
        return self.store.health()

    def migration_status(self) -> dict[str, Any]:
        return self.store.migration_status()

    def close(self) -> None:
        self.store.close()


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


__all__ = ["EclipseMemoryService", "MemoryWriteError", "VALID_SOURCES"]
