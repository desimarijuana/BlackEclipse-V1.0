"""Sessions, profiles, session history search and learning-review routes.

Extracted verbatim from `main.py` so the front door stays navigable. Behavior,
authorization (`require_operator`, transport/token only) and response shapes are
unchanged; the shared runtime service comes from `harness.deps`.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request

from ..deps import require_operator, service
from ..persistence import now_iso

router = APIRouter()

# ── Session history search (full-session historical recall) ─────────────────


@router.get("/session-search/health")
def session_search_health() -> dict[str, Any]:
    """Index health + whether FTS5 is available. Never claims success falsely."""
    store = service.store
    return {
        "success": True,
        "fts5": store.fts5_available(),
        "indexed": store.session_message_count(),
        "retentionDays": service.memory.policy.get("session_retention_days"),
        "historyEnabled": service.memory.policy.get("session_history_enabled"),
        "indexingEnabled": service.memory.policy.get("session_indexing_enabled"),
    }


@router.get("/session-search")
def session_search(
    q: str,
    scopeId: Optional[str] = None,
    scope: Optional[str] = None,
    runId: Optional[str] = None,
    sessionId: Optional[str] = None,
    profileId: Optional[str] = None,
    role: Optional[str] = None,
    kind: Optional[str] = None,
    market: Optional[str] = None,
    skillId: Optional[str] = None,
    memoryAction: Optional[str] = None,
    dateFrom: Optional[str] = None,
    dateTo: Optional[str] = None,
    limit: int = 10,
) -> dict[str, Any]:
    """Search indexed session history. Historical content is context, not
    current financial evidence."""
    if not service.memory.policy.get("session_history_enabled"):
        raise HTTPException(status_code=403, detail="session history is disabled by policy")
    result = service.store.search_session_messages(
        q,
        user_id=None if scope == "global" else scopeId,
        run_id=runId,
        session_id=sessionId,
        profile_id=profileId,
        role=role,
        kind=kind,
        market=market,
        skill_id=skillId,
        memory_action=memoryAction,
        date_from=dateFrom,
        date_to=dateTo,
        limit=limit,
    )
    return {"success": True, **result}


# ── Named sessions + profiles (M3/M4) ───────────────────────────────────────


@router.get("/sessions")
def list_sessions(
    profileId: Optional[str] = None, userId: Optional[str] = None,
    status: Optional[str] = None, limit: int = 50,
) -> dict[str, Any]:
    return {"success": True, "sessions": service.store.list_chat_sessions(
        profile_id=profileId, user_id=userId, status=status, limit=limit
    )}


@router.post("/sessions")
def create_session(payload: dict[str, Any], _: bool = Depends(require_operator)) -> dict[str, Any]:
    from ..persistence import new_id  # noqa: PLC0415

    session_id = str(payload.get("id") or new_id("sess"))
    session = service.store.create_chat_session(
        session_id,
        profile_id=payload.get("profileId"),
        user_id=payload.get("userId"),
        title=payload.get("title"),
        summary=payload.get("summary"),
    )
    return {"success": True, "session": session}


@router.get("/sessions/{session_id}")
def get_session(session_id: str) -> dict[str, Any]:
    session = service.store.get_chat_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    return {"success": True, "session": session, "runs": service.store.session_runs(session_id)}


@router.patch("/sessions/{session_id}")
def update_session(session_id: str, payload: dict[str, Any], _: bool = Depends(require_operator)) -> dict[str, Any]:
    allowed = {k: payload[k] for k in ("title", "status", "summary", "archivedAt") if k in payload}
    session = service.store.update_chat_session(session_id, **allowed)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    return {"success": True, "session": session}


@router.post("/sessions/{session_id}/fork")
def fork_session(session_id: str, payload: Optional[dict[str, Any]] = None, _: bool = Depends(require_operator)) -> dict[str, Any]:
    from ..persistence import new_id  # noqa: PLC0415

    new_id_value = str((payload or {}).get("id") or new_id("sess"))
    session = service.store.fork_chat_session(session_id, new_id_value)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    return {"success": True, "session": session}


@router.delete("/sessions/{session_id}")
def delete_session(session_id: str, hard: bool = False, _: bool = Depends(require_operator)) -> dict[str, Any]:
    return {"success": True, **service.store.delete_chat_session(session_id, hard=hard)}


@router.get("/sessions/{session_id}/export")
def export_session(session_id: str) -> dict[str, Any]:
    """A bounded, portable export of one session (metadata + indexed messages)."""
    session = service.store.get_chat_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    messages: list[dict[str, Any]] = []
    for run_id in service.store.session_runs(session_id):
        messages.extend(service.store.open_session(run_id).get("messages", []))
    return {"success": True, "session": session, "messages": messages,
            "note": "Historical session content is context, never current financial evidence."}


@router.get("/sessions/{session_id}/summary")
def session_summary(session_id: str) -> dict[str, Any]:
    """A bounded, deterministic session summary (searchable; never auto-injected)."""
    from ..session_index import build_summary  # noqa: PLC0415

    if service.store.get_chat_session(session_id) is None:
        raise HTTPException(status_code=404, detail="session not found")
    return {"success": True, **build_summary(service.store, session_id)}


@router.get("/profiles")
def list_profiles() -> dict[str, Any]:
    return {"success": True, "profiles": service.memory.profiles.list(), "root": service.memory.profiles.root}


@router.post("/profiles")
def create_profile(payload: dict[str, Any], _: bool = Depends(require_operator)) -> dict[str, Any]:
    from ..eclipse_memory.profiles import ProfileError  # noqa: PLC0415

    try:
        profile = service.memory.profiles.create(
            str(payload.get("id") or ""), name=payload.get("name"),
            inherits=payload.get("inherits"),
            retention_days=int(payload.get("retentionDays") or 0),
            settings=payload.get("settings"),
        )
    except ProfileError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"success": True, "profile": profile}


@router.get("/profiles/{profile_id}")
def get_profile(profile_id: str) -> dict[str, Any]:
    profile = service.memory.profiles.get(profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="profile not found")
    return {"success": True, "profile": profile,
            "inherited": service.memory.profiles.inherited_ids(profile_id)}


@router.patch("/profiles/{profile_id}")
def update_profile(profile_id: str, payload: dict[str, Any], _: bool = Depends(require_operator)) -> dict[str, Any]:
    from ..eclipse_memory.profiles import ProfileError  # noqa: PLC0415

    try:
        profile = service.memory.profiles.update(profile_id, **payload)
    except ProfileError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"success": True, "profile": profile}


@router.delete("/profiles/{profile_id}")
def delete_profile(profile_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    from ..eclipse_memory.profiles import ProfileError  # noqa: PLC0415

    try:
        return {"success": True, **service.memory.profiles.delete(profile_id)}
    except ProfileError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/session-search/{run_id}")
def session_open(run_id: str) -> dict[str, Any]:
    """Open a bounded window of one indexed run's messages."""
    if not service.memory.policy.get("session_history_enabled"):
        raise HTTPException(status_code=403, detail="session history is disabled by policy")
    return {"success": True, **service.store.open_session(run_id)}


@router.post("/session-search/reindex")
def session_reindex(
    payload: dict[str, Any] | None = None, _: bool = Depends(require_operator)
) -> dict[str, Any]:
    """Reindex one run or all runs into the session search index (operator)."""
    payload = payload or {}
    if not bool(payload.get("operator")):
        raise HTTPException(status_code=403, detail="reindex requires an authorized operator")
    from ..session_index import index_run

    if payload.get("runId"):
        return {"success": True, **index_run(service.store, str(payload["runId"]))}
    indexed = 0
    runs = service.store.list_runs(limit=int(payload.get("limit", 200)))
    for run in runs:
        result = index_run(service.store, run["id"], user_id=run.get("userId"))
        indexed += int(result.get("indexed") or 0)
    return {"success": True, "runs": len(runs), "indexed": indexed}


@router.post("/session-search/delete/{run_id}")
def session_delete(
    run_id: str, payload: dict[str, Any] | None = None, _: bool = Depends(require_operator)
) -> dict[str, Any]:
    """Remove a run's indexed messages (privacy/delete control). The full run
    trace in agent-memory is untouched."""
    if not bool((payload or {}).get("operator")):
        raise HTTPException(status_code=403, detail="session delete requires an authorized operator")
    removed = service.store.delete_session_messages(run_id)
    return {"success": True, "runId": run_id, "removed": removed}


# ── Learning review (automatic, bounded, inert outcomes) ────────────────────


@router.get("/learning-review/health")
def learning_review_health() -> dict[str, Any]:
    """Queue + audit health. Nothing here enables a skill or writes memory."""
    return {"success": True, **service.learning_review.health()}


@router.get("/learning-review")
def list_learning_reviews(status: Optional[str] = None, limit: int = 50) -> dict[str, Any]:
    return {
        "success": True,
        "reviews": service.store.list_learning_reviews(status=status, limit=limit),
    }


@router.get("/learning-review/{review_id}")
def get_learning_review(review_id: str) -> dict[str, Any]:
    review = service.store.get_learning_review(review_id)
    if review is None:
        raise HTTPException(status_code=404, detail="review not found")
    return {"success": True, "review": review}


@router.post("/learning-review/run")
def run_learning_review(
    payload: dict[str, Any] | None = None, _: bool = Depends(require_operator)
) -> dict[str, Any]:
    """Run a review for ONE run synchronously (operator-triggered).

    Deterministic by default; `model: true` adds the optional bounded model
    review. Outcomes are inert — durable writes still pass the decision gate and
    an operator decides in the UI.
    """
    payload = payload or {}
    if not bool(payload.get("operator")):
        raise HTTPException(status_code=403, detail="review requires an authorized operator")
    run_id = str(payload.get("runId") or "").strip()
    if not run_id:
        raise HTTPException(status_code=400, detail="runId is required")
    from ..learning_review import review_run

    model_settings = None
    if bool(payload.get("model")):
        # Reuse the run's own model settings — no second adapter.
        run = service.store.get_run(run_id) or {}
        try:
            from ..schemas import ModelSettings  # noqa: PLC0415

            model_settings = ModelSettings(
                provider=run.get("provider") or "openai",
                model=run.get("model") or "gpt-4o-mini",
            )
        except Exception:  # noqa: BLE001 - fall back to deterministic only
            model_settings = None
    result = review_run(service.memory, service.store, run_id, model=model_settings is not None, model_settings=model_settings)
    record = service.store.save_learning_review({
        "runId": run_id, "status": "completed", "mode": result["mode"],
        "result": result, "createdAt": now_iso(),
    })
    result["reviewId"] = record["id"]
    service.store.update_learning_review(record["id"], result=result)
    return {"success": True, "review": service.store.get_learning_review(record["id"])}


@router.post("/learning-review/decide")
def decide_learning_review(
    payload: dict[str, Any] | None = None, _: bool = Depends(require_operator)
) -> dict[str, Any]:
    """Accept or reject one review outcome (operator only).

    Accepting a durable-memory outcome writes through the ONE decision gate with
    `run_analysis` provenance — no background path can bypass it. Accepting a
    skill outcome remains inert (it is still never enabled automatically).
    """
    payload = payload or {}
    if not bool(payload.get("operator")):
        raise HTTPException(status_code=403, detail="review decision requires an authorized operator")
    review_id = str(payload.get("reviewId") or "").strip()
    action = str(payload.get("action") or "").strip()
    if action not in ("accept", "reject"):
        raise HTTPException(status_code=400, detail="action must be accept or reject")
    review = service.store.get_learning_review(review_id)
    if review is None:
        raise HTTPException(status_code=404, detail="review not found")
    result = review.get("result") or {}
    outcomes = result.get("outcomes") or []
    index = int(payload.get("outcomeIndex") or 0)
    if index < 0 or index >= len(outcomes):
        raise HTTPException(status_code=400, detail="outcomeIndex out of range")
    outcome = outcomes[index]
    outcome["decided"] = action
    if action == "accept" and outcome.get("category") in ("durable_memory_proposal", "memory_suggestion"):
        content = (outcome.get("payload") or {}).get("content")
        if content:
            from ..eclipse_memory.decision import authorize_proposal

            decision = authorize_proposal(
                content=content, provenance="run_analysis",
                memory_type=(outcome.get("payload") or {}).get("memoryType", "semantic"),
                settings=service.memory.policy.get_all(),
                user_id=payload.get("userId"),
            )
            outcome = service.memory.commit_decision(decision, user_id=payload.get("userId"))
            outcome["category"] = "durable_memory_proposal"
    service.store.update_learning_review(review_id, result={**result, "outcomes": outcomes})
    return {"success": True, "action": action, "outcome": outcome}

