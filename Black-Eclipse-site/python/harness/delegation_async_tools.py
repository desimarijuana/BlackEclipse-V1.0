"""W7 async delegation tools.

`delegate` remains the synchronous, predictable fan-out. These tools add the
durable lifecycle on top of the Execution Fabric: submit now, continue, then
read/cancel/steer later. They never execute a model call themselves.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from .config.flags import get_bool
from .delegation import (
    DEPTH_EXCEEDED,
    MAX_CHILDREN,
    MAX_DEPTH,
    WIDTH_EXCEEDED,
    DelegationChild,
    DelegationError,
    DelegationRequest,
)
from .delegation_lifecycle import (
    cancel,
    get_result,
    get_status,
    submit_batch,
    typed_outcome,
    wait,
)
from .delegation_store import DelegationStore
from .delegation_tools import DelegateInput, delegate_schema
from .tools import ToolContext, ToolDefinition


def _refusal(code: str, reason: str) -> tuple[str, Any]:
    return f"REFUSED ({code}): {reason}", {"status": "refused", "code": code, "reason": reason}


def _request_from_input(model: DelegateInput) -> DelegationRequest:
    if model.strategy not in ("split", "best_of"):
        raise DelegationError("DELEGATION_INVALID", "That isn't a kind of delegation Eclipse knows.")
    if model.strategy == "best_of":
        if model.children:
            raise DelegationError(
                "DELEGATION_INVALID",
                "For a best-of run, give one goal and a count, not separate parts.",
            )
        goal = (model.goal or "").strip()
        if not goal:
            raise DelegationError("DELEGATION_INVALID",
                                  "A best-of run needs the one task every attempt should try.")
        count = model.count or 3
        if count < 2:
            raise DelegationError(WIDTH_EXCEEDED, "A best-of run needs at least two attempts to compare.")
        if count > MAX_CHILDREN:
            raise DelegationError(WIDTH_EXCEEDED,
                                  f"This asks for {count} at once; the most Eclipse does is {MAX_CHILDREN}.")
        agent_ids = [a for a in (model.agent_ids or []) if a]
        models = [m for m in (model.models or []) if m]
        temperatures = [t for t in (model.temperatures or []) if isinstance(t, (int, float))]
        approaches = [t.strip()[:300] for t in (model.approaches or []) if t and t.strip()]
        contexts = [t.strip()[:8000] for t in (model.contexts or []) if t and t.strip()]
        parts = [
            DelegationChild(
                goal=goal,
                approach=approaches[i] if i < len(approaches) else None,
                context=contexts[i] if i < len(contexts) else "",
                agent_id=agent_ids[i] if i < len(agent_ids) else None,
                model=models[i] if i < len(models) else None,
                temperature=temperatures[i] if i < len(temperatures) else None,
                output_schema=model.output_schema,
                schema_repair=model.schema_repair,
                isolated=model.isolated,
            )
            for i in range(count)
        ]
        title = model.title or goal
    else:
        if len(model.children) > MAX_CHILDREN:
            raise DelegationError(WIDTH_EXCEEDED,
                                  f"This asks for {len(model.children)} at once; the most Eclipse does is {MAX_CHILDREN}.")
        if not model.children:
            raise DelegationError("DELEGATION_INVALID", "Give at least one part to look at.")
        parts = [
            DelegationChild(
                goal=c.goal, context=c.context, approach=c.approach,
                agent_id=c.agent_id, model=c.model, temperature=c.temperature,
                tool_subset=c.tool_subset, workspace_id=c.workspace_id,
                output_schema=c.output_schema, schema_repair=c.schema_repair,
                isolated=c.isolated,
            )
            for c in model.children
        ]
        title = model.title
    return DelegationRequest(
        children=parts,
        aggregate=model.aggregate,  # type: ignore[arg-type]
        strategy=model.strategy,  # type: ignore[arg-type]
        title=title,
    )


def _resolve_id(args: dict[str, Any], ctx: ToolContext) -> Optional[str]:
    delegation_id = str(args.get("delegationId") or "").strip()
    job_id = str(args.get("jobId") or "").strip()
    store = getattr(ctx, "memory_store", None)
    if store is None:
        return delegation_id or None
    if delegation_id:
        return delegation_id
    if job_id:
        batch = DelegationStore(store).find_by_job(job_id)
        if batch:
            return str(batch.get("delegationId"))
    return None


async def delegate_async_handler(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    if not get_bool("HARNESS_ASYNC_DELEGATION"):
        return _refusal(
            "ASYNC_DELEGATION_DISABLED",
            "Background delegation is off. Use `delegate` (it waits for the parts) or enable "
            "HARNESS_ASYNC_DELEGATION.",
        )
    try:
        model = DelegateInput(**{k: v for k, v in args.items() if v is not None})
        request = _request_from_input(model)
    except DelegationError as exc:
        return _refusal(exc.code, exc.reason)
    except Exception as exc:  # noqa: BLE001 - a malformed request is a refusal
        return _refusal("DELEGATION_INVALID", str(exc))
    depth = int(getattr(ctx, "delegation_depth", 0) or 0)
    if depth >= MAX_DEPTH:
        return _refusal(DEPTH_EXCEEDED, "This work is nested too deeply for Eclipse to keep it straight.")
    workspace = getattr(getattr(ctx, "workspace", None), "id", None)
    try:
        result = await submit_batch(
            request,
            store=getattr(ctx, "memory_store", None),
            parent_run_id=ctx.run_id,
            parent_agent_id=str(getattr(getattr(ctx, "agent", None), "id", "") or "") or None,
            parent_allowed=getattr(ctx, "allowed", None),
            depth=depth,
            parent_workspace_id=workspace,
            user_id=ctx.user_id,
            session_id=getattr(ctx, "session_id", None),
            model_settings=getattr(ctx, "model_settings", None),
            parent_autonomy=getattr(ctx, "autonomy", None),
        )
    except DelegationError as exc:
        return _refusal(exc.code, exc.reason)
    # Draw the rows immediately (the same event the synchronous fan-out uses),
    # then let the worker's durable `delegation.child.completed` update them.
    try:
        from .code.tools import emit_code_event  # noqa: PLC0415

        await emit_code_event(ctx, "delegation.started", {
            "delegationId": result["delegationId"],
            "children": len(request.children),
            "aggregate": request.aggregate,
            "strategy": request.strategy,
            "title": request.title,
            "agents": [
                {
                    "childIndex": i,
                    "goal": child.goal[:200],
                    **({"agentId": child.agent_id} if child.agent_id else {}),
                    **({"model": child.model} if child.model else {}),
                    **({"approach": child.approach} if child.approach else {}),
                }
                for i, child in enumerate(request.children)
            ],
        })
    except Exception:  # noqa: BLE001 - a display event must not fail the submit
        pass
    ids = [c["jobId"] for c in result["children"] if c.get("jobId")]
    text = (
        f"Started {len(result['children'])} delegated part(s) in the background.\n"
        f"Delegation: {result['delegationId']}\n"
        f"Jobs: {', '.join(ids) if ids else '(none queued)'}\n"
        "You can keep working. Use delegate_status or delegate_result when you need them."
    )
    return text, {"status": "queued", **result}


async def delegate_status_handler(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    store = getattr(ctx, "memory_store", None)
    if store is None:
        return _refusal("RUNTIME_UNAVAILABLE", "The delegation store isn't available.")
    batch = get_status(
        store,
        delegation_id=str(args.get("delegationId") or "") or None,
        job_id=str(args.get("jobId") or "") or None,
    )
    if not batch.get("found"):
        return "No such delegation is on record.", {"status": "not_found", **batch}
    lines = [f"Delegation {batch.get('delegationId')} — {batch.get('status')}"]
    for child in batch.get("children", []):
        lines.append(
            f"- part {int(child.get('childIndex') or 0) + 1}: {child.get('status')}"
            + (f" — {child.get('reason')}" if child.get("reason") else "")
        )
    return "\n".join(lines), {"status": "ok", **batch}


async def delegate_result_handler(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    store = getattr(ctx, "memory_store", None)
    if store is None:
        return _refusal("RUNTIME_UNAVAILABLE", "The delegation store isn't available.")
    batch = get_result(
        store,
        delegation_id=str(args.get("delegationId") or "") or None,
        job_id=str(args.get("jobId") or "") or None,
    )
    if not batch.get("found"):
        return "No such delegation is on record.", {"status": "not_found", **batch}
    outcomes = [typed_outcome(row) for row in batch.get("children", [])]
    lines = [f"Delegation {batch.get('delegationId')} — {batch.get('status')}"]
    for outcome in outcomes:
        label = f"part {outcome.child_index + 1}: {outcome.status}"
        if outcome.schema_valid is False:
            label += " (schema invalid)"
        summary = outcome.summary.strip()
        lines.append(f"- {label} — {summary[:600] if summary else '(no output)'}")
    data = {
        "status": "ok",
        **batch,
        "outcomes": [o.model_dump(by_alias=True) for o in outcomes],
    }
    return "\n".join(lines), data


async def delegate_cancel_handler(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    store = getattr(ctx, "memory_store", None)
    if store is None:
        return _refusal("RUNTIME_UNAVAILABLE", "The delegation store isn't available.")
    result = await cancel(
        store,
        delegation_id=str(args.get("delegationId") or "") or None,
        job_id=str(args.get("jobId") or "") or None,
        reason=str(args.get("reason") or ""),
    )
    if not result.get("found"):
        return "No such delegation is on record.", {"status": "not_found", **result}
    return (
        f"Asked {len(result.get('cancelled') or [])} part(s) to stop. "
        "Each one stops at its next safe boundary.",
        {"status": "cancelling", **result},
    )


async def delegate_steer_handler(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    if not get_bool("HARNESS_ASYNC_DELEGATION"):
        return _refusal("ASYNC_DELEGATION_DISABLED", "Background delegation is off.")
    store = getattr(ctx, "memory_store", None)
    if store is None:
        return _refusal("RUNTIME_UNAVAILABLE", "The delegation store isn't available.")
    delegation_id = _resolve_id(args, ctx)
    message = str(args.get("message") or "").strip()
    if not delegation_id:
        return _refusal("DELEGATION_INVALID", "Name the delegation (or one of its jobs) to steer.")
    if not message:
        return _refusal("DELEGATION_INVALID", "A steering message must not be empty.")
    db = DelegationStore(store)
    batch = db.get(delegation_id)
    if not batch.get("found"):
        return "No such delegation is on record.", {"status": "not_found"}
    if batch.get("status") in ("completed", "failed", "cancelled", "refused"):
        return "That delegation has already finished; there is nothing to steer.", {
            "status": "finished", "delegationId": delegation_id,
        }
    try:
        from .config.flags import get_int  # noqa: PLC0415

        seq = db.append_steer(
            delegation_id, message, max_pending=max(1, get_int("HARNESS_DELEGATION_STEER_MAX")),
        )
    except ValueError as exc:
        return _refusal("DELEGATION_STEER_LIMIT", str(exc))
    return (
        f"Added guidance to delegation {delegation_id} (message {seq}). "
        "It will be read at the next step boundary, not mid-tool.",
        {"status": "queued", "delegationId": delegation_id, "seq": seq},
    )


async def delegate_wait_handler(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    store = getattr(ctx, "memory_store", None)
    delegation_id = _resolve_id(args, ctx)
    if store is None or not delegation_id:
        return _refusal("DELEGATION_INVALID", "Name the delegation to wait for.")
    timeout_s = float(args.get("timeoutS") or args.get("timeout_s") or 0)
    batch = await wait(store, delegation_id=delegation_id, timeout_s=timeout_s)
    text, data = await delegate_status_handler({"delegationId": delegation_id}, ctx)
    return text, {**data, "timedOut": bool(batch.get("timedOut"))}


_STATUS_SCHEMA = {
    "type": "object",
    "properties": {
        "delegationId": {"type": "string"},
        "jobId": {"type": "string"},
    },
    "additionalProperties": False,
}


def register_delegation_async_tools(registry: Any) -> list[str]:
    definitions = [
        ToolDefinition(
            name="delegate_async",
            description=(
                "Start 1-4 independent parts in the BACKGROUND over the durable Execution "
                "Fabric and keep working. Returns a delegation id + job ids. Use "
                "delegate_status/result/cancel/steer to manage them. `delegate` is the "
                "synchronous variant."
            ),
            input_schema=delegate_schema(),
            handler=delegate_async_handler,
            permission="read", risk="low", timeout_ms=30_000,
        ),
        ToolDefinition(
            name="delegate_status",
            description="Read the durable status/progress of a background delegation. Read-only.",
            input_schema=_STATUS_SCHEMA,
            handler=delegate_status_handler,
            permission="read", risk="none", timeout_ms=10_000,
        ),
        ToolDefinition(
            name="delegate_result",
            description=(
                "Read a background delegation's typed results, schema validity and diff "
                "handles. Idempotent; never re-runs a child."
            ),
            input_schema=_STATUS_SCHEMA,
            handler=delegate_result_handler,
            permission="read", risk="none", timeout_ms=10_000,
        ),
        ToolDefinition(
            name="delegate_cancel",
            description="Ask a background delegation (or one job) to stop at its next safe boundary.",
            input_schema={
                "type": "object",
                "properties": {
                    "delegationId": {"type": "string"},
                    "jobId": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "additionalProperties": False,
            },
            handler=delegate_cancel_handler,
            permission="read", risk="low", timeout_ms=15_000,
        ),
        ToolDefinition(
            name="delegate_steer",
            description=(
                "Add guidance to a RUNNING background part. It is delivered at the child's "
                "next step boundary, never in the middle of a tool call."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "delegationId": {"type": "string"},
                    "jobId": {"type": "string"},
                    "message": {"type": "string"},
                },
                "required": ["message"],
                "additionalProperties": False,
            },
            handler=delegate_steer_handler,
            permission="read", risk="low", timeout_ms=10_000,
        ),
        ToolDefinition(
            name="delegate_wait",
            description="Wait up to `timeoutS` for a delegation to finish, then return its status.",
            input_schema={
                "type": "object",
                "properties": {
                    "delegationId": {"type": "string"},
                    "jobId": {"type": "string"},
                    "timeoutS": {"type": "number", "minimum": 0, "maximum": 300},
                },
                "additionalProperties": False,
            },
            handler=delegate_wait_handler,
            permission="read", risk="none", timeout_ms=310_000,
        ),
    ]
    added: list[str] = []
    for tool in definitions:
        try:
            registry.register(tool)
            added.append(tool.name)
        except ValueError:
            continue
    return added


__all__ = ["register_delegation_async_tools"]
