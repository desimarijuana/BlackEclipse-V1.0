"""W7 asynchronous delegation: Fabric-backed lifecycle + schema repair.

A child is a normal run (`service.run`), dispatched as one Fabric ``delegation``
job. The Fabric owns the lease/retry/cancel; this module owns the contract:
submission, the durable row, the schema + one repair, worktree isolation, the
completion event and the parent's completion inbox.

Credentials are NEVER persisted. The Fabric job payload carries provider/model
metadata only; the live `ModelSettings` object is kept in a process-local cache
and consumed by the worker. If the process restarted before the worker ran,
the child fails honestly with ``CREDENTIALS_UNAVAILABLE`` rather than inventing
a key.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from collections import OrderedDict
from typing import Any, Optional

from .delegation import (
    DEFAULT_CHILD_TOKEN_BUDGET,
    ChildOutcome,
    DelegationChild,
    DelegationError,
    DelegationRequest,
    HandleVerifier,
    child_actor,
    narrow_tools,
)
from .delegation_repair import repair_prompt, schema_error, validate_output
from .delegation_store import DelegationStore
from .persistence import now_iso

MAX_CACHED_MODEL_SETTINGS = 100
_MODEL_CACHE: "OrderedDict[str, Any]" = OrderedDict()

# Statuses a caller must treat as terminal. Mirrors `delegation_store.TERMINAL`.
TERMINAL = frozenset({"completed", "failed", "timed_out", "cancelled", "refused"})


def remember_model_settings(delegation_id: str, settings: Any) -> None:
    """Hold the live model settings for the worker without persisting them."""
    if settings is None:
        return
    _MODEL_CACHE[delegation_id] = settings
    _MODEL_CACHE.move_to_end(delegation_id)
    while len(_MODEL_CACHE) > MAX_CACHED_MODEL_SETTINGS:
        _MODEL_CACHE.popitem(last=False)


def _take_model_settings(delegation_id: str) -> Any:
    return _MODEL_CACHE.get(delegation_id)


def _forget_model_settings(delegation_id: str) -> None:
    _MODEL_CACHE.pop(delegation_id, None)


def _safe_model_metadata(settings: Any) -> dict[str, Any]:
    """Provider/model/temperature only. Never a key, base URL or token."""
    if settings is None:
        return {}
    out: dict[str, Any] = {}
    for key in ("provider", "model", "temperature", "max_tokens", "maxTokens", "context_window"):
        value = getattr(settings, key, None)
        if value is not None:
            out[key] = value
    return out


async def submit_batch(
    request: DelegationRequest,
    *,
    store: Any,
    parent_run_id: str,
    parent_agent_id: Optional[str],
    parent_allowed: Optional[set[str]],
    depth: int,
    parent_workspace_id: Optional[str],
    user_id: Optional[str],
    session_id: Optional[str],
    model_settings: Any,
    parent_autonomy: Optional[str] = None,
    delegation_id: Optional[str] = None,
) -> dict[str, Any]:
    """Validate + persist + submit children. Returns the durable handle."""
    from .fabric.tools import get_fabric_manager  # noqa: PLC0415
    from .delegation_store import new_delegation_id  # noqa: PLC0415

    if store is None:
        raise DelegationError("RUNTIME_UNAVAILABLE", "The delegation store isn't available right now.")
    fabric = get_fabric_manager()
    if fabric is None:
        raise DelegationError("RUNTIME_UNAVAILABLE", "Asynchronous delegation isn't available right now.")

    delegation_id = delegation_id or new_delegation_id()
    db = DelegationStore(store)

    # Validate every child BEFORE the batch exists, so a bad request never
    # leaves half a fan-out queued.
    for child in request.children:
        problem = schema_error(child.output_schema)
        if problem is not None:
            raise DelegationError("DELEGATION_SCHEMA_INVALID", problem)
        child_actor(_parent_actor(parent_allowed, parent_workspace_id, user_id), child)
        narrow_tools(parent_allowed, child)

    db.create_batch(
        delegation_id=delegation_id,
        parent_run_id=parent_run_id,
        parent_agent_id=parent_agent_id,
        children=request.children,
        strategy=request.strategy,
        aggregate=request.aggregate,
        title=request.title,
        token_budget=request.token_budget,
    )
    remember_model_settings(delegation_id, model_settings)

    handles: list[dict[str, Any]] = []
    for index, child in enumerate(request.children):
        metadata = _safe_model_metadata(model_settings)
        payload = {
            "delegationId": delegation_id,
            "childIndex": index,
            "parentRunId": parent_run_id,
            "parentAgentId": parent_agent_id,
            "depth": depth,
            "child": child.model_dump(by_alias=True),
            "allowedTools": sorted(parent_allowed) if parent_allowed is not None else None,
            "parentWorkspaceId": parent_workspace_id,
            "parentAutonomy": parent_autonomy,
            "userId": user_id,
            "sessionId": session_id,
            "tokenBudget": request.token_budget,
            "modelMetadata": metadata,
        }
        try:
            result = await fabric.submit(
                "delegation", payload,
                worker_kind="delegation",
                await_result=False,
                timeout_ms=900_000,
                max_attempts=1,
                correlation_id=parent_run_id,
                idempotency_key=f"delegation:{delegation_id}:{index}",
                user_id=user_id,
                session_id=session_id,
                workspace_id=parent_workspace_id,
            )
            job_id = str((result or {}).get("jobId") or "")
            db.attach_job(delegation_id, index, job_id=job_id)
            handles.append({"childIndex": index, "jobId": job_id, "status": "queued"})
        except Exception as exc:  # noqa: BLE001 - one failed submit is data
            db.complete(
                delegation_id, index, status="failed",
                reason=f"could not queue this part: {exc}"[:500],
            )
            handles.append({"childIndex": index, "jobId": None, "status": "failed"})
    return {"delegationId": delegation_id, "title": request.title, "children": handles}


def _parent_actor(allowed: Optional[set[str]], workspace_id: Optional[str], user_id: Optional[str]):
    from .skills.permissions import Actor  # noqa: PLC0415

    return Actor(id=user_id or "local", operator=False, workspace_id=workspace_id)


# ── status / result / cancel / wait ─────────────────────────────────────────


def get_status(store: Any, *, delegation_id: Optional[str] = None,
               job_id: Optional[str] = None) -> dict[str, Any]:
    db = DelegationStore(store)
    batch = db.find_by_job(job_id) if job_id else None
    if batch is None and delegation_id:
        batch = db.get(delegation_id)
    if batch is None:
        return {"found": False, "delegationId": delegation_id, "jobId": job_id}
    return batch


def get_result(store: Any, *, delegation_id: Optional[str] = None,
               job_id: Optional[str] = None) -> dict[str, Any]:
    return get_status(store, delegation_id=delegation_id, job_id=job_id)


async def cancel(store: Any, *, delegation_id: Optional[str] = None,
                 job_id: Optional[str] = None, reason: str = "") -> dict[str, Any]:
    from .fabric.tools import get_fabric_manager  # noqa: PLC0415

    db = DelegationStore(store)
    batch = db.find_by_job(job_id) if job_id else None
    if batch is None and delegation_id:
        batch = db.get(delegation_id)
    if batch is None or not batch.get("found"):
        return {"found": False, "cancelled": []}
    fabric = get_fabric_manager()
    cancelled: list[str] = []
    for child in batch.get("children", []):
        job = child.get("fabricJobId")
        if not job or child.get("status") in TERMINAL:
            continue
        try:
            if fabric is not None:
                await fabric.cancel(job)
            cancelled.append(job)
        except Exception:  # noqa: BLE001 - a cancel race is not fatal
            continue
    _forget_model_settings(str(batch.get("delegationId")))
    return {"found": True, "cancelled": cancelled, "reason": reason[:500]}


async def wait(store: Any, *, delegation_id: str, timeout_s: float = 0.0) -> dict[str, Any]:
    """Bounded wait. With `timeout_s=0` this is one read, never a sleep."""
    deadline = time.monotonic() + max(0.0, float(timeout_s))
    while True:
        batch = get_status(store, delegation_id=delegation_id)
        if not batch.get("found") or batch.get("status") in TERMINAL:
            return batch
        if time.monotonic() >= deadline:
            batch = dict(batch)
            batch["timedOut"] = True
            return batch
        await asyncio.sleep(0.25)


# ── the worker ──────────────────────────────────────────────────────────────


def _narrowed_agent(payload: dict[str, Any], child: DelegationChild) -> Any:
    from .agents import DEFAULT_AGENT_ID, get_agent  # noqa: PLC0415
    from .code import policy as code_policy  # noqa: PLC0415
    from .schemas import AgentConfig  # noqa: PLC0415

    base = get_agent(child.agent_id or payload.get("parentAgentId") or DEFAULT_AGENT_ID)
    allowed_raw = payload.get("allowedTools")
    allowed = set(allowed_raw) if isinstance(allowed_raw, list) else None
    if base.tools is None:
        # The base has no allowlist. Use the parent's resolved set when one was
        # supplied; otherwise this is the unrestricted case.
        tools: Optional[list[str]] = list(allowed) if allowed is not None else None
    else:
        tools = list(base.tools)
        if allowed is not None:
            tools = [name for name in tools if name in allowed]
    if tools is not None and child.tool_subset:
        wanted = set(child.tool_subset)
        tools = [name for name in tools if name in wanted]
    # A write is only legal inside an isolated worktree. A non-isolated child
    # keeps the read half of the surface. When the base had no allowlist we
    # cannot identify a safe subset, so a non-isolated child gets NO tools.
    if not child.isolated:
        tools = (
            [name for name in tools if name not in code_policy.WRITE_TOOLS]
            if tools is not None else []
        )
    max_steps = max(1, min(int(getattr(base, "maxSteps", 24) or 24), 24))
    return AgentConfig(
        id=base.id,
        name=base.name,
        systemPrompt=base.systemPrompt,
        tools=tools,
        maxSteps=max_steps,
        toolTimeoutMs=getattr(base, "toolTimeoutMs", 120_000),
        runTimeoutMs=min(int(getattr(base, "runTimeoutMs", 600_000) or 600_000), 600_000),
        maxToolCalls=getattr(base, "maxToolCalls", None),
        maxTokens=max(1_000, int(payload.get("tokenBudget") or DEFAULT_CHILD_TOKEN_BUDGET)),
    )


def _child_query(child: DelegationChild) -> str:
    query = child.goal
    if child.approach:
        query += f"\n\nApproach: {child.approach}"
    if child.context:
        query += f"\n\nContext:\n{child.context}"
    if child.output_schema is not None:
        query += (
            "\n\nReturn ONLY JSON that satisfies this schema (no prose, no markdown):\n"
            + json.dumps(child.output_schema, ensure_ascii=False)[:8_000]
        )
    return query


async def execute_job(service: Any, ctx: Any) -> Any:
    """Fabric ``delegation`` worker: run one child, persist, emit."""
    from .fabric.workers import WorkerOutcome  # noqa: PLC0415

    payload = dict(ctx.job.input or {})
    delegation_id = str(payload.get("delegationId") or "")
    index = int(payload.get("childIndex") or 0)
    raw_child = payload.get("child") if isinstance(payload.get("child"), dict) else {}
    try:
        child = DelegationChild(**raw_child)
    except Exception as exc:  # noqa: BLE001 - a malformed contract is a refusal
        return WorkerOutcome(status="failed", error=str(exc)[:500],
                             error_class="DELEGATION_INVALID")

    store = getattr(service, "store", None)
    if store is None:
        return WorkerOutcome(status="failed", error="the agent-memory store is unavailable",
                             error_class="RUNTIME_UNAVAILABLE")
    db = DelegationStore(store)
    existing = db.get(delegation_id)
    row = next(
        (c for c in existing.get("children", []) if int(c.get("childIndex") or 0) == index),
        None,
    )
    if row is not None and row.get("status") in TERMINAL:
        # A Fabric retry or a cancel race must not re-run a terminal child.
        return WorkerOutcome(status="succeeded", output=row.get("result") or {})
    child_run_id = f"{payload.get('parentRunId')}_dlg{index}_{uuid.uuid4().hex[:8]}"
    db.mark_running(delegation_id, index, child_run_id=child_run_id)

    settings = _take_model_settings(delegation_id)
    if settings is None:
        # Tests may pass a NON-secret model dict explicitly. Never accept a key.
        candidate = payload.get("modelSettings")
        if isinstance(candidate, dict) and not any(
            k in candidate for k in ("api_key", "apiKey", "token", "password")
        ):
            from .schemas import ModelSettings  # noqa: PLC0415

            try:
                settings = ModelSettings(**candidate)
            except Exception:  # noqa: BLE001
                settings = None
    if settings is None:
        reason = ("This part needs the run's model credentials, which are not "
                  "available after a restart. Start it again from the chat.")
        db.complete(delegation_id, index, status="failed", child_run_id=child_run_id,
                    reason=reason, result={"errorClass": "CREDENTIALS_UNAVAILABLE"})
        await _emit_completion(service, payload, index, "failed", reason=reason)
        return WorkerOutcome(status="failed", error=reason,
                             error_class="CREDENTIALS_UNAVAILABLE")
    # A part may name another model on the SAME provider and its own sampling
    # temperature. The provider/credential never change.
    try:
        updates: dict[str, Any] = {}
        if child.model and getattr(settings, "model", None) != child.model:
            updates["model"] = child.model
        if child.temperature is not None:
            updates["temperature"] = child.temperature
        if updates:
            settings = settings.model_copy(update=updates)
    except Exception:  # noqa: BLE001 - keep the parent's settings
        pass

    workspace = None
    scratch_token: Optional[str] = None
    if child.isolated:
        try:
            from .code import worktree  # noqa: PLC0415

            workspace = worktree.allocate()
            scratch_token = worktree.mint_scratch_token(workspace.root)
        except Exception as exc:  # noqa: BLE001 - isolation is a hard requirement
            reason = f"This part needs an isolated workspace, which is unavailable: {exc}"[:500]
            db.complete(delegation_id, index, status="refused", child_run_id=child_run_id,
                        reason=reason, result={"errorClass": "WORKTREE_UNAVAILABLE"})
            await _emit_completion(service, payload, index, "refused", reason=reason)
            return WorkerOutcome(status="failed", error=reason,
                                 error_class="WORKTREE_UNAVAILABLE")

    try:
        from .schemas import RunInput, RunRequest  # noqa: PLC0415

        request = RunRequest(
            runId=child_run_id,
            input=RunInput(
                query=_child_query(child)[:100_000],
                context={
                    "source": "delegation",
                    "delegationId": delegation_id,
                    "delegationDepth": int(payload.get("depth") or 0) + 1,
                },
            ),
            agent=_narrowed_agent(payload, child),
            modelSettings=settings,
            parentRunId=payload.get("parentRunId"),
            userId=payload.get("userId"),
            sessionId=payload.get("sessionId"),
            workspaceId=(workspace.id if workspace is not None else child.workspace_id),
            workspaceScratchToken=scratch_token,
            # A child may hold the parent's autonomy profile only when it is
            # bound to a workspace; the profile still narrows through the tool
            # allowlist, and `operator` is never inherited.
            autonomy=(
                payload.get("parentAutonomy")
                if (workspace is not None or child.workspace_id) else None
            ),
            callbackBaseUrl=os.environ.get("HARNESS_CALLBACK_URL", "http://127.0.0.1"),
        )
        result = await service.run(request)
        dumped = result.model_dump() if hasattr(result, "model_dump") else dict(result)
        error = dumped.get("error")
        status = "completed" if dumped.get("status") == "completed" else "failed"
        raw = str(dumped.get("output") or "")
        tokens = max(0, int(dumped.get("totalTokens") or 0))
        reason = error.get("message") if isinstance(error, dict) else None
    except asyncio.CancelledError:
        db.complete(delegation_id, index, status="cancelled", child_run_id=child_run_id,
                    reason="This part was stopped.")
        await _emit_completion(service, payload, index, "cancelled",
                               reason="This part was stopped.")
        raise
    except Exception as exc:  # noqa: BLE001 - a child failure is data
        db.complete(delegation_id, index, status="failed", child_run_id=child_run_id,
                    reason=str(exc)[:500])
        await _emit_completion(service, payload, index, "failed", reason=str(exc)[:500])
        return WorkerOutcome(status="failed", error=str(exc)[:2_000],
                             error_class="DELEGATION_CHILD_FAILED")

    validated = validate_output(raw, child.output_schema)
    repair_run_id: Optional[str] = None
    repair_attempted = False
    if validated["valid"] is False and child.schema_repair and child.output_schema is not None:
        repair_attempted = True
        repair_run_id = f"{child_run_id}_repair"
        try:
            from .schemas import RunInput, RunRequest  # noqa: PLC0415

            repair_request = RunRequest(
                runId=repair_run_id,
                input=RunInput(
                    query=repair_prompt(child.output_schema, raw, validated["errors"]),
                    context={"source": "delegation_repair", "delegationId": delegation_id},
                ),
                agent=_repair_agent(payload, child),
                modelSettings=settings,
                parentRunId=child_run_id,
                userId=payload.get("userId"),
                sessionId=payload.get("sessionId"),
                callbackBaseUrl=os.environ.get("HARNESS_CALLBACK_URL", "http://127.0.0.1"),
            )
            repaired = await service.run(repair_request)
            repaired_dump = repaired.model_dump() if hasattr(repaired, "model_dump") else dict(repaired)
            if repaired_dump.get("status") == "completed":
                second = validate_output(str(repaired_dump.get("output") or ""), child.output_schema)
                if second["valid"] is True:
                    validated = second
                else:
                    validated = second
        except Exception as exc:  # noqa: BLE001 - a repair failure preserves the raw
            validated = {
                "valid": False,
                "text": raw,
                "errors": [*validated["errors"], f"repair failed: {exc}"[:500]],
            }

    diff = None
    if workspace is not None:
        try:
            from .code import worktree  # noqa: PLC0415

            diff = worktree.diff(workspace.id, strategy=workspace.strategy)
            diff = {k: diff.get(k) for k in (
                "available", "strategy", "base", "digest", "filesChanged",
                "additions", "deletions",
            )}
            diff["workspaceId"] = workspace.id
        except Exception:  # noqa: BLE001 - a missing diff never invents one
            diff = {"workspaceId": workspace.id, "available": False}

    outcome = {
        "status": status,
        "runId": child_run_id,
        "summary": validated["text"],
        "rawSummary": raw,
        "tokens": tokens,
        "schemaValid": validated["valid"],
        "schemaErrors": validated["errors"],
        "repairAttempted": repair_attempted,
        "repairRunId": repair_run_id,
        "workspaceId": workspace.id if workspace is not None else child.workspace_id,
        "diff": diff,
        "reason": reason,
        "handles": [{"kind": "run_id", "value": child_run_id}],
    }
    db.complete(
        delegation_id, index, status=status, child_run_id=child_run_id,
        raw_summary=raw, summary=validated["text"],
        schema_valid=validated["valid"], schema_errors=validated["errors"],
        tokens=tokens, reason=reason, result=outcome,
    )
    await _emit_completion(service, payload, index, status, reason=reason, outcome=outcome)
    return WorkerOutcome(
        status="succeeded" if status == "completed" else "failed",
        output=outcome,
        error=reason,
        error_class="DELEGATION_CHILD_FAILED" if status != "completed" else "",
        metrics={"runId": child_run_id, "totalTokens": tokens},
    )


def _repair_agent(payload: dict[str, Any], child: DelegationChild) -> Any:
    from .agents import DEFAULT_AGENT_ID, get_agent  # noqa: PLC0415
    from .schemas import AgentConfig  # noqa: PLC0415

    base = get_agent(child.agent_id or payload.get("parentAgentId") or DEFAULT_AGENT_ID)
    return AgentConfig(
        id=base.id,
        name=base.name,
        systemPrompt=(
            base.systemPrompt
            + "\n\n## Schema repair\nReturn ONLY corrected JSON. Do not call tools."
        ),
        tools=[],
        maxSteps=1,
        toolTimeoutMs=1_000,
        runTimeoutMs=120_000,
    )


async def _emit_completion(service: Any, payload: dict[str, Any], index: int,
                           status: str, *, reason: Optional[str] = None,
                           outcome: Optional[dict[str, Any]] = None) -> None:
    parent = str(payload.get("parentRunId") or "")
    if not parent:
        return
    try:
        from .events import RunEmitter  # noqa: PLC0415

        emitter = RunEmitter(parent, service.store, getattr(service, "bus", None))
        await emitter.emit("delegation.child.completed", {
            "delegationId": payload.get("delegationId"),
            "childIndex": index,
            "status": status,
            "tokens": int((outcome or {}).get("tokens") or 0),
            "schemaValid": (outcome or {}).get("schemaValid"),
            **({"reason": reason} if reason else {}),
        })
        db = DelegationStore(service.store)
        batch = db.get(str(payload.get("delegationId")))
        if batch.get("found") and batch.get("status") in TERMINAL:
            await emitter.emit("delegation.completed", {
                "delegationId": payload.get("delegationId"),
                "status": batch.get("status"),
                "children": len(batch.get("children") or []),
            })
            _forget_model_settings(str(payload.get("delegationId")))
    except Exception:  # noqa: BLE001 - an event must never change the outcome
        pass


# ── parent inbox ────────────────────────────────────────────────────────────


def peek_inbox(store: Any, parent_run_id: str) -> tuple[str, list[tuple[str, int]]]:
    """A bounded text block + the (delegationId, childIndex) rows it names."""
    db = DelegationStore(store)
    rows = db.inbox(parent_run_id)
    if not rows:
        return "", []
    keys: list[tuple[str, int]] = []
    lines = ["<delegated-results>", "Delegated work finished while you were busy."]
    for row in rows[:8]:
        deleg = str(row.get("id"))
        index = int(row.get("childIndex") or 0)
        keys.append((deleg, index))
        summary = str(row.get("summary") or row.get("rawSummary") or "").strip().replace("\n", " ")
        if len(summary) > 500:
            summary = summary[:500].rsplit(" ", 1)[0] + "…"
        schema = row.get("schemaValid")
        shape = "" if schema is None else (" [schema ok]" if schema else " [schema invalid]")
        lines.append(f"- part {index + 1}: {row.get('status')}{shape} — {summary or '(no output)'}")
    if len(rows) > 8:
        lines.append(f"- …and {len(rows) - 8} more part(s).")
    lines.append("Use delegate_result for the full typed result. Do not re-run these parts.")
    lines.append("</delegated-results>")
    return "\n".join(lines), keys


def mark_inbox_consumed(store: Any, keys: list[tuple[str, int]]) -> None:
    db = DelegationStore(store)
    grouped: dict[str, list[int]] = {}
    for delegation_id, index in keys:
        grouped.setdefault(delegation_id, []).append(index)
    for delegation_id, indexes in grouped.items():
        db.mark_consumed(delegation_id, indexes)


# ── tools-facing helpers ────────────────────────────────────────────────────


def typed_outcome(row: dict[str, Any]) -> ChildOutcome:
    from .delegation import VerifiableHandle  # noqa: PLC0415

    result = row.get("result") or {}
    handles = [
        VerifiableHandle(kind=str(h.get("kind")), value=str(h.get("value")))
        for h in (row.get("result", {}).get("handles") or result.get("handles") or [])
        if isinstance(h, dict) and h.get("kind") and h.get("value")
    ]
    return ChildOutcome(
        child_index=int(row.get("childIndex") or 0),
        run_id=row.get("childRunId") or result.get("runId"),
        status=str(row.get("status") or "failed"),  # type: ignore[arg-type]
        summary=str(row.get("summary") or ""),
        raw_summary=str(row.get("rawSummary") or ""),
        schema_valid=row.get("schemaValid"),
        schema_errors=list(row.get("schemaErrors") or []),
        repair_attempted=bool(result.get("repairAttempted")),
        repair_run_id=result.get("repairRunId"),
        workspace_id=result.get("workspaceId"),
        diff=result.get("diff"),
        tokens=int(row.get("tokens") or 0),
        goal=str(row.get("goal") or ""),
        approach=row.get("approach"),
        model=row.get("model"),
        handles=handles,
        reason=row.get("reason"),
    )


__all__ = [
    "TERMINAL",
    "bind_store",
    "cancel",
    "execute_job",
    "get_result",
    "get_status",
    "mark_inbox_consumed",
    "peek_inbox",
    "remember_model_settings",
    "submit_batch",
    "typed_outcome",
    "wait",
]
