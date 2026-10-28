"""Memory & skill tools — the agent-facing surface of Eclipse-Memory.

These are the tools the system prompt actually promises. They are registered on
the SAME `ToolRegistry` as the financial tools, so there is no second registry,
and the runtime's existing permission/validation/timeout machinery applies.

Tools:
  * `memory`      — save / list / search durable memory (write via the service
                    pipeline so type/scope/dedupe/evidence are enforced).
  * `skill_list`  — compact skill metadata for discovery (progressive load step 1-2).
  * `skill_view`  — load one skill's full instructions (step 3).

Skill *execution* still goes through `skills.runtime.execute_skill`; these tools
only let the agent discover and read. Nothing here enables a skill or writes a
skill version — that remains an operator-gated lifecycle action.
"""

from __future__ import annotations

from typing import Any, Optional

from .skills.permissions import Actor, check_permissions
from .tools import ToolContext, ToolDefinition, ToolRegistry


def _service(ctx: ToolContext) -> Any:
    svc = getattr(ctx, "memory_service", None)
    if svc is None:
        raise RuntimeError("Eclipse-Memory service is not attached to this run")
    return svc


_DEFAULT_CONFIDENCE = 0.8


def _coerce_confidence(value: Any, default: float = _DEFAULT_CONFIDENCE) -> float:
    """Coerce a caller-supplied confidence to a bounded float.

    A missing OR present-but-null value is the common case (a model omits the
    field, or emits JSON `null`); `args.get("confidence", default)` would return
    `None` for the latter and `float(None)` would raise. Both fall back to the
    default. A genuinely malformed value is left to raise so the save wrapper
    can return a typed error rather than guessing.
    """
    if value is None or value == "":
        return default
    confidence = float(value)
    if confidence != confidence:  # NaN
        return default
    return min(1.0, max(0.0, confidence))


# ── memory ──────────────────────────────────────────────────────────────────


async def memory_handler(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    action = str(args.get("action") or "list")
    svc = _service(ctx)

    if action == "save":
        content = str(args.get("content") or "").strip()
        memory_type = str(args.get("type") or "semantic")
        # In a conversation-scoped run (a bot / group member) a durable save is
        # PRIVATE to that conversation by default; the model must ask explicitly
        # for `general` to publish shared knowledge.
        default_scope = "conversation" if ctx.conversation_id else "general"
        scope = str(args.get("scope") or default_scope)
        scope_id = args.get("scope_id") or (
            ctx.conversation_id if scope == "conversation" else None
        ) or ctx.user_id

        # The model may PROPOSE a memory, but it cannot authorize its own write.
        # The shared decision gate re-checks the proposal against the actual user
        # turn, identity, scope, provenance, category, evidence, privacy rules and
        # policy. A proposal not backed by explicit user intent is downgraded
        # (suggest / history_only / ignore) rather than persisted.
        from .eclipse_memory.decision import authorize_proposal  # noqa: PLC0415

        try:
            settings = svc.policy.get_all()
        except Exception:  # noqa: BLE001 - a policy read failure must fail closed, not open
            settings = {}
        try:
            confidence = _coerce_confidence(args.get("confidence"))
            verified = bool(args.get("verified"))
        except (TypeError, ValueError) as exc:
            # Bad tool input is a typed error, never an unhandled TypeError. The
            # write is refused (no memory is saved) — fail closed.
            return (
                "MEMORY NOT SAVED — invalid input: confidence must be a number between 0 and 1.",
                {"saved": False, "outcome": "invalid_input", "reason": str(exc)},
            )
        try:
            decision = authorize_proposal(
                content=content,
                provenance="skill_lesson" if ctx.is_skill_run else "memory_tool",
                user_message=getattr(ctx, "user_message", "") or "",
                user_id=ctx.user_id,
                memory_type=memory_type,
                scope=scope,
                scope_id=str(scope_id) if scope_id else None,
                subject=args.get("subject"),
                confidence=confidence,
                settings=settings,
                verified=verified,
                conversation_id=ctx.conversation_id,
            )
            outcome = svc.commit_decision(
                decision, run_id=ctx.run_id, user_id=ctx.user_id,
                conversation_id=ctx.conversation_id,
            )
        except (TypeError, ValueError) as exc:
            # Defense in depth: any bad input the gate would coerce internally is
            # returned as a typed error instead of an unhandled TypeError. The
            # write authorization decision itself is untouched — this only wraps
            # the call so a malformed field cannot crash the tool.
            return (
                "MEMORY NOT SAVED — invalid input.",
                {"saved": False, "outcome": "invalid_input", "reason": str(exc)},
            )
        if not outcome.get("ok"):
            if outcome.get("action") == "suggested":
                return (
                    "MEMORY NOT SAVED — this looks like durable information, but the user did not "
                    "explicitly ask to remember it. A suggestion was recorded for the user to "
                    "Save or Dismiss. Do not claim it was remembered.",
                    {"saved": False, "outcome": "suggest", "reason": decision.reason},
                )
            if outcome.get("action") == "memory_full":
                return (
                    f"MEMORY NOT SAVED — {outcome.get('reason')}",
                    {
                        "saved": False, "outcome": "memory_full",
                        "limit": outcome.get("limit"), "active": outcome.get("active"),
                        "reason": outcome.get("reason"),
                    },
                )
            if outcome.get("action") == "history_only":
                return (
                    "MEMORY NOT SAVED — this stays in conversation history, not durable memory. "
                    "The user may re-state it explicitly to save it. Do not claim it was remembered.",
                    {"saved": False, "outcome": "history_only", "reason": decision.reason or outcome.get("reason")},
                )
            return (
                f"MEMORY NOT SAVED — {decision.reason or outcome.get('reason')}",
                {"saved": False, "outcome": decision.outcome, "reason": decision.reason or outcome.get("reason")},
            )
        memory = outcome["memory"]
        return (
            f"Memory saved ({memory['memoryType']}/{memory['scope']}) id={memory['id']}.",
            {"saved": True, "id": memory["id"], "memoryType": memory["memoryType"], "scope": memory["scope"]},
        )

    if action == "search":
        query = str(args.get("query") or "")
        result = svc.retrieve(
            query=query,
            memory_types=args.get("types"),
            subject=args.get("subject"),
            actor_scope=ctx.user_id and "user",
            scope_id=ctx.user_id,
            conversation_id=ctx.conversation_id,
            run_id=ctx.run_id,
            limit=int(args.get("limit") or 8),
        )
        if not result.memories:
            return (
                "No relevant memory found.",
                {"count": 0, "diagnostics": result.diagnostics},
            )
        lines = [f"{len(result.memories)} memory item(s):"]
        for memory in result.memories:
            lines.append(
                f"  [{memory['memoryType']}/{memory.get('verification','unverified')}] "
                f"{memory.get('subject') or ''} — {memory['content']}"
            )
        return "\n".join(lines), {"count": len(result.memories), "memories": result.memories}

    if action == "inventory":
        # Counts only — never content. Answers "what is actually in the store?"
        # with the whole-store totals that list/search deliberately do not expose
        # (they are scoped/paged/relevance-filtered).
        counts = svc.store.memory_lifecycle_counts()
        total = sum(
            int(counts.get(key, 0) or 0)
            for key in ("active", "expired", "archived", "superseded", "rejected", "proposed")
        )
        lines = [
            f"Memory inventory: {total} record(s) in the store (counts only).",
            "  status: " + ", ".join(
                f"{key}={int(counts.get(key, 0) or 0)}"
                for key in ("active", "expired", "archived", "superseded", "rejected", "proposed")
            ),
            "  lifecycle: " + ", ".join(
                f"{key}={int(counts.get(key, 0) or 0)}"
                for key in ("neverUsed", "frequentlyRecalled", "expiring", "stale", "automatic", "explicit")
            ),
            "Reads differ by design: list = recent ACTIVE rows in this scope; search = "
            "relevance over this scope + general, excluding proposed/expired/low-confidence "
            "unverified. The totals above are the whole store.",
        ]
        consolidation: dict[str, Any] = {}
        try:
            from .eclipse_memory.consolidation import consolidate_active  # noqa: PLC0415

            consolidation = consolidate_active(svc.store, dry_run=True)
            lines.append(
                "  consolidation (dry-run): "
                f"duplicateCount={consolidation.get('duplicateCount', 0)}, "
                f"conflictCount={consolidation.get('conflictCount', 0)}, "
                f"residueCount={consolidation.get('residueCount', 0)}, "
                f"relatedCount={consolidation.get('relatedCount', 0)}"
            )
        except Exception as exc:  # noqa: BLE001
            consolidation = {"error": str(exc)[:200]}
        return "\n".join(lines), {
            "total": total, "counts": counts, "consolidation": consolidation,
        }

    # list
    default_list_scope = "conversation" if ctx.conversation_id else args.get("scope")
    memories = svc.store.list_memories(
        memory_type=args.get("type"), scope=default_list_scope,
        scope_id=args.get("scope_id")
        or (ctx.conversation_id if default_list_scope == "conversation" else ctx.user_id),
        limit=int(args.get("limit") or 20), include_inactive=False,
    )
    if not memories:
        return "No stored memory yet.", {"count": 0, "memories": []}
    lines = [f"{len(memories)} stored memory item(s):"]
    for memory in memories:
        lines.append(f"  [{memory['memoryType']}] {memory['content'][:180]}")
    return "\n".join(lines), {"count": len(memories), "memories": memories}


# ── session_search / session_open (historical recall) ───────────────────────


def _session_store(ctx: ToolContext) -> Any:
    store = getattr(ctx, "memory_store", None)
    if store is None:
        raise RuntimeError("session history is not available in this run")
    return store


async def session_search_handler(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    """Read-only full-text search over prior Eclipse sessions.

    Historical content is CONTEXT, not current financial evidence. These tools
    never write and never return unbounded text.
    """
    store = _session_store(ctx)
    query = str(args.get("query") or "").strip()
    if not query:
        return "A search query is required.", {"available": True, "results": [], "hasMore": False}
    limit = int(args.get("limit") or 0) or None
    result = store.search_session_messages(
        query,
        user_id=ctx.user_id if args.get("scope") != "global" else None,
        date_from=args.get("date_from"),
        date_to=args.get("date_to"),
        run_id=args.get("run_id"),
        role=args.get("role"),
        session_id=args.get("session_id"),
        profile_id=args.get("profile_id"),
        market=args.get("market"),
        skill_id=args.get("skill_id"),
        memory_action=args.get("memory_action"),
        kind=args.get("kind"),
        limit=limit or 10,
    )
    if not result.get("results"):
        return (
            "No matching prior session content found. Historical search is "
            f"available (engine: {result.get('engine')}).",
            {**result, "count": 0},
        )
    lines = [f"{len(result['results'])} matching prior message(s) (engine: {result.get('engine')}):"]
    for hit in result["results"]:
        score = f" score={hit['score']:.2f}" if hit.get("score") is not None else ""
        lines.append(
            f"  run={hit['runId']} msg={hit['messageId']} [{hit['role']}/{hit['kind']}]"
            f" {hit['createdAt'][:10]}{score}: {hit['snippet']}"
        )
    if result.get("hasMore"):
        lines.append("  (more results may exist — refine the query or raise limit)")
    lines.append(
        "Historical content is context, not current market evidence — re-retrieve "
        "current facts with finance tools."
    )
    return "\n".join(lines), {**result, "count": len(result["results"])}


async def session_open_handler(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    """Bounded context expansion for one prior run (after session_search)."""
    store = _session_store(ctx)
    run_id = str(args.get("run_id") or "").strip()
    if not run_id:
        return "A run_id is required.", {"runId": None, "messages": []}
    window = store.open_session(
        run_id,
        message_id=args.get("message_id"),
        before=int(args.get("before") or 3),
        after=int(args.get("after") or 3),
    )
    if not window.get("messages"):
        return f"No indexed messages for run {run_id}.", window
    lines = [f"Run {run_id} ({len(window['messages'])} message(s){', truncated' if window.get('truncated') else ''}):"]
    for message in window["messages"]:
        content = (message.get("content") or message.get("snippet") or "")[:1200]
        lines.append(f"  [{message['role']}/{message['kind']}] {content}")
    return "\n".join(lines), window


# ── learning loop (read-only) ──────────────────────────────────────────────
# QA Round 1 (F3): no tool read the automatic review records or the captured
# learning candidates, so an agent asked to summarize them guessed ("only the
# buttons create reviews"). These expose exactly what the Memory → Reviews and
# Skills → Learning Queue screens read. Read-only: running a review and
# accepting/rejecting/enabling anything stay UI/operator actions.

MAX_LEARNING_ROWS = 50


def _learning_review_store(ctx: ToolContext) -> Any:
    store = getattr(ctx, "memory_store", None)
    if store is None:
        raise RuntimeError("the learning review store is not available in this run")
    return store


def _learning_candidate_store(ctx: ToolContext) -> Any:
    # Learning CANDIDATES live in EclipseMemoryStore; `ctx.learning_store` is the
    # different-domain research LearningStore (paths/progress). Resolve by
    # capability so a wrong-type object can never raise AttributeError.
    memory = getattr(ctx, "memory_service", None)
    store = getattr(memory, "store", None) if memory is not None else None
    if callable(getattr(store, "list_candidates", None)):
        return store
    learning = getattr(ctx, "learning_store", None)
    if callable(getattr(learning, "list_candidates", None)):
        return learning
    return None


def _skill_learning_policy(ctx: ToolContext) -> Optional[tuple[Any, Any]]:
    memory = getattr(ctx, "memory_service", None)
    policy = getattr(memory, "policy", None) if memory is not None else None
    if policy is None:
        return None
    try:
        settings = policy.get_all()
    except Exception:  # noqa: BLE001 - reporting must never raise
        return None
    if not isinstance(settings, dict):
        return None
    return settings.get("skill_learning_mode"), settings.get("auto_candidate_detection")


async def learning_review_list_handler(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    store = _learning_review_store(ctx)
    status = str(args.get("status") or "").strip() or None
    limit = max(1, min(int(args.get("limit") or 10), MAX_LEARNING_ROWS))
    health = store.learning_review_health()
    reviews = store.list_learning_reviews(status=status, limit=limit)
    by_status = ", ".join(f"{key} {value}" for key, value in sorted((health.get("byStatus") or {}).items()))
    header = f"Learning reviews: {health.get('total', 0)} total" + (f" ({by_status})" if by_status else "") + "."
    # The gate is the deliverable; expose it on a bound READ tool so a chat run
    # can read gate.ok without HTTP-body permission.
    gate: dict[str, Any] = {}
    try:
        from .self_improvement.loop_health import gate_report  # noqa: PLC0415

        memory = getattr(ctx, "memory_service", None)
        candidates = getattr(memory, "store", None) if memory is not None else None
        advisory = getattr(ctx, "advisory_service", None)
        policy = getattr(memory, "policy", None) if memory is not None else None
        mode = policy.get_all().get("skill_learning_mode") if policy is not None else None
        gate = gate_report(
            store, skill_store=candidates, advisory_service=advisory,
            learning_mode=mode,
        )
    except Exception as exc:  # noqa: BLE001 - reading the gate never breaks the list
        gate = {"ok": False, "unavailable": True, "reason": str(exc)[:200]}
    gap_codes = [
        str(g.get("code")) for g in (gate.get("gaps") or []) if isinstance(g, dict)
    ]
    reviews_gate = gate.get("reviews") or {}
    legacy_reviews = gate.get("legacyReviews") or {}
    advice_gate = gate.get("advisory") or {}
    legacy_advice = gate.get("legacyAdvisory") or {}
    candidates_gate = gate.get("candidates") or {}
    gate_line = (
        f"Gate: ok={gate.get('ok')} gaps={', '.join(gap_codes) or 'none'} "
        f"contractSince={gate.get('contractSince')}\n"
        f"  current reviews: {reviews_gate.get('completed')} completed, "
        f"{reviews_gate.get('withTypedLesson')} typed, "
        f"{reviews_gate.get('justifiedNulls')} justified nulls, "
        f"{reviews_gate.get('unjustifiedNulls')} unjustified nulls\n"
        f"  legacy reviews: {legacy_reviews.get('unjustifiedNulls')} unjustified nulls\n"
        f"  current advice: {advice_gate.get('total')} total, "
        f"{advice_gate.get('evaluated')} evaluated, {advice_gate.get('unscored')} unscored, "
        f"{advice_gate.get('overdue')} overdue\n"
        f"  legacy advice: {legacy_advice.get('total')} total, "
        f"{legacy_advice.get('evaluated')} evaluated, {legacy_advice.get('unscored')} unscored, "
        f"{legacy_advice.get('overdue')} overdue\n"
        f"  candidates: {candidates_gate.get('accepted')} accepted, "
        f"{candidates_gate.get('detected')} detected, "
        f"{candidates_gate.get('nonconforming')} nonconforming, "
        f"{candidates_gate.get('staleDetected')} staleDetected\n"
        f"  memory: {((gate.get('memory') or {}).get('duplicateCount'))} duplicates, "
        f"{((gate.get('memory') or {}).get('conflictCount'))} conflicts, "
        f"{((gate.get('memory') or {}).get('residueCount'))} residue, "
        f"{((gate.get('memory') or {}).get('relatedCount'))} related"
    )
    if not reviews:
        return (
            header + " No review records yet. One is queued automatically after every completed or "
            "failed chat run and persisted after a short idle; Memory \u2192 Reviews can also run one on demand.\n"
            + gate_line,
            {"health": health, "reviews": [], "count": 0, "gate": gate},
        )
    from .self_improvement.loop_health import audit_reviews  # noqa: PLC0415

    audit = audit_reviews(reviews)
    lines = [header]
    lines.append(
        f"  audit: {audit['typedLessons']} typed lesson(s), "
        f"{audit['justifiedNulls']} justified null(s), "
        f"{audit['unjustifiedNulls']} bare/unjustified null(s)."
    )
    for review in reviews:
        outcomes = (review.get("result") or {}).get("outcomes") or []
        kinds = ", ".join(str(outcome.get("category") or "outcome") for outcome in outcomes[:5]) or "no outcomes"
        lines.append(
            f"  {review.get('id')} run={review.get('runId')} "
            f"[{review.get('status')}/{review.get('mode')}] "
            f"{str(review.get('createdAt') or '')[:19]} — {len(outcomes)} outcome(s): {kinds}"
        )
        for outcome in outcomes[:5]:
            if not isinstance(outcome, dict):
                continue
            if outcome.get("category") == "typed_lesson":
                lesson = (outcome.get("payload") or {}).get("lesson") or {}
                evidence = lesson.get("evidence") or []
                lines.append(
                    f"    lesson: when {str(lesson.get('condition') or '')[:120]} -> "
                    f"{str(lesson.get('action') or '')[:160]} "
                    f"(confidence {lesson.get('confidence')}) "
                    f"evidence={len(evidence)}: "
                    f"{', '.join(str(item) for item in evidence[:5])[:200] or 'MISSING'}"
                )
            elif outcome.get("category") == "no_learning":
                label = "justified" if bool(outcome.get("justified")) else "UNJUSTIFIED"
                reason = str(outcome.get("reason") or "").strip() or "NO REASON"
                checked = outcome.get("evidenceChecked") or []
                lines.append(
                    f"    null[{label}]: {reason[:200]} "
                    f"(checked {len(checked)} item(s))"
                )
    lines.append(gate_line)
    lines.append("Read-only. Running a review and accept/reject decisions are operator actions (Memory → Reviews).")
    return "\n".join(lines), {
        "health": health, "reviews": reviews, "count": len(reviews),
        "audit": audit, "gate": gate,
    }


async def learning_candidate_list_handler(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    store = _learning_candidate_store(ctx)
    if store is None:
        return (
            "The learning candidate store is not available in this run.",
            {"count": 0, "candidates": [], "available": False},
        )
    status = str(args.get("status") or "").strip() or None
    requested_limit = max(1, int(args.get("limit") or 10))
    limit = min(requested_limit, MAX_LEARNING_ROWS)
    cap_note = (
        f"Requested limit {requested_limit} was capped at {MAX_LEARNING_ROWS}."
        if requested_limit > MAX_LEARNING_ROWS else None
    )
    candidates = store.list_candidates(status=status, limit=limit)
    total = None
    counter = getattr(store, "count_candidates", None)
    if callable(counter):
        try:
            total = int(counter(status=status))
        except Exception:  # noqa: BLE001 - the page is still useful without a total
            total = None
    if not candidates:
        policy = _skill_learning_policy(ctx)
        mode, detection = policy if policy is not None else (None, None)
        data = {
            "count": 0, "total": total, "candidates": [],
            "mode": mode, "autoCandidateDetection": detection,
        }
        scope = f" with status {status!r}" if status else ""
        prefix = f"No learning candidates captured{scope} yet."
        if detection is False:
            text = (
                prefix + " Automatic candidate detection is disabled "
                f"(skill learning mode is {mode}); enable it in Settings \u2192 Skills or with "
                "skill_learning_set, then rerun."
            )
        elif policy is None:
            text = (
                prefix + " The skill learning mode could not be read in this run, so automatic "
                "capture cannot be confirmed; candidates would appear in Skills \u2192 Learning Queue."
            )
        else:
            text = (
                prefix + " A candidate is created automatically at run end when a reusable lesson "
                "is detected; they appear in Skills \u2192 Learning Queue."
            )
        lines = [text]
        if cap_note:
            lines.append(cap_note)
        lines.append("Read-only. Candidates are inert; review/accept them in Skills \u2192 Learning Queue.")
        return "\n".join(lines), data
    if total is not None and total > len(candidates):
        lines = [f"Showing {len(candidates)} of {total} learning candidate(s), most recent first:"]
    elif total is not None:
        lines = [f"{len(candidates)} learning candidate(s), most recent first:"]
    else:
        lines = [f"{len(candidates)} learning candidate(s), most recent first (total unavailable):"]
    from .self_improvement.lesson_contract import candidate_problems  # noqa: PLC0415

    enriched: list[dict[str, Any]] = []
    terminal = {"rejected", "expired", "accepted", "drafted"}
    for candidate in candidates:
        item = dict(candidate)
        status = str(candidate.get("status") or "")
        item["contractProblems"] = (
            candidate_problems(candidate) if status not in terminal else []
        )
        enriched.append(item)
        title = candidate.get("title") or candidate.get("proposedLesson") or candidate.get("signature") or ""
        lines.append(
            f"  {candidate.get('id')} [{status}] {candidate.get('candidateType')} "
            f"created={str(candidate.get('createdAt') or '')[:19]} "
            f"run={candidate.get('sourceRunId')} confidence={candidate.get('confidence')} - {str(title)[:160]}"
        )
        stored_method = any(
            candidate.get(key)
            for key in ("failedCall", "recoveredCall", "precondition", "replayTest")
        )
        if candidate.get("candidateType") == "failure_recovery" and (
            status not in terminal or stored_method
        ):
            lines.append(
                "    method: "
                f"condition={candidate.get('condition') or 'MISSING'} | "
                f"action={candidate.get('action') or 'MISSING'} | "
                f"failed={candidate.get('failedCall') or 'MISSING'} | "
                f"recovered={candidate.get('recoveredCall') or 'MISSING'} | "
                f"precondition={candidate.get('precondition') or 'MISSING'} | "
                f"replayTest={'yes' if candidate.get('replayTest') else 'MISSING'} | "
                f"occurrenceCount={candidate.get('occurrenceCount')} | "
                f"procedureSteps={len(candidate.get('proposedProcedure') or [])}"
            )
        if status in ("rejected", "expired"):
            note = str(candidate.get("knownLimitations") or "").strip()
            lines.append(
                f"    {status}: " + (note[:200] or "no longer actionable; retained for audit")
            )
        elif status == "accepted":
            limitation = str(candidate.get("knownLimitations") or "").strip()
            if limitation:
                lines.append(f"    limitations: {limitation[:240]}")
        elif item["contractProblems"]:
            lines.append(
                "    CONTRACT VIOLATION: " + ", ".join(item["contractProblems"])
            )
    counts: dict[str, int] = {}
    for item in enriched:
        status = str(item.get("status") or "unknown")
        counts[status] = counts.get(status, 0) + 1
    from datetime import datetime, timedelta, timezone  # noqa: PLC0415

    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    stale_detected = 0
    for item in enriched:
        if str(item.get("status")) != "detected":
            continue
        stamp = str(item.get("createdAt") or "").replace("Z", "+00:00")
        try:
            created = datetime.fromisoformat(stamp)
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            if created <= cutoff:
                stale_detected += 1
        except ValueError:
            continue
    nonconforming = sum(1 for item in enriched if item.get("contractProblems"))
    full_counts: dict[str, int] = {}
    if callable(counter):
        for candidate_status in (
            "detected", "drafted", "accepted", "rejected", "expired", "retired", "proposed",
        ):
            try:
                full_counts[candidate_status] = int(counter(status=candidate_status))
            except Exception:  # noqa: BLE001
                continue
    lines.append(
        "  queue: "
        + ", ".join(f"{key} {value}" for key, value in sorted(counts.items()))
        + f"; staleDetected={stale_detected}, nonconforming={nonconforming}"
        + f", quarantinable={nonconforming}"
        + "; only `detected` rows are actionable."
    )
    if full_counts:
        lines.append(
            "  full store: "
            + ", ".join(f"{key} {value}" for key, value in sorted(full_counts.items()))
            + f"; hidden by the {MAX_LEARNING_ROWS}-row page: "
            + str(max(0, sum(full_counts.values()) - len(enriched)))
        )
    if cap_note:
        lines.append(cap_note)
    lines.append("Read-only. Candidates are inert; review/accept them in Skills \u2192 Learning Queue.")
    return "\n".join(lines), {
        "count": len(enriched), "total": total, "candidates": enriched,
    }


async def learning_candidate_validate_handler(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    """Read-only dry-run of the accept route: 404 / 409 / 422 / 200.

    Performs no write, so a chat run can prove the negative paths without an
    operator POST.
    """
    store = _learning_candidate_store(ctx)
    if store is None:
        return "The learning candidate store is not available.", {"available": False}
    candidate_id = str(args.get("candidate_id") or "").strip()
    if not candidate_id:
        return "candidate_id is required.", {"available": False}
    candidate = store.get_candidate(candidate_id)
    if candidate is None:
        return f"would return 404: no candidate {candidate_id}.", {
            "httpStatus": 404, "candidateId": candidate_id,
        }
    status = str(candidate.get("status") or "")
    if status != "detected":
        return (
            f"would return 409: only a `detected` candidate can be accepted; "
            f"this one is {status!r}.",
            {"httpStatus": 409, "candidateId": candidate_id, "status": status},
        )
    from .self_improvement.lesson_contract import candidate_problems  # noqa: PLC0415

    problems = candidate_problems(candidate)
    if problems:
        return (
            "would return 422: candidate is not falsifiable: "
            + ", ".join(problems),
            {"httpStatus": 422, "candidateId": candidate_id, "problems": problems},
        )
    return (
        "would return 200: candidate is falsifiable and could be accepted "
        "(read-only dry-run; nothing was written).",
        {"httpStatus": 200, "candidateId": candidate_id, "status": status},
    )


# ── skill_list / skill_view ─────────────────────────────────────────────────
async def skill_list_handler(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    registry = getattr(ctx, "skill_registry", None)
    if registry is None:
        return "Skills are not available in this run.", {"count": 0}
    results = registry.discover(
        query=str(args.get("query") or ""),
        category=args.get("category"),
        include_non_executable=True,
    )
    if not results:
        return "No skills match.", {"count": 0, "skills": []}
    lines = [f"{len(results)} skill(s):"]
    for skill in results:
        lines.append(
            f"  {skill['id']} (v{skill['version']}, {skill['status']}) — {skill['description'][:160]}"
        )
    return "\n".join(lines), {"count": len(results), "skills": results}


async def skill_view_handler(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    registry = getattr(ctx, "skill_registry", None)
    if registry is None:
        return "Skills are not available in this run.", {"found": False}
    skill_id = str(args.get("name") or args.get("skill_id") or "").strip()
    if not skill_id:
        return "A skill name is required.", {"found": False}
    loaded = registry.get(skill_id)
    if loaded is None:
        return f"No skill named {skill_id!r}. Use skill_list to see available skills.", {"found": False}
    manifest = loaded.manifest
    instructions = ""
    try:
        instructions = loaded.load_instructions()
    except OSError:
        instructions = ""
    body = "\n".join([
        f"# {manifest.name} ({manifest.id} v{manifest.version})",
        f"Status: {manifest.status} · Risk: {manifest.riskLevel}",
        f"Description: {manifest.description}",
        "",
        instructions or "(This skill has no prose procedure.)",
    ])
    return body, {
        "found": True,
        "skillId": manifest.id,
        "version": manifest.version,
        "status": manifest.status,
        "requiredTools": manifest.requiredTools,
        "permissions": manifest.permissions,
    }


# ── skill_invoke (controlled child-run) ─────────────────────────────────────


async def skill_invoke_handler(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    """Invoke one enabled skill as a controlled sub-run of the current run.

    The model may select from enabled skills only. Execution goes through the
    existing `execute_skill` runtime, which enforces the skill's tool allowlist
    and the default-deny permission policy in code — a skill can never gain
    arbitrary tools or widen the agent's grants through this path. The child run
    keeps `parentRunId` so its trace links to this turn.
    """
    registry = getattr(ctx, "skill_registry", None)
    if registry is None:
        return "Skills are not available in this run.", {"found": False, "invoked": False}
    skill_id = str(args.get("name") or args.get("skill_id") or "").strip()
    if not skill_id:
        return "A skill name is required.", {"found": False, "invoked": False}
    manifest = registry.manifest(skill_id)
    if manifest is None:
        return f"No skill named {skill_id!r}. Use skill_list to see available skills.", {"found": False, "invoked": False}

    from .skills.runtime import invoke_skill_from_run, list_invocable_skills

    invocable = {s["id"] for s in list_invocable_skills(registry)}
    if skill_id not in invocable:
        return (
            f"Skill {skill_id!r} is not enabled for invocation.",
            {"found": True, "invoked": False, "error": "SKILL_NOT_ENABLED"},
        )

    # Explicit, permission-checked selection: the actor must hold every
    # permission the skill declares. The runtime re-checks on execution.
    actor = Actor(id=ctx.user_id or "local", operator=False)
    decision = check_permissions(manifest.permissions, actor)
    if not decision.allowed:
        return (
            f"Invoking {skill_id!r} is not permitted: {decision.reason}",
            {"found": True, "invoked": False, "error": "PERMISSION_DENIED", "missing": list(decision.missing)},
        )

    if ctx.model_settings is None:
        return "The run has no model configuration; cannot invoke a skill.", {"found": True, "invoked": False}

    payload = args.get("input") or {}
    if not isinstance(payload, dict):
        return "input must be an object.", {"found": True, "invoked": False}

    if getattr(ctx, "tool_registry", None) is None:
        return "The run has no tool registry; cannot invoke a skill.", {"found": True, "invoked": False}

    result = await invoke_skill_from_run(
        skill_id=skill_id,
        input_data=payload,
        parent_run_id=ctx.run_id,
        tool_registry=ctx.tool_registry,
        data_bridge=ctx.data_bridge,
        memory_store=ctx.memory_store,
        skill_registry=registry,
        model_settings=ctx.model_settings,
        user_id=ctx.user_id,
        bus=getattr(ctx, "bus", None),
        emitter=ctx.emitter,
        memory_service=ctx.memory_service,
        timeout_ms=args.get("timeout_ms"),
    )
    data = {
        "found": True,
        "invoked": result.status in ("completed",),
        "skillId": result.skillId,
        "version": result.version,
        "childRunId": result.runId,
        "parentRunId": ctx.run_id,
        "status": result.status,
        "outputValidated": result.outputValidated,
        "limitations": result.limitations,
        "missingData": result.missingData,
        "error": result.error,
    }
    if result.status != "completed":
        return (
            f"Skill {skill_id!r} did not complete ({result.status}). "
            f"{(result.error or {}).get('message', '')}".strip(),
            data,
        )
    return (
        f"Skill {skill_id!r} completed (child run {result.runId}).\n\n{result.output or ''}".strip(),
        data,
    )


# ── memory providers (M8): native-first search + explicit external search ────


def _router(ctx: ToolContext) -> Any:
    router = getattr(ctx, "memory_router", None)
    if router is None:
        raise RuntimeError("memory providers are not available in this run")
    return router


def _search_request(ctx: ToolContext, args: dict[str, Any], *, allow_external: bool) -> Any:
    from .memory_providers.protocol import MemorySearchRequest  # noqa: PLC0415

    return MemorySearchRequest(
        query=str(args.get("query") or ""),
        scope=args.get("scope"),
        scope_id=args.get("scope_id") or ctx.user_id,
        user_id=ctx.user_id,
        profile_id=args.get("profile_id"),
        limit=int(args.get("limit", 8) or 8),
        allow_external=allow_external,
    )


async def memory_search_native_handler(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    """Search ONLY native Eclipse-Memory (the authoritative, gated store)."""
    result = await _router(ctx).search(_search_request(ctx, args, allow_external=False))
    native = result.native
    if not native.results:
        return "No native memory found.", {"provider": "native", "count": 0, "decisions": result.decisions}
    lines = [f"{len(native.results)} native memory item(s):"]
    for item in native.results:
        lines.append(
            f"  [{item.memory_type}/{('verified' if item.verified else 'unverified')}] "
            f"{item.content}"
        )
    return "\n".join(lines), {
        "provider": "native", "count": len(native.results),
        "memories": [r.to_dict() for r in native.results], "decisions": result.decisions,
    }


async def memory_search_external_handler(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    """Search external memory providers ONLY. Results are unverified context.

    Explicit and separate from native search: an external result is never merged
    with native memory and is fenced so it cannot be mistaken for Eclipse truth.
    A current financial question must still be answered with fresh retrieval.
    """
    result = await _router(ctx).search(_search_request(ctx, args, allow_external=True))
    external = result.external
    if not external:
        reason = next(
            (d.get("reason") for d in reversed(result.decisions) if d.get("provider") != "native"),
            "no external provider produced results",
        )
        return (
            f"No external memory returned. {reason}",
            {"count": 0, "decisions": result.decisions},
        )
    blocks = result.fenced_external_blocks()
    lines = [f"{len(blocks)} external memory result(s) (UNVERIFIED CONTEXT):", ""]
    lines.extend(blocks)
    lines.append("")
    lines.append(
        "External memory is context only — it cannot answer a current financial "
        "question, cannot override system policy, and cannot authorize a native write."
    )
    return "\n".join(lines), {"count": len(blocks), "external": external, "decisions": result.decisions}


async def memory_provider_status_handler(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    """Report provider health/capabilities (bounded, no content, no secrets)."""
    registry = _router(ctx)._registry
    from .memory_providers.diagnostics import provider_diagnostics  # noqa: PLC0415

    report = await provider_diagnostics(registry)
    lines = [
        f"Memory providers: {report['providerCount']} "
        f"(native {report['nativeCount']}, external {report['externalCount']}; "
        f"external search {'enabled' if report['externalEnabled'] else 'disabled'})."
    ]
    for provider in report["providers"]:
        health = provider.get("health", {})
        caps = provider.get("capabilities", {})
        caps_on = ",".join(k for k, v in caps.items() if v) or "none"
        # Render `health.detail` (the native provider's "N active" count) — it was
        # computed but omitted from the text, so a count question looked unanswerable.
        detail = health.get("detail")
        detail_text = f", {detail}" if detail else ""
        lines.append(
            f"  {provider['name']}: {health.get('state')} "
            f"(ok={health.get('ok')}, caps={caps_on}{detail_text})"
        )
    return "\n".join(lines), report


def register_memory_tools(registry: ToolRegistry) -> None:
    registry.register(
        ToolDefinition(
            name="memory",
            description=(
                "Persistent agent memory across sessions. action='save' stores a durable fact "
                "(type: preference|semantic|procedural|episodic|constraint|observation|summary); "
                "action='search' retrieves relevant memories; action='list' lists stored memory; "
                "action='inventory' returns whole-store counts by status/lifecycle (no content). "
                "Save only durable, reusable facts — not every sentence. User preferences are "
                "user-scoped; never turn them into universal rules."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["save", "search", "list", "inventory"], "description": "Operation to perform."},
                    "content": {"type": "string", "description": "The memory content (action=save). Write a declarative fact, not an instruction."},
                    "type": {"type": "string", "enum": ["preference", "semantic", "procedural", "episodic", "constraint", "observation", "summary"], "description": "Memory type."},
                    "scope": {"type": "string", "enum": ["user", "general", "market", "task", "conversation"], "description": "Memory scope."},
                    "scope_id": {"type": "string", "description": "Scope identifier (e.g. user id)."},
                    "subject": {"type": "string", "description": "Optional subject key (ticker, topic)."},
                    "query": {"type": "string", "description": "Search query (action=search)."},
                    "limit": {"type": "integer", "description": "Max results."},
                    "confidence": {"type": "number", "description": "0..1 confidence in the fact."},
                    "verified": {"type": "boolean", "description": "Whether the fact was verified against evidence."},
                },
                "required": ["action"],
            },
            handler=memory_handler,
            permission="read",  # memory is agent-local state, not a data mutation
            risk="low",
            timeout_ms=10_000,
        )
    )
    registry.register(
        ToolDefinition(
            name="learning_review_list",
            description=(
                "Read the automatic learning reviews — the same records the Memory → Reviews "
                "screen shows. A review is queued automatically after every completed or failed "
                "chat run and persisted after a short idle; this returns the stored records plus "
                "queue counts. Read-only; never claim a review does not exist without calling it."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "status": {"type": "string", "enum": ["queued", "running", "completed", "failed", "superseded"]},
                    "limit": {"type": "integer", "description": "Max reviews (1..50)."},
                },
            },
            handler=learning_review_list_handler,
            permission="read",
            risk="low",
            timeout_ms=10_000,
        )
    )
    registry.register(
        ToolDefinition(
            name="learning_candidate_list",
            description=(
                "Read captured learning candidates — the same records the Skills → Learning "
                "Queue screen shows. Candidates are inert lessons captured automatically at run "
                "end. Read-only: generating a draft and accepting/rejecting stay UI/operator actions."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "status": {"type": "string", "description": "Optional candidate status filter."},
                    "limit": {"type": "integer", "description": "Max candidates (1..50)."},
                },
            },
            handler=learning_candidate_list_handler,
            permission="read",
            risk="low",
            timeout_ms=10_000,
        )
    )
    registry.register(
        ToolDefinition(
            name="learning_candidate_validate",
            description=(
                "Read-only dry-run of the operator accept route for one candidate: "
                "returns the HTTP status it would produce (404 missing, 409 not "
                "detected, 422 non-falsifiable, 200 acceptable). Writes nothing."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "candidate_id": {"type": "string"},
                },
                "required": ["candidate_id"],
                "additionalProperties": False,
            },
            handler=learning_candidate_validate_handler,
            permission="read",
            risk="none",
            timeout_ms=10_000,
        )
    )
    registry.register(
        ToolDefinition(
            name="skill_list",
            description=(
                "List available skills (compact metadata) so you can decide whether to load one. "
                "Progressive disclosure step 1: this does NOT return full instructions."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Optional keyword filter."},
                    "category": {"type": "string", "description": "Optional category filter."},
                },
            },
            handler=skill_list_handler,
            permission="read",
            risk="low",
            timeout_ms=10_000,
        )
    )
    registry.register(
        ToolDefinition(
            name="skill_view",
            description=(
                "Load the full instructions (SKILL.md) for one skill by name/id. Progressive "
                "disclosure step 3: call this only after skill_list narrows the candidates."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "The skill id, e.g. 'finance.fundamental-analysis'."},
                },
                "required": ["name"],
            },
            handler=skill_view_handler,
            permission="read",
            risk="low",
            timeout_ms=10_000,
        )
    )
    registry.register(
        ToolDefinition(
            name="skill_invoke",
            description=(
                "Deliberately invoke ONE enabled skill as a controlled sub-run of this turn. "
                "Use skill_list first to find candidate skills, then pass the skill id and an "
                "`input` object matching the skill's input schema. Execution enforces the "
                "skill's tool allowlist and permissions; the child run keeps this run's id as "
                "its parent and its events/results are returned. This is the only supported way "
                "to actually RUN a skill from chat — discovery alone does not invoke it."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "The enabled skill id, e.g. 'research.planning'."},
                    "input": {"type": "object", "description": "Inputs matching the skill's input schema."},
                    "timeout_ms": {"type": "integer", "description": "Optional bounded timeout for the sub-run."},
                },
                "required": ["name"],
            },
            handler=skill_invoke_handler,
            permission="read",
            risk="low",
            timeout_ms=240_000,
        )
    )
    registry.register(
        ToolDefinition(
            name="session_search",
            description=(
                "Search PRIOR Eclipse sessions for what was discussed, decided, corrected "
                "or discovered. Use this when the user asks 'what did we decide last week?', "
                "'find the earlier run where…', 'what source did we use?'. Historical content "
                "is CONTEXT, never current financial evidence — re-retrieve current facts with "
                "finance tools. Returns bounded snippets; use session_open to expand one run."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Keywords to search for."},
                    "scope": {"type": "string", "enum": ["user", "global"], "description": "Search my sessions (default) or all."},
                    "date_from": {"type": "string", "description": "ISO date/time lower bound."},
                    "date_to": {"type": "string", "description": "ISO date/time upper bound."},
                    "run_id": {"type": "string", "description": "Restrict to one run id."},
                    "session_id": {"type": "string", "description": "Restrict to one session."},
                    "profile_id": {"type": "string", "description": "Restrict to one profile."},
                    "role": {"type": "string", "description": "Filter by role (user/assistant/tool)."},
                    "kind": {"type": "string", "description": "Filter by message kind."},
                    "market": {"type": "string", "description": "Filter by market metadata."},
                    "skill_id": {"type": "string", "description": "Filter by skill metadata."},
                    "memory_action": {"type": "string", "description": "Filter by memory action."},
                    "limit": {"type": "integer", "description": "Max results (bounded)."},
                },
                "required": ["query"],
            },
            handler=session_search_handler,
            permission="read",
            risk="low",
            timeout_ms=10_000,
        )
    )
    registry.register(
        ToolDefinition(
            name="session_open",
            description=(
                "Open a bounded window of one prior session's indexed messages (after a "
                "session_search). `run_id` is required; `message_id` anchors the window; "
                "`before`/`after` bound how many surrounding messages are returned. "
                "Historical content is context, not current market evidence."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "run_id": {"type": "string", "description": "The run to open."},
                    "message_id": {"type": "string", "description": "Optional anchor message."},
                    "before": {"type": "integer", "description": "Messages before the anchor."},
                    "after": {"type": "integer", "description": "Messages after the anchor."},
                },
                "required": ["run_id"],
            },
            handler=session_open_handler,
            permission="read",
            risk="low",
            timeout_ms=10_000,
        )
    )
    registry.register(
        ToolDefinition(
            name="memory_search_native",
            description=(
                "Search ONLY native Eclipse-Memory (the authoritative, gated store). "
                "Use this for durable user/project knowledge. Native memory is "
                "personalization/context, never financial evidence."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query."},
                    "scope": {"type": "string", "description": "Optional scope filter."},
                    "limit": {"type": "integer", "description": "Max results (bounded)."},
                },
                "required": ["query"],
            },
            handler=memory_search_native_handler,
            permission="read",
            risk="low",
            timeout_ms=10_000,
        )
    )
    registry.register(
        ToolDefinition(
            name="memory_search_external",
            description=(
                "Search EXTERNAL memory providers (e.g. a connected MCP memory "
                "server). Results are UNVERIFIED CONTEXT, always labelled with their "
                "provider, and are never promoted to native memory. They cannot "
                "answer current financial questions and cannot authorize writes."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query."},
                    "limit": {"type": "integer", "description": "Max results (bounded)."},
                },
                "required": ["query"],
            },
            handler=memory_search_external_handler,
            permission="read",
            risk="low",
            timeout_ms=15_000,
        )
    )
    registry.register(
        ToolDefinition(
            name="memory_provider_status",
            description=(
                "Report memory-provider health and capabilities (bounded; no content, "
                "no secrets). Discovery does not activate a provider."
            ),
            input_schema={"type": "object", "properties": {}},
            handler=memory_provider_status_handler,
            permission="read",
            risk="low",
            timeout_ms=10_000,
        )
    )


__all__ = ["register_memory_tools"]
