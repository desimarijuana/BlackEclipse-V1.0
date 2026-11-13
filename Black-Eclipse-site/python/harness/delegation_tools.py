"""The `delegate` tool handler (Phase 7), extracted from `code/tools.py`.

Registration lives in `code/tools.register_code_tools`; the handler lives here so
the already-large `code/tools.py` stays under its size ceiling. A child IS a
normal run (`execute_run` with a `parentRunId`) — this module owns only the tool
surface: the caps, the narrowing and the aggregation it delegates to
`harness.delegation`.
"""

from __future__ import annotations

import asyncio
import os
import re
import uuid
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from .delegation_progress import ChildProgressBridge
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
    approach: Optional[str] = Field(default=None, max_length=300)
    agent_id: Optional[str] = Field(default=None, max_length=64)  # noqa: N815
    model: Optional[str] = Field(default=None, max_length=128)
    temperature: Optional[float] = Field(default=None, ge=0.0, le=2.0)
    tool_subset: Optional[list[str]] = Field(default=None, max_length=64)  # noqa: N815
    workspace_id: Optional[str] = Field(default=None, max_length=128)  # noqa: N815
    output_schema: Optional[dict[str, Any]] = None  # noqa: N815
    schema_repair: bool = True  # noqa: N815
    isolated: bool = False


class DelegateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Split mode uses `children`; best-of uses `goal` + `count`. Both stay
    # optional here so the handler can refuse with a plain, structured reason
    # instead of a pydantic error that carries no code.
    children: list[DelegateChildModel] = Field(default_factory=list, max_length=8)
    aggregate: str = Field("list", max_length=16)
    strategy: str = Field("split", max_length=16)
    goal: Optional[str] = Field(default=None, max_length=2000)
    title: Optional[str] = Field(default=None, max_length=200)
    count: Optional[int] = Field(default=None, ge=1, le=8)
    agent_ids: Optional[list[str]] = Field(default=None, max_length=8)  # noqa: N815
    models: Optional[list[str]] = Field(default=None, max_length=8)
    temperatures: Optional[list[float]] = Field(default=None, max_length=8)
    approaches: Optional[list[str]] = Field(default=None, max_length=8)
    contexts: Optional[list[str]] = Field(default=None, max_length=8)
    output_schema: Optional[dict[str, Any]] = None  # noqa: N815
    schema_repair: bool = True  # noqa: N815
    isolated: bool = False


def delegate_schema() -> dict[str, Any]:
    child = {
        "type": "object",
        "properties": {
            "goal": {"type": "string", "description": "The one independent sub-question for this part."},
            "context": {"type": "string", "description": "Background ONLY this part needs."},
            "approach": {"type": "string", "description": "A short angle for this part (e.g. 'add a retry', 'mock the API'). Used as guidance and shown as the row label."},
            "agent_id": {"type": "string", "description": "Run this part with a different agent (optional; defaults to this task's agent)."},
            "model": {"type": "string", "description": "Run this part with a different model on the SAME provider (optional)."},
            "temperature": {"type": "number", "minimum": 0, "maximum": 2, "description": "Sampling temperature for this part (optional; the parent's setting otherwise)."},
            "tool_subset": {"type": "array", "items": {"type": "string"}, "description": "Limit this part to these tools (must be a subset of this task's tools)."},
            "workspace_id": {"type": "string", "description": "A folder this task already has, for a part that writes."},
            "output_schema": {"type": "object", "description": "Optional bounded JSON Schema this part's answer must satisfy. A miss gets one repair turn; the raw answer is kept."},
            "schema_repair": {"type": "boolean", "description": "Allow one bounded repair turn when the output schema is missed (default true)."},
            "isolated": {"type": "boolean", "description": "Give a writing part its own disposable worktree. The parent gets a diff, never an automatic merge."},
        },
        "required": ["goal"],
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {
            "strategy": {
                "type": "string",
                "enum": ["split", "best_of"],
                "description": "split: independent sub-questions (use children). best_of: the SAME task tried several ways, then the strongest verified result is chosen (use goal + count).",
            },
            "children": {"type": "array", "description": "split only: the independent sub-questions to work on at once (1-4).", "items": child},
            "goal": {"type": "string", "description": "best_of only: the one task every attempt should try."},
            "title": {"type": "string", "description": "A short label for the whole fan-out (optional; best_of defaults to the goal)."},
            "count": {"type": "integer", "minimum": 2, "maximum": 4, "description": "best_of only: how many attempts (2-4). Defaults to 3."},
            "agent_ids": {"type": "array", "items": {"type": "string"}, "description": "best_of only: optional agents to use per attempt (they must be ones this task may use)."},
            "models": {"type": "array", "items": {"type": "string"}, "description": "best_of only: optional models to try per attempt. They must be on the SAME provider as this task; the provider and its credential do not change."},
            "temperatures": {"type": "array", "items": {"type": "number", "minimum": 0, "maximum": 2}, "description": "best_of only: optional temperature per attempt, so the samples differ. Providers that ignore temperature are unaffected."},
            "approaches": {"type": "array", "items": {"type": "string"}, "description": "best_of only: optional different angles per attempt (e.g. 'retry with backoff', 'mock the API'). Guidance, never a claimed result."},
            "contexts": {"type": "array", "items": {"type": "string"}, "description": "best_of only: optional background per attempt (bounded), for tries that should work from different evidence."},
            "aggregate": {"type": "string", "enum": ["list", "compare", "merge_claims"], "description": "split only: how to combine the results."},
            "output_schema": {"type": "object", "description": "best_of only: optional JSON Schema every attempt must satisfy."},
            "isolated": {"type": "boolean", "description": "best_of only: give each attempt its own worktree."},
        },
        "additionalProperties": False,
    }


def _present(args: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in args.items() if v is not None}


def _verifier(ctx: ToolContext) -> HandleVerifier:
    """A handle verifier bound to THIS run's real state (no globals).

    Fail-closed by design: a handle is confirmed only when a real store can
    resolve it. An `artifact_digest` is confirmed only when the Artifact Center
    actually holds the artifact; without the service it is NOT admitted (never
    admitted merely for being non-empty).
    """
    ledger = getattr(ctx, "code_ledger", None)
    check_ids = {r.command_execution_id for r in ledger.records} if ledger is not None else set()

    def _run_exists(rid: str) -> bool:
        store = getattr(ctx, "memory_store", None)
        try:
            return bool(store and store.get_run(rid))
        except Exception:  # noqa: BLE001
            return False

    def _artifact_exists(digest: str) -> bool:
        service = getattr(ctx, "artifact_service", None)
        if service is None:
            return False
        try:
            return bool(service.get(digest))
        except Exception:  # noqa: BLE001 - a failed lookup must never confirm
            return False

    return HandleVerifier(
        run_exists=_run_exists,
        ledger_has=lambda cid: cid in check_ids,
        artifact_exists=_artifact_exists,
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

    try:
        model = DelegateInput(**_present(args))
    except Exception as exc:  # noqa: BLE001 - a malformed request is a refusal
        return _refusal("DELEGATION_INVALID", str(exc))

    if model.strategy not in ("split", "best_of"):
        return _refusal("DELEGATION_INVALID", "That isn't a kind of delegation Eclipse knows.")
    if model.strategy == "best_of":
        if model.children:
            return _refusal(
                "DELEGATION_INVALID",
                "For a best-of run, give one goal and a count, not separate parts.",
            )
        goal = (model.goal or "").strip()
        if not goal:
            return _refusal(
                "DELEGATION_INVALID",
                "A best-of run needs the one task every attempt should try.",
            )
        count = model.count or 3
        if count < 2:
            return _refusal(
                WIDTH_EXCEEDED,
                "A best-of run needs at least two attempts to compare.",
            )
        if count > MAX_CHILDREN:
            return _refusal(
                WIDTH_EXCEEDED,
                f"This asks for {count} at once; the most Eclipse does is {MAX_CHILDREN}.",
            )
        agent_ids = [agent for agent in (model.agent_ids or []) if agent]
        if agent_ids:
            from .agents import get_agent  # noqa: PLC0415

            try:
                for agent_id in agent_ids:
                    get_agent(agent_id)
            except Exception:  # noqa: BLE001 - an unknown agent is a refusal
                return _refusal(
                    "DELEGATION_INVALID",
                    "One of those agents isn't one Eclipse knows.",
                )
        models = [name for name in (model.models or []) if name]
        temperatures = [
            value for value in (model.temperatures or [])
            if isinstance(value, (int, float))
        ]
        approaches = [
            text.strip()[:300] for text in (model.approaches or []) if text and text.strip()
        ]
        contexts = [
            text.strip()[:8000] for text in (model.contexts or []) if text and text.strip()
        ]
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
    else:
        if len(model.children) > MAX_CHILDREN:
            return _refusal(WIDTH_EXCEEDED,
                            f"This asks for {len(model.children)} at once; the most Eclipse does is {MAX_CHILDREN}.")
        if not model.children:
            return _refusal("DELEGATION_INVALID", "Give at least one part to look at.")
        parts = [
            DelegationChild(goal=c.goal, context=c.context, approach=c.approach,
                            agent_id=c.agent_id, model=c.model,
                            temperature=c.temperature, tool_subset=c.tool_subset,
                            workspace_id=c.workspace_id,
                            output_schema=c.output_schema,
                            schema_repair=c.schema_repair,
                            isolated=c.isolated)
            for c in model.children
        ]

    depth = int(getattr(ctx, "delegation_depth", 0) or 0)
    if depth >= MAX_DEPTH:
        return _refusal(DEPTH_EXCEEDED, "This work is nested too deeply for Eclipse to keep it straight.")

    # A writing child needs the isolation primitive; refuse rather than run it
    # outside isolation (the Phase 3 rule: a missing primitive refuses honestly).
    if any(c.workspace_id for c in parts):
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
            children=parts,
            aggregate=model.aggregate,  # type: ignore[arg-type]
            strategy=model.strategy,  # type: ignore[arg-type]
            title=model.title or ((model.goal or "").strip() if model.strategy == "best_of" else None),
        )
    except Exception as exc:  # noqa: BLE001
        return _refusal("DELEGATION_INVALID", str(exc))

    # Pre-allocated so each part's progress bridge can name the fan-out before
    # `run_delegation` starts it. The executor accepts a caller-supplied id.
    delegation_id = "dlg_" + uuid.uuid4().hex[:16]

    async def _run_child(child: DelegationChild, child_run_id: str, allowed: Any, actor: Actor) -> Any:
        query = child.goal
        if child.approach:
            query += f"\n\nApproach: {child.approach}"
        if child.context:
            query += f"\n\nContext:\n{child.context}"
        if child.output_schema is not None:
            import json  # noqa: PLC0415

            query += (
                "\n\nReturn ONLY JSON that satisfies this schema (no prose, no markdown):\n"
                + json.dumps(child.output_schema, ensure_ascii=False)[:8_000]
            )
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
        # A part may name another model on the PARENT'S provider, and/or its own
        # temperature. The provider and its credential stay unchanged, so this
        # can never reach for a key this run does not hold.
        updates: dict[str, Any] = {}
        if child.model and getattr(ctx.model_settings, "model", None) != child.model:
            updates["model"] = child.model
        if child.temperature is not None:
            updates["temperature"] = child.temperature
        child_settings = ctx.model_settings
        if updates:
            try:
                child_settings = ctx.model_settings.model_copy(update=updates)
            except Exception:  # noqa: BLE001 - keep the parent's settings, never crash
                child_settings = ctx.model_settings
        # W7: a writing part gets its own disposable worktree. The token is an
        # opaque, process-local capability; no path is passed.
        scratch_token = None
        workspace = None
        if child.isolated:
            try:
                from .code import worktree  # noqa: PLC0415

                workspace = worktree.allocate()
                scratch_token = worktree.mint_scratch_token(workspace.root)
            except Exception as exc:  # noqa: BLE001 - isolation is required
                return {
                    "status": "refused", "runId": child_run_id,
                    "summary": "", "reason": f"no isolated workspace: {exc}"[:500],
                    "tokens": 0, "handles": [],
                }
        child_request = RunRequest(
            runId=child_run_id,
            # Carry the depth so a grandchild cannot reset it to 0 and bypass MAX_DEPTH.
            input=RunInput(query=query[:100_000], context={"delegationDepth": depth + 1}),
            agentId=child.agent_id or DEFAULT_AGENT_ID,
            **({"agent": child_agent} if child_agent is not None else {}),
            modelSettings=child_settings,
            parentRunId=ctx.run_id,
            autonomy=(
                getattr(ctx, "autonomy", None)
                if (child.workspace_id or workspace is not None) else None
            ),
            workspaceId=(
                workspace.id if workspace is not None else child.workspace_id
            ),
            workspaceScratchToken=scratch_token,
            callbackBaseUrl=os.environ.get("HARNESS_CALLBACK_URL", "http://127.0.0.1"),
        )
        # The child runs on its OWN run id, so its events never reach the parent's
        # stream. Bridge them into one throttled snapshot on the parent emitter so
        # the chat can show this part working (see `delegation_progress.py`).
        index_match = re.search(r"_child(\d+)_", child_run_id)
        bridge = ChildProgressBridge(
            bus=getattr(ctx, "bus", None),
            child_run_id=child_run_id,
            delegation_id=delegation_id,
            child_index=int(index_match.group(1)) if index_match else 0,
            goal=child.goal,
            approach=child.approach,
            agent_id=child.agent_id or DEFAULT_AGENT_ID,
            provider=getattr(child_settings, "provider", None),
            model=getattr(child_settings, "model", None),
            emit=_on_event,
        )
        bridge.start()
        # A stop signal this child's cooperating tools can watch (sandbox,
        # browser, shell). `run_delegation` cancels the task; this also tells the
        # work inside it to stop rather than leaving a process running.
        cancel_event = asyncio.Event()
        try:
            result = await execute_run(
                child_request, ctx.tool_registry, ctx.data_bridge, ctx.memory_store, getattr(ctx, "bus", None),
                cancel_event=cancel_event,
                retrieval_cache=getattr(ctx, "retrieval_cache", None),
                memory_service=getattr(ctx, "memory_service", None),
                skill_registry=getattr(ctx, "skill_registry", None),
                memory_router=getattr(ctx, "memory_router", None),
                mcp_manager=getattr(ctx, "mcp_manager", None),
                code_store=getattr(ctx, "code_store", None),
            )
        except asyncio.CancelledError:
            # A stopped part is STOPPED, not failed. Tell cooperating tools, then
            # let the cancellation propagate so every outcome is terminal.
            cancel_event.set()
            await bridge.finish("cancelled")
            raise
        except BaseException:
            cancel_event.set()
            await bridge.finish("failed")
            raise
        dumped = result.model_dump() if hasattr(result, "model_dump") else dict(result)
        error = dumped.get("error")
        status = "completed" if dumped.get("status") == "completed" else "failed"
        tokens = max(0, int(dumped.get("totalTokens") or 0))
        reason = error.get("message") if isinstance(error, dict) else None
        raw = str(dumped.get("output") or "")

        # W7: validate the contract and allow ONE bounded repair turn. The raw
        # answer is kept whatever happens.
        from .delegation_repair import repair_prompt, validate_output  # noqa: PLC0415

        validated = validate_output(raw, child.output_schema)
        repair_run_id = None
        repair_attempted = False
        if validated["valid"] is False and child.schema_repair and child.output_schema is not None:
            repair_attempted = True
            repair_run_id = f"{child_run_id}_repair"
            try:
                from .agents import get_agent as _get_agent  # noqa: PLC0415
                from .schemas import AgentConfig as _AgentConfig  # noqa: PLC0415

                base = _get_agent(child.agent_id or DEFAULT_AGENT_ID)
                repair_request = RunRequest(
                    runId=repair_run_id,
                    input=RunInput(query=repair_prompt(child.output_schema, raw, validated["errors"])),
                    agent=_AgentConfig(
                        id=base.id, name=base.name,
                        systemPrompt=base.systemPrompt + "\n\n## Schema repair\nReturn ONLY corrected JSON.",
                        tools=[], maxSteps=1,
                    ),
                    modelSettings=child_settings,
                    parentRunId=child_run_id,
                    callbackBaseUrl=os.environ.get("HARNESS_CALLBACK_URL", "http://127.0.0.1"),
                )
                repaired = await execute_run(
                    repair_request, ctx.tool_registry, ctx.data_bridge, ctx.memory_store,
                    getattr(ctx, "bus", None),
                )
                repaired_dump = repaired.model_dump() if hasattr(repaired, "model_dump") else dict(repaired)
                if repaired_dump.get("status") == "completed":
                    validated = validate_output(str(repaired_dump.get("output") or ""), child.output_schema)
            except Exception as exc:  # noqa: BLE001 - preserve the raw answer
                validated = {
                    "valid": False, "text": raw,
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
            except Exception:  # noqa: BLE001
                diff = {"workspaceId": workspace.id, "available": False}

        await bridge.finish(status, tokens=tokens, reason=reason)
        return {
            "status": status,
            "runId": dumped.get("runId", child_run_id),
            "summary": validated["text"],
            "rawSummary": raw,
            "schemaValid": validated["valid"],
            "schemaErrors": validated["errors"],
            "repairAttempted": repair_attempted,
            "repairRunId": repair_run_id,
            "workspaceId": workspace.id if workspace is not None else child.workspace_id,
            "diff": diff,
            # REAL usage for the budget report — never estimated.
            "tokens": tokens,
            # A run_id handle lets the parent re-check existence. A check-claim
            # additionally needs a real ledger row (partition_claims enforces it).
            "handles": [{"kind": "run_id", "value": dumped.get("runId", child_run_id)}],
            "reason": reason,
        }

    async def _on_event(event_type: str, data: dict[str, Any]) -> None:
        # Progress is high-frequency and worthless after the run: publish it live
        # only (no SQLite row per snapshot). Everything else keeps the normal,
        # persisted `delegation.*` path.
        if event_type == "delegation.progress":
            emitter = getattr(ctx, "emitter", None)
            if emitter is not None and hasattr(emitter, "emit_transient"):
                try:
                    emitter.emit_transient(event_type, data)
                    return
                except Exception:  # noqa: BLE001 - fall back to the normal seam
                    pass
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
            workflow_id=_parent_workflow_id(ctx),
            on_event=_on_event,
            delegation_id=delegation_id,
        )
    except DelegationError as exc:
        return _refusal(exc.code, exc.reason)

    _record_blob(ctx, result.to_blob())
    done = sum(1 for o in result.outcomes if o.status == "completed")
    text = (
        result.aggregate
        if request.strategy == "best_of"
        else f"I looked at {done} of {len(result.outcomes)}.\n\n{result.aggregate}"
    )
    data = {
        "status": "ok",
        "delegationId": result.delegationId,
        "strategy": result.strategy,
        "winner": result.winner,
        "completed": done,
        "total": len(result.outcomes),
        "droppedClaims": len(result.droppedClaims),
        "outcomes": [
            {
                "childIndex": o.child_index, "runId": o.run_id, "status": o.status,
                "reason": o.reason, "claimed": o.claimed, "dropped": o.dropped,
                "schemaValid": o.schema_valid, "schemaErrors": o.schema_errors,
                "repairAttempted": o.repair_attempted,
                **({"workspaceId": o.workspace_id} if o.workspace_id else {}),
            }
            for o in result.outcomes
        ],
        "budget": result.budget.model_dump(by_alias=True),
    }
    return text, data


def _parent_workflow_id(ctx: ToolContext) -> Optional[str]:
    """The parent run's workflow id, so the fan-out is attributed to it.

    Read from the same persisted run row the lineage writer uses. Absent store
    or absent column => None (an ordinary chat run has no workflow), never a
    fabricated id.
    """
    store = getattr(ctx, "memory_store", None)
    if store is None:
        return None
    try:
        run = store.get_run(ctx.run_id)
    except Exception:  # noqa: BLE001 - attribution must never break the call
        return None
    if isinstance(run, dict):
        return run.get("workflowId")
    return getattr(run, "workflowId", None)


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
