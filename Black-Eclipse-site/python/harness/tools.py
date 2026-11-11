"""Tool registry — authoritative on the Python side.

The agentic layer owns tool definitions, validation, permission, risk, timeout
and execution. Tools are of two kinds:

  * native Python tools (implemented here), and
  * JDdS-backed tools (market data / fundamentals / news) which MUST read the
    one real data layer. Those call the thin TS bridge `/api/harness/data`,
    because JDdS lives in Node. The Python side still owns the tool's contract,
    validation, permission and risk; the bridge is only the data accessor.

Validation uses pydantic (already present via LangChain), so there is no
hand-rolled schema validator here.
"""

from __future__ import annotations

import asyncio
import json
import time
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Optional

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, ValidationError, create_model

from .async_timeout import await_bounded
from .schemas import HarnessError

ToolPermission = str  # "read" | "write" | "external_action"
ToolRisk = str  # "none" | "low" | "medium" | "high"

# Run-scoped fallback context for the LangChain tool path. A ContextVar is
# copied into each child task, so concurrent runs cannot overwrite each other.
_ACTIVE_CTX: ContextVar[Optional[Any]] = ContextVar("harness_tool_context", default=None)

TIMEOUT_FLOOR_MS = 100
TIMEOUT_CEILING_MS = 120_000
DEFAULT_TIMEOUT_MS = 20_000
# The agent-level tool timeout. This is a CEILING, not a blanket override: a
# tool's own declared `timeout_ms` is authoritative and is only shortened when it
# exceeds this ceiling. Before this, the graph passed its agent value as a hard
# override, so `research_search_news` (declared 30s) was silently clamped to 20s
# and timed out — collapsing a per-tool budget into the agent default. The global
# *run* timeout (`runTimeoutMs`) remains a distinct, larger budget for the model
# turn; this ceiling only bounds one tool call.
DEFAULT_TOOL_CEILING_MS = 30_000

# ── Native tool-result text bound (one seam, every tool) ──────────────────────
# A tool's text result is appended verbatim into the model's context as a
# `ToolMessage`, so a handler with no internal cap can silently consume an
# unbounded slice of the window. `ToolRegistry.execute` is the ONE seam that
# every tool (native and MCP) passes through, so the ceiling lives here rather
# than in each handler.
#
# The value is tied to the measured context budget (`context_budget.py` and
# `graph.py`), not picked arbitrarily:
#   * `CHARS_PER_TOKEN = 4` → 24_000 chars ≈ 6_000 estimated tokens.
#   * `graph.MAX_HISTORY_CHARS = 40_000` bounds the ENTIRE conversation history;
#     a single tool result must be a fraction of that, never larger than it.
#   * `research.synthesis.MAX_PACKET_CHARS = 24_000` is the largest deliberate
#     evidence packet the runtime already accepts. A single RAW tool result has
#     no reason to exceed the fully-SYNTHESIZED packet bound, so 24_000 aligns
#     with that existing, reviewed precedent.
# Under the bound the text is returned byte-identical (a safety net, not a
# formatting feature). The matching MCP ceiling (`outputLimitBytes`) remains
# operator-configurable per server; this is the outer, global seam.
MAX_TOOL_RESULT_CHARS = 24_000


def bound_tool_text(text: str, limit: int = MAX_TOOL_RESULT_CHARS) -> tuple[str, bool, int, int]:
    """Bound a tool's text result. Returns (text, truncated, shown_chars, total_chars).

    Under `limit` the text is returned byte-identical. Over it, the cut text is
    followed by an unmistakable, clearly NON-JSON marker naming the shown and
    total sizes, so a partial JSON document can never be mistaken for a complete
    one (the trailer cannot parse as JSON, and the structured `truncated` flag is
    set on the `ToolResult`). Only the text is bounded; `ToolResult.data` — the
    structured payload the front door reads — is never touched here.
    """
    total = len(text)
    if total <= limit:
        return text, False, total, total
    marker = (
        f"\n\n[TRUNCATED: tool output was {total} characters; only the first "
        f"{limit} are shown. The result is incomplete.]"
    )
    return text[:limit] + marker, True, limit, total



@dataclass
class ToolResult:
    tool_call_id: str
    name: str
    ok: bool
    text: str
    data: Any = None
    error: Optional[HarnessError] = None
    duration_ms: int = 0
    # Text-bound reporting. `truncated` is True only when the result exceeded
    # `MAX_TOOL_RESULT_CHARS`; `shown_chars`/`total_chars` let the event stream
    # and the front door report the trim without re-parsing the marker text. For
    # an untruncated result all three are the honest full size.
    truncated: bool = False
    shown_chars: int = 0
    total_chars: int = 0
    # A handle to the FULL text when it was truncated (Round 5 / C3). Read it
    # with `read_tool_output`; it is scoped to the run that produced it.
    output_id: Optional[str] = None


# ── The per-run READ LEDGER (Round 3 / W3, ADR-H282) ───────────────────────
#
# Which files this run has READ, and the hash each had at the time. It is the
# evidence the ONE edit tool insists on: a file may be changed only if this run
# read it, and only if it has not changed since.
#
# It lives here, in the lowest module, because EVERY read tool feeds it and the
# registry is the one place that sees every tool's result. Putting it in the
# code subsystem would make `harness.tools` depend on `harness.code`, and the
# code tools already depend on `harness.tools` - a cycle.
#
# The state is a plain dict on the shared `ToolContext` (one per run), the same
# shape the registry's "warn once per run" deprecation set uses. The paths are
# WORKSPACE-RELATIVE and POSIX-style, so the ledger is independent of which
# copy of the tree the run is bound to.

_READ_LEDGER_ATTR = "_read_ledger"


def read_ledger(ctx: ToolContext) -> dict[str, str]:
    """The files this run has read, mapped to the hash they had.

    A fresh (empty) ledger when the context cannot hold one - a frozen context
    must never break a tool call.
    """
    ledger = getattr(ctx, _READ_LEDGER_ATTR, None)
    if ledger is None:
        ledger = {}
        try:
            setattr(ctx, _READ_LEDGER_ATTR, ledger)
        except Exception:  # noqa: BLE001 - a frozen ctx must not break the call
            return {}
    return ledger


def record_read(ctx: ToolContext, path: str, digest: str) -> None:
    """Record that this run read `path`, and the hash it had."""
    if not path or not digest:
        return
    read_ledger(ctx)[str(path)] = str(digest)


@dataclass
class ToolContext:
    run_id: str
    log: Callable[[str, Optional[dict[str, Any]]], None]
    # The invoking user, used for memory scope isolation (None = anonymous).
    user_id: Optional[str] = None
    # The verified tenant for this run. Set by the graph from the API-verified
    # identity; the security gateway scopes every effect to it. None = single-tenant.
    tenant_id: Optional[str] = None
    # The durable task this run is executing, when the run came from the task
    # scheduler (`input.context.taskId`). A capability activated later can resume
    # that task from its checkpoint. None = an ordinary chat run.
    task_id: Optional[str] = None
    # The conversation this run belongs to, when the caller opted in (a bot chat
    # or a group-room member turn). Durable memory captured in such a run is
    # stored in that conversation's PRIVATE bucket, isolated from every other
    # conversation and from the shared stores. None = ordinary chat (unchanged).
    conversation_id: Optional[str] = None
    # The chat session id this run belongs to (the front door's `chatId`; set by
    # the graph from `RunRequest.sessionId`). This is the USER-VISIBLE
    # conversation for an ordinary chat turn, where `conversation_id` is None.
    # Used to associate produced artifacts with the conversation they came from.
    session_id: Optional[str] = None
    # The actual user turn text for THIS run. A model-facing `memory` write is
    # authorized against it by the shared decision gate — tool output, retrieved
    # memory and documents are never user intent.
    user_message: str = ""
    # True when this turn is executing a named skill (memory saves then carry
    # execution-lesson provenance rather than explicit-user provenance).
    is_skill_run: bool = False
    # Eclipse-Memory service (memory + skills). Attached per run so the memory
    # and skill tools can reach it without a global.
    memory_service: Any = None
    # The memory-provider router (native + external providers). Attached per run
    # so `memory_search_native`/`memory_search_external`/`memory_provider_status`
    # can route without a global. None = provider tools report unavailable.
    memory_router: Any = None
    # The skill registry, for progressive discovery (skill_list / skill_view).
    skill_registry: Any = None
    # Accessor for JDdS-backed data; wired to the TS bridge by the service.
    data_bridge: "DataBridge | None" = None
    # Lazily-attached per-run retrieval layer (set by retrieval tools). Typed as
    # Any to keep this core module free of a circular import on the layer.
    retrieval: Any = None
    # Lazily-attached per-run retrieval cache, shared by the layer and tools.
    retrieval_cache: Any = None
    # The run's event emitter (RunEmitter). Retrieval tools publish their
    # `retrieval.*` events through this so they reach the live SSE stream and the
    # persisted trace — a plain `log` callback would silently discard them.
    emitter: Any = None
    # The harness memory store (AgentMemoryStore), for durable retrieval replay
    # (D1) and agent memory/skill tools.
    memory_store: Any = None
    # Source collection sink for an ORDINARY run. Retrieval tools call
    # `sink(result)` after each successful retrieval so the run's provenance
    # (citations + consulted sources) can be surfaced as a Sources panel, exactly
    # like a gated research run. None = collection disabled (no sink attached).
    source_sink: Any = None
    # The model settings for THIS run, so a controlled skill sub-run inherits the
    # same provider/credentials (never a second adapter).
    model_settings: Any = None
    # The RESOLVED agent for this run (prompt, tool allowlist, ceilings and any
    # surface policy). The delegation tool reads the surface's subagent prompt
    # from it, so a delegated child inherits the parent's context policy.
    agent: Any = None
    # The run's live event bus, so a skill child-run's `skill.*` events reach the
    # parent's SSE stream.
    bus: Any = None
    # The active ToolRegistry, so a controlled skill child-run can execute through
    # the SAME registry (no second registry).
    tool_registry: Any = None
    # The durable TaskManager, when the runtime has one. Used by capability
    # activation to resume a parked original task from its checkpoint.
    task_manager: Any = None
    # An optional async effect authorizer for NON-read tools. The registry is
    # authoritative and calls this with (tool, clean_args, ctx) whenever a tool's
    # permission is not `read`; it must return True only for an explicit, valid
    # approval bound to this exact server/tool/arguments (MCP Phase 5G). No
    # authorizer ⇒ every non-read tool is refused, exactly as before.
    authorize_effect: Any = None
    # The argument digest authorized for the CURRENT tool call, set by the effect
    # authorizer so a second authorization seam in the same call (the MCP
    # manager's re-assert) does not consume a second single-use approval. Cleared
    # by the registry at the start of every tool call.
    effect_authorized_digest: Any = None
    # Approval-card mode: when True, a non-read tool with no matching approval
    # PAUSES the run (awaiting the operator's decision via the decide route)
    # instead of being refused outright. The decision is still the single-use,
    # digest-bound approval — this only changes whether the run waits for it.
    pause_for_approval: bool = False
    # How long a paused run waits for a decision before refusing the call. Kept
    # below the run deadline by the caller; the default matches the approval TTL.
    approval_timeout_s: float = 900.0
    # The process-wide MCP manager, so native retrieval can consider
    # operator-declared MCP data sources (Milestone 6). None = no MCP sources.
    mcp_manager: Any = None
    # Names of deprecated tools already warned about THIS run, so the registry
    # warns once per run, not once per call (Phase 6).
    deprecated_warned: Any = None
    # The resolved, read-only workspace binding for THIS run (Phase 1). Set by
    # the graph from `resolve_workspace(request.workspace)`; None = no code
    # capability (every code tool then refuses with WORKSPACE_UNAVAILABLE).
    workspace: Any = None
    # The run's autonomy profile (Phase 2). "edit_verify"/"approve_external" grant
    # code.write; absent/unknown grants nothing (fail-closed, Phase 0 policy).
    autonomy: Any = None
    # The code-workspace store (CodeWorkspace rows). Attached per run so the
    # patch/diff tools can record a workspace without a global. None = no record.
    code_store: Any = None
    # Operator feature flags for command classes (Phase 3). A class in
    # commands.OPERATOR_GATED_CLASSES (dependency_install) is refused unless its
    # name maps to True here. Default {} = every gated class off.
    command_flags: Any = None
    # The run's VerificationLedger (Phase 4). Every recorded command execution is
    # also recorded here so the final answer can be checked against proven fact.
    # None = runs without a ledger (direct tool calls, tests).
    code_ledger: Any = None
    # The run's resolved tool allowlist (Phase 7). The `delegate` tool narrows a
    # child's tools against it; None = the unrestricted case. Set by the graph
    # from `resolve_surface`; never caller-supplied.
    allowed: Any = None
    # The process-wide CIUE runtime (LSP manager + per-workspace code index/watcher).
    # Attached per run so the `code_*` tools resolve one shared runtime instead of a
    # global. None = the tool falls back to the process-wide singleton.
    code_intel_runtime: Any = None
    # How deep this run sits in a delegation chain (Phase 7). 0 = a top-level
    # run; a child is parent_depth + 1 and cannot spawn past MAX_DEPTH.
    delegation_depth: int = 0
    # Whether the analysis sandbox is enabled for this run (Phase 8). Default
    # False: discovery is not activation. Set by the graph from
    # `RunRequest.analysisEnabled`.
    analysis_enabled: bool = False
    # The run's cancellation signal (an `asyncio.Event`). A long-running
    # sandbox call watches it and kills its process tree, so a cancelled run
    # does not leave a child behind (W14).
    cancel_event: Optional[Any] = None
    # The process-wide approval store (MCP 5G / code actions). Attached per run so
    # the `terminal_run` effect authorizer can claim a single-use approval for an
    # `ask`-classified command. None = no approvals reachable (an `ask` command
    # then refuses).
    approvals: Any = None
    # Folder-selection: when True, the disposable code workspace is the SELECTED
    # trusted root itself (direct edits to the user's folder). Opt-in per run.
    direct: bool = False
    # The agent id executing this run (e.g. "code-agent" or "eclipse-agent"). The
    # terminal subsystem stamps every session/process it creates with this, so a
    # multi-agent runtime can attribute and isolate execution. None = unattributed.
    agent_id: Optional[str] = None
    # The per-run EvidenceStore for the web research engine (bound to the ONE
    # agent-memory connection). Set by the graph from the service; None = the
    # research tools run without persistence (still honest, just not stored).
    evidence_store: Any = None
    # The per-run LearningStore for the learning-research engine (bound to the ONE
    # eclipse-memory connection). Set by the graph from the service; None = the
    # learning tools lazily build one from `memory_service` (still persisted).
    learning_store: Any = None
    # The process-wide Financial Data Gateway provider registry (capabilities,
    # credential refs, rate limits, usage policy). Set by the graph from the
    # service; None = the `financial_providers` tool builds a default registry.
    provider_registry: Any = None
    # The per-run Market Data Gateway (market models + routing + quality). Set by
    # the graph from the service; None = a market tool lazily builds one from the
    # bridge. It never calls a provider directly — only the read-only bridge.
    market_gateway: Any = None
    # The process-wide market persistence (instruments/snapshots/quality events)
    # on the ONE agent-memory connection. Set by the graph; None = no persistence.
    market_store: Any = None
    # The process-wide Quant Engine store (strategies + experiments) on the ONE
    # agent-memory connection. Set by the graph from the service; None = the
    # `quant_*` tools report STORE_UNAVAILABLE rather than losing a result.
    quant_store: Any = None
    # The process-wide Project store (projects + their members) on the ONE
    # agent-memory connection. Set by the graph from the service; None = the
    # `project_*` tools report the store as unavailable rather than pretending.
    project_store: Any = None
    project_store: Any = None
    # The process-wide immutable research-dataset store (manifests + artifacts) on
    # the ONE agent-memory connection. Set by the graph from the service; None =
    # the dataset tools report UNAVAILABLE rather than pretending to persist.
    dataset_store: Any = None
    # The process-wide real-time market stream manager. Set by the graph; None =
    # a stream tool resolves the process-wide singleton.
    market_stream: Any = None
    # The per-run vision-result collector. Set by the graph; a vision tool calls
    # `vision_sink(result.to_dict())` after each analysis so the run carries a
    # bounded, structured vision blob (asset ids, regions, OCR, confidence,
    # provenance) for the right sidebar. None = no collection attached.
    vision_sink: Any = None
    # The per-run document-intelligence collector. Set by the graph; a document
    # tool calls `document_sink(result.to_dict())` so the run carries a bounded,
    # structured document blob (type, pages, status, capabilities, entities,
    # evidence counts) for the right sidebar. None = no collection attached.
    document_sink: Any = None
    # The per-run internet-image collector. Set by the graph; an `image_search`
    # tool calls `image_sink(images)` so the run carries a bounded, validated
    # image blob the chat renders INLINE. None = no collection attached.
    image_sink: Any = None
    # The per-run native-video collector. Set by the graph; a `video_*` tool
    # calls `video_sink(record)` when it queues a render/preview job so the run
    # carries a bounded `video` blob the chat renders as a live job card
    # (progress, playback, download, revise/regenerate). None = no collection.
    video_sink: Any = None
    # The per-run advisory collector (the Fiduciary Gate). Set by the graph; every
    # `portfolio_*` tool call is handed here so the answer seam can verify an
    # actionable recommendation against a computation the run actually performed.
    # None = no advisory verification attached.
    advisory_sink: Any = None
    # The Advisory Ledger service. Set by the graph; `advisory_*` tools reach the
    # ONE ledger through it. None = the ledger tools report unavailable.
    advisory_service: Any = None
    # The typed-decision service (System One-shaped judgments). Set by the graph;
    # `decision_*` tools reach the ONE provider registry + audit store through it.
    # None = the decision tools report unavailable (never a guessed answer).
    decision_service: Any = None
    # The Portfolio Accounting Engine service (ledger + valuation). Set by the
    # graph from the service; None = the `portfolio_*` tools report unavailable.
    portfolio_service: Any = None
    # The General Ledger service (double-entry books). Set by the graph from the
    # service; None = the `ledger_*` tools report LEDGER_UNAVAILABLE.
    ledger_service: Any = None
    # The unified Retrieval / Search Intelligence service. Set by the graph from
    # the service; None = the retrieval/search tools report search unavailable.
    search: Any = None
    # The run's workspace id, used to scope authorized search results. Set by the
    # graph from `RunRequest.workspaceId`; None = no workspace scope.
    workspace_id: Optional[str] = None
    # The ACTUAL per-call ceiling the registry will enforce for the tool call in
    # flight (set immediately before `execute`). A long-running tool reads this to
    # size its OWN internal budget so it can return a bounded partial result
    # BEFORE the harness hard-kills it. None = no declared per-call budget known.
    tool_timeout_ms: Optional[int] = None
    # The process-wide Plugin Platform manager. Set by the graph from the service;
    # None = the `plugin_*` tools resolve the module singleton (or report the
    # platform unavailable). Attached per run, never a global.
    plugin_manager: Any = None
    # The process-wide Artifact Center service. Set by the graph from the service;
    # None = the `artifact_*` tools report ARTIFACT_UNAVAILABLE rather than
    # losing a produced file. Producers also reach it via the boot singleton.
    artifact_service: Any = None
    # The process-wide UI Engineering service (component catalog + blueprint
    # store). Set by the graph from the service; None = the `ui_*` tools report
    # UI_UNAVAILABLE rather than inventing UI state. Also reachable via the boot
    # singleton so tools work even when the run context pre-dates the UI layer.
    ui_service: Any = None


class DataBridge:
    """Read-only access to JDdS data via the TS harness.

    Implementing it as a protocol-like class (rather than importing httpx here)
    keeps the registry testable with a fake, and keeps the single financial
    data path explicit.
    """

    async def fetch(self, capability: str, params: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError


ToolHandler = Callable[[dict[str, Any], ToolContext], Coroutine[Any, Any, str | tuple[str, Any]]]


@dataclass
class ToolDefinition:
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: ToolHandler
    permission: ToolPermission = "read"
    risk: ToolRisk = "low"
    timeout_ms: int = DEFAULT_TIMEOUT_MS
    output_schema: Optional[dict[str, Any]] = None
    # When set, this tool's real-world effect class (e.g. "write",
    # "external_action") and its source identity. A non-read `permission` is only
    # executable when the run's `ToolContext.authorize_effect` approves THIS exact
    # call. MCP effectful tools set this; native tools leave it unset.
    effect: Optional[str] = None
    effect_metadata: Optional[dict[str, Any]] = None
    # ── Lifecycle (Phase 6) ────────────────────────────────────────────────
    # A semver string for the tool contract. Advisory: it identifies the tool's
    # own version for operators/observability.
    version: str = "1.0.0"
    # A tool registered AFTER boot from persisted state (a per-model predictor).
    # Excluded from the portable manifest: the manifest must be a function of the
    # CODE, not of which models happen to exist in the database.
    dynamic: bool = False
    # When True, the registry warns ONCE per run when this tool is called, naming
    # its replacement, and still executes it (deprecation is not a hard block).
    deprecated: bool = False
    # The tool that replaces a deprecated one (informational; never auto-called).
    replacement: Optional[str] = None
    # A LONG-RUNNING tool (e.g. a deep research run) declares its own per-call
    # budget as authoritative and is NOT shortened by the agent's `toolTimeoutMs`
    # ceiling. The registry still bounds it by its own `timeout_ms` (its declared
    # budget), and the graph additionally caps it at the run's remaining time. Use
    # only for a tool that owns an internal deadline + returns bounded partials.
    long_running: bool = False


def _args_model(name: str, schema: dict[str, Any]) -> type[BaseModel]:
    properties = schema.get("properties", {}) or {}
    required = set(schema.get("required", []) or [])
    type_map = {
        "string": str,
        "number": float,
        "integer": int,
        "boolean": bool,
        "object": dict,
        "array": list,
    }
    fields: dict[str, Any] = {}
    for prop, spec in properties.items():
        declared = spec.get("type", "string")
        # A JSON-Schema union type (`["string", "object"]`) means the argument can
        # be more than one shape (e.g. a browser target is a ref or an object), so
        # accept any — the handler validates the concrete shape itself.
        if isinstance(declared, list):
            py_type: Any = Any
        else:
            py_type = type_map.get(str(declared), Any)
        enum = spec.get("enum")
        if enum:
            # Constrain to the declared values so pydantic rejects bad input.
            from typing import Literal

            py_type = Literal[tuple(enum)]  # type: ignore[valid-type]
        if prop in required:
            fields[prop] = (py_type, ...)
        else:
            fields[prop] = (Optional[py_type], None)
    if not fields:
        fields["_unused"] = (Optional[str], None)
    return create_model(f"{name}_args", **fields)  # type: ignore[call-overload]


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, tool: ToolDefinition) -> None:
        if not tool.name or not tool.name.replace("_", "").isalnum():
            raise ValueError(f"Invalid tool name: {tool.name!r}")
        if tool.name in self._tools:
            raise ValueError(f"Tool {tool.name!r} is already registered")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[ToolDefinition]:
        return self._tools.get(name)

    def unregister(self, name: str) -> bool:
        """Remove a tool. Returns whether it existed.

        Used by MCP reload: a server's tool set can change between catalogs, so
        re-registration must be able to drop stale names. Native tools are never
        unregistered by that path (it tracks only the names it added).
        """
        return self._tools.pop(name, None) is not None

    def names(self) -> list[str]:
        return list(self._tools.keys())

    def list(self) -> list[ToolDefinition]:
        return list(self._tools.values())

    def suggest(self, name: str, *, limit: int = 5, max_distance: int = 2) -> list[str]:
        """Registered tool names within Levenshtein distance ``max_distance``."""
        scored: list[tuple[int, str]] = []
        for candidate in self._tools:
            distance = _levenshtein(str(name), candidate)
            if distance <= max_distance:
                scored.append((distance, candidate))
        scored.sort(key=lambda item: (item[0], item[1]))
        return [candidate for _distance, candidate in scored[:limit]]

    def schemas(self, allowed: Optional[set[str]] = None) -> list[dict[str, Any]]:
        return [
            {"name": t.name, "description": t.description, "parameters": t.input_schema}
            for t in self._tools.values()
            if allowed is None or t.name in allowed
        ]

    def langchain_tools(self, allowed: Optional[set[str]] = None) -> list[StructuredTool]:
        """LangChain tool views backed by this registry's execute()."""
        tools: list[StructuredTool] = []
        for tool in self._tools.values():
            if allowed is not None and tool.name not in allowed:
                continue
            args_model = _args_model(tool.name, tool.input_schema)
            tools.append(self._as_langchain(tool, args_model))
        return tools

    def _as_langchain(self, tool: ToolDefinition, args_model: type[BaseModel]) -> StructuredTool:
        async def _run(**kwargs: Any) -> str:
            args = {k: v for k, v in kwargs.items() if v is not None and k != "_unused"}
            # The graph attaches ctx per call via `run_tool`; the LangChain path
            # uses the run-scoped context for THIS task (Round 5 / ADR-H348).
            ctx = _ACTIVE_CTX.get() or ToolContext(run_id="", log=lambda *_: None)
            result = await self.execute(tool.name, [], args, ctx)
            return result.text

        return StructuredTool.from_function(
            coroutine=_run,
            name=tool.name,
            description=tool.description,
            args_schema=args_model,
        )

    def set_active_context(self, ctx: ToolContext) -> None:
        """Bind the fallback context for the CURRENT task/context only.

        A class attribute used to hold this, so two concurrent runs on the same
        registry overwrote each other's context. A `ContextVar` is copied into
        each child task, which is the isolation a run needs.
        """
        _ACTIVE_CTX.set(ctx)

    async def execute(
        self,
        name: str,
        call_id: str,
        arguments: dict[str, Any],
        ctx: ToolContext,
        *,
        allowed: Optional[set[str]] = None,
        timeout_ms: Optional[int] = None,
    ) -> ToolResult:
        started = time.monotonic()
        call_id = call_id or f"call_{name}"

        tool = self._tools.get(name)
        if tool is None:
            # D10: keep the refusal, but teach the correction. Suggestions are
            # advisory only - the suggested tool is NEVER auto-executed.
            suggestions = self.suggest(name)
            message = f"Unknown tool {name!r}"
            if suggestions:
                message += f". Did you mean: {', '.join(suggestions)}?"
            return self._failure(
                call_id, name, "TOOL_NOT_FOUND", message, started,
                data={"suggestions": suggestions, "autoExecuted": False},
            )
        if allowed is not None and name not in allowed:
            return self._failure(call_id, name, "TOOL_FORBIDDEN", f"Tool {name!r} is not allowed for this run", started)

        _warn_deprecated(self, tool, ctx)

        args_model = _args_model(name, tool.input_schema)
        try:
            validated = args_model(**arguments)
        except ValidationError as exc:
            return self._failure(call_id, name, "TOOL_VALIDATION_FAILED", str(exc), started)
        clean = {k: v for k, v in validated.model_dump().items() if k != "_unused"}

        if tool.permission != "read":
            # A non-read tool is refused unless the run explicitly authorizes THIS
            # call (bound to the server/tool/arguments). No authorizer ⇒ refused.
            authorizer = getattr(ctx, "authorize_effect", None)
            approved = False
            # Clear the per-call authorization scope so an approval consumed for a
            # PREVIOUS call cannot authorize this one.
            try:
                ctx.effect_authorized_digest = None
            except Exception:  # noqa: BLE001
                pass
            if authorizer is not None:
                # Arity-tolerant and exception-safe (shared with the MCP manager
                # seam): a failing authorizer must never authorize.
                approved = await _invoke_authorizer(authorizer, tool, clean, ctx)
            if not approved:
                return self._failure(
                    call_id, name, "TOOL_FORBIDDEN",
                    f"Tool {name!r} has effect {tool.effect or tool.permission!r} and is not approved for this call",
                    started,
                )
            store = getattr(ctx, "memory_store", None)
            if store is not None:
                from .self_improvement.effectful_widening import check_call  # noqa: PLC0415

                limit = check_call(
                    store, str(getattr(ctx, "agent_id", "") or ""), name, clean,
                )
                if limit is not None and not limit.get("ok"):
                    return self._failure(
                        call_id, name, "WIDENING_CAP_EXCEEDED",
                        f"Tool {name!r} blocked by effectful widening cap {limit.get('reason')!r}",
                        started,
                    )

        effective_timeout = effective_timeout_ms(
            tool.timeout_ms, timeout_ms, long_running=tool.long_running
        )
        # Expose the ACTUAL per-call ceiling to the handler (and the run) so a
        # long-running tool can size its own internal deadline to finish before the
        # harness hard-kills it. Set here, after the ceiling is resolved, so it is
        # the true effective value (honoring `long_running`).
        try:
            ctx.tool_timeout_ms = effective_timeout
        except Exception:  # noqa: BLE001 - a frozen/foreign ctx must not break dispatch
            pass
        try:
            # Wait slightly past the logical deadline so a tool that honors its
            # own internal timeout can return its structured diagnostic (naming
            # the timeout category + latency) instead of being hard-killed by
            # asyncio before it can report WHY. `await_bounded` keeps the wait
            # bounded even when a handler swallows cancellation — a plain
            # `asyncio.wait_for` would hang the run behind such a handler.
            output = await await_bounded(
                tool.handler(clean, ctx), (effective_timeout + _TIMEOUT_GRACE_MS) / 1000
            )
        except asyncio.TimeoutError:
            return self._failure(
                call_id, name, "TOOL_TIMEOUT",
                f"Tool {name!r} timed out after {effective_timeout}ms "
                f"(category=timeout, retryable=false at the tool boundary)",
                started,
            )
        except Exception as exc:  # noqa: BLE001 - tool failures are data, not crashes
            return self._failure(call_id, name, "TOOL_ERROR", str(exc), started)

        text, data = output if isinstance(output, tuple) else (output, None)
        # Fiduciary Gate provenance: record every `portfolio_*` call (a computation
        # or a consult) so the answer seam can verify actionable advice against
        # what the run actually did. Additive and best-effort — it never changes
        # the result.
        advisory_sink = getattr(ctx, "advisory_sink", None)
        if advisory_sink is not None and (
            name.startswith("portfolio_") or name in ("market_get_quote", "get_quote")
        ):
            try:
                advisory_sink(name, clean, data)
            except Exception:  # noqa: BLE001 - collection must not break a run
                pass
        # Round 3 / W3 (ADR-H282): a read that returns a file hash FEEDS the
        # per-run read ledger. ONE place, so every read tool participates - the
        # model does not have to remember to read a file a particular way before
        # it may change it.
        if tool.permission == "read" and isinstance(data, dict):
            read_path, read_digest = data.get("path"), data.get("sha256")
            if isinstance(read_path, str) and isinstance(read_digest, str) and read_digest:
                record_read(ctx, read_path, read_digest)
        # Bound the model-facing text at this single seam; `data` is untouched.
        full_text = str(text)
        bounded_text, truncated, shown_chars, total_chars = bound_tool_text(full_text)
        output_id: Optional[str] = None
        if truncated:
            # Round 5 / C3: keep the FULL text behind a run-scoped handle instead
            # of losing it. The read tool pages it back on demand.
            try:
                from .tool_outputs import ToolOutputStore  # noqa: PLC0415

                memory_store = getattr(ctx, "memory_store", None)
                db = getattr(memory_store, "_db", None) if memory_store is not None else None
                if db is not None:
                    store = getattr(memory_store, "_tool_output_store", None)
                    if store is None:
                        store = ToolOutputStore(db)
                        try:
                            setattr(memory_store, "_tool_output_store", store)
                        except Exception:  # noqa: BLE001 - a read-only stub
                            pass
                    saved = store.save(ctx.run_id, name, full_text)
                    if saved is not None:
                        output_id = saved["id"]
                        bounded_text = (
                            f"{bounded_text}\n[FULL OUTPUT: {saved['chars']} chars. "
                            f'Call read_tool_output with id "{saved["id"]}" and offset '
                            f"{shown_chars} to continue.]"
                        )
            except Exception:  # noqa: BLE001 - offload must never break a tool call
                output_id = None
        return ToolResult(
            tool_call_id=call_id,
            name=name,
            ok=True,
            text=bounded_text,
            data=data,
            duration_ms=int((time.monotonic() - started) * 1000),
            truncated=truncated,
            shown_chars=shown_chars,
            total_chars=total_chars,
            output_id=output_id,
        )

    def _failure(self, call_id: str, name: str, code: str, message: str, started: float,
                 data: Any = None) -> ToolResult:
        return ToolResult(
            tool_call_id=call_id,
            name=name,
            ok=False,
            text=f"Tool error ({code}): {message}",
            data=data,
            error=HarnessError(code=code, message=message),  # type: ignore[arg-type]
            duration_ms=int((time.monotonic() - started) * 1000),
        )


def _warn_deprecated(registry: "ToolRegistry", tool: ToolDefinition, ctx: ToolContext) -> None:
    """Warn ONCE PER RUN when a deprecated tool is called, naming its replacement.

    Deprecation is advisory, not a hard block: the tool still executes. The
    warning is recorded on the shared `ToolContext` (one per run) so a tool called
    many times in a run warns only once, and surfaced through the run emitter.
    """
    if not tool.deprecated:
        return
    seen = getattr(ctx, "deprecated_warned", None)
    if seen is None:
        seen = set()
        try:
            ctx.deprecated_warned = seen
        except Exception:  # noqa: BLE001 - a frozen ctx must not break execution
            return
    if tool.name in seen:
        return
    seen.add(tool.name)
    replacement = f" Use {tool.replacement!r} instead." if tool.replacement else ""
    message = f"Tool {tool.name!r} is deprecated.{replacement}"
    try:
        if ctx.log is not None:
            ctx.log(message, {"tool": tool.name, "deprecated": True, "replacement": tool.replacement})
    except Exception:  # noqa: BLE001
        pass
    emitter = getattr(ctx, "emitter", None)
    if emitter is not None:
        try:
            # Fire-and-forget: the emitter path is async in the graph; here we
            # only have a sync seam, so record a persisted event best-effort.
            emitter.emit_sync(
                "tool.deprecated",
                {"tool": tool.name, "replacement": tool.replacement},
            )
        except Exception:  # noqa: BLE001 - a warning must never break a call
            pass


# Grace added to the asyncio wait so an internally-timed-out tool can surface its
# structured diagnostic before being hard-killed. Bounded and small.
_TIMEOUT_GRACE_MS = 1_500


async def _invoke_authorizer(authorizer: Any, tool: ToolDefinition, args: dict[str, Any], ctx: ToolContext) -> bool:
    """Invoke an effect authorizer, tolerating both signatures and never on error.

    Delegates to the shared helper so the registry and the MCP manager re-check
    treat a failing or legacy-signed authorizer identically. Imported lazily to
    keep this core module free of an import cycle on the MCP package.
    """
    from .mcp.approvals import invoke_effect_authorizer  # noqa: PLC0415

    return await invoke_effect_authorizer(authorizer, tool, args, ctx)


def _clamp_timeout(ms: int) -> int:
    if ms is None:
        return DEFAULT_TIMEOUT_MS
    return max(TIMEOUT_FLOOR_MS, min(int(ms), TIMEOUT_CEILING_MS))


def effective_timeout_ms(
    tool_timeout_ms: Optional[int],
    agent_ceiling_ms: Optional[int],
    *,
    long_running: bool = False,
) -> int:
    """Resolve the effective per-tool timeout.

    The tool's OWN declared timeout is authoritative. The agent value is a
    ceiling: it may only shorten a tool that declares more, never override a
    tool that declares less. This keeps per-tool budgets distinct from the
    agent/global run budget (WS2). An explicit per-call override
    (`execute(..., timeout_ms=...)`) is still honored as an exact value — that is
    what tests use to drive the floor.

    A `long_running` tool ignores the agent ceiling and uses its OWN declared
    budget (still clamped to the global `TIMEOUT_CEILING_MS`). Such a tool is
    responsible for bounding itself; the graph additionally caps it at the run's
    remaining deadline.
    """
    tool_ms = _clamp_timeout(tool_timeout_ms if tool_timeout_ms is not None else DEFAULT_TIMEOUT_MS)
    if long_running or agent_ceiling_ms is None:
        return tool_ms
    ceiling = _clamp_timeout(agent_ceiling_ms)
    return min(tool_ms, ceiling)


def _levenshtein(a: str, b: str) -> int:
    """Classic edit distance (insert/delete/substitute) over two short names."""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        current = [i]
        for j, cb in enumerate(b, start=1):
            insert = current[j - 1] + 1
            delete = previous[j] + 1
            substitute = previous[j - 1] + (0 if ca == cb else 1)
            current.append(min(insert, delete, substitute))
        previous = current
    return previous[-1]


def dumps(value: Any) -> str:
    return json.dumps(value, default=str)


__all__ = [
    "ToolDefinition",
    "ToolRegistry",
    "ToolResult",
    "ToolContext",
    "DataBridge",
    "dumps",
]
