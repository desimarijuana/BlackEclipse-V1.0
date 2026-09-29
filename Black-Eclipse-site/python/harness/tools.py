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
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Optional

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, ValidationError, create_model

from .schemas import HarnessError

ToolPermission = str  # "read" | "write" | "external_action"
ToolRisk = str  # "none" | "low" | "medium" | "high"

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


@dataclass
class ToolResult:
    tool_call_id: str
    name: str
    ok: bool
    text: str
    data: Any = None
    error: Optional[HarnessError] = None
    duration_ms: int = 0


@dataclass
class ToolContext:
    run_id: str
    log: Callable[[str, Optional[dict[str, Any]]], None]
    # The invoking user, used for memory scope isolation (None = anonymous).
    user_id: Optional[str] = None
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
    # The run's live event bus, so a skill child-run's `skill.*` events reach the
    # parent's SSE stream.
    bus: Any = None
    # The active ToolRegistry, so a controlled skill child-run can execute through
    # the SAME registry (no second registry).
    tool_registry: Any = None
    # An optional async effect authorizer for NON-read tools. The registry is
    # authoritative and calls this with (tool, clean_args) whenever a tool's
    # permission is not `read`; it must return True only for an explicit, valid
    # approval bound to this exact server/tool/arguments (MCP Phase 5G). No
    # authorizer ⇒ every non-read tool is refused, exactly as before.
    authorize_effect: Any = None


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
        py_type = type_map.get(str(spec.get("type", "string")), Any)
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
            # uses a default context stored on the registry for this run.
            ctx = self._active_ctx or ToolContext(run_id="", log=lambda *_: None)
            result = await self.execute(tool.name, [], args, ctx)
            return result.text

        return StructuredTool.from_function(
            coroutine=_run,
            name=tool.name,
            description=tool.description,
            args_schema=args_model,
        )

    _active_ctx: Optional[ToolContext] = None

    def set_active_context(self, ctx: ToolContext) -> None:
        self._active_ctx = ctx

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
            return self._failure(call_id, name, "TOOL_NOT_FOUND", f"Unknown tool {name!r}", started)
        if allowed is not None and name not in allowed:
            return self._failure(call_id, name, "TOOL_FORBIDDEN", f"Tool {name!r} is not allowed for this run", started)

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
            if authorizer is not None:
                try:
                    approved = bool(await authorizer(tool, clean))
                except Exception:  # noqa: BLE001 - a failing authorizer must not authorize
                    approved = False
            if not approved:
                return self._failure(
                    call_id, name, "TOOL_FORBIDDEN",
                    f"Tool {name!r} has effect {tool.effect or tool.permission!r} and is not approved for this call",
                    started,
                )

        effective_timeout = effective_timeout_ms(tool.timeout_ms, timeout_ms)
        try:
            # Wait slightly past the logical deadline so a tool that honors its
            # own internal timeout can return its structured diagnostic (naming
            # the timeout category + latency) instead of being hard-killed by
            # asyncio before it can report WHY. The wait_for is still bounded.
            output = await asyncio.wait_for(
                tool.handler(clean, ctx), timeout=(effective_timeout + _TIMEOUT_GRACE_MS) / 1000
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
        return ToolResult(
            tool_call_id=call_id,
            name=name,
            ok=True,
            text=text,
            data=data,
            duration_ms=int((time.monotonic() - started) * 1000),
        )

    def _failure(self, call_id: str, name: str, code: str, message: str, started: float) -> ToolResult:
        return ToolResult(
            tool_call_id=call_id,
            name=name,
            ok=False,
            text=f"Tool error ({code}): {message}",
            error=HarnessError(code=code, message=message),  # type: ignore[arg-type]
            duration_ms=int((time.monotonic() - started) * 1000),
        )


# Grace added to the asyncio wait so an internally-timed-out tool can surface its
# structured diagnostic before being hard-killed. Bounded and small.
_TIMEOUT_GRACE_MS = 1_500


def _clamp_timeout(ms: int) -> int:
    if ms is None:
        return DEFAULT_TIMEOUT_MS
    return max(TIMEOUT_FLOOR_MS, min(int(ms), TIMEOUT_CEILING_MS))


def effective_timeout_ms(tool_timeout_ms: Optional[int], agent_ceiling_ms: Optional[int]) -> int:
    """Resolve the effective per-tool timeout.

    The tool's OWN declared timeout is authoritative. The agent value is a
    ceiling: it may only shorten a tool that declares more, never override a
    tool that declares less. This keeps per-tool budgets distinct from the
    agent/global run budget (WS2). An explicit per-call override
    (`execute(..., timeout_ms=...)`) is still honored as an exact value — that is
    what tests use to drive the floor.
    """
    tool_ms = _clamp_timeout(tool_timeout_ms if tool_timeout_ms is not None else DEFAULT_TIMEOUT_MS)
    if agent_ceiling_ms is None:
        return tool_ms
    ceiling = _clamp_timeout(agent_ceiling_ms)
    return min(tool_ms, ceiling)


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
