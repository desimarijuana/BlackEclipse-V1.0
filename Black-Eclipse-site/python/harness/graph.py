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


def build_graph(
    request: RunRequest,
    registry: ToolRegistry,
    data_bridge: DataBridge,
    store: AgentMemoryStore,
    emitter: RunEmitter,
    bus: Optional[EventBus] = None,
    cancel_event: Optional[asyncio.Event] = None,
    retrieval_cache: Optional[Any] = None,
) -> Any:
    """Compile a LangGraph StateGraph for one run. Returns an awaitable app."""
    agent = resolve_agent(request)
    max_steps: int = agent.maxSteps or 8
    tool_timeout_ms = agent.toolTimeoutMs or 20_000
    run_timeout_s = (agent.runTimeoutMs or 120_000) / 1000
    allowed = set(agent.tools) if agent.tools else None

    model = build_chat_model(request.modelSettings)
    lc_tools = registry.langchain_tools(allowed)
    model_with_tools = model.bind_tools(lc_tools) if lc_tools else model

    # The retrieval layer is built lazily by the retrieval tools from `ctx`;
    # the shared process-wide cache is attached here so concurrent runs reuse
    # each other's in-flight/cached retrievals (Milestone 2H).
    ctx = ToolContext(
        run_id=request.runId,
        log=lambda m, d=None: None,
        data_bridge=data_bridge,
        retrieval_cache=retrieval_cache,
        emitter=emitter,
        memory_store=store,
    )
    registry.set_active_context(ctx)

    seen_calls: dict[str, int] = {}

    async def agent_node(state: GraphState) -> GraphState:
        step = state.get("step", 0) + 1
        await emitter.emit("model.requested", {"step": step, "messages": len(state["messages"])})
        # On the last allowed step, forbid tools so the model MUST answer from the
        # evidence it already gathered. Without this a tool-calling model can loop
        # until max steps and produce MAX_STEPS_EXCEEDED instead of an answer —
        # the exact failure that made the agent "unable to answer".
        finalizing = step >= max_steps
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
                message = f"Reached the maximum of {max_steps} steps without a final answer."
                await emitter.emit("run.failed", {"error": {"code": "MAX_STEPS_EXCEEDED", "message": message}})
                return {**state, **usage_state, "step": step, "error": {"code": "MAX_STEPS_EXCEEDED", "message": message}}
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
    )
    await emitter.emit("run.created", {"agentId": agent.id})
    store.update_run(request.runId, status="running", startedAt=started)
    await emitter.emit("run.started", {"maxSteps": agent.maxSteps, "provider": request.modelSettings.provider})

    messages: list[BaseMessage] = [
        SystemMessage(content=agent.systemPrompt),
        *_history_messages(request),
        HumanMessage(content=_user_message(request)),
    ]

    try:
        app = build_graph(request, registry, data_bridge, store, emitter, bus, cancel_event, retrieval_cache)
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
        return _result(request.runId, "failed", store, err)

    output = final_state.get("final") or ""
    store.update_run(request.runId, status="completed", output=output, finishedAt=now_iso())
    await emitter.emit("run.completed", {"steps": final_state.get("step", 0)})
    return _result(request.runId, "completed", store, None, output)


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
