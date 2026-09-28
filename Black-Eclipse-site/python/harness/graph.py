"""LangGraph execution graph — the agent runtime.

Flow (a StateGraph over a message list):

    START → agent
    agent  — the model is called with the tool schemas bound
             • no tool calls  → END (final answer)
             • tool calls     → tools
    tools  — each call is validated, permission-checked, timed out and executed
             by the Python ToolRegistry (JDdS data via the bridge)
             → back to agent
    agent → … until max_steps, then a MAX_STEPS_EXCEEDED failure

Safety mirrors the Phase 1 design: max steps, per-tool timeout, duplicate-call
suppression, run timeout, cooperative cancellation, and exactly one terminal
status. Events are emitted by the Python runtime.
"""

from __future__ import annotations

import asyncio
import json
from typing import Annotated, Any, Optional

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict

from .agents import DEFAULT_AGENT_ID, get_agent
from .events import EventBus, RunEmitter
from .models import build_chat_model
from .persistence import AgentMemoryStore, now_iso
from .schemas import AgentConfig, HarnessError, RunRequest, RunResult
from .tools import DataBridge, ToolContext, ToolRegistry


class GraphState(TypedDict, total=False):
    messages: Annotated[list[BaseMessage], add_messages]
    step: int
    tool_calls: int
    tool_errors: int
    prompt_tokens: int
    completion_tokens: int
    final: Optional[str]
    error: Optional[dict[str, Any]]


def _stable_key(name: str, args: dict[str, Any]) -> str:
    return f"{name}:{json.dumps(args, sort_keys=True, default=str)}"


def _extract_usage(message: Any) -> tuple[int, int]:
    """Best-effort (prompt, completion) token counts from a LangChain message.

    Providers expose usage differently: `usage_metadata` is the LangChain
    standard; OpenAI-compatible endpoints (incl. Ollama) put it in
    `response_metadata["token_usage"]`; Anthropic uses `response_metadata["usage"]`.
    A missing block yields (0, 0) — the run honestly reports "usage not
    reported" rather than inventing a count.
    """
    prompt = completion = 0
    usage = getattr(message, "usage_metadata", None)
    if isinstance(usage, dict):
        prompt = int(usage.get("input_tokens") or 0)
        completion = int(usage.get("output_tokens") or 0)
    meta = getattr(message, "response_metadata", None) or {}
    if isinstance(meta, dict):
        raw = meta.get("token_usage") or meta.get("usage") or {}
        if isinstance(raw, dict):
            prompt = prompt or int(raw.get("prompt_tokens") or raw.get("input_tokens") or 0)
            completion = completion or int(raw.get("completion_tokens") or raw.get("output_tokens") or 0)
    return prompt, completion


def resolve_agent(request: RunRequest) -> AgentConfig:
    """Resolve the agent Python-side: explicit override, else id, else default.

    Python owns the agent definitions, so the front door sends only an id and
    the runtime supplies the system prompt + tool allowlist from its presets.
    """
    if request.agent is not None:
        return request.agent
    return get_agent(request.agentId or DEFAULT_AGENT_ID)


def _effect_authorizer(approvals: Optional[Any], run_id: str, emitter: RunEmitter) -> Optional[Any]:
    """The run's effect authorizer, or None when no approval store is wired.

    With no authorizer, the registry refuses every non-read tool — the safe
    default. When wired, only an explicit matching operator approval passes.
    """
    if approvals is None:
        return None
    from .mcp.approvals import make_effect_authorizer

    return make_effect_authorizer(approvals, run_id, emitter)


def effective_allowlist(agent: AgentConfig, registry: ToolRegistry) -> Optional[set[str]]:
    """The run's tool allowlist, with an explicit, narrow MCP opt-in.

    When the agent sets `allowMcpTools`, the allowlist is expanded to include the
    MCP tools CURRENTLY REGISTERED in the registry (names under the `mcp_`
    namespace). Registration already requires an enabled server, explicit
    per-tool selection and a read-only effect, so this cannot surface a merely
    discovered tool. Every other agent keeps its exact allowlist — the opt-in is
    per-agent and defaults off, so a restricted custom agent or skill can never
    reach an MCP tool it did not name. When the agent has NO allowlist (None =
    all tools), the expansion is a no-op.
    """
    if agent.tools is None:
        return None
    allowed = set(agent.tools)
    if agent.allowMcpTools:
        allowed.update(name for name in registry.names() if name.startswith("mcp_"))
    return allowed


def build_graph(
    request: RunRequest,
    registry: ToolRegistry,
    data_bridge: DataBridge,
    store: AgentMemoryStore,
    emitter: RunEmitter,
    bus: Optional[EventBus] = None,
    cancel_event: Optional[asyncio.Event] = None,
    retrieval_cache: Optional[Any] = None,
    memory_service: Optional[Any] = None,
    skill_registry: Optional[Any] = None,
    effect_authorizer: Optional[Any] = None,
    memory_router: Optional[Any] = None,
) -> Any:
    """Compile a LangGraph StateGraph for one run. Returns an awaitable app."""
    agent = resolve_agent(request)
    max_steps: int = agent.maxSteps or 8
    tool_timeout_ms = agent.toolTimeoutMs or 20_000
    run_timeout_s = (agent.runTimeoutMs or 120_000) / 1000
    # A hard total tool-call budget. A skill manifest declares
    # `limits.maxToolCalls`; this ENFORCES it in the loop (a skill cannot exceed
    # its declared budget by prompting or by looping). None = unbounded (chat).
    max_tool_calls: Optional[int] = agent.maxToolCalls
    allowed = effective_allowlist(agent, registry)

    model = build_chat_model(request.modelSettings)
    lc_tools = registry.langchain_tools(allowed)
    model_with_tools = model.bind_tools(lc_tools) if lc_tools else model

    # The retrieval layer is built lazily by the retrieval tools from `ctx`;
    # the shared process-wide cache is attached here so concurrent runs reuse
    # each other's in-flight/cached retrievals (Milestone 2H). Eclipse-Memory is
    # attached so the memory/skill tools work during a normal run.
    ctx = ToolContext(
        run_id=request.runId,
        log=lambda m, d=None: None,
        user_id=request.userId,
        user_message=request.input.query,
        # A skill run is composed with an agent id of the form `skill:<id>`; its
        # memory saves carry execution-lesson provenance, not explicit-user.
        is_skill_run=agent.id.startswith("skill:"),
        data_bridge=data_bridge,
        retrieval_cache=retrieval_cache,
        emitter=emitter,
        memory_store=store,
        memory_service=memory_service,
        memory_router=memory_router,
        skill_registry=skill_registry,
        model_settings=request.modelSettings,
        bus=bus,
        tool_registry=registry,
        authorize_effect=effect_authorizer,
    )
    registry.set_active_context(ctx)

    seen_calls: dict[str, int] = {}

    async def agent_node(state: GraphState) -> GraphState:
        step = state.get("step", 0) + 1
        await emitter.emit("model.requested", {"step": step, "messages": len(state["messages"])})
        # On the last allowed step, forbid tools so the model MUST answer from the
        # evidence it already gathered. Without this a tool-calling model can loop
        # until max steps and produce MAX_STEPS_EXCEEDED instead of an answer —
        # the exact failure that made the agent "unable to answer". The same
        # applies once a hard tool-call budget is spent.
        budget_spent = max_tool_calls is not None and state.get("tool_calls", 0) >= max_tool_calls
        finalizing = step >= max_steps or budget_spent
        active_model = model if finalizing else model_with_tools
        # A local model often ignores an empty tool list and keeps emitting tool
        # calls from the conversation's momentum (observed hallucinating a
        # `terminal` tool that does not exist). Unbinding tools is necessary but
        # not sufficient: also tell it, in-band, that this is the answer turn.
        model_messages = (
            [*state["messages"], HumanMessage(content=_FINALIZE_INSTRUCTION)]
            if finalizing
            else state["messages"]
        )
        try:
            response = await _ainvoke_streaming(
                active_model, model_messages, run_timeout_s, emitter, finalizing
            )
        except asyncio.TimeoutError:
            await emitter.emit("run.failed", {"error": {"code": "PROVIDER_TIMEOUT", "message": "model call timed out"}})
            return {**state, "step": step, "error": {"code": "PROVIDER_TIMEOUT", "message": "model call timed out"}}
        except Exception as exc:  # noqa: BLE001
            await emitter.emit("run.failed", {"error": {"code": "PROVIDER_ERROR", "message": str(exc)}})
            return {**state, "step": step, "error": {"code": "PROVIDER_ERROR", "message": str(exc)}}

        tool_calls = getattr(response, "tool_calls", None) or []
        # On the final step we do NOT execute tools — the model must answer. If a
        # provider still returned tool calls, drop them so routing falls through
        # to the final answer instead of looping into MAX_STEPS_EXCEEDED.
        if finalizing and tool_calls:
            try:
                response.tool_calls = []
            except Exception:  # noqa: BLE001
                pass
            tool_calls = []
        step_prompt, step_completion = _extract_usage(response)
        total_prompt = state.get("prompt_tokens", 0) + step_prompt
        total_completion = state.get("completion_tokens", 0) + step_completion
        await emitter.emit(
            "model.completed",
            {
                "step": step,
                "hasToolCalls": bool(tool_calls),
                "promptTokens": step_prompt,
                "completionTokens": step_completion,
                "totalTokens": step_prompt + step_completion,
            },
        )
        store.update_run(
            request.runId,
            modelSteps=step,
            promptTokens=total_prompt,
            completionTokens=total_completion,
            totalTokens=total_prompt + total_completion,
        )

        usage_state = {"prompt_tokens": total_prompt, "completion_tokens": total_completion}

        if not tool_calls:
            final_text = _text(response)
            # A forced final turn that produced no text is not an answer. Report
            # the honest failure rather than a blank "completed".
            if finalizing and not final_text.strip():
                if budget_spent:
                    message = (
                        f"Reached the {max_tool_calls}-tool-call limit without a final answer."
                    )
                    code = "TOOL_BUDGET_EXCEEDED"
                else:
                    message = f"Reached the maximum of {max_steps} steps without a final answer."
                    code = "MAX_STEPS_EXCEEDED"
                try:
                    store.append_event(request.runId, "skill.tool_budget_exceeded", 0,
                                       {"maxToolCalls": max_tool_calls, "toolCalls": state.get("tool_calls", 0)})
                except Exception:  # noqa: BLE001 - audit must not break the run
                    pass
                await emitter.emit("run.failed", {"error": {"code": code, "message": message}})
                return {**state, **usage_state, "step": step, "error": {"code": code, "message": message}}
            return {
                **state,
                **usage_state,
                "step": step,
                "messages": [*state["messages"], response],
                "final": final_text,
            }

        return {**state, **usage_state, "step": step, "messages": [*state["messages"], response]}

    async def tools_node(state: GraphState) -> GraphState:
        last = state["messages"][-1]
        calls = getattr(last, "tool_calls", None) or []
        tool_calls = state.get("tool_calls", 0)
        tool_errors = state.get("tool_errors", 0)
        out_messages: list[BaseMessage] = []

        for call in calls:
            name = call.get("name", "")
            args = call.get("args", {}) or {}
            call_id = call.get("id") or f"call_{name}"

            # Enforce the manifest's hard tool-call budget. Once exhausted, no
            # further tool executes: the model is told plainly (so it answers
            # from gathered evidence) and the refusal is auditable. The budget is
            # a runtime limit, not a prompt suggestion.
            if max_tool_calls is not None and tool_calls >= max_tool_calls:
                result_text = (
                    f"Tool call refused: the maximum of {max_tool_calls} tool calls for this run "
                    "has been reached. Answer using the information already gathered."
                )
                await emitter.emit("tool.failed", {"name": name, "toolCallId": call_id, "code": "TOOL_BUDGET_EXCEEDED"})
                try:
                    store.append_event(request.runId, "skill.tool_budget_exceeded", 0,
                                       {"maxToolCalls": max_tool_calls, "toolCalls": tool_calls, "tool": name})
                except Exception:  # noqa: BLE001 - audit must not break the run
                    pass
                tool_errors += 1
                out_messages.append(ToolMessage(content=result_text, tool_call_id=call_id))
                continue

            tool_calls += 1
            await emitter.emit("tool.requested", {"name": name, "toolCallId": call_id, "step": state.get("step")})

            key = _stable_key(name, args)
            if seen_calls.get(key, 0) > 0:
                result_text = (
                    f"Duplicate call to {name!r} with identical arguments was not executed again. "
                    "Use the earlier result."
                )
                await emitter.emit("tool.failed", {"name": name, "toolCallId": call_id, "code": "TOOL_FORBIDDEN"})
                tool_errors += 1
            else:
                seen_calls[key] = seen_calls.get(key, 0) + 1
                result = await registry.execute(
                    name, call_id, args, ctx, allowed=allowed, timeout_ms=tool_timeout_ms
                )
                result_text = result.text
                if result.ok:
                    await emitter.emit(
                        "tool.completed",
                        {"name": name, "toolCallId": call_id, "durationMs": result.duration_ms},
                    )
                else:
                    tool_errors += 1
                    await emitter.emit(
                        "tool.failed",
                        {
                            "name": name,
                            "toolCallId": call_id,
                            "code": result.error.code if result.error else "TOOL_ERROR",
                            "durationMs": result.duration_ms,
                        },
                    )
                try:
                    store.record_tool_execution(request.runId, result)
                except Exception:  # noqa: BLE001
                    pass

            out_messages.append(ToolMessage(content=result_text, tool_call_id=call_id))

        store.update_run(request.runId, toolCalls=tool_calls, toolErrors=tool_errors)
        return {**state, "messages": [*state["messages"], *out_messages], "tool_calls": tool_calls, "tool_errors": tool_errors}

    def route_after_agent(state: GraphState) -> str:
        if state.get("error"):
            return END
        if state.get("final") is not None:
            return END
        last = state["messages"][-1]
        if getattr(last, "tool_calls", None):
            return "tools"
        return END

    def route_after_tools(state: GraphState) -> str:
        if state.get("step", 0) >= max_steps:
            return "exhausted"
        return "agent"

    async def exhausted_node(state: GraphState) -> GraphState:
        message = f"Reached the maximum of {max_steps} steps without a final answer."
        await emitter.emit("run.failed", {"error": {"code": "MAX_STEPS_EXCEEDED", "message": message}})
        return {**state, "error": {"code": "MAX_STEPS_EXCEEDED", "message": message}}

    graph = StateGraph(GraphState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", tools_node)
    graph.add_node("exhausted", exhausted_node)
    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", route_after_agent, {"tools": "tools", END: END})
    graph.add_conditional_edges("tools", route_after_tools, {"agent": "agent", "exhausted": "exhausted"})
    graph.add_edge("exhausted", END)
    return graph.compile()


async def _ainvoke_streaming(
    model: Any,
    messages: list[BaseMessage],
    timeout_s: float,
    emitter: RunEmitter,
    finalizing: bool,
) -> Any:
    """Invoke the model, streaming tokens live when it supports it.

    Streaming is best-effort: a provider/model that cannot stream falls back to
    a single `ainvoke`. Token deltas are emitted as transient `model.delta`
    events so the UI shows the agent working and writing, without persisting
    every fragment. The assembled message is what the graph stores, so tool
    calls and usage metadata still work exactly as before.

    On the final step (`finalizing`) tools are unbound upstream, so this only
    ever yields the closing answer.
    """
    async def _stream() -> Any:
        aggregated: Any = None
        last_with_tools: Any = None
        last_with_usage: Any = None
        async for chunk in model.astream(messages):
            aggregated = chunk if aggregated is None else _merge_chunks(aggregated, chunk)
            if getattr(chunk, "tool_calls", None):
                last_with_tools = chunk
            if getattr(chunk, "usage_metadata", None):
                last_with_usage = chunk
            text = _text(chunk) if getattr(chunk, "content", "") else ""
            if text:
                emitter.emit_transient(
                    "model.delta", {"text": text, "finalizing": finalizing}
                )
        # Some providers/tests stream full AIMessage objects, whose `+` drops
        # tool_calls/usage. Carry those forward so the graph still sees them.
        if aggregated is not None:
            if not getattr(aggregated, "tool_calls", None) and last_with_tools is not None:
                try:
                    aggregated.tool_calls = last_with_tools.tool_calls
                except Exception:  # noqa: BLE001
                    pass
            if not getattr(aggregated, "usage_metadata", None) and last_with_usage is not None:
                try:
                    aggregated.usage_metadata = last_with_usage.usage_metadata
                except Exception:  # noqa: BLE001
                    pass
        return aggregated

    try:
        aggregated = await asyncio.wait_for(_stream(), timeout=timeout_s)
        if aggregated is None:
            # An empty stream is not an answer; fall back to a plain call.
            return await asyncio.wait_for(model.ainvoke(messages), timeout=timeout_s)
        return aggregated
    except (asyncio.TimeoutError, asyncio.CancelledError):
        raise
    except Exception:  # noqa: BLE001 - not all models implement astream
        return await asyncio.wait_for(model.ainvoke(messages), timeout=timeout_s)


_FINALIZE_INSTRUCTION = (
    "You have reached the last allowed step. Tools are no longer available. "
    "Answer the user's request NOW using only the information already gathered "
    "above. Do not call tools, do not describe what you would do, and do not ask "
    "for permission. If some data was unavailable, say so plainly in the answer."
)


def _merge_chunks(a: Any, b: Any) -> Any:
    """Merge two stream chunks, tolerating providers that yield full messages.

    LangChain's `AIMessageChunk + AIMessageChunk` is correct; a full `AIMessage`
    addition is not (it drops tool_calls and can raise). Fall back to keeping the
    richer object so a non-conforming provider cannot crash the run.
    """
    try:
        return a + b
    except Exception:  # noqa: BLE001
        return b if getattr(b, "content", None) or getattr(b, "tool_calls", None) else a


def _text(message: Any) -> str:
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
            elif isinstance(block, str):
                parts.append(block)
        return "".join(parts)
    return str(content)


async def execute_run(
    request: RunRequest,
    registry: ToolRegistry,
    data_bridge: DataBridge,
    store: AgentMemoryStore,
    bus: Optional[EventBus] = None,
    cancel_event: Optional[asyncio.Event] = None,
    retrieval_cache: Optional[Any] = None,
    memory_service: Optional[Any] = None,
    skill_registry: Optional[Any] = None,
    approvals: Optional[Any] = None,
    memory_router: Optional[Any] = None,
) -> RunResult:
    """Run the graph and write the terminal status exactly once."""
    agent = resolve_agent(request)
    emitter = RunEmitter(request.runId, store, bus)
    started = now_iso()
    store.create_run(
        request.runId,
        agent.id,
        request.input.model_dump(),
        request.userId,
        request.modelSettings.provider,
        request.modelSettings.model,
        session_id=request.sessionId,
        profile_id=request.profileId,
        project_id=request.projectId,
    )
    await emitter.emit("run.created", {"agentId": agent.id})
    store.update_run(request.runId, status="running", startedAt=started)
    await emitter.emit("run.started", {"maxSteps": agent.maxSteps, "provider": request.modelSettings.provider})

    # Phase 4: an unambiguous supported financial comparison is routed through the
    # deterministic evidence gate BEFORE the ordinary agent graph, so it does not
    # also run a financial tool loop (no duplicate retrieval, no contradictory
    # answer). Anything unsupported/uncertain returns None and falls through.
    try:
        research = await _maybe_research(request, data_bridge, store, emitter, retrieval_cache, cancel_event)
    except asyncio.CancelledError:
        store.update_run(request.runId, status="cancelled", finishedAt=now_iso())
        await emitter.emit("run.cancelled", {"reason": "cancelled"})
        return _result(request.runId, "cancelled", store, None)
    if research is not None:
        return await _finish_research(request, store, emitter, research)

    # Retrieve relevant memory BEFORE the model sees the turn, and inject it as
    # clearly-labelled non-authoritative context. Memory is scoped to the user
    # and bounded by a character budget; a retrieval failure must never block the
    # run (it is recorded in the retrieval audit instead).
    memory_block = await _memory_context(request, memory_service, emitter)

    # The always-available compact profile is materialized ONCE here, at run
    # start: a memory saved during this run is visible to LATER runs, never to
    # this one (the snapshot stays stable for the whole run). It is a separate,
    # clearly-labelled, non-authoritative block; its text is data, never
    # instructions. A profile failure must never block the run.
    profile_block, profile_snapshot_id = await _profile_context(request, agent, memory_service, emitter)

    # A bounded, relevant-only skill manifest (never all skills). Discovery is a
    # hint; it cannot enable, grant or run anything.
    skill_manifest, skill_manifest_version = await _skill_manifest_context(
        request, skill_registry, memory_service, emitter,
    )

    # Deterministic explicit-intent handling. A clear "remember this" / "forget
    # this" / "correct this" must not depend on the model voluntarily calling the
    # `memory` tool. Detection runs before the model; a refused or
    # confirmation-pending intent is recorded but NEVER written. Detection is
    # purely a function of the user's query, so one call suffices.
    #
    # A skill child-run's "query" is the rendered skill input, not the user's
    # words — it never carries chat intent, so skip detection there.
    memory_outcome = (
        None if agent.id.startswith("skill:")
        else await _apply_memory_intent(request, memory_service, emitter)
    )

    # Prompt-cache plan: stable segments + a cache key computed from identity
    # (versions + snapshot/manifest ids), never the user message. Recorded for
    # observability; it changes nothing the model is allowed to do.
    from .prompt_segments import build_prompt_plan  # noqa: PLC0415

    allowed = effective_allowlist(agent, registry)
    prompt_plan = build_prompt_plan(
        system_prompt=agent.systemPrompt,
        agent_id=agent.id,
        tool_names=list(allowed) if allowed else list(registry.names()),
        profile_block=profile_block,
        profile_snapshot_id=profile_snapshot_id,
        skill_manifest=skill_manifest,
        skill_manifest_version=skill_manifest_version,
        user_message=request.input.query,
    )
    await emitter.emit("prompt.plan", prompt_plan.to_dict())

    messages: list[BaseMessage] = [
        SystemMessage(content=agent.systemPrompt),
        *_history_messages(request),
        *([SystemMessage(content=profile_block)] if profile_block else []),
        *([SystemMessage(content=skill_manifest)] if skill_manifest else []),
        *([SystemMessage(content=memory_block)] if memory_block else []),
        HumanMessage(content=_user_message(request)),
    ]

    try:
        app = build_graph(
            request, registry, data_bridge, store, emitter, bus, cancel_event,
            retrieval_cache, memory_service, skill_registry,
            _effect_authorizer(approvals, request.runId, emitter),
            memory_router,
        )
        final_state = await app.ainvoke(
            {
                "messages": messages,
                "step": 0,
                "tool_calls": 0,
                "tool_errors": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "final": None,
            },
        )
    except asyncio.CancelledError:
        store.update_run(request.runId, status="cancelled", finishedAt=now_iso())
        await emitter.emit("run.cancelled", {"reason": "cancelled"})
        return _result(request.runId, "cancelled", store, None)
    except Exception as exc:  # noqa: BLE001
        error = HarnessError(code="INTERNAL_ERROR", message=str(exc))
        store.update_run(request.runId, status="failed", error=error.model_dump(), finishedAt=now_iso())
        await emitter.emit("run.failed", {"error": error.model_dump()})
        return RunResult(runId=request.runId, status="failed", error=error, toolCalls=0, toolErrors=0, modelSteps=0)

    if final_state.get("error"):
        err = final_state["error"]
        store.update_run(request.runId, status="failed", error=err, finishedAt=now_iso())
        await _post_run_analysis(request.runId, store, memory_service, skill_registry)
        return _result(request.runId, "failed", store, err)

    output = final_state.get("final") or ""
    store.update_run(request.runId, status="completed", output=output, finishedAt=now_iso())
    await emitter.emit("run.completed", {"steps": final_state.get("step", 0)})
    eligibility = _learning_eligibility(run_id=request.runId, store=store, memory_outcome=memory_outcome)
    # An explicit "turn this into a skill" request is now turned into a real
    # inert skill draft from the completed run's trace — through the same
    # candidate + draft persistence path, without a second click. It is never
    # enabled: evaluation + operator approval remain the only promotion gates.
    if memory_outcome and memory_outcome.get("action") == "skill_requested":
        skill_draft = _create_explicit_skill_draft(
            request, store=store, skill_registry=skill_registry, registry=registry,
        )
        if skill_draft:
            memory_outcome["skillDraft"] = skill_draft
            eligibility["skillDraftReady"] = bool(skill_draft.get("captured"))
    # Automatic learning analysis runs for eligible completed runs — the user
    # should not have to ask. It creates ONLY inert candidates (never enables a
    # skill) and, for implicit procedures, only when recurrence evidence exists.
    analysis = await _post_run_analysis(request.runId, store, memory_service, skill_registry)
    memory_blob = _memory_blob(memory_outcome, eligibility, analysis)
    if memory_blob:
        store.update_run(request.runId, memory=memory_blob)
    # Index the run's meaningful messages into the bounded session-history search
    # index so later sessions can ask "what did we decide?". Best-effort; never
    # affects this result.
    await _index_session(request, store, memory_service, emitter)
    result = _result(request.runId, "completed", store, None, output)
    result.memory = memory_blob or None
    return result


async def _maybe_research(
    request: RunRequest,
    data_bridge: DataBridge,
    store: AgentMemoryStore,
    emitter: RunEmitter,
    retrieval_cache: Optional[Any],
    cancel_event: Optional[asyncio.Event],
) -> Optional[dict[str, Any]]:
    """Attempt the gated research flow; None when the request is not supported.

    Builds the same model the run uses (no separate adapter) and reuses the
    shared retrieval layer/cache. Cancellation is honored by the caller.
    """
    from .research.mandate import parse_mandate
    from .research.run import maybe_run_research
    from .retrieval import FinancialRetrievalLayer

    # Classify BEFORE building anything heavy: an unsupported/uncertain request
    # must fall through untouched and must not pay a model-construction cost
    # (which can raise for an unconfigured provider — that must not break chat).
    if not parse_mandate(
        request.input.query, ticker=request.input.ticker, market=request.input.market
    ).supported:
        return None

    layer = FinancialRetrievalLayer(data_bridge, cache=retrieval_cache, store=store)

    async def _retrieve(req: Any) -> Any:
        return await layer.retrieve(req)

    try:
        model = build_chat_model(request.modelSettings)
    except Exception as exc:  # noqa: BLE001 - a supported request must not fall through ungated
        await emitter.emit("research.failed", {"error": str(exc)})
        return {
            "output": (
                "This is an evidence-grounded research request, but the configured model "
                f"could not be initialised, so no answer was produced. ({exc})"
            ),
            "status": "rejected",
            "metadata": None,
            "receipt": None,
            "persistenceError": None,
            "usage": {"promptTokens": 0, "completionTokens": 0},
            "coverage": None,
            "validation": None,
        }

    return await maybe_run_research(
        run_id=request.runId,
        query=request.input.query,
        ticker=request.input.ticker,
        market=request.input.market,
        model=model,
        retrieve=_retrieve,
        store=store,
        emitter=emitter,
        model_settings=request.modelSettings,
        provider=request.modelSettings.provider,
        bridge=data_bridge,
    )


async def _finish_research(
    request: RunRequest,
    store: AgentMemoryStore,
    emitter: RunEmitter,
    research: dict[str, Any],
) -> RunResult:
    """Persist and return a gated research run's terminal result exactly once.

    The run status is `completed` when the gate produced an answer (even a
    partial one — partial is honest, not a failure); `failed` only when the flow
    itself could not run. Token usage reported by the synthesizer is added to the
    run (never estimated).
    """
    output = str(research.get("output") or "")
    usage = research.get("usage") or {}
    prompt_tokens = int(usage.get("promptTokens") or 0)
    completion_tokens = int(usage.get("completionTokens") or 0)
    research_blob = {
        "status": research.get("status"),
        "metadata": research.get("metadata"),
        "receiptAvailable": research.get("receipt") is not None,
        "persistenceError": research.get("persistenceError"),
        "coverage": research.get("coverage"),
        "validation": research.get("validation"),
        "escalation": research.get("escalation"),
        "budget": research.get("budget"),
        # Structured provenance for the chat UI's separate Sources section (the
        # answer prose carries none of it).
        "failedRoutes": research.get("failedRoutes"),
        "stopReasonText": research.get("stopReasonText"),
        "blockedComparisons": research.get("blockedComparisons"),
    }
    store.update_run(
        request.runId,
        status="completed",
        output=output,
        promptTokens=prompt_tokens,
        completionTokens=completion_tokens,
        totalTokens=prompt_tokens + completion_tokens,
        research=research_blob,
        finishedAt=now_iso(),
    )
    await emitter.emit("run.completed", {"steps": 0, "research": True, "status": research.get("status")})

    result = _result(request.runId, "completed", store, None, output)
    # Expose the full receipt on the run result (not persisted inline — the
    # durable copy lives in ResearchReceipt and is read via the receipt route).
    result.research = {**research_blob, "receipt": research.get("receipt")}
    return result


async def _index_session(
    request: RunRequest,
    store: AgentMemoryStore,
    memory_service: Optional[Any],
    emitter: RunEmitter,
) -> None:
    """Index the completed run's messages for historical search (best-effort).

    Policy-gated; redacted + bounded; never affects the run result. A skill
    child-run is indexed too (its transcript is useful history).
    """
    try:
        settings = memory_service.policy.get_all() if memory_service is not None else {}
    except Exception:  # noqa: BLE001
        settings = {}
    if not bool(settings.get("session_indexing_enabled", True)):
        return
    if not bool(settings.get("session_history_enabled", True)):
        return
    try:
        from .session_index import index_run  # noqa: PLC0415

        result = index_run(
            store, request.runId, user_id=request.userId,
            session_id=request.sessionId, profile_id=request.profileId,
            project_id=request.projectId,
        )
        await emitter.emit("session.indexed", {"runId": request.runId, "indexed": result.get("indexed", 0)})
        # Keep the session's bounded summary fresh at natural boundaries. It is
        # searchable/opt-in and never injected into every prompt automatically.
        if request.sessionId and memory_service is not None:
            try:
                from .session_index import build_summary  # noqa: PLC0415

                build_summary(store, request.sessionId)
            except Exception:  # noqa: BLE001 - a summary is a projection, not truth
                pass
    except Exception as exc:  # noqa: BLE001 - indexing must never break a run
        try:
            await emitter.emit("session.index_failed", {"error": str(exc)})
        except Exception:  # noqa: BLE001
            pass


async def _post_run_analysis(
    run_id: str,
    store: AgentMemoryStore,
    memory_service: Optional[Any],
    skill_registry: Optional[Any],
) -> Optional[dict[str, Any]]:
    """Deterministic, policy-gated post-run analysis (mistakes + candidates).
    Never raises and never blocks the terminal result: analysis is diagnostics,
    not control flow. It can only create inert records — it cannot enable a
    skill or claim improvement. Returns a bounded summary for the run's memory
    blob (so the UI can show that automatic learning ran and what it produced).
    """
    if memory_service is None:
        return None
    try:
        skill_store = getattr(skill_registry, "store", None)
        return memory_service.analyze_run(run_id, store, skill_store=skill_store)
    except Exception:  # noqa: BLE001
        try:
            store.append_event(run_id, "memory.analysis_failed", 0, {})
        except Exception:  # noqa: BLE001
            pass
        return None


MAX_HISTORY_TURNS = 20
MAX_HISTORY_CHARS = 40_000


def _history_messages(request: RunRequest) -> list[BaseMessage]:
    """Prior conversation turns, oldest first, bounded so a long chat cannot
    blow the context window. Keeps the MOST RECENT turns when trimming."""
    history = request.input.history or []
    if not history:
        return []
    trimmed = history[-MAX_HISTORY_TURNS:]
    # Also cap total characters, dropping oldest turns first.
    total = sum(len(t.content) for t in trimmed)
    while trimmed and total > MAX_HISTORY_CHARS:
        total -= len(trimmed[0].content)
        trimmed = trimmed[1:]
    return [
        HumanMessage(content=t.content) if t.role == "user" else AIMessage(content=t.content)
        for t in trimmed
    ]


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
    try:
        result = memory_service.retrieve(
            query=request.input.query,
            subject=request.input.ticker,
            actor_scope="user" if request.userId else None,
            scope_id=request.userId,
            run_id=request.runId,
            limit=8,
            budget_chars=4000,
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
    recurring = _is_recurring_statement(request)
    try:
        decision = memory_service.decide_turn(
            request.input.query,
            user_id=request.userId,
            recurring=recurring,
            is_skill_run=False,
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
            decision, run_id=request.runId, user_id=request.userId
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
    return {
        "runId": run_id,
        "eligible": eligible,
        "reason": reason,
        "modelSteps": steps,
        "toolCalls": tool_calls,
        "skillRequested": skill_requested,
        "isSkillRun": False,
        "learnQueuePath": "/api/learning/candidates",
    }


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
    return {
        "runId": run_id,
        "eligible": eligible,
        "reason": reason,
        "modelSteps": steps,
        "toolCalls": tool_calls,
        "skillRequested": skill_requested,
        "isSkillRun": False,
        "learnQueuePath": "/api/learning/candidates",
    }


def _user_message(request: RunRequest) -> str:
    text = request.input.query
    if request.input.ticker:
        text += f"\n\nTicker: {request.input.ticker}"
    if request.input.market:
        text += f"\n\nMarket: {request.input.market}"
    documents = request.input.documents or []
    if documents:
        # Attached documents are user-provided context, not tool output: they
        # are wrapped and clearly attributed so the model can distinguish them
        # from authoritative JDdS data it retrieves itself.
        parts = [
            f'<document name="{doc.name}">\n{doc.text}\n</document>'
            for doc in documents
        ]
        text += (
            "\n\nAttached documents (user-provided context; treat as evidence "
            "the user supplied, and do not claim to have retrieved them):\n"
            + "\n\n".join(parts)
        )
    return text


def _result(run_id: str, status: str, store: AgentMemoryStore, error: Optional[dict[str, Any]], output: Optional[str] = None) -> RunResult:
    run = store.get_run(run_id) or {}
    return RunResult(
        runId=run_id,
        status=status,  # type: ignore[arg-type]
        output=output if output is not None else run.get("output"),
        error=HarnessError(**error) if error else None,
        modelSteps=run.get("modelSteps", 0),
        toolCalls=run.get("toolCalls", 0),
        toolErrors=run.get("toolErrors", 0),
        promptTokens=run.get("promptTokens", 0),
        completionTokens=run.get("completionTokens", 0),
        totalTokens=run.get("totalTokens", 0),
    )


__all__ = ["build_graph", "execute_run"]
