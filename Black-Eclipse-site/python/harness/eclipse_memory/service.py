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

        # 5b. Storage budget. A duplicate return above does not consume budget;
        # a genuinely new record must fit. The budget is never enforced by
        # auto-deleting user memory — the write fails truthfully instead. A
        # correction is exempt: it supersedes an existing record right after, so
        # it does not grow the retained set, and blocking an explicit correction
        # would be worse than a temporarily over-full count.
        if source != "user_correction":
            self._check_budget()

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
        room — the caller must surface the honest full state.
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
                "to free space — existing memory is never deleted automatically.",
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

    # ── Explicit user intent (deterministic post-run path) ──────────────────

    def decide_turn(
        self,
        user_text: str,
        *,
        user_id: Optional[str] = None,
        recurring: bool = False,
        is_skill_run: bool = False,
    ) -> Any:
        """Run the shared decision gate for one user turn.

        Reads policy + recent-dismissal state; never writes. Returns a
        `MemoryDecision`. Every write path must consult this gate.

        `recurring` is evidence that the same durable-sounding statement was seen
        in prior conversation history (computed by the caller from
        `RunRequest.input.history`); it lets a project convention be saved
        without a per-run prompt once it repeats.
        """
        from .decision import content_signature, decide_turn as _decide  # noqa: PLC0415

        settings = self.policy.get_all()
        recently_dismissed = False
        try:
            sig = content_signature(user_text)
            existing = self.store.find_suggestion_by_signature(sig)
            recently_dismissed = bool(existing and existing.get("status") == "dismissed")
        except Exception:  # noqa: BLE001 - dismissal lookup must never block a run
            recently_dismissed = False
        prior = False
        try:
            prior = bool(self.store.list_memories(scope_id=user_id, limit=1, include_inactive=False))
        except Exception:  # noqa: BLE001
            prior = False
        return _decide(
            user_text, user_id=user_id, settings=settings,
            has_prior_memory=prior, recently_dismissed=recently_dismissed,
            recurring=recurring, is_skill_run=is_skill_run,
        )

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
        existing = self.store.find_suggestion_by_signature(signature)
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
        """Accept a suggestion → write one scoped memory, mark it accepted."""
        from .decision import authorize_proposal  # noqa: PLC0415

        suggestion = self.store.get_suggestion(suggestion_id)
        if suggestion is None:
            return {"ok": False, "action": "not_found", "reason": "suggestion not found"}
        if suggestion["status"] != "pending":
            return {"ok": False, "action": suggestion["status"], "reason": "suggestion already decided"}
        scope_id = suggestion.get("scopeId") or user_id
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

    def dismiss_suggestion(self, suggestion_id: str) -> dict[str, Any]:
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
    ) -> dict[str, Any]:
        """Persist (or act on) a detected explicit user intent.

        `intent` is a `MemoryIntent` (or its dict). Persistence always goes
        through `write_memory` (type/scope/dedupe/evidence/audit). A refused or
        confirmation-pending intent NEVER writes — it is returned as an honest
        outcome for the caller to surface.

        Outcomes:
          * save   → `{action: "saved", memory: {...}, requiresConfirmation: False}`
          * correct→ supersedes the prior memory (never hard-deletes) + writes a
                     correction memory
          * forget → archives the matching memory(ies) (never hard-deletes)
          * refused/confirm → `{action: "refused"|"needs_confirmation", ...}`
        """
        from .intent import MemoryIntent

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

        scope_id = intent.scope_id or (user_id if intent.scope == "user" else None)

        if intent.action == "save":
            memory = self.write_memory(
                memory_type=intent.memory_type, content=intent.content,
                source="explicit_user", scope=intent.scope, scope_id=scope_id,
                subject=intent.subject, source_run_id=run_id,
                confidence=intent.confidence,
                verification="unverified", created_by=user_id or "user",
            )
            self.store.append_memory_event(
                "memory.explicit_saved", memory_id=memory["id"], run_id=run_id,
                data={"matchedPhrase": intent.matched_phrase},
            )
            return {"ok": True, "action": "saved", "memory": memory}

        if intent.action == "correct":
            target, ambiguous = self._resolve_target(intent, scope_id)
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
                provided_by=user_id or "user", scope=intent.scope,
                generalizable=intent.generalizable,
            )
            if target:
                # Never hard-delete: supersede + link, history retained.
                self.store.supersede_memory(target["id"], result["memory"]["id"])
            return {"ok": True, "action": "corrected", "memory": result["memory"],
                    "superseded": target["id"] if target else None}

        if intent.action == "forget":
            outcome = self._forget_matching(intent, scope_id, run_id=run_id)
            return outcome

        return {"ok": False, "action": "unsupported", "reason": f"unknown action {intent.action!r}"}

    def commit_decision(
        self,
        decision: Any,
        *,
        run_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """The ONE write entry point for a `MemoryDecision`.

        Only a ``save`` decision with a memory action persists. A ``suggest``
        decision creates an inert suggestion (no durable memory). ``history_only``
        and ``ignore`` write nothing and return an honest outcome. Corrections
        and forgets preserve history (supersede/archive), never hard-delete.
        """
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
            return self.apply_explicit_intent(intent, run_id=run_id, user_id=user_id)
        except MemoryFullError as exc:
            self.store.append_memory_event(
                "memory.budget_full", run_id=run_id,
                data={"limit": exc.limit, "active": exc.active},
            )
            return {
                "ok": False, "action": "memory_full", "outcome": "save",
                "reason": str(exc), "limit": exc.limit, "active": exc.active,
            }

    def _resolve_target(
        self, intent: Any, scope_id: Optional[str]
    ) -> tuple[Optional[dict[str, Any]], list[dict[str, Any]]]:
        """Resolve the single memory a correct/forget request targets.

        Returns `(target, ambiguous)`. When more than one eligible memory
        matches, `target` is None and `ambiguous` holds the candidates so the
        caller can ask rather than changing several records.
        """
        result = self.retrieve(
            query=intent.content, subject=intent.subject,
            scope_id=scope_id, actor_scope="user" if scope_id else None,
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
        self, intent: Any, scope_id: Optional[str], *, run_id: Optional[str]
    ) -> dict[str, Any]:
        """Archive the single memory a forget request targets (never hard-delete).

        An ambiguous request (more than one eligible match) asks for
        clarification instead of archiving several records.
        """
        query = (intent.metadata.get("target") or intent.content or "").strip()
        if not query:
            return {"ok": False, "action": "needs_clarification",
                    "reason": "no memory target was specified"}
        target, ambiguous = self._resolve_target(intent, scope_id)
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

    # ── Post-run analysis (policy-gated, deterministic, never auto-enables) ──

    def analyze_run(
        self,
        run_id: str,
        run_store: Any,
        *,
        skill_store: Any = None,
    ) -> dict[str, Any]:
        """Analyze a finished run per the current policy.

        Under `skill_learning_mode != off`, learning candidates are created for
        qualifying experiences (still inert — promotion is separate). An
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

        mode = str(settings.get("skill_learning_mode") or "automatic_selective")
        if mode == "off":
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
        return {**self.store.health(), "memoryBudget": self.memory_budget()}

    def migration_status(self) -> dict[str, Any]:
        return self.store.migration_status()

    def close(self) -> None:
        self.store.close()


def _decision_to_intent(decision: Any) -> Any:
    """Adapt an authorized `MemoryDecision` to the `MemoryIntent` shape that
    `apply_explicit_intent` consumes. The decision has already passed the gate,
    so this is a lossless structural mapping — never a second authorization."""
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
