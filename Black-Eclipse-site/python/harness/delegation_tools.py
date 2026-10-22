"""The `delegate` tool handler (Phase 7), extracted from `code/tools.py`.

Registration lives in `code/tools.register_code_tools`; the handler lives here so
the already-large `code/tools.py` stays under its size ceiling. A child IS a
normal run (`execute_run` with a `parentRunId`) — this module owns only the tool
surface: the caps, the narrowing and the aggregation it delegates to
`harness.delegation`.
"""

from __future__ import annotations

import os
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from .delegation import (
    BUDGET_EXHAUSTED,
    DEPTH_EXCEEDED,
    MAX_CHILDREN,
    MAX_DEPTH,
    SANDBOX_UNAVAILABLE,
    WIDTH_EXCEEDED,
    DelegationChild,
    DelegationError,
    DelegationRequest,
    HandleVerifier,
    run_delegation,
)
from .tools import ToolContext


class DelegateChildModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    goal: str = Field(..., min_length=1, max_length=2000)
    context: str = Field("", max_length=8000)
    agent_id: Optional[str] = Field(default=None, max_length=64)  # noqa: N815
    tool_subset: Optional[list[str]] = Field(default=None, max_length=64)  # noqa: N815
    workspace_id: Optional[str] = Field(default=None, max_length=128)  # noqa: N815


class DelegateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    children: list[DelegateChildModel] = Field(..., min_length=1, max_length=8)
    aggregate: str = Field("list", max_length=16)


def delegate_schema() -> dict[str, Any]:
    child = {
        "type": "object",
        "properties": {
            "goal": {"type": "string", "description": "The one independent sub-question for this part."},
            "context": {"type": "string", "description": "Background ONLY this part needs."},
            "agent_id": {"type": "string", "description": "Reserved; defaults to this run's agent."},
            "tool_subset": {"type": "array", "items": {"type": "string"}, "description": "Reserved; a subset of this task's tools (narrowing only)."},
            "workspace_id": {"type": "string", "description": "A folder this task already has, for a part that writes."},
        },
        "required": ["goal"],
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {
            "children": {"type": "array", "description": "The independent sub-questions to work on at once (1-4).", "items": child},
            "aggregate": {"type": "string", "enum": ["list", "compare", "merge_claims"], "description": "How to combine the results."},
        },
        "required": ["children"],
        "additionalProperties": False,
    }


def _present(args: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in args.items() if v is not None}


def _verifier(ctx: ToolContext) -> HandleVerifier:
    """A handle verifier bound to THIS run's real state (no globals)."""
    ledger = getattr(ctx, "code_ledger", None)
    check_ids = {r.command_execution_id for r in ledger.records} if ledger is not None else set()

    def _run_exists(rid: str) -> bool:
        store = getattr(ctx, "memory_store", None)
        try:
            return bool(store and store.get_run(rid))
        except Exception:  # noqa: BLE001
            return False

    return HandleVerifier(
        run_exists=_run_exists,
        ledger_has=lambda cid: cid in check_ids,
        artifact_exists=bool,
    )


def _refusal(code: str, reason: str) -> tuple[str, Any]:
    return f"REFUSED ({code}): {reason}", {"status": "refused", "code": code, "reason": reason}


async def delegate_handler(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    """Fan out bounded child runs and aggregate only what each proved."""
    from .agents import DEFAULT_AGENT_ID  # noqa: PLC0415
    from .code.tools import emit_code_event  # noqa: PLC0415
    from .graph import execute_run  # noqa: PLC0415
    from .schemas import RunInput, RunRequest  # noqa: PLC0415
    from .skills.permissions import Actor  # noqa: PLC0415

    model = DelegateInput(**_present(args))
    if len(model.children) > MAX_CHILDREN:
        return _refusal(WIDTH_EXCEEDED,
                        f"This asks for {len(model.children)} at once; the most Eclipse does is {MAX_CHILDREN}.")

    depth = int(getattr(ctx, "delegation_depth", 0) or 0)
    if depth >= MAX_DEPTH:
        return _refusal(DEPTH_EXCEEDED, "This work is nested too deeply for Eclipse to keep it straight.")

    # A writing child needs the isolation primitive; refuse rather than run it
    # outside isolation (the Phase 3 rule: a missing primitive refuses honestly).
    if any(c.workspace_id for c in model.children):
        try:
            from .code import sandbox as _sandbox  # noqa: PLC0415

            if not _sandbox.backend_name():
                raise RuntimeError("no isolation available")
        except Exception:  # noqa: BLE001
            return _refusal(
                SANDBOX_UNAVAILABLE,
                "That part needs to make changes, which isn't available on this computer right now.",
            )

    parent_actor = Actor(
        id=ctx.user_id or "local",
        operator=False,
        workspace_id=getattr(getattr(ctx, "workspace", None), "id", None),
        autonomy=getattr(ctx, "autonomy", None),
    )
    try:
        request = DelegationRequest(
            children=[
                DelegationChild(goal=c.goal, context=c.context, agent_id=c.agent_id,
                                tool_subset=c.tool_subset, workspace_id=c.workspace_id)
                for c in model.children
            ],
            aggregate=model.aggregate,  # type: ignore[arg-type]
        )
    except Exception as exc:  # noqa: BLE001
        return _refusal("DELEGATION_INVALID", str(exc))

    async def _run_child(child: DelegationChild, child_run_id: str, allowed: Any, actor: Actor) -> Any:
        query = child.goal if not child.context else f"{child.goal}\n\nContext:\n{child.context}"
        # A surface may give delegated children their own bounded prompt. The
        # child keeps its OWN agent preset and its narrowed allowlist; the
        # surface only appends prompt evidence, never a tool or a permission.
        child_agent = None
        subagent_prompt = str(
            getattr(getattr(ctx, "agent", None), "subagentPrompt", "") or ""
        ).strip()
        if subagent_prompt:
            from .agents import get_agent  # noqa: PLC0415
            from .schemas import AgentConfig  # noqa: PLC0415

            base = get_agent(child.agent_id or DEFAULT_AGENT_ID)
            # The child's tools are the NARROWED set the delegation already
            # computed (the parent's allowlist, or the child's request within it).
            tool_names = [
                name for name in (base.tools or [])
                if allowed is None or name in allowed
            ]
            child_agent = AgentConfig(
                id=base.id,
                name=base.name,
                systemPrompt=(
                    f"{base.systemPrompt}\n\n## Delegated work\n{subagent_prompt}"
                ),
                tools=tool_names,
                maxSteps=base.maxSteps,
                maxToolCalls=base.maxToolCalls,
            )
        child_request = RunRequest(
            runId=child_run_id,
            # Carry the depth so a grandchild cannot reset it to 0 and bypass MAX_DEPTH.
            input=RunInput(query=query[:4000], context={"delegationDepth": depth + 1}),
            agentId=child.agent_id or DEFAULT_AGENT_ID,
            **({"agent": child_agent} if child_agent is not None else {}),
            modelSettings=ctx.model_settings,
            parentRunId=ctx.run_id,
            autonomy=getattr(ctx, "autonomy", None) if child.workspace_id else None,
            workspaceId=child.workspace_id,
            callbackBaseUrl=os.environ.get("HARNESS_CALLBACK_URL", "http://127.0.0.1"),
        )
        result = await execute_run(
            child_request, ctx.tool_registry, ctx.data_bridge, ctx.memory_store, getattr(ctx, "bus", None),
            retrieval_cache=getattr(ctx, "retrieval_cache", None),
            memory_service=getattr(ctx, "memory_service", None),
            skill_registry=getattr(ctx, "skill_registry", None),
            memory_router=getattr(ctx, "memory_router", None),
            mcp_manager=getattr(ctx, "mcp_manager", None),
            code_store=getattr(ctx, "code_store", None),
        )
        dumped = result.model_dump() if hasattr(result, "model_dump") else dict(result)
        error = dumped.get("error")
        return {
            "status": "completed" if dumped.get("status") == "completed" else "failed",
            "runId": dumped.get("runId", child_run_id),
            "summary": dumped.get("output") or "",
            # A run_id handle lets the parent re-check existence. A check-claim
            # additionally needs a real ledger row (partition_claims enforces it).
            "handles": [{"kind": "run_id", "value": dumped.get("runId", child_run_id)}],
            "reason": error.get("message") if isinstance(error, dict) else None,
        }

    async def _on_event(event_type: str, data: dict[str, Any]) -> None:
        await emit_code_event(ctx, event_type, data)

    try:
        result = await run_delegation(
            request,
            parent_run_id=ctx.run_id,
            parent_actor=parent_actor,
            parent_allowed=getattr(ctx, "allowed", None),
            depth=depth,
            run_child=_run_child,
            verifier=_verifier(ctx),
            on_event=_on_event,
        )
    except DelegationError as exc:
        return _refusal(exc.code, exc.reason)

    _record_blob(ctx, result.to_blob())
    done = sum(1 for o in result.outcomes if o.status == "completed")
    text = f"I looked at {done} of {len(result.outcomes)}.\n\n{result.aggregate}"
    data = {
        "status": "ok",
        "delegationId": result.delegationId,
        "completed": done,
        "total": len(result.outcomes),
        "droppedClaims": len(result.droppedClaims),
        "outcomes": [
            {"childIndex": o.child_index, "runId": o.run_id, "status": o.status,
             "reason": o.reason, "claimed": o.claimed, "dropped": o.dropped}
            for o in result.outcomes
        ],
        "budget": result.budget.model_dump(by_alias=True),
    }
    return text, data


def _record_blob(ctx: ToolContext, blob: dict[str, Any]) -> None:
    """Persist the fan-out on the parent run's additive `delegation` column.

    Owned HERE (like `run_lineage.py` owns its own columns) rather than in the
    ratcheted `persistence.py`. Old-row-safe: the column is added idempotently.
    """
    store = getattr(ctx, "memory_store", None)
    if store is None:
        return
    try:
        import json  # noqa: PLC0415

        db = store._db  # noqa: SLF001 - the one shared connection
        cols = {row["name"] for row in db.execute("PRAGMA table_info(HarnessRun)").fetchall()}
        if "delegation" not in cols:
            db.execute("ALTER TABLE HarnessRun ADD COLUMN delegation TEXT")
        db.execute(
            "UPDATE HarnessRun SET delegation=? WHERE id=?",
            (json.dumps(blob), ctx.run_id),
        )
        db.commit()
    except Exception:  # noqa: BLE001 - the blob is additive; never break the call
        pass


__all__ = ["DelegateChildModel", "DelegateInput", "delegate_handler", "delegate_schema"]
