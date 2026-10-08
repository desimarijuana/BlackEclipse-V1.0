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
import time
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
from .checkpoint_io import (
    checkpoint_payload_of as _checkpoint_payload_of,
    restore_messages as _restore_messages,
    serialize_messages as _serialize_messages,
)
from .code.workspace import resolve_workspace
from .events import EventBus, RunEmitter
from .model_stream import (
    FINALIZE_INSTRUCTION as _FINALIZE_INSTRUCTION,
    ainvoke_streaming as _ainvoke_streaming,
    message_text as _text,
)
from .models import build_chat_model
from .model_runtime import ErrorClass, ModelError, classify_exception, get_runtime
from .persistence import AgentMemoryStore, now_iso
from .schemas import AgentConfig, HarnessError, RunRequest, RunResult
from .tools import DataBridge, ToolContext, ToolRegistry

# Checkpoint (de)serialization lives in `checkpoint_io.py` so this execution
# graph stays under its size ratchet; imported above under the old local names.


def _resume_error(
    run_id: str, code: str, message: str, store: AgentMemoryStore,
) -> RunResult:
    """A structured, non-fresh failure for a bad resume request (Phase 1).

    Never persists a terminal status onto the existing run (a failed resume must
    not overwrite the run's real state) and never starts a fresh run in its place.
    """
    error = HarnessError(code=code, message=message)  # type: ignore[arg-type]
    return RunResult(runId=run_id, status="failed", error=error)


class GraphState(TypedDict, total=False):
    messages: Annotated[list[BaseMessage], add_messages]
    step: int
    tool_calls: int
    tool_errors: int
    prompt_tokens: int
    completion_tokens: int
    final: Optional[str]
    error: Optional[dict[str, Any]]
    # Phase 11 (bounded replanning): the replan count, the failures in the most
    # recent tool step, whether that step repeated the prior one, and the details
    # the replan directive names. Absent/zero for an ordinary run.
    replans: int
    step_failures: int
    stalled: bool
    last_turn_keys: list[str]
    step_failure_details: list[dict[str, Any]]


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


def _task_profile_of(request: RunRequest, agent: AgentConfig) -> str:
    """The task profile the ModelRouter scores against for this run (spec §14)."""
    from .model_runtime.integration import task_profile_of

    return task_profile_of(request, agent)


def _runtime_requirements(request: RunRequest) -> dict[str, Any]:
    """Routing requirements a run may carry via its input context (additive)."""
    from .model_runtime.integration import runtime_requirements

    return runtime_requirements(request)


def _runtime_policy_overrides(request: RunRequest) -> dict[str, Any]:
    """User/workflow routing overrides read from `input.context.modelPolicy`."""
    from .model_runtime.integration import runtime_policy_overrides

    return runtime_policy_overrides(request)
def _resolve_direct(request: Any) -> bool:
    """Whether a run edits the real folder or a disposable copy.

    An explicit `request.direct` always wins. When absent (None), a run edits
    DIRECTLY only if the active root is one the user chose and approved; the
    built-in repo root stays isolated.
    """
    explicit = getattr(request, "direct", None)
    if explicit is not None:
        return bool(explicit)
    from .code.workspace import trusted_root_selected  # noqa: PLC0415

    return trusted_root_selected()


def _effect_authorizer(
    approvals: Optional[Any],
    run_id: str,
    emitter: RunEmitter,
    workspace_id: Optional[str] = None,
) -> Optional[Any]:
    """The run's effect authorizer (composition lives in `code/authorizers.py`)."""
    from .code.authorizers import build_effect_authorizer  # noqa: PLC0415

    return build_effect_authorizer(approvals, run_id, emitter, workspace_id)


def effective_allowlist(
    agent: AgentConfig, registry: ToolRegistry, autonomy: Optional[str] = None,
) -> Optional[set[str]]:
    """The run's tool allowlist, with an explicit, narrow MCP opt-in.

    When the agent sets `allowMcpTools`, the allowlist is expanded to include the
    MCP tools CURRENTLY REGISTERED in the registry (names under the `mcp_`
    namespace). Registration already requires an enabled server, explicit
    per-tool selection and a read-only effect, so this cannot surface a merely
    discovered tool. Every other agent keeps its exact allowlist - the opt-in is
    per-agent and defaults off, so a restricted custom agent or skill can never
    reach an MCP tool it did not name. When the agent has NO allowlist (None =
    all tools), the expansion is a no-op.

    Phase 5: when an `autonomy` profile is given, the declared allowlist is
    NARROWED through the ONE policy authority (`code.policy.allowed_tools`), so a
    write/execute/external tool the profile does not permit is removed BEFORE the
    model sees its schema - the autonomy boundary is structural, not a prompt.
    """
    if agent.tools is None:
        return None
    allowed = set(agent.tools)
    if agent.allowMcpTools:
        allowed.update(name for name in registry.names() if name.startswith("mcp_"))
    if autonomy is not None:
        from .code.policy import allowed_tools  # noqa: PLC0415

        allowed = set(allowed_tools(autonomy, tuple(sorted(allowed))))
    return allowed


# Tools whose surface is gated by a policy key. A tool is dropped from the
# advertised schema AND the run's allowlist when its store is off, so the model
# is never told about a tool it cannot use.
def chat_code_allowlist(
    agent: AgentConfig, registry: ToolRegistry, autonomy: Optional[str],
) -> Optional[set[str]]:
    """The allowlist for a CHAT turn that carries a code profile (Phase 14).

    Only the finance agent (`eclipse-agent`) has a chat code profile, and only
    when the front door sent an autonomy (i.e. the deterministic classifier saw a
    coding request). The profile is `agents.CHAT_CODE_TOOLS`, narrowed through the
    ONE policy authority (`code.policy.allowed_tools`) so `plan_only` removes the
    write/execute tools and `edit_verify` keeps them — and the external actions
    are absent from the declared set entirely (they cannot be added back by a
    profile). Returns None when the agent is not the finance agent, or no autonomy
    was sent, so the caller keeps the ordinary surface.
    """
    from .agents import CHAT_CODE_TOOLS  # noqa: PLC0415

    if agent.id != "eclipse-agent" or not autonomy:
        return None
    from .code.policy import allowed_tools  # noqa: PLC0415

    return set(allowed_tools(autonomy, tuple(CHAT_CODE_TOOLS)))


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
    autonomy: Optional[str] = None,
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
    # A code-agent run with no explicit autonomy resolves to edit_verify, so
    # write/execute tools are available by default; an ordinary finance run keeps
    # `autonomy=None` and is never narrowed.
    effective_autonomy = autonomy
    if effective_autonomy is None and agent.id == "code-agent":
        effective_autonomy = "edit_verify"
    # Phase 14: a CHAT coding turn carries an autonomy on the finance agent. Apply
    # the chat code profile HERE, after the existing autonomy narrowing, so there
    # is exactly ONE place a run's profile is computed and `plan_only` still
    # removes the write/execute tools.
    chat_profile = chat_code_allowlist(agent, registry, autonomy)
    allowed = chat_profile if chat_profile is not None else effective_allowlist(
        agent, registry, effective_autonomy,
    )
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
    approvals: Optional[Any] = None,
    lineage: Optional[Any] = None,
    resume_from: Optional[dict[str, Any]] = None,
    code_store: Optional[Any] = None,
    code_ledger: Optional[Any] = None,
    code_intel_runtime: Optional[Any] = None,
    evidence_store: Optional[Any] = None,
    vision_sink: Optional[Any] = None,
    # The run's document-intelligence result collector, so a `document_*` tool's
    # structured result reaches the run blob the right sidebar renders.
    document_sink: Optional[Any] = None,
    market: Optional[Any] = None,
    # The Portfolio Accounting Engine service, so the `portfolio_*` tools reach
    # the ONE ledger/valuation service (reusing the per-run market gateway).
    portfolio: Optional[Any] = None,
    # The Quant Engine bundle (store), so the `quant_*` tools can persist
    # strategies and experiments on the ONE agent-memory connection.
    quant: Optional[Any] = None,
    # The unified Retrieval / Search Intelligence service, so the `*_search`
    # tools reach the ONE search layer (vector + FTS + rerank).
    search: Optional[Any] = None,
) -> Any:
    """Compile a LangGraph StateGraph for one run. Returns an awaitable app.

    `lineage` is the run's `RunLineage` store (Phase 1), used to write durable
    checkpoints at every boundary and to reuse an already-executed tool result on
    resume. `resume_from` is the latest checkpoint payload when this build is a
    RESUME (None for a fresh run), so already-completed tool calls are skipped
    rather than re-executed.
    """
    agent = resolve_agent(request)
    # On a resume, reuse the allowlist + accumulated counters recorded at the last
    # durable boundary so the run continues exactly where it stopped.
    _resume_payload = (resume_from or {}).get("payload") or {}
    if resume_from and isinstance(_resume_payload.get("allowlist"), list):
        allowed = set(_resume_payload["allowlist"])
    max_steps: int = agent.maxSteps or 8
    tool_timeout_ms = agent.toolTimeoutMs or 20_000
    run_timeout_s = (agent.runTimeoutMs or 120_000) / 1000
    if request.autonomy in ("edit_verify", "approve_external"):
        max_steps = max(max_steps, 24); run_timeout_s = max(run_timeout_s, 600.0)
    # A hard total tool-call budget. A skill manifest declares
    # `limits.maxToolCalls`; this ENFORCES it in the loop (a skill cannot exceed
    # its declared budget by prompting or by looping). None = unbounded (chat).
    max_tool_calls: Optional[int] = agent.maxToolCalls
    # Phase 11: bounded replanning is FLAG-GATED and DEFAULT OFF. When enabled, a
    # failed or stalled tool step routes through ONE `replan` node (a revised
    # approach) before the agent continues — never a second loop or registry.
    from .replan import (  # noqa: PLC0415
        ReplanBudget,
        build_replan_instruction,
        replan_enabled,
        should_replan,
    )

    replan_budget: Optional[ReplanBudget] = ReplanBudget() if replan_enabled() else None
    # `allowed` is the policy-resolved surface from `execute_run` (a disabled
    # store's tool already removed). Fall back to the raw allowlist for direct
    # callers/tests that build a graph without resolving the surface.
    if allowed is None:
        allowed = effective_allowlist(agent, registry)

    # ── Model runtime (provider-agnostic) ──────────────────────────────────
    # The agent no longer talks to a provider. It asks the ModelRuntime to
    # resolve the run's settings through the ModelRouter, then builds the model
    # THROUGH the runtime. The module-level `build_chat_model` is passed as the
    # builder so the existing test seam (and the single construction path) is
    # preserved; the runtime still owns routing, health and usage accounting.
    runtime = get_runtime()
    resolution = runtime.resolve_for_run(
        request.modelSettings,
        task=_task_profile_of(request, agent),
        requirements=_runtime_requirements(request),
        policy_overrides=_runtime_policy_overrides(request),
    )
    model = runtime.build(
        resolution.settings, builder=build_chat_model, adapter=resolution.adapter
    )
    model = runtime.prepare_model(model, resolution)
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
        # The read-only workspace binding for this run (Phase 1). Absent ⇒ no
        # code capability (the default-actor rule).
        workspace=resolve_workspace(request.workspace),
        # Phase 2: the run's autonomy profile and the code-workspace store.
        autonomy=request.autonomy,
        code_store=code_store,
        # The process-wide CIUE runtime (LSP manager + code index/watcher), so the
        # `code_*` tools resolve one shared runtime instead of a global.
        code_intel_runtime=code_intel_runtime,
        # Phase 4: the run's verification ledger — every command execution is
        # recorded here so the final answer can be checked against proven fact.
        code_ledger=code_ledger,
        # Phase 7: the resolved allowlist (a delegate narrows children against it)
        # and how deep this run sits in a delegation chain.
        allowed=allowed,
        delegation_depth=int((request.input.context or {}).get("delegationDepth") or 0),
        # Phase 8: the analysis sandbox is OFF per run unless the caller enables it.
        analysis_enabled=bool(request.analysisEnabled),
        # The approval store, so the terminal authorizer can claim a single-use
        # approval for an `ask`-classified command.
        approvals=approvals,
        # Approval cards: when the request asked to pause, a non-read tool with no
        # matching approval blocks for the operator's decision instead of being
        # refused. The wait is bounded by the agent's run deadline.
        pause_for_approval=str(getattr(request, "approvalMode", "") or "") == "ask",
        approval_timeout_s=max(30.0, run_timeout_s - 15.0),
        # Folder-selection: a run bound to a user-chosen trusted folder edits it
        # directly (that is the point of choosing it); the built-in repo root
        # stays isolated. An explicit `request.direct` always wins.
        direct=_resolve_direct(request),
        # The executing agent, so the terminal subsystem can attribute a session
        # or process to it (multi-agent isolation + observability).
        agent_id=agent.id,
        # The shared EvidenceStore for the web research engine (bound to the ONE
        # agent-memory connection). None = the research tools build their own from
        # the run's memory store (still persisted, just not the shared instance).
        evidence_store=evidence_store,
        # The run's vision-result collector, so a `vision_*` tool's structured
        # result reaches the run blob the right sidebar renders.
        vision_sink=vision_sink,
        # The run's document-intelligence collector (same idiom).
        document_sink=document_sink,
        # The Market Data Layer: gateway (routing + quality), durable snapshot/
        # instrument store and stream manager, as one bundle. Shared process-wide.
        market_gateway=getattr(market, "gateway", None),
        market_store=getattr(market, "store", None),
        market_stream=getattr(market, "stream", None),
        # Quant Engine store (strategies + experiments) on the ONE agent-memory
        # connection, so `quant_*` tools persist and replay research.
        quant_store=getattr(quant, "store", None),
        # The Portfolio Accounting Engine service, so `portfolio_*` tools reach
        # the ONE ledger/valuation engine and the per-run market gateway.
        portfolio_service=getattr(portfolio, "service", None),
        # The unified search service, so the retrieval/search tools reach the ONE
        # index. The run's workspace/owner scope the agent's authorized results.
        search=search,
        workspace_id=request.workspaceId,
    )
    registry.set_active_context(ctx)

    def _checkpoint_payload(state: GraphState) -> dict[str, Any]:
        """A bounded checkpoint reference — enough to resume, never a trace."""
        last = state["messages"][-1] if state.get("messages") else None
        pending = [
            {"id": c.get("id"), "name": c.get("name"), "args": c.get("args")}
            for c in (getattr(last, "tool_calls", None) or [])
        ]
        return {
            "step": state.get("step", 0),
            "toolCalls": state.get("tool_calls", 0),
            "toolErrors": state.get("tool_errors", 0),
            "replans": state.get("replans", 0),
            "promptTokens": state.get("prompt_tokens", 0),
            "completionTokens": state.get("completion_tokens", 0),
            "pendingToolCalls": pending,
            "allowlist": sorted(allowed) if allowed else None,
            "messages": _serialize_messages(state.get("messages", [])),
        }

    async def _write_checkpoint(kind: str, state: GraphState) -> None:
        if lineage is None:
            return
        try:
            lineage.save_checkpoint(request.runId, kind, _checkpoint_payload(state))
        except Exception:  # noqa: BLE001 - a checkpoint must never break a run
            pass

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
        _step_started = time.monotonic()
        try:
            response = await _ainvoke_streaming(
                active_model, model_messages, run_timeout_s, emitter, finalizing
            )
        except asyncio.TimeoutError:
            runtime.record_step(
                resolution,
                latency_ms=(time.monotonic() - _step_started) * 1000.0,
                ok=False,
                error=ModelError(error_class=ErrorClass.TIMEOUT, message="model call timed out"),
                run_id=request.runId,
            )
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
                runtime.record_step(
                    resolution,
                    latency_ms=(time.monotonic() - _step_started) * 1000.0,
                    ok=False,
                    error=ModelError(
                        error_class=ErrorClass.CONTEXT_OVERFLOW, message=message,
                        provider_id=provider, model_id=model_name,
                    ),
                    run_id=request.runId,
                )
                await emitter.emit(
                    "context.overflow",
                    {"step": step, "provider": provider, "windowKnown": window is not None},
                )
                return {**state, "step": step, "error": {"code": code, "message": message}}
            runtime.record_step(
                resolution,
                latency_ms=(time.monotonic() - _step_started) * 1000.0,
                ok=False,
                error=classify_exception(exc, provider_id=request.modelSettings.provider, model_id=request.modelSettings.model),
                run_id=request.runId,
            )
            await emitter.emit("run.failed", {"error": {"code": "PROVIDER_ERROR", "message": str(exc)}})
            return {**state, "step": step, "error": {"code": "PROVIDER_ERROR", "message": str(exc)}}

        runtime.record_step(
            resolution,
            response=response,
            latency_ms=(time.monotonic() - _step_started) * 1000.0,
            ok=True,
            run_id=request.runId,
        )
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
            completed: GraphState = {
                **state,
                **usage_state,
                "step": step,
                "messages": [*state["messages"], response],
                "final": final_text,
            }
            await _write_checkpoint("agent_final", completed)
            return completed

        tool_state: GraphState = {
            **state, **usage_state, "step": step, "messages": [*state["messages"], response],
        }
        # Durable boundary: one checkpoint per completed agent step, BEFORE the
        # tools node runs, so a crash during tool execution resumes here.
        await _write_checkpoint("agent_step", tool_state)
        return tool_state

    async def tools_node(state: GraphState) -> GraphState:
        last = state["messages"][-1]
        calls = getattr(last, "tool_calls", None) or []
        tool_calls = state.get("tool_calls", 0)
        tool_errors = state.get("tool_errors", 0)
        out_messages: list[BaseMessage] = []
        # The agent step that issued these calls — the resume idempotency key
        # scopes a call to (runId, stepIndex, toolCallId).
        step_index = state.get("step", 0)
        # Phase 11 replanning signals: the keys of THIS turn, the failures in it,
        # and (compared against the prior turn) whether the agent is stalling.
        prev_keys = list(state.get("last_turn_keys") or [])
        turn_keys: list[str] = []
        failure_details: list[dict[str, Any]] = []

        # Duplicate suppression is scoped to THIS agent step (one model turn),
        # not the whole run. The guard exists to stop one turn from issuing the
        # same call twice; a run-scoped map also blocked a legitimate re-issue in
        # a later turn — the next page of a listing, re-polling a price after new
        # evidence, a retry after a transient failure. Keying on
        # `(name, canonical-args)` within a single `tools_node` invocation keeps
        # the intra-turn refusal exactly as before while letting a later turn
        # repeat a call. Do NOT key on the assistant message id: the same model
        # message can legitimately recur across steps, which would reintroduce
        # the bug. A cross-turn re-issue does not multiply upstream calls — the
        # retrieval layer still deduplicates identical data fetches per run via
        # the shared `retrieval_cache` passed into `build_graph`.
        seen_calls: dict[str, int] = {}

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
                failure_details.append({"name": name, "code": "TOOL_BUDGET_EXCEEDED"})
                out_messages.append(ToolMessage(content=result_text, tool_call_id=call_id))
                continue

            tool_calls += 1
            # A safe, bounded "what" for the live stream (the command, the file
            # path, the changed paths) — never file content. Derived by a pure
            # function so the event carries display metadata only.
            from .code.activity import tool_detail  # noqa: PLC0415

            detail = tool_detail(name, args if isinstance(args, dict) else {})
            await emitter.emit("tool.requested", {
                "name": name, "toolCallId": call_id, "step": state.get("step"),
                **({"detail": detail} if detail else {}),
            })

            key = _stable_key(name, args)
            turn_keys.append(key)
            # Resume idempotency: if this exact call already executed in a prior
            # attempt of this run, REUSE its recorded result instead of running it
            # again. This is what makes resume safe for a side-effecting tool.
            already = (
                lineage.was_tool_executed(request.runId, step_index, call_id)
                if lineage is not None else None
            )
            if already is not None:
                result_text = already["text"]
                if not already["ok"]:
                    tool_errors += 1
                    failure_details.append({"name": name, "code": "TOOL_ERROR"})
                await emitter.emit(
                    "tool.completed" if already["ok"] else "tool.failed",
                    {"name": name, "toolCallId": call_id, "resumed": True,
                     "code": None if already["ok"] else "TOOL_ERROR"},
                )
            elif seen_calls.get(key, 0) > 0:
                result_text = (
                    f"Duplicate call to {name!r} with identical arguments was not executed again. "
                    "Use the earlier result."
                )
                await emitter.emit("tool.failed", {"name": name, "toolCallId": call_id, "code": "TOOL_FORBIDDEN"})
                tool_errors += 1
                failure_details.append({"name": name, "code": "TOOL_FORBIDDEN"})
            else:
                seen_calls[key] = seen_calls.get(key, 0) + 1
                result = await registry.execute(
                    name, call_id, args, ctx, allowed=allowed, timeout_ms=tool_timeout_ms
                )
                result_text = result.text
                # Record the executed call so a resume never re-runs it.
                if lineage is not None:
                    lineage.mark_tool_executed(request.runId, step_index, call_id, result)
                if result.ok:
                    from .code.activity import tool_result_summary  # noqa: PLC0415

                    summary = tool_result_summary(name, result.data)
                    await emitter.emit(
                        "tool.completed",
                        {
                            "name": name,
                            "toolCallId": call_id,
                            "durationMs": result.duration_ms,
                            "truncated": result.truncated,
                            "shownChars": result.shown_chars,
                            "totalChars": result.total_chars,
                            **({"summary": summary} if summary else {}),
                        },
                    )
                    # A trimmed result is its own honest signal (Phase 3): emitted
                    # once, carrying sizes only, so the stream shows the model got
                    # a partial result without re-parsing the text marker.
                    if result.truncated:
                        await emitter.emit(
                            "tool.truncated",
                            {
                                "name": name,
                                "toolCallId": call_id,
                                "shownChars": result.shown_chars,
                                "totalChars": result.total_chars,
                            },
                        )
                else:
                    tool_errors += 1
                    failure_details.append(
                        {"name": name, "code": result.error.code if result.error else "TOOL_ERROR"}
                    )
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
        step_failures = tool_errors - int(state.get("tool_errors", 0) or 0)
        turn_set = sorted(set(turn_keys))
        stalled = bool(turn_set) and turn_set == sorted(set(prev_keys))
        tool_done: GraphState = {
            **state, "messages": [*state["messages"], *out_messages],
            "tool_calls": tool_calls, "tool_errors": tool_errors,
            "step_failures": step_failures,
            "stalled": stalled,
            "last_turn_keys": turn_set,
            "step_failure_details": failure_details,
        }
        # Durable boundary: a checkpoint after the tool results are recorded.
        await _write_checkpoint("tool_results", tool_done)
        return tool_done

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
        # Phase 11: only when the flag wired a replan node AND a bounded replan
        # remains do we divert through one revision step.
        if replan_budget is not None and should_replan(
            replans=int(state.get("replans", 0) or 0),
            budget=replan_budget,
            step_failures=int(state.get("step_failures", 0) or 0),
            stalled=bool(state.get("stalled")),
        ):
            return "replan"
        return "agent"

    async def replan_node(state: GraphState) -> GraphState:
        """One bounded revision step on the SAME loop (Phase 11).

        It appends INERT prose naming what failed or stalled; it authorizes
        nothing and cannot widen the allowlist. The model may act on it or
        ignore it. `run.replanned` makes the diversion honest and observable.
        """
        reason = should_replan(
            replans=int(state.get("replans", 0) or 0),
            budget=replan_budget,
            step_failures=int(state.get("step_failures", 0) or 0),
            stalled=bool(state.get("stalled")),
        ) or "tool_failures"
        replans = int(state.get("replans", 0) or 0) + 1
        instruction = build_replan_instruction(
            reason,
            failures=state.get("step_failure_details") or [],
            stalled_calls=state.get("last_turn_keys") or [],
        )
        await emitter.emit("run.replanned", {
            "replan": replans,
            "reason": reason,
            "maxReplans": replan_budget.max_replans if replan_budget else 0,
        })
        revised: GraphState = {
            **state,
            "replans": replans,
            "messages": [*state["messages"], HumanMessage(content=instruction)],
            # Clear the trigger so only a new failure/stall causes another replan.
            "step_failures": 0,
            "stalled": False,
        }
        await _write_checkpoint("replan", revised)
        return revised

    async def exhausted_node(state: GraphState) -> GraphState:
        message = f"Reached the maximum of {max_steps} steps without a final answer."
        await emitter.emit("run.failed", {"error": {"code": "MAX_STEPS_EXCEEDED", "message": message}})
        exhausted: GraphState = {"error": {"code": "MAX_STEPS_EXCEEDED", "message": message}}
        await _write_checkpoint("terminal", {**state, **exhausted})
        return {**state, **exhausted}

    graph = StateGraph(GraphState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", tools_node)
    graph.add_node("exhausted", exhausted_node)
    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", route_after_agent, {"tools": "tools", END: END})
    if replan_budget is not None:
        graph.add_node("replan", replan_node)
        graph.add_conditional_edges(
            "tools", route_after_tools,
            {"replan": "replan", "agent": "agent", "exhausted": "exhausted"},
        )
        graph.add_edge("replan", "agent")
    else:
        graph.add_conditional_edges("tools", route_after_tools, {"agent": "agent", "exhausted": "exhausted"})
    graph.add_edge("exhausted", END)
    return graph.compile()


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
    code_store: Optional[Any] = None,
    code_intel_runtime: Optional[Any] = None,
    evidence_store: Optional[Any] = None,
    market: Optional[Any] = None,
    portfolio: Optional[Any] = None,
    quant: Optional[Any] = None,
    search: Optional[Any] = None,
) -> RunResult:
    """Run the graph and write the terminal status exactly once."""
    from .run_lineage import RunLineage  # noqa: PLC0415

    agent = resolve_agent(request)
    emitter = RunEmitter(request.runId, store, bus)
    lineage = RunLineage(store)
    if code_store is None:
        from .code.store import CodeWorkspaceStore  # noqa: PLC0415

        code_store = CodeWorkspaceStore(store)
    # Phase 4: the per-run verification ledger. Rehydrated from the persisted blob
    # when resuming (EMPTY when absent, so a resumed run starts unverified); a
    # fresh run starts empty.
    from .code.verify import VerificationLedger  # noqa: PLC0415

    _prior_run = store.get_run(request.runId)
    code_ledger = VerificationLedger.from_blob(
        request.runId, (_prior_run or {}).get("codeVerification"),
    )
    started = now_iso()
    # Resume, when requested, is validated BEFORE a run row is created so a
    # missing checkpoint / a terminal run never silently starts a fresh run.
    resume_from: Optional[dict[str, Any]] = None
    if request.resumeFrom:
        existing = store.get_run(request.runId)
        if existing is None:
            return _resume_error(request.runId, "RESUME_CONFLICT", "no run exists to resume", store)
        checkpoint = lineage.latest_checkpoint(request.runId)
        if checkpoint is None:
            return _resume_error(
                request.runId, "CHECKPOINT_NOT_FOUND",
                "no checkpoint exists for this run — it cannot be resumed", store,
            )
        if existing.get("status") in ("completed", "failed", "cancelled"):
            return _resume_error(
                request.runId, "RESUME_CONFLICT",
                f"run is already in terminal status '{existing.get('status')}'", store,
            )
        resume_from = checkpoint
        # Re-enter the SAME run: keep its identity, re-mark it running.
        lineage.set_run_parent(request.runId, request.parentRunId)
        store.update_run(request.runId, status="running", startedAt=started)
        await emitter.emit("run.resumed", {"checkpointId": checkpoint["id"], "step": (checkpoint.get("payload") or {}).get("step")})
    else:
        # A caller (the code-task route) may have pre-created the run row so it
        # could write a FK-bound `task.created` checkpoint first. Reuse that row
        # instead of re-inserting it; any other pre-existing row is a genuine
        # duplicate and still fails loudly.
        prior_status = (_prior_run or {}).get("status")
        if _prior_run is None:
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
        elif prior_status != "created":
            raise RuntimeError(
                f"run {request.runId!r} already exists in status {prior_status!r}"
            )
        # Record lineage AFTER the row exists (the columns are owned by the
        # lineage module, not the ratcheted core store).
        lineage.set_run_parent(request.runId, request.parentRunId, request.workflowId)
        await emitter.emit("run.created", {"agentId": agent.id})
        store.update_run(request.runId, status="running", startedAt=started)
        await emitter.emit("run.started", {"maxSteps": agent.maxSteps, "provider": request.modelSettings.provider})

    # Phase 4: an unambiguous supported financial comparison is routed through the
    # deterministic evidence gate BEFORE the ordinary agent graph, so it does not
    # also run a financial tool loop (no duplicate retrieval, no contradictory
    # answer). Anything unsupported/uncertain returns None and falls through.
    research = None
    if resume_from is None:
        # A resumed run was already past classification (it has checkpoints), so
        # it does not re-enter the research gate.
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
    from .prompt_segments import build_prompt_plan, runtime_context_block  # noqa: PLC0415

    # Surface honesty (Milestone 4): resolve the tool surface AND the system
    # prompt FROM POLICY per run — never at import or __init__ time. A disabled
    # store drops its tool from the bound schema and its guidance from the
    # prompt. The resolved prompt is byte-stable for the whole run; a policy
    # change takes effect on the NEXT run.
    try:
        surface_settings = memory_service.policy.get_all() if memory_service is not None else {}
    except Exception:  # noqa: BLE001 - a policy read failure falls back to the full surface
        surface_settings = {}
    allowed, system_prompt = resolve_surface(
        agent, registry, surface_settings, request.autonomy,
    )

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

    # The runtime date/time block: the run's real clock, rendered as its own
    # per-run block (never in the byte-stable system-prompt head). It gives the
    # model the as-of period it needs without a shell call and is excluded from
    # the cache key so a new run date never invalidates the reusable prefix.
    runtime_context = runtime_context_block(request.runId)

    prompt_plan = build_prompt_plan(
        system_prompt=system_prompt,
        agent_id=agent.id,
        tool_names=list(allowed) if allowed else list(registry.names()),
        profile_block=profile_block,
        profile_snapshot_id=profile_snapshot_id,
        skill_manifest=skill_manifest,
        skill_manifest_version=skill_manifest_version,
        runtime_context=runtime_context,
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
        memory_block, "", runtime_context=runtime_context, overrides=budget_overrides,
    )
    history_messages, dropped_block, dropped_turns = await _dropped_context_block(
        request, memory_service, emitter, budget,
    )
    budget = _history_budget(
        request, allowed, registry, system_prompt, profile_block, skill_manifest,
        memory_block, dropped_block, runtime_context=runtime_context, overrides=budget_overrides,
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

    # Ordinary-run vision collection: a `vision_*` tool hands its structured
    # result here so the run carries a bounded vision blob for the right sidebar
    # (asset ids, regions, OCR, confidence, provenance). Additive and best-effort.
    from .vision.collector import VisionCollector  # noqa: PLC0415

    vision_collector = VisionCollector()

    # Ordinary-run document collection: a `document_*` tool hands its structured
    # result here so the run carries a bounded document blob for the right sidebar
    # (type, pages, status, capabilities, entities, evidence counts). Best-effort.
    from .document_intelligence.collector import DocumentCollector  # noqa: PLC0415

    document_collector = DocumentCollector()

    # Bounded recovery (Milestone 4): if the run failed with a classified
    # CONTEXT_OVERFLOW, retry ONCE with a materially tighter history budget. The
    # terminal status is persisted once, below, after recovery resolves.
    # Resume (Phase 1): rebuild the run state from the recorded checkpoint so the
    # graph continues at the boundary it stopped at instead of starting fresh.
    # Already-executed tool calls are reused (not re-run) via the idempotency
    # ledger wired into `build_graph`.
    resume_state: Optional[dict[str, Any]] = None
    if resume_from is not None:
        payload = resume_from.get("payload") or {}
        resume_state = {
            "messages": _restore_messages(payload.get("messages") or []),
            "step": int(payload.get("step", 0)),
            "tool_calls": int(payload.get("toolCalls", 0)),
            "tool_errors": int(payload.get("toolErrors", 0)),
            "prompt_tokens": int(payload.get("promptTokens", 0)),
            "completion_tokens": int(payload.get("completionTokens", 0)),
            "final": None,
        }

    async def _invoke_with_history(
        history_msgs: list[BaseMessage], dropped: Optional[str] = None,
    ) -> dict[str, Any]:
        if resume_state is not None and resume_state.get("messages"):
            initial_state: dict[str, Any] = dict(resume_state)
        else:
            run_messages = _assemble_run_messages(
                request, system_prompt=system_prompt, history_messages=history_msgs,
                profile_block=profile_block, skill_manifest=skill_manifest,
                memory_block=memory_block,
                dropped_block=dropped if dropped is not None else dropped_block,
                runtime_context=runtime_context,
            )
            initial_state = {
                "messages": run_messages,
                "step": 0,
                "tool_calls": 0,
                "tool_errors": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "final": None,
            }
        app = build_graph(
            request, registry, data_bridge, store, emitter, bus, cancel_event,
            retrieval_cache, memory_service, skill_registry,
            _effect_authorizer(approvals, request.runId, emitter, request.workspaceId),
            memory_router,
            allowed=allowed,
            source_sink=source_collector,
            mcp_manager=mcp_manager,
            approvals=approvals,
            lineage=lineage,
            resume_from=resume_from,
            code_store=code_store,
            code_ledger=code_ledger,
            code_intel_runtime=code_intel_runtime,
            evidence_store=evidence_store,
            vision_sink=vision_collector.add,
            document_sink=document_collector.add,
            market=market,
            portfolio=portfolio,
            quant=quant,
            search=search,
        )
        return await app.ainvoke(initial_state)

    retry_budget: Optional[Any] = None
    try:
        final_state = await _invoke_with_history(history_messages)
        if _is_context_overflow(final_state.get("error")):
            final_state, retry_budget = await _retry_with_tighter_budget(
                request, emitter, final_state, base_budget=budget,
                overrides=budget_overrides,
                system_prompt=system_prompt, profile_block=profile_block,
                skill_manifest=skill_manifest, memory_block=memory_block,
                runtime_context=runtime_context,
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
    # Phase 4: make the answer consistent with what the executor actually
    # recorded. A pass-claim with no zero-exit execution is marked, never
    # asserted — the same discipline the finance renderer applies to claims.
    from .code.verify import enforce_run_answer  # noqa: PLC0415

    output, code_verification_blob = await enforce_run_answer(
        output, code_ledger, repair_outcome=None, emitter=emitter,
    )
    # Phase 14: record the run's code profile ALONGSIDE the verification ledger, so
    # a reader (the chat capability panel) can name what Eclipse set out to do. The
    # profile rides in the existing additive blob — no new persisted column, no
    # migration. Only a coding turn carries one; an ordinary run's blob is
    # unchanged.
    if request.autonomy or request.workspaceId:
        code_verification_blob = dict(code_verification_blob or {})
        if request.autonomy:
            code_verification_blob["autonomy"] = request.autonomy
        if request.workspaceId:
            code_verification_blob["workspaceId"] = request.workspaceId
    store.update_run(request.runId, codeVerification=code_verification_blob)
    # Universal financial-fact enforcement (finance_facts.enforce): if the answer
    # asserts a metric the run's own analysis EXCLUDED (ambiguous definition, no
    # period, superseded), or states one side of a cross-source conflict, append the
    # disclosure rather than silently presenting an unverified figure as clean.
    # Deterministic, no model call; a no-op when the run retrieved no finance facts.
    finance_disclosures: list[str] = []
    finance_presentable = True
    finance_excluded: list[str] = []
    try:
        from .finance_facts.enforce import disclosure_note, enforce_finance_answer  # noqa: PLC0415

        finance_analysis = source_collector.finance_analysis()
        if finance_analysis:
            verdict = enforce_finance_answer(output, finance_analysis)
            finance_disclosures = verdict.required_disclosures
            finance_presentable = bool(finance_analysis.get("presentable", True))
            finance_excluded = list(finance_analysis.get("excluded") or [])
            if finance_disclosures:
                note = disclosure_note(finance_disclosures)
                output = f"{output}\n\n{note}" if output.strip() else note
            await emitter.emit("finance.analysis", {
                "presentable": finance_presentable,
                "excluded": finance_excluded,
                "disclosures": finance_disclosures,
            })
    except Exception:  # noqa: BLE001 - enforcement is additive, never fatal
        pass
    context_blob = _context_budget_blob(
        final_budget, request, kind="completed", retried=retry_budget is not None,
    )
    # Provenance collected from this run's retrieval tool calls (None when the
    # run consulted no sources, so an empty panel is never shown). An ordinary
    # run's collected blob carries status `collected`, distinct from a gated
    # research run's `accepted`/`partial`/`rejected`.
    research_blob = source_collector.to_research_blob()
    # Vision results collected from this run's `vision_*` tool calls (None when no
    # vision tool ran), shaped for the right sidebar.
    vision_blob = vision_collector.to_blob()
    # Document results collected from this run's `document_*` tool calls (None when
    # no document tool ran), shaped for the right sidebar.
    documents_blob = document_collector.to_blob()
    store.update_run(
        request.runId, status="completed", output=output, finishedAt=now_iso(),
        context=context_blob,
        **( {"research": research_blob} if research_blob else {} ),
        **( {"vision": vision_blob} if vision_blob else {} ),
        **( {"documents": documents_blob} if documents_blob else {} ),
    )
    # Durable terminal boundary: a resume of a completed run is a RESUME_CONFLICT.
    if lineage is not None:
        try:
            lineage.save_checkpoint(request.runId, "terminal_completed", _checkpoint_payload_of(final_state))
        except Exception:  # noqa: BLE001 - a checkpoint must never break a run
            pass
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
    result.vision = vision_blob
    result.documents = documents_blob
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
        # Route research through the ModelRuntime for the financial_research task
        # profile (reasoning + tools + context), still building via the one
        # factory so the graph's test seam is preserved.
        _runtime = get_runtime()
        _resolution = _runtime.resolve_for_run(
            request.modelSettings, task="financial_research"
        )
        model = _runtime.build(
            _resolution.settings, builder=build_chat_model, adapter=_resolution.adapter
        )
        model = _runtime.prepare_model(model, _resolution)
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


# `MAX_HISTORY_TURNS` / `MAX_HISTORY_CHARS` and the history-bounding helpers live
# in `history.py` (re-exported below) so this graph stays under its size ratchet.


def _history_budget(
    request: RunRequest,
    allowed: Optional[set[str]],
    registry: ToolRegistry,
    system_prompt: str,
    profile_block: str,
    skill_manifest: str,
    memory_block: str,
    dropped_block: str,
    runtime_context: str = "",
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
        runtime_context=runtime_context,
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
    runtime_context: str = "",
) -> list[BaseMessage]:
    """The full message list for one run, with the SAME slot order as before.

    Only the number of history messages varies per budget; the system-prompt
    head and the per-run block order are byte-stable within a run. The
    run-scoped `runtime_context` block sits immediately after the system head so
    the stable head prefix is unaffected.
    """
    return [
        SystemMessage(content=system_prompt),
        *([SystemMessage(content=runtime_context)] if runtime_context else []),
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
    runtime_context: str,
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
        memory_block, "", runtime_context=runtime_context, overrides=overrides, tighter=True,
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


# History bounding + dropped-context extraction live in `history.py` (size
# ratchet) and are re-exported here so existing callers/tests are unchanged.
from .history import (  # noqa: E402,F401
    MAX_HISTORY_CHARS,
    MAX_HISTORY_TURNS,
    _bounded_history,
    _dropped_context_block,
    _history_messages,
    _model_extract_dropped,
)




# Per-run context blocks + memory/learning outcome helpers were extracted to
# graph_context.py to keep this execution graph under its size ratchet. They
# are re-exported here so existing callers/tests (rom harness.graph import
# _memory_context) are unchanged.
from .graph_context import (  # noqa: E402,F401
    _agent_tool_names,
    _apply_memory_intent,
    _create_explicit_skill_draft,
    _is_recurring_statement,
    _learning_eligibility,
    _memory_blob,
    _memory_context,
    _outcome_blob,
    _profile_context,
    _skill_manifest_context,
    learning_eligibility_for_run,
)


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
    try:
        from .run_lineage import RunLineage  # noqa: PLC0415

        children = RunLineage(store).list_child_runs(run_id)
    except Exception:  # noqa: BLE001 - lineage is additive
        children = []
    return RunResult(
        runId=run_id,
        status=status,  # type: ignore[arg-type]
        output=output if output is not None else run.get("output"),
        error=HarnessError(**error) if error else None,
        parentRunId=run.get("parentRunId"),
        childRunIds=children,
        modelSteps=run.get("modelSteps", 0),
        toolCalls=run.get("toolCalls", 0),
        toolErrors=run.get("toolErrors", 0),
        promptTokens=run.get("promptTokens", 0),
        completionTokens=run.get("completionTokens", 0),
        totalTokens=run.get("totalTokens", 0),
        codeVerification=run.get("codeVerification"),
        autonomy=run.get("autonomy"),
        workspaceId=run.get("workspaceId"),
        capability=_capability_of(run),
    )


def _capability_of(run: dict[str, Any]) -> Optional[dict[str, Any]]:
    """The chat capability view for a run, derived from its verification blob."""
    from .code.capability import capability_from_verification  # noqa: PLC0415

    return capability_from_verification(run.get("codeVerification"))


__all__ = ["build_graph", "execute_run"]
