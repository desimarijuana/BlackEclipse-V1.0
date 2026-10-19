"""Per-run context blocks + memory/learning outcomes (extracted from graph.py).

These are the deterministic, best-effort blocks assembled BEFORE the model sees
a turn (recalled memory, the compact persistent profile, the skill manifest) and
the post-turn memory/learning outcome helpers. They were extracted from
`graph.py` so the execution graph stays under its size ratchet while its
behaviour is unchanged: the same functions, same signatures, same order.

Nothing here changes runtime authorization. Every block is clearly-labelled,
bounded, non-authoritative context; every memory write still passes through the
ONE decision gate (`EclipseMemoryService.decide_turn`/`commit_decision`), and a
skill draft is still NEVER enabled (evaluation + operator approval remain the
only promotion gates).
"""

from __future__ import annotations

from typing import Any, Optional

from .events import RunEmitter
from .persistence import AgentMemoryStore
from .schemas import AgentConfig, RunRequest
from .tools import ToolRegistry


async def _memory_context(
    request: RunRequest, memory_service: Optional[Any], emitter: RunEmitter
) -> str:
    """Build the recalled-memory block for this turn (or "" when none).

    Never raises: a memory failure is diagnostics, not a run failure. The
    retrieval is scoped to the invoking user so one user's preferences can never
    leak into another's run, and it is budgeted so it cannot flood the context.
    """
    if memory_service is None:
        return ""
    # A hard-off store surfaces nothing: no retrieval, no injection. This is the
    # other half of surface honesty — a disabled store must not still put memory
    # into the prompt.
    try:
        if memory_service.policy.get("memory_enabled") is False:
            return ""
    except Exception:  # noqa: BLE001 - a policy read failure fails closed to no memory
        return ""
    # Trivial turns skip retrieval too (no stale context attaches to a one-word
    # reply). The gate is pure and writes nothing. A command turn is never
    # trivial, whatever text followed the command.
    from .eclipse_memory.is_trivial import is_trivial_turn  # noqa: PLC0415

    if is_trivial_turn(request.input.query) and not getattr(request, "command", None):
        return ""
    try:
        # The recall budget is the OPERATOR policy (`context_budget_chars`,
        # bounded by eclipse_memory/policy.py), never a hardcoded constant:
        # `EclipseMemoryService.retrieve` falls back to the policy when
        # `budget_chars` is omitted. Passing an explicit value here would bypass
        # Settings and make the operator's budget ineffective.
        result = memory_service.retrieve(
            query=request.input.query,
            subject=request.input.ticker,
            actor_scope="user" if request.userId else None,
            scope_id=request.userId,
            conversation_id=getattr(request, "conversationId", None),
            run_id=request.runId,
            limit=8,
        )
    except Exception as exc:  # noqa: BLE001 - memory must never break a run
        await emitter.emit("memory.retrieval_failed", {"error": str(exc)})
        return ""
    diagnostics = result.diagnostics or {}
    # Bounded run-level observability: record WHICH memories were injected and a
    # bounded sample of exclusions with their reason (scope/status/expiry/
    # relevance/budget/recall-policy). Derived from the retrieval diagnostics;
    # never contains secrets beyond what the local operator may already view.
    selected_ids = [m.get("id") for m in (result.memories or [])]
    excluded = diagnostics.get("excluded") or []
    selection_reasons = diagnostics.get("selectionReasons") or []
    await emitter.emit(
        "memory.retrieved",
        {
            "selected": diagnostics.get("selected", 0),
            "candidates": diagnostics.get("candidates", 0),
            "usedChars": diagnostics.get("usedChars", 0),
            "budgetChars": diagnostics.get("budgetChars", 0),
            "selectedIds": [i for i in selected_ids if i][:20],
            "selectionReasons": list(selection_reasons)[:20],
            "excludedCount": len(excluded),
            "excluded": [dict(e) for e in excluded[:20]],
        },
    )
    return result.context


async def _profile_context(
    request: RunRequest,
    agent: AgentConfig,
    memory_service: Optional[Any],
    emitter: RunEmitter,
) -> tuple[str, Optional[str]]:
    """Build the stable, compact Persistent-context block for this run.

    Returns `(block, snapshot_id)`. Materialized once at run start; a skill
    sub-run is skipped (its prompt and scope differ from chat). Never raises: a
    profile failure is diagnostics.
    """
    if memory_service is None:
        return "", None
    # A skill child-run composes its own prompt; a persistent profile would be
    # noise there and is not the agent identity the user configured.
    if agent.id.startswith("skill:"):
        return "", None
    try:
        settings = memory_service.policy.get_all()
    except Exception:  # noqa: BLE001
        settings = {}
    # A hard-off store injects no profile either (surface honesty).
    if settings.get("memory_enabled") is False:
        return "", None
    if not bool(settings.get("profile_enabled", True)):
        return "", None
    try:
        snapshot = memory_service.build_profile(
            scope_id=request.userId,
            run_scope=None,
            run_id=request.runId,
            persist=True,
        )
    except Exception as exc:  # noqa: BLE001 - a profile must never break a run
        await emitter.emit("memory.profile_failed", {"error": str(exc)})
        return "", None
    from .eclipse_memory.profile import render_prompt_block  # noqa: PLC0415

    block = render_prompt_block(snapshot)
    await emitter.emit(
        "memory.profile_built",
        {
            "snapshotId": snapshot.snapshot_id,
            "entries": len(snapshot.entries),
            "charCount": snapshot.char_count,
            "tokenEstimate": snapshot.token_estimate,
            "excluded": len(snapshot.excluded),
        },
    )
    return block, (snapshot.snapshot_id or None)


async def _skill_manifest_context(
    request: RunRequest,
    skill_registry: Optional[Any],
    memory_service: Optional[Any] = None,
    emitter: Optional[RunEmitter] = None,
) -> tuple[str, Optional[str]]:
    """A bounded, relevant-only skill manifest for this run (never all skills).

    Progressive disclosure: only compact metadata for skills matching the turn
    is injected as a hint; full instructions stay behind `skill_view`, which
    cannot enable or run anything. When the request names a skill bundle, the
    bundle is expanded deterministically instead (missing/disabled members are
    reported, never enabled), and the resolution is recorded for observability.
    """
    if skill_registry is None:
        return "", None

    if getattr(request, "bundleId", None) and memory_service is not None:
        from .skills.bundles import resolve_bundle  # noqa: PLC0415

        try:
            resolution = resolve_bundle(
                memory_service.store, skill_registry, request.bundleId,
            )
        except Exception:  # noqa: BLE001 - a bad bundle must not break the run
            resolution = None
        if resolution is not None:
            if emitter is not None:
                try:
                    await emitter.emit("skill.bundle_resolved", resolution.to_dict())
                except Exception:  # noqa: BLE001
                    pass
            from .prompt_segments import _hash  # noqa: PLC0415

            if resolution.content:
                return resolution.content, _hash(resolution.content)
            return "", None

    from .prompt_segments import build_skill_manifest  # noqa: PLC0415

    query = request.input.query or request.input.ticker or ""
    return build_skill_manifest(skill_registry, query)


async def _apply_memory_intent(
    request: RunRequest,
    memory_service: Optional[Any],
    emitter: RunEmitter,
) -> Optional[dict[str, Any]]:
    """Run the shared memory decision gate for this turn and act on it.

    Every turn goes through `EclipseMemoryService.decide_turn` (the ONE write
    gate). An explicit "remember/forget/correct" command is always honoured when
    safe and clear; a casual durable mention follows `memory_mode`
    (automatic_selective saves strong low-risk evidence without a prompt;
    ask_before_saving stages an inert suggestion; off creates nothing); anything
    else is `history_only`/`ignore` and writes no durable record. An explicit
    "turn this into a skill" request is surfaced here and turned into a real
    inert skill draft AFTER the run's trace exists (see `_create_explicit_skill_draft`
    called from `execute_run`).

    Deterministic; never raises. Returns a bounded outcome dict for the run
    blob, or None when there is nothing user-visible.
    """
    if memory_service is None:
        return None
    # Trivial-prompt gate (Milestone 5): a bare greeting/acknowledgement, a slash
    # command or empty input skips the memory decision entirely. An explicit
    # remember/forget/correct is never trivial, so the always-on intent path still
    # runs. Nothing is written and the reply is unaffected. A recognized chat
    # command (e.g. `/eclipsesdk`, which forces a code profile) is never trivial.
    from .eclipse_memory.is_trivial import is_trivial_turn  # noqa: PLC0415

    if is_trivial_turn(request.input.query) and not getattr(request, "command", None):
        try:
            await emitter.emit("memory.trivial_skipped", {"runId": request.runId})
        except Exception:  # noqa: BLE001
            pass
        return None
    recurring = _is_recurring_statement(request)
    try:
        decision = memory_service.decide_turn(
            request.input.query,
            user_id=request.userId,
            recurring=recurring,
            is_skill_run=False,
            conversation_id=getattr(request, "conversationId", None),
        )
    except Exception as exc:  # noqa: BLE001 - memory must never break a run
        try:
            await emitter.emit("memory.intent_failed", {"error": str(exc)})
        except Exception:  # noqa: BLE001
            pass
        return None

    if decision.outcome in ("ignore", "history_only") and not decision.refused:
        # Nothing durable: leave the turn uncluttered. A skill request is
        # surfaced so the run's completion can create the draft from its trace.
        if decision.action == "skill":
            await emitter.emit("memory.skill_requested", {"runId": request.runId})
            return {
                "outcome": "history_only", "action": "skill_requested", "ok": False,
                "reason": decision.reason, "requiresConfirmation": False, "refused": False,
            }
        return None

    try:
        outcome = memory_service.commit_decision(
            decision, run_id=request.runId, user_id=request.userId,
            conversation_id=getattr(request, "conversationId", None),
        )
    except Exception as exc:  # noqa: BLE001 - memory must never break a run
        try:
            await emitter.emit("memory.intent_failed", {"error": str(exc)})
        except Exception:  # noqa: BLE001
            pass
        return None

    event_type = {
        "saved": "memory.explicit_saved",
        "forgotten": "memory.explicit_forgotten",
        "corrected": "memory.explicit_corrected",
        "suggested": "memory.suggested",
        "needs_review": "memory.conflict_needs_review",
        "needs_clarification": "memory.intent_needs_clarification",
        "refused": "memory.intent_refused",
        "ignored": "memory.intent_ignored",
        "history_only": "memory.intent_history_only",
    }.get(outcome.get("action"))
    if event_type:
        await emitter.emit(event_type, {
            "runId": request.runId,
            "action": outcome.get("action"),
            "outcome": outcome.get("outcome"),
            "refused": bool(outcome.get("action") == "refused"),
        })
    return _outcome_blob(outcome, decision)


def _is_recurring_statement(request: RunRequest) -> bool:
    """True when the current query repeats a durable-sounding statement from
    prior conversation history (deterministic normalized match)."""
    from .eclipse_memory.decision import content_signature  # noqa: PLC0415

    query = (request.input.query or "").strip()
    if not query:
        return False
    signature = content_signature(query)
    for turn in request.input.history or []:
        if turn.role != "user":
            continue
        if content_signature(turn.content) == signature:
            return True
    return False


def _create_explicit_skill_draft(
    request: RunRequest, *, store: Optional[AgentMemoryStore], skill_registry: Optional[Any],
    registry: Optional[ToolRegistry] = None,
) -> Optional[dict[str, Any]]:
    """Create an inert skill draft from an explicit "turn this into a skill".

    Uses the real `capture_from_run` + `propose_draft` persistence path: a
    learning candidate is recorded and a `status: draft` version is stored. The
    draft is never enabled — evaluation + operator approval remain the only way
    to promote it. Never raises; a failure is reported honestly in the blob.
    """
    if store is None or skill_registry is None:
        return None
    skill_store = getattr(skill_registry, "store", None)
    if skill_store is None:
        return None
    try:
        from .skills.draft import propose_draft  # noqa: PLC0415
        from .skills.learning import capture_from_run  # noqa: PLC0415

        result = capture_from_run(
            request.runId, store, skill_store,
            actor_is_operator=True, user_intent="turn this into a skill",
        )
        candidates = result.get("created") or []
        if not candidates:
            return {"captured": False, "reason": "no candidate produced"}
        candidate_id = candidates[0]["id"]
        available = registry.names() if registry is not None else _agent_tool_names(request)
        draft = propose_draft(
            candidate_id, skill_store, available_tools=list(available),
            user_intent="turn this into a skill",
        )
        return {
            "captured": True,
            "candidateId": candidate_id,
            "skillId": (draft.get("draft") or {}).get("id") if draft.get("ok") else None,
            "status": "draft",
            "draftOk": bool(draft.get("ok")),
            "reusable": draft.get("reusable"),
            "issues": draft.get("issues") or [],
        }
    except Exception as exc:  # noqa: BLE001 - a draft failure must not break the run
        return {"captured": False, "reason": str(exc)}


def _agent_tool_names(request: RunRequest) -> list[str]:
    """Tools the run may use, for draft tool-evidence validation. Best-effort."""
    try:
        from .graph import resolve_agent  # noqa: PLC0415 - lazy to avoid a cycle

        agent = resolve_agent(request)
        return list(agent.tools or [])
    except Exception:  # noqa: BLE001
        return []


def _outcome_blob(outcome: dict[str, Any], decision: Any) -> dict[str, Any]:
    memory = outcome.get("memory") or {}
    blob: dict[str, Any] = {
        "outcome": outcome.get("outcome"),
        "action": outcome.get("action"),
        "ok": bool(outcome.get("ok")),
        "refused": bool(outcome.get("action") == "refused"),
        "requiresConfirmation": bool(outcome.get("action") == "needs_confirmation"),
        "reason": outcome.get("reason") or getattr(decision, "reason", ""),
        "matchedPhrase": getattr(decision, "matched_phrase", ""),
    }
    if memory.get("id"):
        blob["memoryId"] = memory["id"]
        blob["memoryType"] = memory.get("memoryType")
        blob["scope"] = memory.get("scope")
        blob["subject"] = memory.get("subject")
        blob["status"] = memory.get("status")
        blob["contentPreview"] = (memory.get("content") or "")[:400]
        blob["inspectPath"] = f"/api/eclipse-memory/memories/{memory['id']}"
        blob["undoPath"] = f"/api/eclipse-memory/memories/{memory['id']}/archive"
        # A proposed record is NOT active truth. Surface why, and whether the
        # proposal came from the semantic candidate layer, so the chat panel can
        # distinguish "proposed for review" from a saved memory.
        status_reason = memory.get("statusReason") or ""
        if status_reason:
            blob["statusReason"] = status_reason
        if memory.get("status") == "proposed":
            blob["requiresReview"] = True
            blob["semanticCandidate"] = "semantic" in status_reason.lower()
    suggestion = outcome.get("suggestion") or {}
    if suggestion.get("id"):
        blob["suggestionId"] = suggestion["id"]
        blob["suggestionContent"] = suggestion.get("content")
        blob["suggestionType"] = suggestion.get("memoryType")
        blob["suggestionScope"] = suggestion.get("scope")
        blob["suggestionPath"] = "/api/eclipse-memory/suggestions"
    if outcome.get("superseded"):
        blob["supersededMemoryId"] = outcome["superseded"]
    if outcome.get("archived"):
        blob["archivedMemoryIds"] = outcome["archived"]
    if outcome.get("candidates"):
        blob["ambiguousMemoryIds"] = outcome["candidates"]
    return blob


def _memory_blob(
    memory_outcome: Optional[dict[str, Any]],
    eligibility: dict[str, Any],
    analysis: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    blob: dict[str, Any] = {"learningEligibility": eligibility}
    if memory_outcome:
        blob.update(memory_outcome)
    if analysis:
        created = int(analysis.get("candidatesCreated") or 0)
        duplicates = int(analysis.get("candidatesSkipped") or 0)
        blob["learningAnalysis"] = {
            "candidatesCreated": created,
            "candidatesSkipped": duplicates,
            "mistakesCreated": analysis.get("mistakesCreated", 0),
            "candidateDetection": analysis.get("candidateDetection"),
        }
        # The eligibility heuristic and the criteria-driven analyzer are not the
        # same test. If automatic learning actually produced a candidate, report
        # the run as eligible so the UI never claims "not a learning candidate"
        # for a run that was just captured.
        if created > 0:
            eligibility["eligible"] = True
            eligibility["autoCaptured"] = True
            if not eligibility.get("skillRequested"):
                eligibility["reason"] = "automatically captured a reusable lesson"
    return blob


def _eligibility_dict(
    run_id: str, *, eligible: bool, reason: str, steps: int, tool_calls: int,
    skill_requested: bool,
) -> dict[str, Any]:
    return {
        "runId": run_id,
        "eligible": eligible,
        "reason": reason,
        "modelSteps": steps,
        "toolCalls": tool_calls,
        "skillRequested": skill_requested,
        "isSkillRun": False,
        "learnQueuePath": "/?tab=skills&sub=skills.learning",
    }


def learning_eligibility_for_run(run_id: str, store: AgentMemoryStore) -> dict[str, Any]:
    """Why a completed ordinary chat run is/isn't a learning candidate.

    Read-only eligibility (does not create anything): a plain informational
    reply is not eligible; a run that used tools / took multiple steps / asked
    to become a skill is. Creating a candidate stays an explicit operator action
    ("Learn from this run").
    """
    run = store.get_run(run_id) or {}
    memory_blob = run.get("memory") or {}
    skill_requested = memory_blob.get("action") == "skill_requested"
    reason = ""
    eligible = False
    steps = int(run.get("modelSteps") or 0)
    tool_calls = int(run.get("toolCalls") or 0)
    if run.get("status") != "completed":
        reason = "run did not complete"
    elif skill_requested:
        eligible, reason = True, "the user asked to turn this run into a skill"
    elif tool_calls == 0:
        reason = "no tool use — an informational reply has no reusable procedure"
    elif steps < 2:
        reason = "single model step — not enough structure to generalize"
    else:
        eligible, reason = True, "multi-step run with tool evidence"
    return _eligibility_dict(
        run_id, eligible=eligible, reason=reason, steps=steps,
        tool_calls=tool_calls, skill_requested=skill_requested,
    )


def _learning_eligibility(
    *, run_id: str, store: AgentMemoryStore, memory_outcome: Optional[dict[str, Any]]
) -> dict[str, Any]:
    """Eligibility for the just-finished run (uses the in-memory outcome, which
    is not yet persisted when this is called)."""
    run = store.get_run(run_id) or {}
    skill_requested = bool(memory_outcome and memory_outcome.get("action") == "skill_requested")
    reason = ""
    eligible = False
    steps = int(run.get("modelSteps") or 0)
    tool_calls = int(run.get("toolCalls") or 0)
    if run.get("status") != "completed":
        reason = "run did not complete"
    elif skill_requested:
        eligible, reason = True, "the user asked to turn this run into a skill"
    elif tool_calls == 0:
        reason = "no tool use — an informational reply has no reusable procedure"
    elif steps < 2:
        reason = "single model step — not enough structure to generalize"
    else:
        eligible, reason = True, "multi-step run with tool evidence"
    return _eligibility_dict(
        run_id, eligible=eligible, reason=reason, steps=steps,
        tool_calls=tool_calls, skill_requested=skill_requested,
    )


__all__ = [
    "_agent_tool_names",
    "_apply_memory_intent",
    "_create_explicit_skill_draft",
    "_is_recurring_statement",
    "_learning_eligibility",
    "_memory_blob",
    "_memory_context",
    "_outcome_blob",
    "_profile_context",
    "_skill_manifest_context",
    "learning_eligibility_for_run",
]
