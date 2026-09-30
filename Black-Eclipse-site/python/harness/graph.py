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


# Tools whose surface is gated by a policy key. A tool is dropped from the
# advertised schema AND the run's allowlist when its store is off, so the model
# is never told about a tool it cannot use.
def surface_disabled_tools(settings: Optional[dict[str, Any]]) -> set[str]:
    """Tool names whose surface is disabled by the resolved policy."""
    settings = settings or {}
    disabled: set[str] = set()
    memory_on = bool(settings.get("memory_enabled", True))
    if not memory_on:
        # The whole memory/skill surface is off (except skill_list/view, which are
        # read-only discovery the prompt still offers; the store is the memory DB
        # but skills are a separate concern — only the memory WRITE tool and the
        # memory-dependent search tools are dropped).
        disabled.update({"memory", "memory_search_native", "memory_search_external"})
    if not bool(settings.get("session_history_enabled", True)):
        disabled.update({"session_search", "session_open"})
    if not bool(settings.get("external_memory_search_enabled", False)):
        disabled.add("memory_search_external")
    return disabled


def resolve_surface(
    agent: AgentConfig,
    registry: ToolRegistry,
    settings: Optional[dict[str, Any]],
) -> tuple[Optional[set[str]], str]:
    """Resolve `(allowlist, system_prompt)` for ONE run from policy.

    Computed where the run's settings are read (never at import time), so a
    policy change takes effect on the next run and the system-prompt head stays
    byte-stable within a run. A disabled store's tool is dropped from BOTH the
    allowlist and the prompt guidance.

    `allowlist` is `None` only when the agent has no allowlist AND nothing is
    disabled (the unrestricted case is passed through unchanged).
    """
    from .prompts import filter_system_prompt  # noqa: PLC0415

    settings = settings or {}
    disabled = surface_disabled_tools(settings)
    allowed = effective_allowlist(agent, registry)
    if allowed is None:
        if disabled:
            allowed = {name for name in registry.names() if name not in disabled}
        else:
            allowed = None
    else:
        allowed = {name for name in allowed if name not in disabled}
    prompt = filter_system_prompt(
        agent.systemPrompt,
        memory_enabled=bool(settings.get("memory_enabled", True)),
        session_history_enabled=bool(settings.get("session_history_enabled", True)),
    )
    return allowed, prompt


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
    allowed: Optional[set[str]] = None,
    source_sink: Optional[Any] = None,
    mcp_manager: Optional[Any] = None,
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
    # `allowed` is the policy-resolved surface from `execute_run` (a disabled
    # store's tool already removed). Fall back to the raw allowlist for direct
    # callers/tests that build a graph without resolving the surface.
    if allowed is None:
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
        source_sink=source_sink,
        skill_registry=skill_registry,
        model_settings=request.modelSettings,
        bus=bus,
        tool_registry=registry,
        authorize_effect=effect_authorizer,
        mcp_manager=mcp_manager,
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
            # Classify a provider context-length rejection SPECIFICALLY, before the
            # generic provider error. The terminal run.failed for overflow is
            # emitted once by `execute_run` after the bounded recovery attempt, so
            # a successful retry does not leave a spurious terminal failure.
            from .models import (  # noqa: PLC0415
                classify_context_overflow,
                context_overflow_error,
                resolve_context_window,
            )

            if classify_context_overflow(exc):
                provider = request.modelSettings.provider
                model_name = request.modelSettings.model
                # Prefer the operator-declared window when the catalog cannot know
                # it, so the error message states the real window.
                window = getattr(request.modelSettings, "context_window", None)
                if window is None:
                    window = resolve_context_window(provider, model_name)
                code, message = context_overflow_error(provider, model_name, window)
                await emitter.emit(
                    "context.overflow",
                    {"step": step, "provider": provider, "windowKnown": window is not None},
                )
                return {**state, "step": step, "error": {"code": code, "message": message}}
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
    mcp_manager: Optional[Any] = None,
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

    # Surface honesty (Milestone 4): resolve the tool surface AND the system
    # prompt FROM POLICY per run — never at import or __init__ time. A disabled
    # store drops its tool from the bound schema and its guidance from the
    # prompt. The resolved prompt is byte-stable for the whole run; a policy
    # change takes effect on the NEXT run.
    try:
        surface_settings = memory_service.policy.get_all() if memory_service is not None else {}
    except Exception:  # noqa: BLE001 - a policy read failure falls back to the full surface
        surface_settings = {}
    allowed, system_prompt = resolve_surface(agent, registry, surface_settings)

    # A test/operator seam: allows a deterministic tighter budget to be injected
    # (used to exercise the overflow-recovery path without a live provider). It
    # only narrows the derived allowance — it can never widen it.
    budget_overrides: dict[str, Any] = {}
    try:
        raw_override = (request.input.context or {}).get("_context_budget_override")
        if isinstance(raw_override, dict):
            budget_overrides = dict(raw_override)
    except Exception:  # noqa: BLE001 - an override is never required
        budget_overrides = {}

    prompt_plan = build_prompt_plan(
        system_prompt=system_prompt,
        agent_id=agent.id,
        tool_names=list(allowed) if allowed else list(registry.names()),
        profile_block=profile_block,
        profile_snapshot_id=profile_snapshot_id,
        skill_manifest=skill_manifest,
        skill_manifest_version=skill_manifest_version,
        user_message=request.input.query,
    )
    await emitter.emit("prompt.plan", prompt_plan.to_dict())

    # Measure the request and derive the history budget from the RESOLVED model's
    # declared context window. When the window is unknown the budget is inert and
    # the bound falls back to the module constants (byte-identical to before).
    #
    # The dropped-context block itself costs tokens, so the budget must be
    # measured with it present. We derive it once with the conservative bound to
    # extract the dropped context, then re-derive so the final bound accounts for
    # the block's own size. Two passes, no loop.
    budget = _history_budget(
        request, allowed, registry, system_prompt, profile_block, skill_manifest,
        memory_block, dropped_block="", overrides=budget_overrides,
    )
    history_messages, dropped_block, dropped_turns = await _dropped_context_block(
        request, memory_service, emitter, budget,
    )
    budget = _history_budget(
        request, allowed, registry, system_prompt, profile_block, skill_manifest,
        memory_block, dropped_block=dropped_block, overrides=budget_overrides,
    )
    if budget.effective:
        # Re-derive the trimmed set under the measured bound (re-extraction is
        # cheap and deterministic; the extraction event is emitted once).
        history_messages, dropped_block, dropped_turns = await _dropped_context_block(
            request, memory_service, emitter, budget, emit=False,
        )

    # Ordinary-run source collection: retrieval tools hand their results to this
    # collector so the answer can show a Sources panel built ONLY from what was
    # actually retrieved (the gated research path has its own citations). It is
    # additive, best-effort provenance; it never affects the tool result or the
    # run's authorization.
    from .source_collector import SourceCollector  # noqa: PLC0415

    source_collector = SourceCollector()

    # Bounded recovery (Milestone 4): if the run failed with a classified
    # CONTEXT_OVERFLOW, retry ONCE with a materially tighter history budget. The
    # terminal status is persisted once, below, after recovery resolves.
    async def _invoke_with_history(
        history_msgs: list[BaseMessage], dropped: Optional[str] = None,
    ) -> dict[str, Any]:
        run_messages = _assemble_run_messages(
            request, system_prompt=system_prompt, history_messages=history_msgs,
            profile_block=profile_block, skill_manifest=skill_manifest,
            memory_block=memory_block,
            dropped_block=dropped if dropped is not None else dropped_block,
        )
        app = build_graph(
            request, registry, data_bridge, store, emitter, bus, cancel_event,
            retrieval_cache, memory_service, skill_registry,
            _effect_authorizer(approvals, request.runId, emitter),
            memory_router,
            allowed=allowed,
            source_sink=source_collector,
            mcp_manager=mcp_manager,
        )
        return await app.ainvoke(
            {
                "messages": run_messages,
                "step": 0,
                "tool_calls": 0,
                "tool_errors": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "final": None,
            },
        )

    retry_budget: Optional[Any] = None
    try:
        final_state = await _invoke_with_history(history_messages)
        if _is_context_overflow(final_state.get("error")):
            final_state, retry_budget = await _retry_with_tighter_budget(
                request, emitter, final_state, base_budget=budget,
                overrides=budget_overrides,
                system_prompt=system_prompt, profile_block=profile_block,
                skill_manifest=skill_manifest, memory_block=memory_block,
                memory_service=memory_service, allowed=allowed,
                registry=registry, invoke=_invoke_with_history,
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
        err = dict(final_state["error"])
        # An unrecovered CONTEXT_OVERFLOW is a specific, user-facing failure.
        # Rewrite the message to state whether the tighter retry was actually
        # attempted (honest — no claim of a retry that did not happen), and emit
        # the terminal event here (the classifier deliberately does not) so the
        # stream and the persisted run agree.
        context_blob = _context_budget_blob(
            retry_budget or budget, request, kind="overflow",
            retried=retry_budget is not None,
        )
        if _is_context_overflow(err):
            from .models import context_overflow_error  # noqa: PLC0415

            window = getattr(retry_budget or budget, "window", None)
            _code, message = context_overflow_error(
                request.modelSettings.provider, request.modelSettings.model,
                window, retried=retry_budget is not None,
            )
            err["message"] = message
            store.update_run(
                request.runId, status="failed", error=err, finishedAt=now_iso(),
                context=context_blob,
            )
            await emitter.emit("run.failed", {"error": err})
        else:
            store.update_run(request.runId, status="failed", error=err, finishedAt=now_iso())
        await _post_run_analysis(request.runId, store, memory_service, skill_registry)
        result = _result(request.runId, "failed", store, err)
        result.context = context_blob
        return result

    # The user-visible trimming signal (Defect C): emitted on the SUCCESS path
    # whenever history was actually trimmed, with counts and estimates only —
    # never memory/dropped content. Nothing is emitted when nothing was dropped.
    # Re-derived with the FINAL budget so a tighter retry is reflected.
    final_budget = retry_budget or budget
    kept_final, dropped_final = _bounded_history(request, final_budget)
    if dropped_final:
        await emitter.emit("memory.history_bounded", _history_bounded_data(
            final_budget, kept_turns=len(kept_final), dropped_turns=dropped_final,
            retried=retry_budget is not None,
        ))

    output = final_state.get("final") or ""
    context_blob = _context_budget_blob(
        final_budget, request, kind="completed", retried=retry_budget is not None,
    )
    # Provenance collected from this run's retrieval tool calls (None when the
    # run consulted no sources, so an empty panel is never shown). An ordinary
    # run's collected blob carries status `collected`, distinct from a gated
    # research run's `accepted`/`partial`/`rejected`.
    research_blob = source_collector.to_research_blob()
    store.update_run(
        request.runId, status="completed", output=output, finishedAt=now_iso(),
        context=context_blob,
        **( {"research": research_blob} if research_blob else {} ),
    )
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
    result.context = context_blob
    result.research = research_blob
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


def _history_budget(
    request: RunRequest,
    allowed: Optional[set[str]],
    registry: ToolRegistry,
    system_prompt: str,
    profile_block: str,
    skill_manifest: str,
    memory_block: str,
    dropped_block: str,
    *,
    overrides: Optional[dict[str, Any]] = None,
    tighter: bool = False,
) -> Any:
    """Compute the per-run history budget from the resolved model + real request.

    Pure and local (no network). The window is the resolved model's declared
    context size; an unknown window yields an inert budget and the bound falls
    back to the module constants. `overrides` is the test/operator seam — it may
    supply a known window or a reserved-output value, never fabricate one.
    """
    from .context_budget import DEFAULT_RESERVED_OUTPUT_TOKENS, compute_history_budget  # noqa: PLC0415

    overrides = overrides or {}
    reserved = int(overrides.get("reserved_output_tokens", DEFAULT_RESERVED_OUTPUT_TOKENS))
    # Window precedence: an explicit override (test seam) wins, else the
    # operator-declared `ModelSettings.contextWindow` (used when the catalog
    # cannot know the window), else compute_history_budget falls back to the
    # catalog resolver. A declared value is a real declaration, not a guess.
    window_override = overrides.get("window")
    if window_override is None:
        window_override = getattr(request.modelSettings, "context_window", None)
    if overrides.get("tighter") and not tighter:
        tighter = True
    tool_schemas = ""
    try:
        from .context_budget import tool_schema_text  # noqa: PLC0415

        tool_schemas = tool_schema_text(registry.schemas(allowed))
    except Exception:  # noqa: BLE001 - a schema read failure must not break the run
        tool_schemas = ""
    return compute_history_budget(
        provider=request.modelSettings.provider,
        model=request.modelSettings.model,
        system_prompt=system_prompt,
        tool_schemas=tool_schemas,
        profile_block=profile_block,
        skill_manifest=skill_manifest,
        memory_block=memory_block,
        dropped_block=dropped_block,
        user_turn=_user_message(request),
        absolute_max_turns=MAX_HISTORY_TURNS,
        absolute_max_chars=MAX_HISTORY_CHARS,
        reserved_output_tokens=reserved,
        tighter=tighter,
        window_override=window_override,
    )


def _assemble_run_messages(
    request: RunRequest,
    *,
    system_prompt: str,
    history_messages: list[BaseMessage],
    profile_block: str,
    skill_manifest: str,
    memory_block: str,
    dropped_block: str,
) -> list[BaseMessage]:
    """The full message list for one run, with the SAME slot order as before.

    Only the number of history messages varies per budget; the system-prompt
    head and the per-run block order are byte-stable within a run.
    """
    return [
        SystemMessage(content=system_prompt),
        *history_messages,
        *([SystemMessage(content=profile_block)] if profile_block else []),
        *([SystemMessage(content=skill_manifest)] if skill_manifest else []),
        *([SystemMessage(content=memory_block)] if memory_block else []),
        *([SystemMessage(content=dropped_block)] if dropped_block else []),
        HumanMessage(content=_user_message(request)),
    ]


def _is_context_overflow(error: Optional[dict[str, Any]]) -> bool:
    return bool(error) and error.get("code") == "CONTEXT_OVERFLOW"


def _history_bounded_data(
    budget: Any,
    *,
    kept_turns: int,
    dropped_turns: list[Any],
    retried: bool = False,
) -> dict[str, Any]:
    """The bounded, content-free payload for `memory.history_bounded`.

    Counts and estimated tokens only — never memory content or the dropped text.
    """
    from .eclipse_memory.profile import estimate_tokens  # noqa: PLC0415

    dropped_tokens = sum(estimate_tokens(t.content) for t in dropped_turns)
    return {
        "keptTurns": kept_turns,
        "droppedTurns": len(dropped_turns),
        "droppedTokensEstimate": dropped_tokens,
        "window": budget.window,
        "windowKnown": bool(budget.window_known),
        "tighterRetry": bool(retried),
    }


def _context_budget_blob(
    budget: Any, request: RunRequest, *, kind: str, retried: bool = False,
) -> Optional[dict[str, Any]]:
    """The additive `RunResult.context` blob for a completed/overflowed run.

    Present only when history was actually trimmed or the run overflowed, so an
    ordinary short run leaves `context` absent (old clients unaffected).
    """
    kept, dropped = _bounded_history(request, budget)
    if not dropped and kind != "overflow":
        return None
    data = _history_bounded_data(
        budget, kept_turns=len(kept), dropped_turns=dropped, retried=retried,
    )
    data["status"] = kind
    return data


async def _retry_with_tighter_budget(
    request: RunRequest,
    emitter: RunEmitter,
    final_state: dict[str, Any],
    *,
    base_budget: Any,
    overrides: dict[str, Any],
    system_prompt: str,
    profile_block: str,
    skill_manifest: str,
    memory_block: str,
    memory_service: Optional[Any],
    allowed: Optional[set[str]],
    registry: ToolRegistry,
    invoke: Any,
) -> tuple[dict[str, Any], Optional[Any]]:
    """Retry ONCE with a materially tighter history allowance.

    Only the history allowance changes: the system prompt, tools, per-run blocks
    and side-effecting tools are NOT re-run differently. An unknown-window budget
    (inert) is unaffected by `tighter`, so overflow on an unknown window fails
    honestly with no pointless second attempt. Returns
    `(final_state, retry_budget_or_None)`.
    """
    if not base_budget.effective:
        return final_state, None
    # Only recover when the overflow happened on the FIRST model call, before any
    # tool executed. Rebuilding the graph would otherwise re-run side-effecting
    # tools already executed this run.
    if int(final_state.get("step") or 1) > 1:
        return final_state, None
    tighter_budget = _history_budget(
        request, allowed, registry, system_prompt, profile_block, skill_manifest,
        memory_block, dropped_block="", overrides=overrides, tighter=True,
    )
    kept, _dropped = _bounded_history(request, tighter_budget)
    base_kept_count = len(_bounded_history(request, base_budget)[0])
    # Nothing left to remove: a second attempt would be identical, so do not make
    # one. The honest CONTEXT_OVERFLOW stands.
    if len(kept) >= base_kept_count:
        return final_state, None
    kept_messages = [
        HumanMessage(content=t.content) if t.role == "user" else AIMessage(content=t.content)
        for t in kept
    ]
    # Re-extract the (now larger) dropped window and carry it in the retry so the
    # attempt is materially smaller than the first, not merely a re-ask.
    _msgs, tighter_dropped_block, _dt = await _dropped_context_block(
        request, memory_service, emitter, tighter_budget, emit=False,
    )
    await emitter.emit("context.retry", {
        "reason": "context_overflow",
        "windowKnown": bool(tighter_budget.window_known),
        "keptTurns": len(kept),
        "maxHistoryChars": tighter_budget.max_history_chars,
    })
    retried_state = await invoke(kept_messages, tighter_dropped_block)
    return retried_state, tighter_budget


def _bounded_history(
    request: RunRequest, budget: Optional[Any] = None,
) -> tuple[list[Any], list[Any]]:
    """Return `(kept, dropped)` turns under the history bound.

    `kept` is the oldest-first list actually prompted; `dropped` is the prefix
    the bound removed. A history under the bound drops nothing — `dropped` is
    empty and the caller must behave exactly as before.

    The bound comes from the per-run measured `budget` when it is effective (the
    resolved model's window is known); otherwise it falls back to the module
    constants. The fallback is byte-for-byte today's behaviour, which is the
    safety property for an unknown window.
    """
    history = request.input.history or []
    if budget is not None and getattr(budget, "effective", False):
        max_turns = int(getattr(budget, "max_history_turns", MAX_HISTORY_TURNS))
        max_chars = int(getattr(budget, "max_history_chars", MAX_HISTORY_CHARS))
    else:
        max_turns = MAX_HISTORY_TURNS
        max_chars = MAX_HISTORY_CHARS
    if not history:
        return [], []
    trimmed = list(history[-max_turns:]) if max_turns > 0 else []
    dropped = list(history[: max(0, len(history) - max_turns)]) if max_turns > 0 else list(history)
    # Also cap total characters, dropping oldest turns first.
    total = sum(len(t.content) for t in trimmed)
    while trimmed and total > max_chars:
        total -= len(trimmed[0].content)
        dropped.append(trimmed[0])
        trimmed = trimmed[1:]
    return trimmed, dropped


def _history_messages(request: RunRequest, budget: Optional[Any] = None) -> list[BaseMessage]:
    """Prior conversation turns, oldest first, bounded so a long chat cannot
    blow the context window. Keeps the MOST RECENT turns when trimming."""
    trimmed, _dropped = _bounded_history(request, budget)
    return [
        HumanMessage(content=t.content) if t.role == "user" else AIMessage(content=t.content)
        for t in trimmed
    ]


async def _dropped_context_block(
    request: RunRequest,
    memory_service: Optional[Any],
    emitter: RunEmitter,
    budget: Optional[Any] = None,
    *,
    emit: bool = True,
) -> tuple[list[BaseMessage], str, list[Any]]:
    """The bounded history messages plus an inert dropped-context block ("").

    Returns `(messages, block, dropped_turns)`. When the history is under the
    bound nothing is dropped, so no block is produced and the message list is
    byte-identical to the pre-change behaviour. Extraction is deterministic-first
    and produces INERT candidates only. It is fail-closed: if extraction cannot
    complete, NO block is emitted (never a lossy summary) and an honest event is
    recorded. Extraction never blocks or fails the run.

    `emit=False` suppresses the extraction event, used when `execute_run`
    re-derives the history after measuring the dropped block's own cost (so the
    event is emitted exactly once).
    """
    kept, dropped = _bounded_history(request, budget)
    messages = [
        HumanMessage(content=t.content) if t.role == "user" else AIMessage(content=t.content)
        for t in kept
    ]
    if not dropped:
        return messages, "", dropped
    try:
        from .eclipse_memory.dropped_context import (  # noqa: PLC0415
            MAX_ITEMS,
            DroppedTurn,
            extract_dropped_context,
            render_dropped_context_block,
        )

        settings: dict[str, Any] = {}
        if memory_service is not None:
            try:
                settings = memory_service.policy.get_all()
            except Exception:  # noqa: BLE001 - policy read failure is not fatal
                settings = {}
        result = extract_dropped_context(
            [DroppedTurn(role=t.role, content=t.content) for t in dropped],
            settings=settings, user_id=request.userId,
        )
        model_used = False
        # Optional, policy-gated model-assisted extraction. It is additive to the
        # deterministic pass, inert, bounded, and fail-closed: any failure leaves
        # the deterministic result untouched and emits no lossy summary.
        if settings.get("dropped_context_model_extraction") and memory_service is not None:
            try:
                model_items = await _model_extract_dropped(
                    request, [DroppedTurn(role=t.role, content=t.content) for t in dropped],
                )
                if model_items:
                    merged = list(result.items)
                    seen = {(i.action, i.content) for i in merged}
                    for item in model_items:
                        key = (item.action, item.content)
                        if key not in seen:
                            merged.append(item)
                            seen.add(key)
                    result.items = merged[:MAX_ITEMS]
                    model_used = True
            except Exception:  # noqa: BLE001 - model extraction must never break the run
                model_used = False
        block = render_dropped_context_block(result)
        try:
            if emit:
                await emitter.emit(
                    "memory.dropped_context_extracted",
                    {
                        "droppedTurns": len(dropped),
                        "scanned": result.scanned,
                        "candidates": len(result.items),
                        "emitted": bool(block),
                        "ok": result.ok,
                        "modelAssisted": model_used,
                        "reason": result.reason or None,
                    },
                )
        except Exception:  # noqa: BLE001
            pass
        return messages, block, dropped
    except Exception as exc:  # noqa: BLE001 - extraction must never break a run
        try:
            if emit:
                await emitter.emit("memory.dropped_context_failed", {"error": str(exc), "droppedTurns": len(dropped)})
        except Exception:  # noqa: BLE001
            pass
        # Fail closed: emit no block at all, carry on.
        return messages, "", dropped



async def _model_extract_dropped(
    request: RunRequest, turns: list[Any],
) -> list[Any]:
    """Optionally ask the run's own model for INERT candidates from dropped turns.

    Uses the SAME model/provider the run already resolved (no new dependency, no
    extra client). Bounded by a short timeout and the extractor's own item cap.
    Any failure returns [] — the deterministic extraction is unaffected and the
    caller emits no lossy summary. Never raises to the caller.
    """
    from .eclipse_memory.dropped_context import (  # noqa: PLC0415
        build_extraction_prompt,
        parse_extraction_response,
    )

    prompt = build_extraction_prompt(turns)
    if not prompt:
        return []
    try:
        model = build_chat_model(request.modelSettings)
        response = await asyncio.wait_for(
            model.ainvoke([HumanMessage(content=prompt)]), timeout=20.0,
        )
    except Exception:  # noqa: BLE001 - absence/failure is not an error here
        return []
    text = _text(response)
    parsed = parse_extraction_response(text)
    return parsed.items if parsed.ok else []


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
    # reply). The gate is pure and writes nothing.
    from .eclipse_memory.is_trivial import is_trivial_turn  # noqa: PLC0415

    if is_trivial_turn(request.input.query):
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
    # runs. Nothing is written and the reply is unaffected.
    from .eclipse_memory.is_trivial import is_trivial_turn  # noqa: PLC0415

    if is_trivial_turn(request.input.query):
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
