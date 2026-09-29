"""Eclipse-Memory routes: memories, lifecycle, compaction, policy, retrieval,
corrections/mistakes, profile, transfer (export/import/backup/reset),
suggestions, semantic status and external memory providers.

Extracted verbatim from `main.py` so the front door stays navigable. Behavior,
authorization (`require_operator`, transport/token only) and response shapes are
unchanged; the shared runtime service and helpers come from `harness.deps`.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException

from ..deps import memory_available, require_operator, service

router = APIRouter()

@router.get("/eclipse-memory/health")
def eclipse_memory_health() -> dict[str, Any]:
    return {"success": True, **service.memory.health()}


@router.get("/eclipse-memory/usage-report")
def memory_usage_report(windowDays: int = 30) -> dict[str, Any]:
    """Real-usage measurement over persisted rows (read-only, bounded, honest).

    Counts durable-write outcomes, real conflict resolutions and likely-missed
    conflicts. Complements the synthetic labeled evals, which only prove the
    detector implements its rules. Never writes; empty data yields an honest
    empty report.
    """
    return {"success": True, **service.memory.usage_report(window_days=windowDays)}


def memory_available() -> bool:
    """True when the memory database is readable and not corrupt.

    A corrupt database must fail HONESTLY ("memory unavailable") rather than
    answer a recall/write with wrong data. Cheap enough for the mutation/read
    paths that guard on it.
    """
    try:
        store = service.memory_store
        return bool(store.db.integrity_ok())
    except Exception:  # noqa: BLE001 - unreadable memory is unavailable memory
        return False


@router.get("/eclipse-memory/overview")
def eclipse_memory_overview() -> dict[str, Any]:
    """Real counts only — never fabricated activity."""
    store = service.memory_store
    memories = store.list_memories(limit=500, include_inactive=True)
    by_type: dict[str, int] = {}
    by_status: dict[str, int] = {}
    for memory in memories:
        by_type[memory["memoryType"]] = by_type.get(memory["memoryType"], 0) + 1
        by_status[memory["status"]] = by_status.get(memory["status"], 0) + 1
    return {
        "success": True,
        "memories": {"total": len(memories), "byType": by_type, "byStatus": by_status},
        "skills": {"installed": len(service.skill_registry.all_manifests())},
        "candidates": len(store.list_candidates(limit=500)),
        "corrections": len(store.list_corrections(limit=500)),
        "mistakes": len(store.list_mistakes(limit=500)),
        "retrievals": len(store.list_retrievals(limit=500)),
        "suggestions": len(store.list_suggestions(status="pending", limit=500)),
        "health": service.memory.health(),
    }


@router.get("/eclipse-memory/memories")
def list_memories(
    memoryType: Optional[str] = None, scope: Optional[str] = None,
    status: Optional[str] = None, subject: Optional[str] = None,
    source: Optional[str] = None, limit: int = 100,
) -> dict[str, Any]:
    return {"success": True, "memories": service.memory_store.list_memories(
        memory_type=memoryType, scope=scope, status=status, subject=subject,
        source=source, limit=limit, include_inactive=True,
    )}


@router.get("/eclipse-memory/memories/{memory_id}")
def get_memory(memory_id: str) -> dict[str, Any]:
    memory = service.memory_store.get_memory(memory_id)
    if memory is None:
        raise HTTPException(status_code=404, detail="Memory not found")
    return {
        "success": True,
        "memory": memory,
        "evidence": service.memory_store.list_evidence(memory_id),
        "links": service.memory_store.list_links(memory_id),
        "explanation": service.memory.explain_memory(memory_id),
    }


@router.get("/eclipse-memory/lifecycle")
def memory_lifecycle(view: Optional[str] = None, scopeId: Optional[str] = None, limit: int = 100) -> dict[str, Any]:
    """Lifecycle overview + a named view (active/expired/superseded/never-used/…).

    Content is returned because this is the local operator's own memory; never
    expose secrets (there are none stored — secrets are refused on write).
    """
    overview = service.memory.lifecycle_overview()
    payload: dict[str, Any] = {"success": True, **overview}
    if view:
        payload["memories"] = service.memory_store.list_lifecycle_memories(
            view, scope_id=scopeId, limit=limit,
        )
        payload["view"] = view
    return payload


@router.get("/eclipse-memory/memories/{memory_id}/explain")
def explain_memory(memory_id: str) -> dict[str, Any]:
    explanation = service.memory.explain_memory(memory_id)
    if explanation is None:
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"success": True, "explanation": explanation}


@router.get("/eclipse-memory/memories/{memory_id}/conflict")
def conflict_review(memory_id: str) -> dict[str, Any]:
    """Side-by-side competing-memory view + safe resolution actions (read-only)."""
    review = service.memory.conflict_review(memory_id)
    if review is None:
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"success": True, "review": review}


@router.post("/eclipse-memory/memories/{memory_id}/resolve")
def resolve_conflict(
    memory_id: str,
    payload: Optional[dict[str, Any]] = None,
    _: bool = Depends(require_operator),
) -> dict[str, Any]:
    """Apply a conflict-resolution action. Operator-gated; reversible/audited."""
    payload = payload or {}
    if not bool(payload.get("operator")):
        raise HTTPException(status_code=403, detail="conflict resolution requires an authorized operator")
    result = service.memory.resolve_conflict(
        memory_id,
        action=str(payload.get("action") or ""),
        target_id=payload.get("targetId"),
        merged_content=payload.get("mergedContent"),
        reason=payload.get("reason"),
    )
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error") or "resolution failed")
    return {"success": True, **result}


@router.post("/eclipse-memory/memories/{memory_id}/conflict-label")
def label_conflict(
    memory_id: str,
    payload: Optional[dict[str, Any]] = None,
    _: bool = Depends(require_operator),
) -> dict[str, Any]:
    """Record the operator's ground-truth judgement of a raised conflict.

    `label` is `true_conflict` or `false_positive`. Append-only; feeds the
    real-usage report's precision/recall. Operator-gated; never mutates records.
    """
    payload = payload or {}
    if not bool(payload.get("operator")):
        raise HTTPException(status_code=403, detail="conflict labelling requires an authorized operator")
    result = service.memory.label_conflict(
        memory_id, str(payload.get("label") or ""), reason=payload.get("reason"),
    )
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error") or "labelling failed")
    return {"success": True, **result}


@router.get("/eclipse-memory/compaction")
def list_compaction(status: Optional[str] = None) -> dict[str, Any]:
    """Inert near-duplicate compaction proposals (read-only)."""
    return {
        "success": True,
        "proposals": service.memory_store.list_compaction_proposals(status, 200),
    }


@router.post("/eclipse-memory/compaction/detect")
def detect_compaction(
    payload: Optional[dict[str, Any]] = None,
    operator: bool = Depends(require_operator),
) -> dict[str, Any]:
    """Detect (and persist) inert compaction proposals. Operator-gated."""
    if not operator:
        raise HTTPException(status_code=403, detail="operator authorization required")
    proposals = service.memory.detect_compaction(persist=True)
    return {"success": True, "proposals": proposals}


@router.post("/eclipse-memory/compaction/{proposal_id}/accept")
def accept_compaction(
    proposal_id: str,
    payload: Optional[dict[str, Any]] = None,
    operator: bool = Depends(require_operator),
) -> dict[str, Any]:
    """Accept a proposal: merge + supersede originals (retained). Operator-gated."""
    if not operator:
        raise HTTPException(status_code=403, detail="operator authorization required")
    payload = payload or {}
    result = service.memory.accept_compaction(
        proposal_id, merged_content=payload.get("mergedContent"),
    )
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error") or "compaction failed")
    return {"success": True, **result}


@router.post("/eclipse-memory/compaction/{proposal_id}/reject")
def reject_compaction(
    proposal_id: str,
    operator: bool = Depends(require_operator),
) -> dict[str, Any]:
    if not operator:
        raise HTTPException(status_code=403, detail="operator authorization required")
    result = service.memory.reject_compaction(proposal_id)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error") or "reject failed")
    return {"success": True, **result}


@router.post("/eclipse-memory/memories")
def create_memory(payload: dict[str, Any], _: bool = Depends(require_operator)) -> dict[str, Any]:
    if not bool(payload.get("operator")):
        raise HTTPException(status_code=403, detail="memory write requires an authorized operator")
    # A UI save is a direct human action, but it still passes the ONE shared
    # decision gate (provenance=ui_save) so privacy/content rules cannot be
    # bypassed and the write always goes through the service pipeline.
    from ..eclipse_memory.decision import authorize_proposal

    try:
        decision = authorize_proposal(
            content=str(payload.get("content") or ""),
            provenance="ui_save",
            user_id=payload.get("scopeId"),
            memory_type=str(payload.get("memoryType") or "semantic"),
            scope=str(payload.get("scope") or "general"),
            scope_id=payload.get("scopeId"),
            subject=payload.get("subject"),
            confidence=float(payload.get("confidence", 0.7)),
            settings=service.memory.policy.get_all(),
        )
        outcome = service.memory.commit_decision(decision, user_id=payload.get("scopeId"))
        if not outcome.get("ok"):
            raise ValueError(decision.reason or outcome.get("reason") or "write rejected")
        memory = outcome["memory"]
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 - a rejected write is a 400, not a crash
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"success": True, "memory": memory}


@router.patch("/eclipse-memory/memories/{memory_id}")
def patch_memory(memory_id: str, payload: dict[str, Any], _: bool = Depends(require_operator)) -> dict[str, Any]:
    if not bool(payload.get("operator")):
        raise HTTPException(status_code=403, detail="memory update requires an authorized operator")
    updated = service.memory_store.update_memory(
        memory_id, content=payload.get("content"), status=payload.get("status"),
        confidence=payload.get("confidence"),
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"success": True, "memory": updated}


@router.post("/eclipse-memory/memories/{memory_id}/archive")
def archive_memory(memory_id: str, payload: Optional[dict[str, Any]] = None, _: bool = Depends(require_operator)) -> dict[str, Any]:
    payload = payload or {}
    if not bool(payload.get("operator")):
        raise HTTPException(status_code=403, detail="memory archive requires an authorized operator")
    updated = service.memory_store.archive_memory(
        memory_id, payload.get("status", "archived"), reason=payload.get("reason"),
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"success": True, "memory": updated}


@router.post("/eclipse-memory/memories/{memory_id}/restore")
def restore_memory(memory_id: str, payload: Optional[dict[str, Any]] = None, _: bool = Depends(require_operator)) -> dict[str, Any]:
    payload = payload or {}
    if not bool(payload.get("operator")):
        raise HTTPException(status_code=403, detail="memory restore requires an authorized operator")
    updated = service.memory_store.restore_memory(memory_id)
    if updated is None:
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"success": True, "memory": updated}


@router.post("/eclipse-memory/memories/{memory_id}/renew")
def renew_memory(memory_id: str, payload: Optional[dict[str, Any]] = None, _: bool = Depends(require_operator)) -> dict[str, Any]:
    payload = payload or {}
    if not bool(payload.get("operator")):
        raise HTTPException(status_code=403, detail="memory renewal requires an authorized operator")
    days = payload.get("days")
    updated = service.memory.renew_memory(memory_id, days=int(days) if days is not None else None)
    if updated is None:
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"success": True, "memory": updated}


@router.post("/eclipse-memory/retention/sweep")
def retention_sweep(_: bool = Depends(require_operator)) -> dict[str, Any]:
    """Apply the configured retention policy: due AUTOMATIC memories become
    inert (`expired`). Never deletes; explicit memories are exempt. Idempotent
    and observable (inspected/expired/skipped/ranAt)."""
    return {"success": True, **service.memory.expire_due_memories()}


@router.get("/eclipse-memory/retention/preview")
def retention_preview() -> dict[str, Any]:
    """Preview what a retention sweep would expire, without sweeping."""
    return {"success": True, **service.memory.preview_retention()}


@router.get("/eclipse-memory/retention")
def retention_status() -> dict[str, Any]:
    """The retention policy state + the last sweep outcome (no memory content)."""
    return {"success": True, **service.memory.retention_status()}


@router.get("/eclipse-memory/semantic-status")
def semantic_status() -> dict[str, Any]:
    """Retired: the optional semantic candidate layer was removed on the evidence
    that it added no measurable recall at a safe threshold (deterministic
    normalization closed the gap). Kept as an honest, non-mutating tombstone so an
    old client gets a truthful answer instead of a 404.
    """
    return {
        "success": True,
        "retired": True,
        "mode": "lexical",
        "lexicalActive": True,
        "semanticEnabled": False,
        "semanticAvailable": False,
        "reason": (
            "the semantic candidate layer was removed; deterministic lexical "
            "detection is authoritative"
        ),
        "doc": "docs/harness/memory-contradiction-detection.md",
    }


@router.post("/eclipse-memory/semantic/rebuild")
def semantic_rebuild(_: bool = Depends(require_operator)) -> dict[str, Any]:
    """Retired tombstone: the semantic candidate layer was removed, so there is no
    index to rebuild. Non-mutating; kept so an old client gets a truthful answer.
    """
    return {
        "success": True,
        "retired": True,
        "rebuilt": False,
        "persistentIndex": False,
        "reason": "the semantic candidate layer was removed; there is nothing to rebuild",
    }


# ── Memory providers (M8) ───────────────────────────────────────────────────


@router.get("/memory-providers/status")
async def memory_provider_status() -> dict[str, Any]:
    """Health/capabilities for every memory provider (bounded, content-free)."""
    from ..memory_providers.diagnostics import provider_diagnostics  # noqa: PLC0415

    registry = service.memory_router._registry
    external_enabled = False
    try:
        external_enabled = bool(service.memory.policy.get("external_memory_search_enabled"))
    except Exception:  # noqa: BLE001
        external_enabled = False
    registry.set_external_enabled(external_enabled)
    report = await provider_diagnostics(registry)
    return {"success": True, **report}


@router.post("/memory-providers/test")
async def memory_provider_test(payload: dict[str, Any], _: bool = Depends(require_operator)) -> dict[str, Any]:
    """Bounded, non-destructive test of ONE provider (operator-gated).

    Probes health + a capped search only; never writes/deletes/exports.
    """
    from ..memory_providers.diagnostics import provider_test  # noqa: PLC0415

    if not bool(payload.get("operator")):
        raise HTTPException(status_code=403, detail="provider test requires an authorized operator")
    name = str(payload.get("provider") or "native")
    return {"success": True, **await provider_test(service.memory_router._registry, name)}


@router.post("/memory-providers/search")
async def memory_provider_search(payload: dict[str, Any]) -> dict[str, Any]:
    """Native-first memory search; external results are fenced and unverified.

    `allowExternal` must be explicitly true to reach an external provider, and
    external search must also be enabled by policy. Native results are always
    returned and are never replaced by external ones.
    """
    from ..memory_providers.protocol import MemorySearchRequest  # noqa: PLC0415

    request = MemorySearchRequest(
        query=str(payload.get("query") or ""),
        scope=payload.get("scope"),
        scope_id=payload.get("scopeId"),
        memory_types=payload.get("types"),
        limit=int(payload.get("limit", 8) or 8),
        allow_external=bool(payload.get("allowExternal")),
    )
    routed = await service.memory_router.search(request, allow_external=bool(payload.get("allowExternal")))
    return {"success": True, **routed.to_dict()}


@router.post("/eclipse-memory/memories/{memory_id}/review")
def review_memory(memory_id: str, payload: dict[str, Any], _: bool = Depends(require_operator)) -> dict[str, Any]:
    if not bool(payload.get("operator")):
        raise HTTPException(status_code=403, detail="memory review requires an authorized operator")
    updated = service.memory.review_memory(memory_id, approve=bool(payload.get("approve")), reviewed_by="operator")
    if updated is None:
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"success": True, "memory": updated}


@router.post("/eclipse-memory/retrieve")
def retrieve_memory(payload: dict[str, Any]) -> dict[str, Any]:
    if not memory_available():
        raise HTTPException(status_code=503, detail="memory is unavailable (database unreadable or corrupt)")
    result = service.memory.retrieve(
        query=str(payload.get("query") or ""),
        memory_types=payload.get("types"),
        scope=payload.get("scope"),
        scope_id=payload.get("scopeId"),
        subject=payload.get("subject"),
        actor_scope=payload.get("actorScope"),
        budget_chars=int(payload.get("budgetChars", 4000)),
        limit=int(payload.get("limit", 8)),
        run_id=payload.get("runId"),
    )
    return {"success": True, "memories": result.memories, "context": result.context,
            "diagnostics": result.diagnostics}


@router.get("/eclipse-memory/retrievals")
def list_retrievals(limit: int = 50) -> dict[str, Any]:
    return {"success": True, "retrievals": service.memory_store.list_retrievals(limit)}


@router.get("/eclipse-memory/corrections")
def list_corrections(limit: int = 100) -> dict[str, Any]:
    return {"success": True, "corrections": service.memory_store.list_corrections(limit)}


@router.get("/eclipse-memory/mistakes")
def list_mistakes(runId: Optional[str] = None, limit: int = 100) -> dict[str, Any]:
    return {"success": True, "mistakes": service.memory_store.list_mistakes(runId, limit)}


@router.post("/eclipse-memory/corrections")
def create_correction(payload: dict[str, Any], _: bool = Depends(require_operator)) -> dict[str, Any]:
    if not bool(payload.get("operator")):
        raise HTTPException(status_code=403, detail="correction capture requires an authorized operator")
    # A correction is an explicit human action, but it still passes the shared
    # gate so a correction cannot smuggle a secret/override/financial fact into
    # durable memory.
    from ..eclipse_memory.decision import authorize_proposal

    correction_text = str(payload.get("correction") or "")
    decision = authorize_proposal(
        content=correction_text, provenance="correction",
        user_id=payload.get("scopeId"),
        memory_type="correction",
        scope=str(payload.get("scope") or "user"),
        subject=payload.get("subject"),
        confidence=0.9,
        settings=service.memory.policy.get_all(),
    )
    if decision.outcome != "save":
        raise HTTPException(status_code=400, detail=decision.reason or "correction rejected")
    result = service.memory.record_correction(
        wrong=str(payload.get("wrong") or ""),
        correction=correction_text,
        subject=payload.get("subject"),
        run_id=payload.get("runId"),
        provided_by=str(payload.get("providedBy") or "user"),
        scope=str(payload.get("scope") or "user"),
        generalizable=bool(payload.get("generalizable")),
    )
    return {"success": True, **result}


@router.get("/eclipse-memory/policies")
def get_policies() -> dict[str, Any]:
    from ..eclipse_memory.policy import BOUNDS, DEFAULTS, LOCKED_VALUES

    return {
        "success": True,
        "policies": service.memory.policy.get_all(),
        "defaults": DEFAULTS,
        "bounds": {k: list(v) for k, v in BOUNDS.items()},
        "locked": LOCKED_VALUES,
        "budget": service.memory.memory_budget(),
    }


@router.put("/eclipse-memory/policies")
def update_policies(payload: dict[str, Any], _: bool = Depends(require_operator)) -> dict[str, Any]:
    if not bool(payload.get("operator")):
        raise HTTPException(status_code=403, detail="policy changes require an authorized operator")
    updates = payload.get("policies") or {}
    if not isinstance(updates, dict):
        raise HTTPException(status_code=400, detail="policies must be an object")
    from ..eclipse_memory.policy import PolicyError

    applied: list[dict[str, Any]] = []
    try:
        for key, value in updates.items():
            applied.append(service.memory.policy.set(key, value, updated_by="operator"))
    except PolicyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"success": True, "applied": applied, "policies": service.memory.policy.get_all()}


@router.post("/eclipse-memory/analyze/{run_id}")
def analyze_run_endpoint(run_id: str, payload: Optional[dict[str, Any]] = None, _: bool = Depends(require_operator)) -> dict[str, Any]:
    """Deterministic post-run analysis: mistakes + (policy-gated) candidates.

    This creates records, so it requires proof of operator authorization
    (transport/token) — a body boolean cannot authorize it.
    """
    payload = payload or {}
    if service.get_run(run_id) is None:
        raise HTTPException(status_code=404, detail="Run not found")
    result = service.memory.analyze_run(run_id, service.store, skill_store=service.skill_store)
    return {"success": True, **result}


@router.get("/eclipse-memory/events")
def list_memory_events(limit: int = 100) -> dict[str, Any]:
    return {
        "success": True,
        "events": service.memory_store.list_memory_events(limit),
        "skillEvents": service.skill_store.list_events(limit=limit),
    }


# ── Compact prompt profile (always-available personalization) ────────────────


@router.get("/eclipse-memory/profile")
def memory_profile(scopeId: Optional[str] = None) -> dict[str, Any]:
    """The current compact profile (read-only materialization, not persisted).

    Returns the selected memories, the excluded memories + reasons, the
    character/token estimate and the rendered prompt block.
    """
    if not memory_available():
        raise HTTPException(status_code=503, detail="memory is unavailable (database unreadable or corrupt)")
    snapshot = service.memory.build_profile(scope_id=scopeId, persist=False)
    from ..eclipse_memory.profile import preview_payload

    payload = preview_payload(snapshot)
    payload["history"] = service.memory.profile_history(limit=10)
    return payload


@router.get("/eclipse-memory/profile/preview")
def memory_profile_preview(scopeId: Optional[str] = None) -> dict[str, Any]:
    """A pure preview of what the next run would inject (never persisted)."""
    if not memory_available():
        raise HTTPException(status_code=503, detail="memory is unavailable (database unreadable or corrupt)")
    return service.memory.profile_preview(scope_id=scopeId)


@router.post("/eclipse-memory/profile/rebuild")
def memory_profile_rebuild(
    payload: dict[str, Any] | None = None, _: bool = Depends(require_operator)
) -> dict[str, Any]:
    """Materialize and PERSIST a fresh profile snapshot (operator action).

    Rebuilds the projection from current active memory and records the
    reproducible snapshot metadata. It never writes or alters a memory record.
    """
    payload = payload or {}
    if not bool(payload.get("operator")):
        raise HTTPException(status_code=403, detail="profile rebuild requires an authorized operator")
    snapshot = service.memory.build_profile(
        scope_id=payload.get("scopeId"), persist=True
    )
    from ..eclipse_memory.profile import preview_payload

    return {**preview_payload(snapshot), "rebuilt": True}


# ── Export / import / backup / health / reset (local operator control) ───────
@router.get("/eclipse-memory/export")
def export_memory(include_inactive: bool = True) -> dict[str, Any]:
    """A readable, versioned JSON export of the memory domain (read-only)."""
    from ..eclipse_memory.transfer import export_payload

    return {"success": True, **export_payload(service.memory_store, include_inactive=include_inactive)}


@router.post("/eclipse-memory/import")
def import_memory(payload: dict[str, Any], _: bool = Depends(require_operator)) -> dict[str, Any]:
    """Validate + import an export document through the normal write pipeline.

    Requires operator authorization. Each record is written via `write_memory`
    (privacy/type/scope/conflict/duplicate rules apply) with `imported`
    provenance, so an import can never bypass the safety gates.
    """
    from ..eclipse_memory.transfer import import_payload

    if not bool(payload.get("operator")):
        raise HTTPException(status_code=403, detail="memory import requires an authorized operator")
    document = payload.get("document")
    if document is None:
        # Allow the export body itself to be posted directly.
        document = payload
    try:
        report = import_payload(
            service.memory, document,
            source=str(payload.get("source") or "imported"),
            dry_run=bool(payload.get("dryRun")),
            scope_filter=payload.get("scopeFilter"),
            type_filter=payload.get("typeFilter"),
            bundles_only=bool(payload.get("bundlesOnly")),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"success": True, **report}


@router.post("/eclipse-memory/backup")
def backup_memory(payload: Optional[dict[str, Any]] = None, _: bool = Depends(require_operator)) -> dict[str, Any]:
    from ..eclipse_memory.transfer import create_backup

    payload = payload or {}
    if not bool(payload.get("operator")):
        raise HTTPException(status_code=403, detail="memory backup requires an authorized operator")
    try:
        result = create_backup(service.memory_store, payload.get("path"))
    except (FileNotFoundError, FileExistsError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"success": True, **result}


@router.get("/eclipse-memory/database-health")
def memory_database_health() -> dict[str, Any]:
    from ..eclipse_memory.transfer import database_health

    return {"success": True, **database_health(service.memory_store)}


@router.post("/eclipse-memory/reset")
def reset_memory_endpoint(payload: dict[str, Any], _: bool = Depends(require_operator)) -> dict[str, Any]:
    """Reset the memory domain only. Requires explicit confirmation; backs up
    first by default; never touches skills or unrelated application data."""
    from ..eclipse_memory.transfer import reset_memory as _reset

    if not bool(payload.get("operator")):
        raise HTTPException(status_code=403, detail="memory reset requires an authorized operator")
    if payload.get("confirm") is not True:
        raise HTTPException(status_code=400, detail="reset requires an explicit confirm=true")
    try:
        result = _reset(
            service.memory_store,
            confirm=True,
            backup_first=payload.get("backupFirst", True) is not False,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"success": True, **result}


# ── Memory suggestions (inert, non-recalled Save/Dismiss proposals) ──────────
# A suggestion is NOT a memory: it is never injected into a run. Accepting it
# writes exactly one scoped memory through the shared gate; dismissing it keeps
# a record so the same suggestion is not re-offered.


@router.get("/eclipse-memory/suggestions")
def list_suggestions(
    status: Optional[str] = "pending", scopeId: Optional[str] = None, limit: int = 100,
) -> dict[str, Any]:
    """Inert Save/Dismiss proposals.

    `scopeId` narrows the list to one user scope (plus unscoped suggestions), so
    a caller can request only their own. This app has no account system, so the
    filter is caller-supplied by design; the authoritative cross-user guard is
    the mismatch refusal in accept/dismiss below.
    """
    return {
        "success": True,
        "suggestions": service.memory_store.list_suggestions(
            status=status, scope_id=scopeId, limit=limit,
        ),
    }


@router.post("/eclipse-memory/suggestions/{suggestion_id}/accept")
def accept_suggestion(suggestion_id: str, payload: Optional[dict[str, Any]] = None, _: bool = Depends(require_operator)) -> dict[str, Any]:
    payload = payload or {}
    if not bool(payload.get("operator")):
        raise HTTPException(status_code=403, detail="accepting a suggestion requires an authorized operator")
    result = service.memory.accept_suggestion(suggestion_id, user_id=payload.get("userId"))
    if result.get("action") == "not_found":
        raise HTTPException(status_code=404, detail="Suggestion not found")
    if result.get("action") == "forbidden":
        raise HTTPException(status_code=403, detail=result.get("reason") or "suggestion scope denied")
    return {"success": bool(result.get("ok")), **result}


@router.post("/eclipse-memory/suggestions/{suggestion_id}/dismiss")
def dismiss_suggestion(suggestion_id: str, payload: Optional[dict[str, Any]] = None, _: bool = Depends(require_operator)) -> dict[str, Any]:
    payload = payload or {}
    if not bool(payload.get("operator")):
        raise HTTPException(status_code=403, detail="dismissing a suggestion requires an authorized operator")
    result = service.memory.dismiss_suggestion(suggestion_id, user_id=payload.get("userId"))
    if result.get("action") == "not_found":
        raise HTTPException(status_code=404, detail="Suggestion not found")
    if result.get("action") == "forbidden":
        raise HTTPException(status_code=403, detail=result.get("reason") or "suggestion scope denied")
    return {"success": bool(result.get("ok")), **result}

